"""Brain — the LLM client and the reason -> act -> observe -> learn loop.

v4 rewrite. The v3 build used six separate regexes to tease a tool call out of
the model's reply; that was fragile and a parse miss was invisible (the tool
silently never ran and the model filled the gap with invention). v4 uses ONE
tolerant parser that handles every form a small local model actually emits:

    ACTION: name                 <- bare, arg on following lines
    ```ACTION: name\n<arg>```      <- fenced, arg inside
    ```ACTION: name <arg>```       <- fenced, arg inline
    ACTION: name <arg>             <- inline, arg after the name

Plus strip_control() so the user only ever sees prose.
"""

from __future__ import annotations

import json
import re

import requests

# --- boundaries that end an action's argument block -------------------------
_CTRL = r"(?:ACTION|TOOL|LEARNED|REMEMBER)\s*:"
# A bare/inline ACTION header: colon then name, ending at a newline OR end.
_HEAD = re.compile(
    r"(?:^|\n)\s*(?:ACTION|TOOL)\s*:\s*([A-Za-z_][\w]*)", re.I)
# A fenced ACTION header sitting inside a ``` fence (e.g. `` ```ACTION: name ``).
_FENCE_HEAD = re.compile(
    r"```\s*(?:ACTION|TOOL)\s*:\s*([A-Za-z_][\w]*)", re.I)


def parse_action(text: str):
    """Extract the FIRST tool call. Returns (name, arg) or None.

    Robust to fenced / inline / bare forms and small-model quirks.
    """
    if not text:
        return None
    # Prefer a fenced header (```ACTION: name) — arg lives inside the fence.
    m = _FENCE_HEAD.search(text)
    if m:
        name = m.group(1).lower()
        after = text[m.end():].lstrip("\n")
        body = after[3:] if after.startswith("```") else after
        end = body.rfind("```")
        if end != -1:
            body = body[:end]
        arg = body.strip("\n").strip("`").strip()
        return (name, arg) if arg else None

    # Bare header `ACTION: name` — arg may be on the SAME line (the form this
    # fine-tune prefers: "ACTION: list_dir /home/zaine") or on following lines.
    m = _HEAD.search(text)
    if not m:
        return None
    name = m.group(1).lower()
    # Capture the rest of the header line PLUS following lines until the next
    # control block or end of text. This covers both inline and multiline args.
    line_rest = text[m.end():]
    # Split off the rest of the current line (inline arg) ...
    parts = line_rest.split("\n", 1)
    inline = parts[0].strip().strip("`").strip()
    remainder = parts[1] if len(parts) > 1 else ""
    # ... then take everything up to the next control block.
    cut = re.search(r"\n\s*" + _CTRL, remainder, re.I)
    if cut:
        remainder = remainder[:cut.start()]
    remainder = remainder.strip("\n").strip("`").strip()
    arg = (inline + "\n" + remainder).strip() if remainder else inline
    arg = arg.strip()
    if not arg:
        return None
    return name, arg


def strip_control(text: str) -> str:
    """Remove ACTION/LEARNED/REMEMBER blocks so the user sees only prose."""
    if not text:
        return ""
    # 1) drop fenced code blocks (action arguments live here)
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    # 2) drop control blocks: a header line plus any following non-blank
    #    lines up to the first blank line (the argument), keeping any prose
    #    that follows. Small models sometimes append a stray line after an
    #    action; we must not leak the control block into the reply.
    ctrl = re.compile(r"^\s*(?:ACTION|TOOL|LEARNED|REMEMBER)\s*:", re.I)
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        if ctrl.match(lines[i]):
            i += 1
            while i < len(lines) and lines[i].strip() and not ctrl.match(
                    lines[i]):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class LLM:
    """Talks to an OpenAI-compatible endpoint (Ollama by default)."""

    def __init__(self, base_url: str, model: str, api_key: str | None = None,
                 timeout: int = 1800, keep_alive: str = "5m",
                 max_tokens: int = 2048):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        # read timeout: a cold-loading remote/slow model can take minutes.
        self.timeout = timeout
        # keep_alive: pin the model in VRAM between turns.
        self.keep_alive = keep_alive
        # max_tokens: hard cap on generation. Small fine-tunes can ignore the
        # "stop after ACTION" instruction and ramble for 10k+ tokens; this
        # bounds a single turn so the agent loop stays responsive.
        self.max_tokens = max_tokens

    def chat(self, messages: list[dict], temperature: float = 0.7) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            "keep_alive": self.keep_alive,
            "max_tokens": self.max_tokens,
        }
        req_timeout = (15, self.timeout)
        try:
            with requests.post(f"{self.base_url}/chat/completions",
                               json=payload, headers=headers,
                               timeout=req_timeout, stream=True) as r:
                if r.status_code != 200:
                    raise RuntimeError(
                        f"model returned HTTP {r.status_code}: {r.text[:200]}")
                content = []
                for line in r.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if line.startswith("data:"):
                        chunk = line[len("data:"):].strip()
                        if chunk == "[DONE]":
                            break
                        try:
                            data = json.loads(chunk)
                        except (ValueError, json.JSONDecodeError):
                            continue
                        delta = (data.get("choices") or [{}])[0] \
                            .get("message", {}) or \
                            (data.get("choices") or [{}])[0].get("delta", {})
                        piece = delta.get("content")
                        if piece:
                            content.append(piece)
                return "".join(content) or ""
        except requests.exceptions.ConnectTimeout as e:
            raise TimeoutError(
                f"can't connect to the model at {self.base_url} within 15s — "
                f"is the host up and reachable?") from e
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(
                f"can't reach the model at {self.base_url} — is it running?") \
                from e
        except requests.exceptions.ReadTimeout as e:
            raise TimeoutError(
                f"model at {self.base_url} took too long to respond "
                f"(>{self.timeout}s). If it's cold-loading, try again or "
                f"raise 'timeout'.") from e

    def available(self) -> bool:
        try:
            requests.get(f"{self.base_url}/models", timeout=5)
            return True
        except Exception:
            return False

    def keep_hot(self) -> bool:
        """Pin the model in VRAM so it never cold-loads mid-session."""
        import requests as _r
        try:
            _r.post(f"{self.base_url}/api/generate",
                    json={"model": self.model, "keep_alive": self.keep_alive,
                          "prompt": " ", "stream": False},
                    timeout=(15, int(self.timeout)))
            return True
        except Exception:
            return False
