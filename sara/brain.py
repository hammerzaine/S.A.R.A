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
                 timeout: int = 180):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def chat(self, messages: list[dict], temperature: float = 0.7) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {"model": self.model, "messages": messages,
                   "temperature": temperature, "stream": False}
        try:
            r = requests.post(f"{self.base_url}/chat/completions",
                              json=payload, headers=headers,
                              timeout=self.timeout)
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(
                f"can't reach the model at {self.base_url} — is it running?"
            ) from e
        if r.status_code != 200:
            raise RuntimeError(f"model returned HTTP {r.status_code}: "
                               f"{r.text[:200]}")
        data = r.json()
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError):
            raise RuntimeError(f"unexpected model response: {str(data)[:200]}")

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
