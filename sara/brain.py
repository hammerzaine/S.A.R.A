"""Brain — the LLM client and the reason → act → observe → learn loop."""

from __future__ import annotations

import json
import re

import requests

TOOL_RE = re.compile(
    r"(?:^|\n)\s*(?:ACTION|TOOL)\s*:\s*([a-z_]+)\s*\n```(?:[a-z]*\n)?(.*?)```",
    re.S | re.I)
# Some models put the whole thing inside the fence: ```action: list_dir\n<arg>```
TOOL_FENCED_RE = re.compile(
    r"```(?:[a-z]*\s*\n)?\s*(?:ACTION|TOOL)\s*:\s*([a-z_]+)\s*\n(.*?)```",
    re.S | re.I)
# ...and some put the ARG on the same line inside the fence:
#   ```ACTION: list_dir /home/zaine```
TOOL_FENCED_INLINE_RE = re.compile(
    r"```(?:[a-z]*\s*\n)?\s*(?:ACTION|TOOL)\s*:\s*([a-z_]+)[ \t]+([^\n`]+)",
    re.I)
TOOL_INLINE_RE = re.compile(
    r"(?:^|\n)\s*(?:ACTION|TOOL)\s*:\s*([a-z_]+)[ \t]+([^\n]+)", re.I)
LEARN_RE = re.compile(
    r"(?:^|\n)\s*LEARNED\s*:\s*([^\n]+)\n(.*?)(?=\nLEARNED:|\Z)", re.S | re.I)
REMEMBER_RE = re.compile(r"(?:^|\n)\s*REMEMBER\s*:\s*([^\n]+)", re.I)


class LLM:
    """Talks to an OpenAI-compatible endpoint (Ollama by default)."""

    def __init__(self, base_url: str, model: str, api_key: str | None = None,
                 timeout: int = 900, keep_alive: str = "-1"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        # read timeout: how long to wait for a (possibly cold-loading) response
        # body. A remote Ollama host can take minutes to page a multi-GB model
        # in over a slow link, so this is deliberately generous and tunable
        # via the 'timeout' config key. The connect timeout stays short (dead
        # host fails fast instead of hanging for the full read budget).
        self.timeout = timeout
        # how long Ollama keeps the model loaded after a request. "5m" avoids
        # reloading the multi-GB weights on every turn over a slow LAN.
        self.keep_alive = keep_alive

    def chat(self, messages: list[dict], temperature: float = 0.7) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        # keep_alive: pin the model in VRAM between turns so a remote Ollama
        # host doesn't reload the (multi-GB) weights on every request — cold
        # loads over the LAN can exceed the read timeout.
        payload = {"model": self.model, "messages": messages,
                   "temperature": temperature, "stream": True,
                   "keep_alive": self.keep_alive}

        # (connect, read) tuple: connect fails fast on a dead host; read is the
        # generous, tunable cold-load budget.
        req_timeout = (15, self.timeout)
        try:
            # stream=True: tokens arrive as they're produced, so the connection
            # never goes idle and a slow cold-load can't trip read-timeout.
            with requests.post(f"{self.base_url}/chat/completions",
                               json=payload, headers=headers,
                               timeout=req_timeout, stream=True) as r:
                if r.status_code != 200:
                    raise RuntimeError(f"model returned HTTP {r.status_code}: "
                                       f"{r.text[:200]}")
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
                f"is the host up and reachable?"
            ) from e
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(
                f"can't reach the model at {self.base_url} — is it running?"
            ) from e
        except requests.exceptions.ReadTimeout as e:
            raise TimeoutError(
                f"model at {self.base_url} took too long to respond "
                f"(>{self.timeout}s). If it's a remote Ollama host, the model "
                f"may be cold-loading — try again, or raise 'timeout' "
                f"(/set timeout <seconds>)."
            ) from e

    def available(self) -> bool:
        try:
            requests.get(f"{self.base_url}/models", timeout=5)
            return True
        except Exception:
            return False


def parse_action(text: str):
    """Extract the FIRST tool call. Returns (name, arg) or None.

    Accepts both fenced and inline forms because small models are inconsistent
    about which they emit. Also accepts the UNFENCED `ACTION: name` followed by
    a newline and the argument (the canonical form shown in PROTOCOL) — some
    models emit exactly that and must not be dropped to None.
    """
    # FENCED multi-line:  ACTION: name\n```<arg>```
    m = TOOL_RE.search(text)
    if m:
        return m.group(1).strip().lower(), m.group(2).strip()
    # FENCED, action inside the fence
    m = TOOL_FENCED_RE.search(text)
    if m:
        return m.group(1).strip().lower(), m.group(2).strip()
    # FENCED with arg on same line inside fence:  ```ACTION: name <arg>```
    m = TOOL_FENCED_INLINE_RE.search(text)
    if m:
        return m.group(1).strip().lower(), m.group(2).strip().strip("`")
    # UNFENCED:  ACTION: name <first-line>\n<arg continues on following lines>
    # This is the most common small-model form for write_file etc. where the
    # path is on the ACTION line and the content streams on the next lines.
    m = re.search(
        r"(?:^|\n)\s*(?:ACTION|TOOL)\s*:\s*([a-z_]+)[ \t]+([^\n]+)\n(.*?)(?=\n(?:ACTION|TOOL|LEARNED|REMEMBER)\s*:|\Z)",
        text, re.S | re.I)
    if m:
        name = m.group(1).strip().lower()
        first = m.group(2).strip().strip("`")
        rest = m.group(3).strip("\n")
        arg = (first + "\n" + rest).strip() if rest else first
        if arg:
            return name, arg
    # UNFENCED, no trailing content (arg entirely on the ACTION line)
    m = re.search(r"(?:^|\n)\s*(?:ACTION|TOOL)\s*:\s*([a-z_]+)[ \t]+([^\n]+)",
                  text, re.I)
    if m:
        arg = m.group(2).strip().strip("`")
        if arg and not arg.lower().startswith("```"):
            return m.group(1).strip().lower(), arg
    # INLINE (single-line, no continuation):  ACTION: name <arg>
    m = TOOL_INLINE_RE.search(text)
    if m:
        arg = m.group(2).strip().strip("`")
        if arg:
            return m.group(1).strip().lower(), arg
    # UNFENCED multi-line arg only (canonical PROTOCOL form, no inline path)
    m = re.search(r"(?:^|\n)\s*(?:ACTION|TOOL)\s*:\s*([a-z_]+)\s*\n(.*?)(?=\n(?:ACTION|TOOL|LEARNED|REMEMBER)\s*:|\Z)",
                  text, re.S | re.I)
    if m:
        name, arg = m.group(1).strip().lower(), m.group(2).strip()
        if arg:
            return name, arg
    return None


def parse_learnings(text: str) -> list[tuple[str, str]]:
    out = []
    for m in LEARN_RE.finditer(text):
        title = m.group(1).strip()
        body = m.group(2).strip()
        if title and body:
            out.append((title, body))
    return out


def parse_memories(text: str) -> list[str]:
    return [m.group(1).strip() for m in REMEMBER_RE.finditer(text)
            if m.group(1).strip()]


def strip_control(text: str) -> str:
    """Remove ACTION/LEARNED/REMEMBER blocks so the user sees only prose."""
    text = TOOL_RE.sub("", text)
    text = TOOL_FENCED_RE.sub("", text)
    text = TOOL_FENCED_INLINE_RE.sub("", text)
    text = TOOL_INLINE_RE.sub("", text)
    text = LEARN_RE.sub("", text)
    text = REMEMBER_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
