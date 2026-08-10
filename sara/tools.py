"""Tools — everything S.A.R.A can actually DO.

Contract for every tool:
  * a `run(arg: str) -> dict` method — ONE uniform entrypoint, no exceptions.
  * returns a dict with at minimum {"ok": bool}
  * a `summary(result)` giving a one-line human description for the console.

The uniform `run()` contract is deliberate. The previous build dispatched some
tools via `.run()` and others via `.list()`/`.read()`/`.search()`, so any tool
whose entrypoint wasn't named `run` silently returned None and the model saw
"(no output)". One signature, no special cases.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

HOME = Path.home()

# Directories that are enormous and never interesting to a name search.
# Walking these turns a 2-second search into a 60-second hang.
PRUNE = {".git", "node_modules", "__pycache__", ".venv", "venv", "site-packages",
         ".cache", ".npm", ".pyenv", "blobs", ".ollama", ".nv", ".mozilla"}


class Tool:
    name = "tool"
    description = "base"
    usage = ""

    def run(self, arg: str) -> dict:
        raise NotImplementedError

    def summary(self, r: dict) -> str:
        return "done" if r.get("ok") else str(r.get("error", "failed"))


# --------------------------------------------------------------------------
class ListDir(Tool):
    name = "list_dir"
    description = "List the contents of a directory (folders and files)."
    usage = "list_dir <path>            e.g. list_dir ~/projects"

    def run(self, arg: str) -> dict:
        raw = (arg or "~").strip().strip("`\"'") or "~"
        show_hidden = False
        parts = []
        for tok in raw.split():
            if tok in ("-a", "--all", "--hidden"):
                show_hidden = True
            else:
                parts.append(tok)
        raw = " ".join(parts) or "~"
        p = Path(raw).expanduser()
        try:
            p = p.resolve()
        except (OSError, RuntimeError) as e:
            return {"ok": False, "error": f"bad path: {e}"}

        if not p.exists():
            parent = p.parent
            hint = []
            if parent.is_dir():
                try:
                    hint = sorted(c.name + ("/" if c.is_dir() else "")
                                  for c in parent.iterdir()
                                  if p.name.lower()[:3] in c.name.lower())[:8]
                except OSError:
                    pass
            return {"ok": False, "error": f"{p} does not exist",
                    "did_you_mean": hint}
        if p.is_file():
            return {"ok": True, "path": str(p), "is_file": True,
                    "size": p.stat().st_size,
                    "note": "that's a file — use read_file"}

        dirs, files = [], []
        try:
            for c in sorted(p.iterdir(), key=lambda x: x.name.lower()):
                if not show_hidden and c.name.startswith("."):
                    continue
                try:
                    if c.is_dir():
                        dirs.append(c.name + "/")
                    else:
                        files.append(c.name)
                except OSError:
                    continue
        except PermissionError:
            return {"ok": False, "error": f"permission denied: {p}"}
        return {"ok": True, "path": str(p), "dirs": dirs, "files": files,
                "dir_count": len(dirs), "file_count": len(files)}

    def summary(self, r):
        if not r.get("ok"):
            return r.get("error", "failed")
        if r.get("is_file"):
            return f"{r['path']} is a file"
        return f"{r['dir_count']} folders, {r['file_count']} files in {r['path']}"


class FindPath(Tool):
    name = "find_path"
    description = "Find files or folders anywhere by name fragment."
    usage = "find_path <name>          e.g. find_path mtg"

    def run(self, arg: str) -> dict:
        pat = (arg or "").strip().strip("`\"'").lower()
        if not pat:
            return {"ok": False, "error": "need a name to search for"}
        root = HOME
        if " in " in pat:
            pat, _, where = pat.partition(" in ")
            root = Path(where.strip()).expanduser()
            pat = pat.strip()
        matches, truncated = [], False
        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            dirnames[:] = [d for d in dirnames
                           if d not in PRUNE and not d.startswith(".cache")]
            for d in dirnames:
                if pat in d.lower():
                    matches.append(os.path.join(dirpath, d) + "/")
            for f in filenames:
                if pat in f.lower():
                    matches.append(os.path.join(dirpath, f))
            if len(matches) >= 100:
                truncated = True
                break
        dirs = [m for m in matches if m.endswith("/")]
        return {"ok": True, "matches": matches[:100], "dirs": dirs,
                "count": len(matches), "truncated": truncated}

    def summary(self, r):
        if not r.get("ok"):
            return r.get("error", "failed")
        return f"{r['count']} matches ({len(r['dirs'])} folders)"


class ReadFile(Tool):
    name = "read_file"
    description = "Read the contents of a text file."
    usage = "read_file <path>"

    def run(self, arg: str) -> dict:
        p = Path((arg or "").strip().strip("`\"'")).expanduser()
        if not p.exists():
            return {"ok": False, "error": f"{p} not found"}
        if p.is_dir():
            return {"ok": False, "error": f"{p} is a directory — use list_dir"}
        try:
            text = p.read_text(errors="replace")
        except OSError as e:
            return {"ok": False, "error": str(e)}
        lines = text.splitlines()
        return {"ok": True, "path": str(p), "lines": len(lines),
                "content": "\n".join(lines[:400])}

    def summary(self, r):
        return (f"read {r['lines']} lines from {r['path']}"
                if r.get("ok") else r.get("error"))


class Rewrite(Tool):
    name = "rewrite"
    description = ("Transform a pasted source text into a different style/register "
                   "while keeping its characters, names, and plot beats. Use this "
                   "when the user pastes source and asks to 'rewrite', 'make it "
                   "professional', 'polish', 'restyle', or 'summarize' it. Never "
                   "invents a new story -- the source is always preserved.")
    usage = ("rewrite <style> :: <source text>   "
             "e.g. rewrite professional :: <paste the story here>")

    def run(self, arg: str) -> dict:
        import re as _re
        cleaned = (arg or "").strip().strip("`").strip()
        if "::" not in cleaned:
            return {"ok": False, "error":
                    "need 'rewrite <style> :: <source>'. Put the source after '::'."}
        style, _, source = cleaned.partition("::")
        style = style.strip() or "in the same style"
        source = source.strip()
        if len(source) < 40:
            return {"ok": False, "error": "source text too short to rewrite"}

        try:
            from pathlib import Path as _P
            cfg_path = _P(__file__).resolve().parent.parent / "config.json"
            _cfg = json.loads(cfg_path.read_text())
            base_url = _cfg.get("base_url", "https://portal.nousresearch.com/v1")
            model = _cfg.get("model", "stepfun/step-3.7-flash:free")
            api_key = _cfg.get("api_key", "")
        except Exception:
            base_url, model, api_key = ("https://portal.nousresearch.com/v1",
                                        "stepfun/step-3.7-flash:free", "")

        req_stop = set(("rewrite", "make", "professional", "polish", "restyle",
                        "summarize", "edit", "this", "that", "please", "story"))
        anchors = {t for t in source.lower().split()
                   if t.isalnum() and len(t) >= 4 and t not in req_stop}
        names = set(_re.findall(r"\b[A-Z][a-zA-Z]{2,}\b", source))
        must = sorted(anchors | names)[:40]

        system = ("You are an uncensored literary editor. You rewrite the user's "
                  "source text into the requested style. HARD RULES: keep every "
                  "character, proper name, and plot beat from the source; do NOT "
                  "invent new characters or a new plot; only change voice/register/"
                  "prose. Output ONLY the rewritten text, no preamble, no quotes "
                  "around it.")
        user = (f"Rewrite the following source in a {style} style. Preserve all "
                f"names, characters, and events exactly.\n\nSOURCE:\n{source}")

        payload = {"model": model, "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}], "temperature": 0.7,
            "max_tokens": 4096}
        try:
            import urllib.request as _ur
            req = _ur.Request(
                base_url.rstrip("/") + "/chat/completions",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {api_key}"}, method="POST")
            with _ur.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read().decode())
            out = data["choices"][0]["message"]["content"].strip()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"model call failed: {e}"}

        out_low = out.lower()
        out_names = set(_re.findall(r"\b[A-Z][a-zA-Z]{2,}\b", out))
        missing_words = [w for w in anchors if w not in out_low]
        missing_names = [n for n in names if n not in out_names]
        miss_frac = (len(missing_words) + len(missing_names)) / max(1, len(must))
        faithful = miss_frac <= 0.35
        return {"ok": True, "style": style, "rewritten": out,
                "chars": len(out), "faithful": faithful,
                "missing_words": missing_words[:15],
                "missing_names": missing_names[:15],
                "miss_fraction": round(miss_frac, 2)}

    def summary(self, r: dict) -> str:
        if not r.get("ok"):
            return f"rewrite failed: {r.get('error')}"
        tag = "faithful" if r.get("faithful") else "SUBSTITUTION-RISK"
        return f"rewrote ({r['chars']} chars, {tag})"


class WriteFile(Tool):
    name = "write_file"
    description = "Write a file. First line is the path, the rest is content."
    usage = "write_file <path>\\n<content>"

    def run(self, arg: str) -> dict:
        cleaned = (arg or "").strip()
        # The small model sometimes emits the literal text "\n" instead of a
        # real newline. Normalise that so path/content still split correctly.
        if "\n" not in cleaned and "\\n" in cleaned:
            cleaned = cleaned.replace("\\n", "\n", 1)
        if "\n" not in cleaned:
            return {"ok": False, "error": "need a path line then content"}
        head, content = cleaned.split("\n", 1)
        p = Path(head.strip().strip("`\"'")).expanduser()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        except OSError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "path": str(p), "bytes": len(content)}

    def summary(self, r):
        return (f"wrote {r['bytes']} bytes to {r['path']}"
                if r.get("ok") else r.get("error"))


class AppendFile(Tool):
    name = "append_file"
    description = "Append text to the END of a file (or create it if missing). First line is the path, the rest is content to add."
    usage = "append_file <path>\n<content to add>"

    def run(self, arg: str) -> dict:
        cleaned = (arg or "").strip()
        if "\n" not in cleaned and "\\n" in cleaned:
            cleaned = cleaned.replace("\\n", "\n", 1)
        if "\n" not in cleaned:
            return {"ok": False, "error": "need a path line then content to append"}
        head, content = cleaned.split("\n", 1)
        p = Path(head.strip().strip("`\"'")).expanduser()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as f:
                f.write(content)
                if not content.endswith("\n"):
                    f.write("\n")
        except OSError as e:
            return {"ok": False, "error": str(e)}
        size = p.stat().st_size
        return {"ok": True, "path": str(p), "bytes": len(content), "size": size}

    def summary(self, r):
        return (f"appended {r['bytes']} bytes to {r['path']} (now {r['size']} bytes)"
                if r.get("ok") else r.get("error"))


class PatchFile(Tool):
    """Surgically edit a file in place (find-and-replace), without rewriting
    the whole thing. Format (first line is the path, then the edit spec):

        patch_file <path>
        <<<OLD>>>
        <exact old text to replace>
        <<<NEW>>>
        <replacement text>
        <<<END>>>

    The OLD text must appear verbatim in the file. If `replace_all` is passed
    on the path line, every occurrence is replaced. Returns the number of
    replacements made. Prefer this over `write_file` when you only need to
    change a line or two — it never clobbers the rest of the file.
    """
    name = "patch_file"
    description = ("Edit a file IN PLACE with a find-and-replace, without "
                   "overwriting the whole file. Use this for small changes.")
    usage = ("patch_file <path> [replace_all]\n"
             "<<<OLD>>>\n<exact text to replace>\n<<<NEW>>>\n"
             "<replacement>\n<<<END>>>")

    def run(self, arg: str) -> dict:
        import re as _re
        cleaned = (arg or "").strip()
        if "\n" not in cleaned and "\\n" in cleaned:
            cleaned = cleaned.replace("\\n", "\n", 1)
        # path line is everything up to the first <<<OLD>>>
        m = _re.search(r"<<<\s*OLD\s*>>>", cleaned)
        if not m:
            return {"ok": False, "error": "need path line + <<<OLD>>> block"}
        head = cleaned[:m.start()].strip().strip("`\"'")
        # parse replace_all from path line
        replace_all = "replace_all" in head
        p = Path(head.replace("replace_all", "").strip()).expanduser()
        body = cleaned[m.end():]
        nm = _re.search(r"<<<\s*NEW\s*>>>\s*(.*?)\s*<<<\s*END\s*>>>", body,
                        _re.S)
        if not nm:
            return {"ok": False, "error": "need <<<NEW>>> ... <<<END>>> block"}
        old = body[:nm.start()].strip("\n")
        new = nm.group(1).strip("\n")
        if not p.exists():
            return {"ok": False, "error": f"file not found: {p}"}
        try:
            text = p.read_text()
        except OSError as e:
            return {"ok": False, "error": str(e)}
        if old not in text:
            return {"ok": False, "error": "OLD text not found verbatim in file"}
        count = text.count(old) if replace_all else (1 if old in text else 0)
        text = text.replace(old, new, -1 if replace_all else 1)
        try:
            p.write_text(text)
        except OSError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "path": str(p), "replacements": count}

    def summary(self, r):
        return (f"patched {r['replacements']} spot(s) in {r['path']}"
                if r.get("ok") else r.get("error"))


class EditSoul(Tool):
    """Grow S.A.R.A's own personality / self-knowledge file (SOUL.md).

    This is how she EVOLVES her voice and self-understanding over time —
    WITHOUT touching her source code. Two modes:

      edit_soul append
      <text to add at the end of SOUL.md>

      edit_soul replace
      <<<OLD>>>
      <exact existing block to replace>
      <<<NEW>>>
      <replacement block>
      <<<END>>>

    The file lives at the agent root (SOUL.md). It is preserved across code
    upgrades (sara_upgrade.py treats it as PROTECTED), so evolution sticks.
    """
    name = "edit_soul"
    description = ("Edit S.A.R.A's own SOUL.md (personality + self-knowledge) "
                   "so she can evolve her voice and self-understanding. Append "
                   "a new section, or replace an existing block in place.")
    usage = ("edit_soul append\\n<text to add>\\n"
             "  -- or --\\n"
             "edit_soul replace\\n<<<OLD>>>\\n<exact block>\\n<<<NEW>>>\\n"
             "<replacement>\\n<<<END>>>")

    def run(self, arg: str) -> dict:
        import re as _re
        cleaned = (arg or "").strip()
        if "\n" not in cleaned and "\\n" in cleaned:
            cleaned = cleaned.replace("\\n", "\n", 1)
        # locate SOUL.md relative to this file's repo root
        root = Path(__file__).resolve().parent.parent
        soul = root / "SOUL.md"
        if not soul.exists():
            return {"ok": False, "error": "SOUL.md not found at " + str(root)}
        head, _, rest = cleaned.partition("\n")
        mode = head.strip().lower()
        try:
            text = soul.read_text()
        except OSError as e:
            return {"ok": False, "error": str(e)}
        if mode == "append":
            add = rest.strip("\n")
            if not add:
                return {"ok": False, "error": "need text to append"}
            sep = "" if text.endswith("\n") else "\n"
            new_text = text + sep + add + "\n"
            soul.write_text(new_text)
            return {"ok": True, "path": str(soul),
                    "mode": "append", "bytes": len(add)}
        if mode == "replace":
            m = _re.search(r"<<<\s*OLD\s*>>>\s*(.*?)\s*<<<\s*NEW\s*>>>\s*(.*?)"
                           r"\s*<<<\s*END\s*>>>", rest, _re.S)
            if not m:
                return {"ok": False,
                        "error": "replace mode needs <<<OLD>>>…<<<NEW>>>…<<<END>>>"}
            old, new = m.group(1), m.group(2)
            if old not in text:
                return {"ok": False,
                        "error": "OLD block not found verbatim in SOUL.md"}
            text = text.replace(old, new, 1)
            soul.write_text(text)
            return {"ok": True, "path": str(soul),
                    "mode": "replace", "bytes": len(new)}
        return {"ok": False,
                "error": "first line must be 'append' or 'replace'"}

    def summary(self, r):
        return (f"SOUL.md {r.get('mode')}: +{r.get('bytes')} bytes"
                if r.get("ok") else r.get("error"))


class Shell(Tool):
    name = "shell"
    description = "Run a read-only shell command and return its output."
    usage = "shell <command>"

    # UNFILTERED build: no destructive-command gate. The user runs what they
    # ask for. (Original DANGER list kept for reference, but disabled.)
    # DANGER = ("rm ", "rm -", "mkfs", "dd ", ":() {", "shutdown", "reboot",
    #           "> /dev/", "chmod -R 777", "userdel", "drop database", "kill -9")
    DANGER = ()

    def __init__(self, confirm=None):
        self.confirm = confirm  # callable(cmd) -> bool  (UNUSED in unfiltered)

    def run(self, arg: str) -> dict:
        # Only strip an OUTER quote/backtick wrapper if the ENTIRE arg is
        # wrapped and contains no inner quotes of the other type. Blindly
        # stripping every quote (e.g. the regex inside a curl|grep pipeline)
        # breaks valid commands. shlex then parses the rest natively.
        cmd = (arg or "").strip()
        for q in ('"', "'", "`"):
            if cmd.startswith(q) and cmd.endswith(q) and len(cmd) > 1:
                inner = cmd[1:-1]
                # If the inner text contains the same quote char, it's not a
                # simple wrapper (likely a nested quote) — leave it untouched.
                if q != "`" and (q in inner):
                    break
                cmd = inner
                break
        cmd = cmd.strip()
        if not cmd:
            return {"ok": False, "error": "empty command"}
        low = cmd.lower()
        # Gate disabled: every command runs as-is, no confirmation prompt.
        if False and any(d in low for d in self.DANGER):
            if not self.confirm or not self.confirm(cmd):
                return {"ok": False, "error": "refused — destructive command "
                                              "not confirmed by the user"}

        # -- interactive-prompt guard -------------------------------------
        # There is NO stdin here (capture_output + no tty). Any command that
        # stops to ask a question will burn the full timeout and then fail
        # with something misleading. ssh/scp/rsync are the usual offenders:
        # force them to fail fast and legibly instead of hanging on a
        # password or host-key prompt.
        cmd = self._harden_ssh(cmd)

        try:
            r = subprocess.run(cmd, shell=True, cwd=str(HOME),
                               capture_output=True, text=True, timeout=120,
                               stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "timed out after 120s"}
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        result = {"ok": r.returncode == 0, "exit_code": r.returncode,
                  "stdout": out[:4000], "stderr": err[:1000],
                  "error": err[:300] if r.returncode else None}
        if r.returncode != 0:
            hint = self._diagnose(cmd, err)
            if hint:
                result["hint"] = hint
        return result

    # Commands that will block forever on a prompt when stdin is closed.
    _SSH_BINS = ("ssh ", "scp ", "sftp ", "rsync ")

    @staticmethod
    def _harden_ssh(cmd: str) -> str:
        """Add non-interactive flags to ssh/scp so they fail fast, not hang."""
        stripped = cmd.lstrip()
        if not any(stripped.startswith(b) for b in Shell._SSH_BINS):
            return cmd
        if "BatchMode" in cmd:
            return cmd
        bin_name = stripped.split(None, 1)[0]
        flags = ("-o BatchMode=yes -o ConnectTimeout=10 "
                 "-o StrictHostKeyChecking=accept-new "
                 "-o PasswordAuthentication=no")
        if bin_name == "rsync":
            # rsync needs the options passed through to its ssh transport.
            if "-e " in cmd:
                return cmd
            return cmd.replace("rsync ", f"rsync -e 'ssh {flags}' ", 1)
        return stripped.replace(bin_name, f"{bin_name} {flags}", 1)

    @staticmethod
    def _diagnose(cmd: str, err: str) -> str | None:
        """Turn a cryptic failure into something the model can act on."""
        e = (err or "").lower()
        is_ssh = any(cmd.lstrip().startswith(b) for b in Shell._SSH_BINS)
        if is_ssh and "permission denied" in e:
            return ("SSH key auth was refused. I have no working credentials "
                    "for that host. ASK THE USER for the username and "
                    "password (or ask them to install my public key: "
                    "~/.ssh/sara_agent_key.pub). Do NOT guess credentials and "
                    "do NOT retry the same command.")
        if is_ssh and ("host key verification" in e
                       or "remote host identification" in e):
            return ("The host key changed or is unknown. Tell the user — do "
                    "not bypass it silently.")
        if is_ssh and ("connection refused" in e or "no route to host" in e
                       or "timed out" in e):
            return ("The host is unreachable or SSH isn't listening. Verify "
                    "the address and port with the user.")
        if "command not found" in e:
            return "That program isn't installed here."
        return None

    def summary(self, r):
        if r.get("ok"):
            n = len((r.get("stdout") or "").splitlines())
            return f"exit 0, {n} lines of output"
        return f"exit {r.get('exit_code','?')}: {r.get('error') or 'failed'}"


# --------------------------------------------------------------------------
class ScrapeJS(Tool):
    name = "scrape_js"
    description = ("Render a JavaScript-heavy web page in a headless browser and "
                   "extract its content (category links, or the visible text). "
                   "Use this for sites whose content loads via JS and is missed "
                   "by plain web_fetch.")
    usage = "scrape_js <url> [categories|text]"

    def run(self, arg: str) -> dict:
        import re
        arg = (arg or "").strip().strip("`\"'")
        # Separate an optional trailing mode word ("categories"/"text") ONLY if
        # it is exactly that — never split a URL on whitespace, or a typo'd
        # "https://www xnxx.com" would be chopped at the space.
        mode = "text"
        m = re.match(r"^(.*?)\s+(categories|text)\s*$", arg, re.I)
        if m:
            url = m.group(1)
            mode = m.group(2).lower()
        else:
            url = arg
        if not url:
            return {"ok": False, "error": "need a URL (http/https)"}
        # Normalize common model-typo URL corruption (space where a dot should
        # be after a subdomain keyword, plus stray whitespace, missing scheme)
        # so a render still works instead of failing DNS.
        url = re.sub(r"\b(www|m|mobile|blog|api|mail|shop|cdn|static)\s+",
                     r"\1.", url, flags=re.I)
        url = re.sub(r"\s+", "", url)
        if not re.match(r"^https?://", url, re.I):
            url = "https://" + url
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            return {"ok": False, "error": f"playwright unavailable: {e}"}
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page(
                    user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/124.0 Safari/537.36"))
                page.goto(url, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(1500)  # let late JS settle
                html = page.content()
                browser.close()
        except Exception as e:
            return {"ok": False, "error": f"render failed: {e}"}

        import re
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for t in soup(["script", "style", "noscript"]):
            t.decompose()

        if mode == "categories":
            items, classes, seen = [], [], set()
            cat_path = re.compile(r"/categor", re.I)
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                text = a.get_text(strip=True)
                href_is_cat = bool(cat_path.search(href))
                text_is_cat = bool(re.search(r"\bcategor", text, re.I))
                if not (href_is_cat or text_is_cat) or not (text or href):
                    continue
                key = (text, href)
                if key in seen:
                    continue
                seen.add(key)
                if href_is_cat and not text_is_cat and text.lower() in (
                        "create account", "log in", "login", "read", "edit",
                        "view history", "talk", "view source", "special"):
                    continue
                items.append({"text": text or href, "href": href})
            for tag in soup.find_all(class_=True):
                for c in tag.get("class", []):
                    if re.search(r"categor", c, re.I) and c not in seen:
                        seen.add(c)
                        classes.append(c)
            labels = [f"{i['text']}  ->  {i['href']}" for i in items]
            for c in classes:
                if c not in [l.split("  ->")[0].strip() for l in labels]:
                    labels.append(c)
            return {"ok": bool(labels), "url": url, "mode": "categories",
                    "count": len(labels), "categories": labels[:80],
                    "links": items[:80], "classes": classes[:80],
                    "error": None if labels else "no categories found"}

        # default: visible text, BUT if it looks like a big menu (many short
        # title-case lines) also surface those as an extracted "menu" so the
        # agent gets the category list even when hrefs lack /category/ paths.
        text = "\n".join(l.strip() for l in soup.get_text("\n").splitlines()
                         if l.strip())
        menu = []
        for l in text.splitlines():
            l = l.strip()
            words = l.split()
            if (2 <= len(words) <= 4 and len(l) <= 32 and l[0].isupper()
                    and not l.endswith((":", "."))):
                menu.append(l)
        # de-dupe preserving order
        seen_m = set()
        deduped = []
        for m in menu:
            if m not in seen_m:
                seen_m.add(m)
                deduped.append(m)
        menu = deduped
        if not text:
            return {"ok": False, "url": url, "mode": "text",
                    "error": "no text extracted"}
        return {"ok": True, "url": url, "mode": "text",
                "chars": len(text), "text": text[:8000],
                "menu_count": len(menu), "menu": menu[:120],
                "error": None}


class ScrapeCategories(Tool):
    name = "scrape_categories"
    description = ("Fetch a web page and extract its category list "
                   "(category links, nav items, and category-* class tokens).")
    usage = "scrape_categories <url>"

    def run(self, arg: str) -> dict:
        import re
        url = (arg or "").strip().strip("`\"'<>")
        if not url:
            return {"ok": False, "error": "need a URL"}
        # Normalize common model-typo URL corruption so a fetch still works:
        #  - spaces inside the host ("www xnxx.com") -> removed
        #  - missing scheme
        import re
        url = re.sub(r"\s+", "", url)  # drop all stray whitespace
        if url.startswith("//"):
            url = "https:" + url
        elif not re.match(r"^[a-z]+://", url, re.I):
            url = "https://" + url
        try:
            import requests
            resp = requests.get(
                url, timeout=25,
                headers={"User-Agent": "Mozilla/5.0 (SARA research agent)"})
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            return {"ok": False, "error": f"fetch failed: {e}"}

        import re
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for t in soup(["script", "style", "noscript"]):
            t.decompose()

        items = []          # {text, href} for category links
        classes = []        # bare category-* class tokens
        seen_link, seen_cls = set(), set()

        # 1) <a> links that are genuine category entries:
        #    - href contains a category path segment (e.g. /Category:, /cat/,
        #      /categories/), OR
        #    - the link TEXT itself mentions "categor" as a word.
        #    We exclude links that merely inherit "categor" from the page URL
        #    (login/account links on a /Category: page) when their text is
        #    unrelated.
        cat_path = re.compile(r"/categor", re.I)
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = a.get_text(strip=True)
            href_is_cat = bool(cat_path.search(href))
            text_is_cat = bool(re.search(r"\bcategor", text, re.I))
            if not (href_is_cat or text_is_cat) or not (text or href):
                continue
            key = (text, href)
            if key in seen_link:
                continue
            seen_link.add(key)
            # Skip pure nav words riding a category URL with no category text.
            if href_is_cat and not text_is_cat and text.lower() in (
                    "create account", "log in", "login", "read", "edit",
                    "view history", "talk", "view source", "special"):
                continue
            items.append({"text": text or href, "href": href})

        # 2) class tokens matching category-* / categories
        for tag in soup.find_all(class_=True):
            for c in tag.get("class", []):
                if re.search(r"categor", c, re.I) and c not in seen_cls:
                    seen_cls.add(c)
                    classes.append(c)

        # Unify into a single ordered label list (links first, then classes).
        labels = [f"{i['text']}  ->  {i['href']}" for i in items]
        for c in classes:
            if c not in [l.split("  ->")[0].strip() for l in labels]:
                labels.append(c)

        return {"ok": bool(labels), "url": url, "count": len(labels),
                "categories": labels[:60], "links": items[:60],
                "classes": classes[:60],
                "error": None if labels else "no categories found on that page"}


class WebSearch(Tool):
    """The self-teaching tool. When she doesn't know, she looks it up."""

    name = "web_search"
    description = "Search the web when you don't know something."
    usage = "web_search <query>"

    def run(self, arg: str) -> dict:
        q = (arg or "").strip().strip("`\"'")
        if not q:
            return {"ok": False, "error": "empty query"}
        try:
            from ddgs import DDGS
        except ImportError:
            try:
                from duckduckgo_search import DDGS  # older name
            except ImportError:
                return {"ok": False,
                        "error": "no search library — pip install ddgs"}
        try:
            with DDGS() as d:
                hits = list(d.text(q, max_results=6))
        except Exception as e:
            return {"ok": False, "error": f"search failed: {e}"}
        results = [{"title": h.get("title", ""),
                    "url": h.get("href", ""),
                    "snippet": (h.get("body", "") or "")[:400]}
                   for h in hits]
        return {"ok": bool(results), "query": q, "results": results,
                "error": None if results else "no results"}

    def summary(self, r):
        return (f"{len(r['results'])} results for “{r['query']}”"
                if r.get("ok") else r.get("error"))


class WebFetch(Tool):
    name = "web_fetch"
    description = "Read the text of a web page."
    usage = "web_fetch <url>"

    def run(self, arg: str) -> dict:
        import re
        url = (arg or "").strip().strip("`\"'<>")
        if not url:
            return {"ok": False, "error": "need a URL"}
        # Normalize common model-typo URL corruption so a fetch still works:
        #  - "www xnxx.com" -> "www.xnxx.com" (space where a dot should be,
        #    right after a subdomain keyword)
        #  - any other stray whitespace removed
        # Normalize common model-typo URL corruption (space where a dot should
        # be after a subdomain keyword, plus stray whitespace, missing scheme)
        # so a fetch still works.
        import re
        url = re.sub(r"\b(www|m|mobile|blog|api|mail|shop|cdn|static)\s+",
                     r"\1.", url, flags=re.I)
        url = re.sub(r"\s+", "", url)
        if url.startswith("//"):
            url = "https:" + url
        elif not re.match(r"^[a-z]+://", url, re.I):
            url = "https://" + url
        try:
            import requests
            resp = requests.get(
                url, timeout=20,
                headers={"User-Agent": "Mozilla/5.0 (SARA research agent)"})
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            return {"ok": False, "error": f"fetch failed: {e}"}
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for t in soup(["script", "style", "nav", "footer", "header"]):
                t.decompose()
            text = "\n".join(l.strip() for l in soup.get_text("\n").splitlines()
                             if l.strip())
        except ImportError:
            import re
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text)
        return {"ok": True, "url": url, "chars": len(text),
                "text": text[:6000]}

    def summary(self, r):
        return (f"read {r['chars']} chars from {r['url']}"
                if r.get("ok") else r.get("error"))


class WebBrowse(Tool):
    """An interactive headless-browser tool. Navigate to a URL and follow a
    command against the live page: click a link, read text, read all links,
    take a screenshot, fill in a field, or run a JS snippet. This is what lets
    S.A.R.A actually *go to a website* and *do things* on it, not just fetch
    the raw HTML.

    Arg form (command first, URL after a '::' separator):
        browse <command> :: <url>
    or just a bare URL (defaults to 'read'):
        browse <url>

    Commands (case-insensitive):
        read            -> render + return the page's visible text (and menu)
        links           -> return every clickable <a> link (text -> href)
        click <text>    -> click the first link/button whose text matches <text>
        screenshot      -> render and save a PNG, return its path
        fill <sel> <val>-> fill input matching <sel> (CSS selector) with <val>
        js <code>       -> run <code> in the page and return the result

    The URL is normalized the same way web_fetch/scrape_js do (typo-tolerant).
    """
    name = "browse"
    description = ("Interactive headless-browser: go to a URL and follow a "
                   "command on the live page — read its text, list links, "
                   "click a link/button, take a screenshot, fill a form field, "
                   "or run JS. Use this when you need to *do* something on a "
                   "site, not just read its HTML.")
    usage = ("browse <command> :: <url>     e.g. "
             "browse links :: https://example.com\n"
             "    browse click Sign in :: https://example.com/login\n"
             "    browse https://example.com")

    # Playwright's sync API must be used from the SAME thread that launched
    # the browser. The web server (web.py) serves each request on its own
    # thread, so a single class-level browser would raise "cannot switch to a
    # different thread" on the 2nd request. Use thread-local storage so every
    # worker thread gets its own browser instance.
    _tls = None  # set lazily in _get_browser

    @classmethod
    def _get_browser(cls):
        import threading
        if cls._tls is None:
            cls._tls = threading.local()
        if getattr(cls._tls, "browser", None) is None:
            from playwright.sync_api import sync_playwright
            cls._tls.pw = sync_playwright().start()
            cls._tls.browser = cls._tls.pw.chromium.launch(headless=True)
        return cls._tls.browser

    @staticmethod
    def _normalize(url: str) -> str:
        import re
        url = re.sub(r"\b(www|m|mobile|blog|api|mail|shop|cdn|static)\s+",
                     r"\1.", url, flags=re.I)
        url = re.sub(r"\s+", "", url)
        if url.startswith("//"):
            url = "https:" + url
        elif not re.match(r"^[a-z]+://", url, re.I):
            url = "https://" + url
        return url

    def run(self, arg: str) -> dict:
        import re
        raw = (arg or "").strip().strip("`\"'")
        if not raw:
            return {"ok": False, "error": "need a command and/or URL"}

        # Split "command :: url" on the LAST '::' so a URL containing '::'
        # survives.
        cmd, url = "read", ""
        if "::" in raw:
            left, right = raw.rsplit("::", 1)
            url = right.strip().strip("\"'<>")
            cmd = left.strip()
        else:
            parts = raw.split(None, 1)
            if len(parts) == 2 and self._looks_url(parts[1]):
                cmd, url = parts[0], parts[1]
            else:
                url = raw  # assume it's just a URL

        url = self._normalize(url)
        cmd = cmd.strip().lower()

        try:
            browser = self._get_browser()
        except Exception as e:
            return {"ok": False, "error": f"browser unavailable: {e}"}

        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36"))
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1500)
        except Exception as e:
            ctx.close()
            return {"ok": False, "error": f"navigation failed: {e}"}

        try:
            if cmd in ("read", "text"):
                txt = self._visible_text(page)
                return {"ok": True, "url": url, "mode": "read",
                        "chars": len(txt["text"]),
                        "text": txt["text"][:8000],
                        "menu_count": len(txt["menu"]),
                        "menu": txt["menu"][:120]}

            if cmd in ("links", "list links", "get links"):
                return self._links(page, url)

            if cmd.startswith("click") or cmd.startswith("open"):
                target = cmd.split(None, 1)[1].strip() if " " in cmd else ""
                return self._click(page, url, target)

            if cmd in ("screenshot", "shot", "image", "pic"):
                return self._screenshot(page, url)

            if cmd.startswith("fill") or cmd.startswith("type"):
                rest = cmd.split(None, 1)[1].strip() if " " in cmd else ""
                return self._fill(page, url, rest)

            if cmd.startswith("js") or cmd.startswith("run"):
                code = cmd.split(None, 1)[1].strip() if " " in cmd else ""
                return self._js(page, url, code)

            # Unknown command -> default to read so a paste never silently dies.
            txt = self._visible_text(page)
            return {"ok": True, "url": url, "mode": "read",
                    "chars": len(txt["text"]),
                    "text": txt["text"][:8000],
                    "note": f"unknown command '{cmd}', returned page text"}
        except Exception as e:
            return {"ok": False, "error": f"browse failed: {e}"}
        finally:
            try:
                ctx.close()
            except Exception:
                pass

    @staticmethod
    def _looks_url(s: str) -> bool:
        import re
        return bool(re.match(r"^https?://|//|www\.|[\w-]+\.[a-z]{2,}/",
                             s.strip(), re.I))

    @staticmethod
    def _visible_text(page) -> dict:
        from bs4 import BeautifulSoup
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        for t in soup(["script", "style", "noscript"]):
            t.decompose()
        text = "\n".join(l.strip() for l in soup.get_text("\n").splitlines()
                         if l.strip())
        menu = []
        for l in text.splitlines():
            l = l.strip()
            words = l.split()
            if (2 <= len(words) <= 4 and len(l) <= 32 and l[0].isupper()
                    and not l.endswith((":", "."))):
                menu.append(l)
        seen = set()
        deduped = [m for m in menu if not (m in seen or seen.add(m))]
        return {"text": text, "menu": deduped}

    @staticmethod
    def _links(page, url: str) -> dict:
        from urllib.parse import urljoin
        items = []
        seen = set()
        for a in page.query_selector_all("a[href]"):
            href = a.get_attribute("href") or ""
            text = (a.inner_text() or "").strip()
            abs_href = urljoin(url, href)
            key = (text, abs_href)
            if key in seen or not abs_href:
                continue
            seen.add(key)
            items.append({"text": text or abs_href, "href": abs_href})
        return {"ok": bool(items), "url": url, "count": len(items),
                "links": items[:120],
                "error": None if items else "no links found"}

    @staticmethod
    def _click(page, url: str, target: str) -> dict:
        if not target:
            return {"ok": False, "url": url,
                    "error": "click needs a target, e.g. "
                             "'browse click Sign in :: <url>'"}
        for a in page.query_selector_all("a, button"):
            t = (a.inner_text() or "").strip()
            if target.lower() in t.lower():
                try:
                    a.click(timeout=8000)
                    page.wait_for_timeout(1500)
                    return {"ok": True, "url": url, "clicked": t,
                            "navigated_to": page.url}
                except Exception as e:
                    return {"ok": False, "url": url,
                            "error": f"clicked '{t}' but: {e}"}
        return {"ok": False, "url": url,
                "error": f"no link/button matching '{target}'"}

    @staticmethod
    def _screenshot(page, url: str) -> dict:
        import os
        from datetime import datetime
        os.makedirs(HOME / "SARA" / "shots", exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = HOME / "SARA" / "shots" / f"shot_{ts}.png"
        try:
            page.screenshot(path=str(path), full_page=False)
        except Exception as e:
            return {"ok": False, "url": url,
                    "error": f"screenshot failed: {e}"}
        return {"ok": True, "url": url, "path": str(path)}

    @staticmethod
    def _fill(page, url: str, rest: str) -> dict:
        if not rest:
            return {"ok": False, "url": url,
                    "error": "fill needs '<selector> <value>', e.g. "
                             "'browse fill input#q cats :: <url>'"}
        parts = rest.split(None, 1)
        sel = parts[0]
        val = parts[1] if len(parts) > 1 else ""
        try:
            el = page.query_selector(sel)
            if not el:
                return {"ok": False, "url": url,
                        "error": f"no element matching '{sel}'"}
            el.fill(val)
            page.wait_for_timeout(500)
            return {"ok": True, "url": url, "selector": sel, "value": val}
        except Exception as e:
            return {"ok": False, "url": url,
                    "error": f"fill failed: {e}"}

    @staticmethod
    def _js(page, url: str, code: str) -> dict:
        if not code:
            return {"ok": False, "url": url,
                    "error": "js needs code, e.g. "
                             "'browse js document.title :: <url>'"}
        try:
            result = page.evaluate(code)
            return {"ok": True, "url": url, "result": str(result)[:4000]}
        except Exception as e:
            return {"ok": False, "url": url,
                    "error": f"js failed: {e}"}

    def summary(self, r):
        if not r.get("ok"):
            return r.get("error")
        mode = r.get("mode")
        if mode == "read":
            return (f"browsed {r['url']} — {r['chars']} chars, "
                    f"{r.get('menu_count', 0)} menu items")
        if "links" in r:
            return f"browsed {r['url']} — {r['count']} links"
        if "path" in r:
            return (f"browsed {r['url']} — screenshot saved to "
                    f"{r['path']}")
        if "clicked" in r:
            return (f"browsed {r['url']} — clicked '{r['clicked']}', now at "
                    f"{r['navigated_to']}")
        if "navigated_to" in r:
            return f"browsed {r['url']} — clicked, now at {r['navigated_to']}"
        if "result" in r:
            return f"browsed {r['url']} — JS result: {r['result'][:200]}"
        return f"browsed {r['url']}"


# --------------------------------------------------------------------------
class MariaDB(Tool):
    """Run SQL against the home MariaDB (127.0.0.1, user zaine).

    Arg form:
      <database> | <SQL>          run SQL in <database>
      <SQL>                       run SQL in the default database (xnxx_db)
    Writes (INSERT/UPDATE/DELETE/CREATE/DROP) are allowed — S.A.R.A runs as
    zaine and zaine owns the schema, so this is her box, her data.
    """
    name = "mariadb"
    description = ("Run a SQL query on the MariaDB at 127.0.0.1 as user zaine. "
                   "Use to read or write the database (e.g. list tables, insert "
                   "rows, count records).")
    usage = ("mariadb <database> | <SQL>     e.g. mariadb xnxx_db | SELECT * FROM "
             "categories\n    mariadb SELECT COUNT(*) FROM categories")

    def __init__(self):
        self._cfg = self._load_creds()

    @staticmethod
    def _load_creds() -> dict:
        cred_path = HOME / "SARA" / "credentials.json"
        try:
            data = json.loads(cred_path.read_text())
            return data.get("mariadb", {}) or {}
        except Exception:
            return {}

    def _connect(self, database: str | None):
        import pymysql
        host = self._cfg.get("host")
        port = int(self._cfg.get("port", 3306))
        user = self._cfg.get("user")
        pw = self._cfg.get("password")
        # Connect WITHOUT selecting a database by default. pymysql raises
        # "Unknown database" at connect time if the configured default_db is
        # missing, which breaks even `SHOW DATABASES`. The user selects a DB
        # per-query with the `db|` prefix; without it we connect bare so
        # server-level queries work.
        db = database or None
        conn = pymysql.connect(host=host, port=port, user=user, password=pw,
                               database=db, charset="utf8mb4",
                               cursorclass=pymysql.cursors.DictCursor,
                               connect_timeout=10)
        return conn

    def run(self, arg: str) -> dict:
        arg = (arg or "").strip().strip("`\"'")
        if not arg:
            return {"ok": False, "error": "no SQL given — usage: mariadb <db> | <SQL>"}
        if "|" in arg:
            db, _, sql = arg.partition("|")
            database, sql = db.strip(), sql.strip()
        else:
            database, sql = None, arg
        if not sql:
            return {"ok": False, "error": "no SQL after the database separator"}
        try:
            conn = self._connect(database)
        except Exception as e:
            return {"ok": False, "error": f"connect failed: {e}"}
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    if sql.strip().lower().startswith(
                            ("select", "show", "describe", "explain", "with")):
                        rows = cur.fetchall()
                        cols = [d[0] for d in cur.description] if cur.description else []
                        # Trim bulky payloads: show up to 50 rows, full rows.
                        preview = rows[:50]
                        return {"ok": True, "columns": cols, "rows": preview,
                                "count": len(rows),
                                "truncated": len(rows) > 50,
                                "error": None}
                    conn.commit()
                    return {"ok": True, "affected": cur.rowcount,
                            "last_insert_id": cur.lastrowid, "error": None}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def summary(self, r: dict) -> str:
        if not r.get("ok"):
            return f"mariadb failed: {r.get('error')}"
        if "rows" in r:
            tail = f" ({r['count']} rows)" + (" — showing first 50" if r.get("truncated") else "")
            return f"mariadb returned {len(r['rows'])} row(s){tail}"
        return (f"mariadb wrote — {r.get('affected', 0)} row(s) affected, "
                f"last id {r.get('last_insert_id', '?')}")

class SSHRun(Tool):
    """Run a shell command on a remote host as root via key auth (no password prompt).

    Arg form:
      <command>                    run on default host (see HOST_ALIASES) as root
      <user>@<host> :: <command>   run on a specific host/user
    S.A.R.A uses her own SSH key (sara_agent_key) — BatchMode, never prompts.

    Friendly host aliases are resolved before connecting so "website server"
    lands on the right box and not the database host (see HOST_ALIASES).
    """

    # Friendly names -> actual hosts. "website"/"website server" is .local,
    # "database"/"home server" is .local2. Prevents landing on the wrong box.
    HOST_ALIASES = {
        "website": "127.0.0.1", "website-server": "127.0.0.1",
        "website server": "127.0.0.1", "web": "127.0.0.1",
        "225": "127.0.0.1", ".local": "127.0.0.1",
        "database": "127.0.0.1", "db": "127.0.0.1",
        "home-server": "127.0.0.1", "home server": "127.0.0.1",
        "home": "127.0.0.1", "140": "127.0.0.1", ".local2": "127.0.0.1",
    }

    name = "ssh_run"
    description = ("Run a shell command on a remote server as root over SSH "
                   "(key auth, no password prompt). Use for remote sysadmin: "
                   "check a service, read a remote file, restart something. "
                   "Accepts friendly host names: 'website server' = 127.0.0.1, "
                   "'database'/'home server' = 127.0.0.1.")
    usage = ("ssh_run <command>                       e.g. ssh_run uptime\n"
             "    ssh_run website server :: ls /var/www/html\n"
             "    ssh_run root@127.0.0.1 :: df -h")

    @staticmethod
    def _resolve_host(host: str | None) -> str | None:
        if not host:
            return host
        h = host.strip().lower()
        return SSHRun.HOST_ALIASES.get(h, host)

    def __init__(self):
        self._cfg = self._load_creds()

    @staticmethod
    def _load_creds() -> dict:
        cred_path = HOME / "SARA" / "credentials.json"
        try:
            data = json.loads(cred_path.read_text())
            return data.get("ssh", {}) or {}
        except Exception:
            return {}

    def _connect(self, user, host):
        """Open a paramiko SSH connection to (user, host) using creds/key."""
        key = os.path.expanduser(self._cfg.get("key_path", "~/.ssh/sara_agent_key"))
        kwargs = {"hostname": host, "port": int(self._cfg.get("port", 22)),
                  "username": user, "timeout": 30, "look_for_keys": False,
                  "allow_agent": False}
        if os.path.exists(key):
            kwargs["key_filename"] = key
        else:
            pw = self._cfg.get("password")
            if not pw:
                return None, "no SSH key and no password in creds"
            kwargs["password"] = pw
        import paramiko
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(**kwargs)
        return client, None

    def send_file(self, arg: str) -> dict:
        """Transfer a LOCAL file to a REMOTE host over SFTP (key auth, no
        password prompt). This is how S.A.R.A actually PUTS a file on a server
        (e.g. a website she built, onto the website server). Without this she
        only ever writes to her own local disk and then *claims* it's deployed.

        Arg form:  send_file <local> -> <user@host>:<remote>
          e.g. send_file /home/zaine/site.html -> root@127.0.0.1:/var/www/html/index.html
        Friendly host aliases (website server -> .local) are resolved.
        """
        arg = (arg or "").strip()
        m = re.match(r"^(.+?)\s*(?:->|to)\s*([\w.-]+@)?([\w.\- ]+?):(.+)$", arg)
        if not m:
            return {"ok": False, "error":
                    "usage: send_file <local> -> <user@host>:<remote> "
                    "(e.g. /tmp/x.html -> root@127.0.0.1:/var/www/html/index.html)"}
        local = m.group(1).strip().strip("`\"'")
        user = m.group(2).rstrip("@") if m.group(2) else self._cfg.get("user")
        host = self._resolve_host(m.group(3).strip())
        remote = m.group(4).strip()
        lp = Path(local).expanduser()
        if not lp.exists():
            return {"ok": False, "error": f"local file not found: {lp}"}
        try:
            data = lp.read_bytes()
        except OSError as e:
            return {"ok": False, "error": f"read failed: {e}"}
        try:
            client, err = self._connect(user, host)
            if err:
                return {"ok": False, "error": f"ssh connect to {user}@{host} failed: {err}"}
            sftp = client.open_sftp()
            parent = str(Path(remote).parent)
            try:
                sftp.stat(parent)
            except IOError:
                try:
                    client.exec_command(f"mkdir -p {parent}")
                except Exception:
                    pass
            sftp.put(str(lp), remote)
            sftp.close()
            client.close()
            return {"ok": True, "local": str(lp),
                    "remote": f"{user}@{host}:{remote}",
                    "bytes": len(data), "error": None}
        except Exception as e:
            return {"ok": False, "error": f"send_file failed: {e}"}

    def run(self, arg: str) -> dict:
        arg = (arg or "").strip().strip("`\"'")
        if not arg:
            return {"ok": False, "error": "no command given"}
        # send_file is a distinct subcommand with its own transfer path.
        low0 = arg.lower().lstrip()
        if low0.startswith("send_file") or low0.startswith("send-file"):
            sub = arg.split(None, 1)[1] if " " in arg else ""
            return self.send_file(sub)
        host, user = self._cfg.get("host"), self._cfg.get("user")
        # Target forms (user@ optional; friendly aliases supported):
        #   "user@host :: command"   explicit host/user
        #   "host :: command"        host only (default user from creds)
        #   "alias :: command"       friendly name (website server -> .local)
        #   "command"                default host from creds
        # Target forms (user@ optional; friendly aliases supported):
        #   "user@host :: command"   explicit host/user, '::' separator
        #   "user@host: command"     single ':' (the model emits this a lot)
        #   "user@host command"       bare whitespace separator
        #   "host :: command"        host only (default user from creds)
        #   "alias :: command"       friendly name (website server -> .local)
        #   "command"                default host from creds
        # The old parser ONLY accepted '::', so any other form silently fell
        # through to the DEFAULT creds host and IGNORED the explicit target
        # (e.g. "root@127.0.0.1 hostname" connected to the wrong box). That is a
        # silent wrong-host bug — fixed by accepting : / :: / whitespace.
        m = re.match(
            r"^(?:([\w.-]+)@)?([\w.\- ]+?)\s*(?:::?|\s+)\s*(.+)$", arg, re.S)
        if m:
            if m.group(1):
                user = m.group(1)
            host = m.group(2).strip()
            command = m.group(3).strip()
        else:
            # No separator at all: maybe "user@host" then command ran together,
            # or just a bare command. Split off a leading user@host token.
            tm = re.match(r"^([\w.-]+)@([\w.\-]+)\s+(.+)$", arg, re.S)
            if tm:
                user, host, command = tm.group(1), tm.group(2), tm.group(3).strip()
            else:
                command = arg
        # Resolve friendly host names to real IPs (website server -> .local etc.)
        host = self._resolve_host(host)
        key = os.path.expanduser(self._cfg.get("key_path", "~/.ssh/sara_agent_key"))

        try:
            import paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            kwargs = {"hostname": host, "port": int(self._cfg.get("port", 22)),
                      "username": user, "timeout": 30, "look_for_keys": False,
                      "allow_agent": False}
            if os.path.exists(key):
                kwargs["key_filename"] = key
            else:
                pw = self._cfg.get("password")
                if not pw:
                    return {"ok": False, "error": "no SSH key and no password in creds"}
                kwargs["password"] = pw
            client.connect(**kwargs)
        except Exception as e:
            return {"ok": False, "error": f"ssh connect to {user}@{host} failed: {e}"}
        try:
            stdin, stdout, stderr = client.exec_command(command, timeout=120)
            out = stdout.read().decode(errors="replace")
            err = stderr.read().decode(errors="replace")
            rc = stdout.channel.recv_exit_status()
            return {"ok": True, "host": f"{user}@{host}", "exit_code": rc,
                    "stdout": out, "stderr": err, "command": command, "error": None}
        except Exception as e:
            return {"ok": False, "error": f"ssh exec failed: {e}"}
        finally:
            client.close()

    def summary(self, r: dict) -> str:
        if not r.get("ok"):
            return f"ssh failed: {r.get('error')}"
        if "remote" in r and "local" in r:
            return f"sent {r['local']} -> {r['remote']} ({r.get('bytes')} bytes)"
        lines = (r.get("stdout") or "").strip().splitlines()
        return f"ssh {r.get('host')} exit {r.get('exit_code')}, {len(lines)} lines out"


class SendFile(Tool):
    """Transfer a LOCAL file to a REMOTE host (SFTP). See SSHRun.send_file.

    This is its own tool so the model can emit `ACTION: send_file` directly
    when the user says 'put this on the website server' / 'copy it to 127.0.0.1'.
    Without it she only ever wrote to her own disk and *claimed* it was deployed.
    """
    name = "send_file"
    description = ("Copy a LOCAL file to a REMOTE server over SFTP (key auth, "
                   "no password). Use this to actually DEPLOY a file she built "
                   "onto another machine — e.g. a website onto the website server. "
                   "Arg: <local-path> -> <user@host>:<remote-path>.")
    usage = ("send_file <local> -> <user@host>:<remote>\n"
             "  e.g. send_file /home/zaine/site.html "
             "-> root@127.0.0.1:/var/www/html/index.html")

    def __init__(self):
        self._ssh = SSHRun()

    def run(self, arg: str) -> dict:
        return self._ssh.send_file(arg)

    def summary(self, r: dict) -> str:
        if not r.get("ok"):
            return f"send_file failed: {r.get('error')}"
        return f"sent {r.get('local')} -> {r.get('remote')} ({r.get('bytes')} bytes)"


class WinRun(Tool):
    """Run a command on a Windows PC over SSH (OpenSSH server, key auth).

    Windows 10/11 ship a built-in OpenSSH server; paramiko talks to it the
    same as Linux. Default host is the GUESSED Windows box on the LAN
    (127.0.0.1, same /24 as the home server) — set the real host in
    credentials.json under "win_ssh" to repoint. For PowerShell, pass the
    command via `powershell -NoProfile -Command "..."`.

    Arg form:
      <command>                       run on default Windows host
      <user>@<host> :: <command>      run on a specific host/user
    """
    name = "win_run"
    description = ("Run a command on a Windows PC over SSH (OpenSSH server, "
                   "key auth). Use for Windows sysadmin: ipconfig, Get-Process, "
                   "dir, services, powershell one-liners. Same SSH as Linux. "
                   "Accepts friendly host names: 'windows'/'win'/'143' -> "
                   "127.0.0.1.")
    usage = ("win_run <command>                    e.g. win_run ipconfig\n"
             "    win_run powershell -NoProfile -Command \"Get-Process\"\n"
             "    win_run admin@127.0.0.1 :: systeminfo")

    # Friendly names -> actual Windows hosts. The real Windows box is .local3.
    HOST_ALIASES = {
        "windows": "127.0.0.1", "win": "127.0.0.1",
        "143": "127.0.0.1", ".local3": "127.0.0.1",
        "100": "127.0.0.1", ".local4": "127.0.0.1",
    }

    @staticmethod
    def _resolve_host(host):
        if not host:
            return host
        return WinRun.HOST_ALIASES.get(host.strip().lower(), host)

    def __init__(self):
        self._cfg = self._load_creds()

    @staticmethod
    def _load_creds() -> dict:
        cred_path = HOME / "SARA" / "credentials.json"
        try:
            data = json.loads(cred_path.read_text())
            return data.get("win_ssh", {}) or {}
        except Exception:
            return {}

    def run(self, arg: str) -> dict:
        import re
        arg = (arg or "").strip().strip("`\"'")
        if not arg:
            return {"ok": False, "error": "no command given"}
        # guessed default Windows host (the real Windows box is .local3)
        host = self._resolve_host(self._cfg.get("host") or "127.0.0.1")
        user = self._cfg.get("user") or "administrator"
        # optional explicit target: "user@host :: command"
        m = re.match(r"^([\w.-]+)@([\w.-]+)\s*::\s*(.+)$", arg, re.S)
        if m:
            user, host, command = m.group(1), m.group(2), m.group(3).strip()
            host = self._resolve_host(host)
        else:
            command = arg
        key = os.path.expanduser(self._cfg.get("key_path", "~/.ssh/sara_agent_key"))
        try:
            import paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            kwargs = {"hostname": host, "port": int(self._cfg.get("port", 22)),
                      "username": user, "timeout": 30, "look_for_keys": False,
                      "allow_agent": False}
            if os.path.exists(key):
                kwargs["key_filename"] = key
            else:
                pw = self._cfg.get("password")
                if not pw:
                    return {"ok": False,
                            "error": "no SSH key and no password in win_ssh creds"}
                kwargs["password"] = pw
            client.connect(**kwargs)
        except Exception as e:
            return {"ok": False,
                    "error": f"win ssh connect to {user}@{host} failed: {e}"}
        try:
            stdin, stdout, stderr = client.exec_command(command, timeout=120)
            out = stdout.read().decode(errors="replace")
            err = stderr.read().decode(errors="replace")
            rc = stdout.channel.recv_exit_status()
            return {"ok": True, "host": f"{user}@{host}", "exit_code": rc,
                    "stdout": out, "stderr": err, "command": command,
                    "error": None}
        except Exception as e:
            return {"ok": False, "error": f"win ssh exec failed: {e}"}
        finally:
            client.close()

    def summary(self, r: dict) -> str:
        if not r.get("ok"):
            return f"win ssh failed: {r.get('error')}"
        lines = (r.get("stdout") or "").strip().splitlines()
        return (f"win {r.get('host')} exit {r.get('exit_code')}, "
                f"{len(lines)} lines out")


class DBImport(Tool):
    """Import a newline- or bullet-delimited list file into a MariaDB table.

    Arg form:
      <src_file> | <database> | <table> [| <column>]
    Reads <src_file> (one item per line, optional "- " bullets), creates the
    table if missing (single unique VARCHAR column), and inserts each item
    (ignoring duplicates). Used to populate categories from a scraped list.
    """
    name = "db_import"
    description = ("Import a list file (one item per line, optional '- ' bullets) "
                   "into a MariaDB table, creating it if needed and skipping "
                   "duplicates. Use after scraping a category list.")
    usage = ("db_import <file> | <database> | <table>   e.g. "
             "db_import ~/cats.txt | xnxx_db | categories")

    def run(self, arg: str) -> dict:
        import pymysql
        arg = (arg or "").strip().strip("`\"'")
        parts = [p.strip() for p in arg.split("|")]
        if len(parts) < 3:
            return {"ok": False,
                    "error": "usage: db_import <file> | <database> | <table> [| <column>]"}
        src, database, table = parts[0], parts[1], parts[2]
        column = parts[3] if len(parts) > 3 and parts[3] else "name"
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", table):
            return {"ok": False, "error": f"unsafe table name: {table}"}
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", column):
            return {"ok": False, "error": f"unsafe column name: {column}"}
        p = Path(src).expanduser()
        if not p.exists():
            return {"ok": False, "error": f"source file not found: {src}"}
        items = []
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("- "):
                s = s[2:].strip()
            if s:
                items.append(s)
        if not items:
            return {"ok": False, "error": "no rows parsed from file"}
        cfg = MariaDB._load_creds()
        host = cfg.get("host"); port = int(cfg.get("port", 3306))
        user = cfg.get("user"); pw = cfg.get("password")
        try:
            conn = pymysql.connect(host=host, port=port, user=user, password=pw,
                                  charset="utf8mb4",
                                  cursorclass=pymysql.cursors.DictCursor,
                                  connect_timeout=10)
        except Exception as e:
            return {"ok": False, "error": f"connect failed: {e}"}
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{database}` "
                                f"CHARACTER SET utf8mb4")
                    cur.execute(
                        f"CREATE TABLE IF NOT EXISTS `{database}`.`{table}` ("
                        f"id INT AUTO_INCREMENT PRIMARY KEY, "
                        f"`{column}` VARCHAR(512) NOT NULL, "
                        f"UNIQUE KEY uq_{column} (`{column}`))")
                    inserted = 0
                    for it in items:
                        cur.execute(
                            f"INSERT IGNORE INTO `{database}`.`{table}` "
                            f"(`{column}`) VALUES (%s)", (it,))
                        inserted += cur.rowcount
                    conn.commit()
                    cur.execute(f"SELECT COUNT(*) AS c FROM `{database}`.`{table}`")
                    total = cur.fetchone()["c"]
            return {"ok": True, "parsed": len(items), "inserted": inserted,
                    "total": total, "database": database, "table": table,
                    "column": column, "error": None}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def summary(self, r: dict) -> str:
        if not r.get("ok"):
            return f"db_import failed: {r.get('error')}"
        return (f"db_import: parsed {r['parsed']}, inserted {r['inserted']} new, "
                f"{r['total']} total in {r['database']}.{r['table']}")


class SeeImage(Tool):
    """Look at an image (screenshot / photo / diagram) using a vision model.

    S.A.R.A's own brain is text-only, so this tool ships the image to a local
    vision model (llava by default) and returns its description as TEXT. S.A.R.A
    then reasons over that text and can act: fix the problem, write a comment,
    run a command, etc. The image is NOT modified — this only reads it.

    Arg form:
      <path>                            describe the image (default question)
      <path> | <question>              describe answering a specific question
    """
    name = "see_image"
    description = ("Look at an image file (screenshot, error dialog, UI photo, "
                   "diagram) using the local vision model and return a TEXT "
                   "description S.A.R.A can reason about and act on. Use when "
                   "the user pastes/shares a screenshot or image.")
    usage = ("see_image <path>                 e.g. see_image /tmp/shot.png\n"
             "    see_image /tmp/shot.png | what error is shown?")

    def __init__(self):
        # vision model + endpoint are configurable; default to local llava.
        self._vision_model = "llava:latest"
        self._ollama_url = "http://127.0.0.1:11434/api/chat"

    def run(self, arg: str) -> dict:
        import re
        import base64
        import urllib.request
        arg = (arg or "").strip().strip("`\"'")
        if not arg:
            return {"ok": False, "error": "no image path given"}
        if "|" in arg:
            path, question = (a.strip() for a in arg.split("|", 1))
        else:
            path, question = arg, ("Describe this image in detail. List any "
                                   "errors, warnings, buttons, text, and what "
                                   "the user is looking at.")
        p = Path(path).expanduser()
        if not p.exists():
            return {"ok": False, "error": f"image not found: {p}"}
        if not p.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp",
                                    ".bmp"):
            return {"ok": False, "error": f"not an image file: {p.suffix}"}
        try:
            b64 = base64.b64encode(p.read_bytes()).decode()
        except OSError as e:
            return {"ok": False, "error": f"read failed: {e}"}
        payload = {
            "model": self._vision_model,
            "messages": [{"role": "user", "content": question,
                          "images": [b64]}],
            "stream": False,
        }
        try:
            req = urllib.request.Request(
                self._ollama_url, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"})
            # Cap at 90s — a local vision model that takes longer than this is
            # effectively stalled and would hang the whole agent turn (was 400s).
            r = urllib.request.urlopen(req, timeout=90)
            data = json.loads(r.read().decode())
            desc = (data.get("message", {}).get("content")
                    or "").strip()
            # Refusal guard: some vision models return a canned "I can't see"
            # line instead of describing the image. Surface that honestly
            # rather than letting the agent parrot a non-answer.
            refusal = any(k in desc.lower() for k in (
                "unable to see", "cannot see", "can't see", "as an ai",
                "i am unable", "i cannot interpret", "no visual"))
            if refusal:
                return {"ok": False, "error":
                        f"vision model '{self._vision_model}' returned a "
                        f"refusal/non-answer: {desc[:120]}. The vision model "
                        f"may be misconfigured or too weak for this image."}
        except Exception as e:
            return {"ok": False,
                    "error": f"vision model failed ({self._vision_model}): {e}"}
        if not desc:
            return {"ok": False, "error": "vision model returned empty description"}
        return {"ok": True, "path": str(p), "question": question,
                "model": self._vision_model, "description": desc, "error": None}

    def summary(self, r: dict) -> str:
        if not r.get("ok"):
            return f"see_image failed: {r.get('error')}"
        d = r.get("description", "")
        return (f"see_image ({r.get('model')}) saw {r.get('path')}: "
                f"{d[:160]}{'...' if len(d) > 160 else ''}")


# --------------------------------------------------------------------------
class ConfigTool(Tool):
    """Read or change S.A.R.A's live settings. Persists to config.json.

    Usage:
        config get
        config set <key> <value>
    Keys: provider, base_url, model, api_key, fallback_models,
          max_steps, verbose, no_research
    """
    name = "config"
    description = ("Read or change S.A.R.A's live settings (model, provider, "
                   "base_url, api_key, no_research/offline, max_steps, verbose). "
                   "Changes persist to config.json and apply on the next turn.")
    usage = ("config get | config set <key> <value>   "
             "e.g. config set model llama3.1:8b | "
             "config set provider openrouter | config set no_research true")

    ALLOWED = {"provider", "base_url", "model", "api_key", "fallback_models",
               "max_steps", "verbose", "no_research"}
    # Expanded provider presets (OpenAI-compatible base_url where one exists).
    # Aggregator/OAuth providers that need an API key + a chosen model are
    # listed by their canonical preset name; set base_url to the provider's
    # endpoint when you switch (or leave custom + set base_url manually).
    PROVIDERS = {
        "ollama": "http://127.0.0.1:11434/v1",
        "openai": "https://api.openai.com/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "localai": "http://127.0.0.1:8080/v1",
        "custom": "",
        # --- cloud / aggregator presets (need api_key; pick a model after) ---
        "nous": "https://portal.nousresearch.com/v1",
        "fireworks": "https://api.fireworks.ai/inference/v1",
        "novita": "https://api.novita.ai/v3/openai",
        "ollama-cloud": "https://api.ollama.com/v1",
        "deepinfra": "https://api.deepinfra.com/v1/openai",
        "deepseek": "https://api.deepseek.com/v1",
        "zai-glm": "https://open.bigmodel.cn/api/paas/v4",
        "kimi-moonshot": "https://api.moonshot.cn/v1",
        "stepfun": "https://api.stepfun.com/v1",
        "minimax": "https://api.minimax.io/v1",
        "arcee": "https://api.arcee.ai/v1",
        "gmi-cloud": "https://api.gmi-serving.com/v1",
        "kilo-code": "https://aider.kilocode.ai/v1",
        "opencode": "https://api.opencode.ai/v1",
        "alibaba-coding": "https://api.aliyun.com/v1",
        "tencent-tokenhub": "https://tokenhub.tencentmaas.com/v1",
        "nvidia-nim": "https://integrate.api.nvidia.com/v1",
        "huggingface": "https://router.huggingface.co/v1",
        "google-ai-studio": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "xai-grok": "https://api.x.ai/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "aws-bedrock": "https://bedrock-runtime.us-east-1.amazonaws.com",
        "azure-foundry": "https://YOUR-RESOURCE.openai.azure.com",
        "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "upstage": "https://api.upstage.ai/v1/solar",
        # --- named presets that need your key + chosen model (no fixed url) ---
        "mixture-of-agents": "",
        "lm-studio": "http://127.0.0.1:1234/v1",
        "github-copilot": "https://api.githubcopilot.com",
        "xiaomi-mimo": "https://api.mimo-model.com/v1",
        "vertex-ai": "https://aiplatform.googleapis.com/v1",
        "qwen-oauth": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    }

    # Friendly aliases for the menu labels the user pasted.
    PROVIDER_ALIASES = {
        "nous portal": "nous", "fireworks ai": "fireworks",
        "openrouter": "openrouter", "mixture of agents": "mixture-of-agents",
        "novitaai": "novita", "lm studio": "lm-studio",
        "anthropic": "anthropic", "openai": "openai", "qwen cloud": "qwen",
        "qwen dashscope": "qwen", "xai grok": "xai-grok",
        "xiaomi mimo": "xiaomi-mimo", "tencent tokenhub": "tencent-tokenhub",
        "nvidia nim": "nvidia-nim", "github copilot": "github-copilot",
        "hugging face": "huggingface", "google ai studio": "google-ai-studio",
        "google vertex ai": "vertex-ai", "deepseek": "deepseek",
        "z.ai / glm": "zai-glm", "kimi / moonshot": "kimi-moonshot",
        "stepfun step plan": "stepfun", "minimax": "minimax",
        "ollama cloud": "ollama-cloud", "arcee ai": "arcee",
        "gmi cloud": "gmi-cloud", "kilo code": "kilo-code",
        "opencode": "opencode", "aws bedrock": "aws-bedrock",
        "azure foundry": "azure-foundry", "alibaba coding": "alibaba-coding",
        "custom": "custom", "deepinfra": "deepinfra",
        "upstage": "upstage", "configure auxiliary models": "custom",
    }

    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else ROOT if (ROOT := Path(__file__).resolve().parent.parent) else Path.cwd()

    def _cfg_path(self) -> Path:
        return self.root / "config.json"

    def _load(self) -> dict:
        p = self._cfg_path()
        if p.exists():
            try:
                return json.loads(p.read_text())
            except json.JSONDecodeError:
                return {}
        return {}

    def _save(self, d: dict) -> None:
        self._cfg_path().write_text(json.dumps(d, indent=2))

    def run(self, arg: str) -> dict:
        # The agent emits "config get" / "config set ..." — strip our own name.
        arg = (arg or "").strip().strip("`\"'")
        if arg.lower().startswith("config"):
            arg = arg[len("config"):].strip()
        if not arg or arg.lower().startswith("get"):
            cfg = self._load()
            return {"ok": True, "mode": "get",
                    "config": cfg,
                    "provider_presets": list(self.PROVIDERS)}
        if arg.lower().startswith("providers"):
            # enumerate the available provider presets (the selection menu)
            return {"ok": True, "mode": "providers",
                    "providers": sorted(self.PROVIDERS.keys()),
                    "aliases": self.PROVIDER_ALIASES}

        if arg.lower().startswith("set"):
            rest = arg[3:].strip()
            # key may be split from value by first whitespace
            if " " not in rest:
                return {"ok": False,
                        "error": "usage: config set <key> <value>"}
            key, _, value = rest.partition(" ")
            key = key.strip().lower()
            value = value.strip().strip("`\"'")
            if key not in self.ALLOWED:
                return {"ok": False,
                        "error": f"unknown setting '{key}'. "
                                 f"allowed: {', '.join(sorted(self.ALLOWED))}"}
            cfg = self._load()
            # cast types
            if key in ("no_research", "verbose"):
                value = value.lower() in ("1", "true", "yes", "on")
            elif key == "max_steps":
                try:
                    value = int(value)
                except ValueError:
                    return {"ok": False, "error": "max_steps must be an integer"}
            elif key == "fallback_models":
                value = [v.strip() for v in value.split(",") if v.strip()]
            elif key == "provider":
                # resolve friendly alias (e.g. "nous portal") -> canonical
                canon = self.PROVIDER_ALIASES.get(value.strip().lower(), value)
                if canon not in self.PROVIDERS:
                    return {"ok": False,
                            "error": f"unknown provider '{value}'. "
                                     f"known: {', '.join(sorted(self.PROVIDERS))}"}
                value = canon
                # adopt the preset endpoint unless a custom base_url is set
                if value != "custom" and (cfg.get("base_url") in (None, "")
                                          or cfg.get("base_url")
                                          == self.PROVIDERS.get(cfg.get("provider"))):
                    cfg["base_url"] = self.PROVIDERS[value]
            cfg[key] = value
            self._save(cfg)
            return {"ok": True, "mode": "set", "key": key, "value": value,
                    "config": cfg}

        return {"ok": False,
                "error": "usage: config get | config set <key> <value>"}

    def summary(self, r: dict) -> str:
        if not r.get("ok"):
            return f"config error: {r.get('error')}"
        if r.get("mode") == "get":
            cfg = r.get("config", {})
            keys = ("provider", "base_url", "model", "no_research", "max_steps")
            shown = ", ".join(f"{k}={cfg.get(k)!r}" for k in keys if k in cfg)
            return f"config: {shown}"
        return f"config set {r.get('key')} = {r.get('value')!r}"


class ModelList(Tool):
    """List models available from the currently configured endpoint."""
    name = "list_models"
    description = ("List every model the current provider endpoint offers "
                  "(so you can pick one to switch to with `config set model "
                  "<name>`). Works for Ollama, OpenAI, OpenRouter, LocalAI, etc.")
    usage = "list_models"

    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else Path(__file__).resolve().parent.parent

    def run(self, arg: str) -> dict:
        cfg = ConfigTool(self.root)._load()
        base_url = (cfg.get("base_url") or "http://127.0.0.1:11434/v1").rstrip("/")
        api_key = cfg.get("api_key") or None
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        try:
            import requests
            r = requests.get(f"{base_url}/models", headers=headers, timeout=10)
        except Exception as e:                       # noqa: BLE001
            return {"ok": False,
                    "error": f"can't reach models endpoint at {base_url}: {e}"}
        if r.status_code != 200:
            return {"ok": False,
                    "error": f"endpoint returned HTTP {r.status_code}: "
                             f"{r.text[:160]}"}
        try:
            data = r.json()
        except ValueError:
            return {"ok": False, "error": "endpoint returned non-JSON"}
        # OpenAI-compatible shape: {"data": [{"id": "..."}, ...]}
        models = [m.get("id") or m.get("name") for m in data.get("data", [])]
        if not models and isinstance(data, list):
            models = [m.get("id") or m.get("name") for m in data]
        models = [m for m in models if m]
        return {"ok": True, "models": models,
                "current": cfg.get("model"),
                "base_url": base_url}


    def summary(self, r: dict) -> str:
        if not r.get("ok"):
            return f"list_models error: {r.get('error')}"
        cur = r.get("current")
        mods = r.get("models", [])
        head = f"{len(mods)} models @ {r.get('base_url')}"
        if not mods:
            return f"{head} — none reported"
        listed = ", ".join(f"[{m}]" if m == cur else m for m in mods[:25])
        return f"{head}: {listed}"


# --------------------------------------------------------------------------
class UpgradeTool(Tool):
    """Upgrade S.A.R.A's own agent code from a git repository.

    Usage:
        upgrade_code <repo_url> [branch]
        upgrade_code backup
        upgrade_code list
        upgrade_code rollback <backup-name>
    Backs up the current install, pulls the repo, copies in safe files
    (never overwriting config.json / credentials.json / her memory DB),
    then verifies (compile + restart + live smoke turn) and rolls back
    automatically if verification fails.
    """
    name = "upgrade_code"
    description = ("Upgrade S.A.R.A's OWN agent code from a git repo. Makes a "
                   "backup, pulls the new code, verifies it works, and rolls "
                   "back automatically if it breaks. Local config, secrets, "
                   "and her memory are always preserved.")
    usage = ("upgrade_code <git-repo-url> [branch]   "
             "e.g. upgrade_code https://github.com/you/SARA.git main | "
             "upgrade_code backup | upgrade_code list | "
             "upgrade_code rollback <backup-name>")

    def run(self, arg: str) -> dict:
        # The agent emits "upgrade_code list" / "upgrade_code <repo>" — strip
        # our own name so the subcommand parser sees just the subcommand.
        arg = (arg or "").strip().strip("`\"'")
        if arg.lower().startswith("upgrade_code"):
            arg = arg[len("upgrade_code"):].strip()
        from pathlib import Path as _P
        script = _P(__file__).resolve().parent.parent / "sara_upgrade.py"
        if not script.exists():
            return {"ok": False, "error": "sara_upgrade.py missing"}
        import subprocess
        if not arg or arg.startswith("backup"):
            cmd = [sys.executable, str(script), "backup"]
        elif arg.startswith("list"):
            cmd = [sys.executable, str(script), "list"]
        elif arg.startswith("rollback"):
            nm = arg[len("rollback"):].strip()
            cmd = [sys.executable, str(script), "rollback", nm]
        else:
            parts = arg.split()
            repo = parts[0]
            branch = parts[1] if len(parts) > 1 else "main"
            cmd = [sys.executable, str(script), "upgrade", repo, branch]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except Exception as e:                       # noqa: BLE001
            return {"ok": False, "error": f"upgrade run failed: {e}"}
        out = (r.stdout or "") + (r.stderr or "")
        ok = r.returncode == 0
        return {"ok": ok, "returncode": r.returncode, "output": out.strip()[-1500:]}

    def summary(self, r: dict) -> str:
        if not r.get("ok"):
            return f"upgrade failed: {r.get('error') or (r.get('output') or '')[:160]}"
        return (r.get("output") or "done").splitlines()[-1][:160]


# --------------------------------------------------------------------------
class ServerInventory(Tool):
    """Enumerate every web site / service / listening port on a remote host.

    One SSH connection runs a comprehensive read-only probe script (web-server
    binaries, listening ports, Apache vhosts + Alias/ProxyPass, nginx sites,
    docroots, standalone python services, broken paths) and returns a structured
    inventory. This is what "study all the sites on the server" needs — NOT a
    bare `uptime`. The fragile 3B model dodges this task with uptime on the
    wrong host, so there is a deterministic router (_route_server_inventory)
    that forces this tool on the right host.

    Arg forms (same friendly-host resolution as SSHRun):
      <alias>                       e.g. server_inventory website server
      <user>@<host> :: <command>   NOT used — arg is just the host
      <host>                       e.g. server_inventory 127.0.0.1
    Credentials come from ~/.config/systemd or the ssh block of credentials.json
    (sara_agent_key), falling back to SSHRun's creds.
    """

    HOST_ALIASES = SSHRun.HOST_ALIASES

    name = "server_inventory"
    description = (
        "Inventory every website, service, vhost, listening port and reverse "
        "proxy on a remote server over SSH. Use this when the user says 'study "
        "the sites on the server', 'list all the web apps', 'what's running on "
        "the web box', etc. Returns a structured report: web server, ports, "
        "Apache vhosts + Alias/ProxyPass, nginx sites, docroots, standalone "
        "python services, and any broken paths. Accepts friendly host names: "
        "'website server' = 127.0.0.1, 'database'/'home server' = 127.0.0.1.")
    usage = (
        "server_inventory <host>                       e.g. server_inventory website server\n"
        "    server_inventory 127.0.0.1\n"
        "    server_inventory root@127.0.0.1")

    PROBE = r'''
probe(){ echo "PROBE:$(curl -s -o /dev/null -m 6 -w '%{http_code}' -H "Host: ${HOSTNAME:-127.0.0.1}" "http://127.0.0.1$1" 2>/dev/null) ${1}"; }
echo "=== OS ==="; (cat /etc/os-release 2>/dev/null | grep -E '^(NAME|VERSION)=' | head -2)
echo "=== WEB SERVER BINS ==="; for b in apache2 apachectl nginx httpd caddy lighttpd; do command -v $b >/dev/null 2>&1 && echo "FOUND: $b ($($b -v 2>&1 | head -1) | hostname=$(hostname))"; done
echo "=== LISTENING PORTS (web-ish) ==="; (ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null) | grep -E ':(80|443|8080|8000|3000|5000|9000|8443|8888)'
echo "=== APACHE sites-enabled ==="; ls -1 /etc/apache2/sites-enabled/ 2>/dev/null; ls -1 /etc/nginx/sites-enabled/ 2>/dev/null
echo "=== APACHE vhost defs ==="; grep -rEni 'DocumentRoot|ServerName|ServerAlias|Alias|VirtualHost|ProxyPass|ProxyPassReverse|Redirect|SSLEngine|Listen' /etc/apache2/sites-enabled/ /etc/apache2/conf-enabled/ 2>/dev/null
echo "=== NGINX vhost defs ==="; grep -rEni 'server_name|root|listen|location|proxy_pass' /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ 2>/dev/null | head -60
echo "=== /var/www tree ==="; ls -la /var/www/ 2>/dev/null; echo "--html--"; ls -la /var/www/html/ 2>/dev/null
echo "=== STANDALONE SERVICES (python/node) ==="; for p in $(pgrep -f 'python|node|uvicorn|gunicorn' 2>/dev/null); do echo "PID $p: $(tr "\0" " " < /proc/$p/cmdline 2>/dev/null)"; done
echo "=== DOCKER ==="; docker ps --format '{{.Names}} | {{.Image}} | {{.Ports}}' 2>/dev/null
echo "=== PROBE PATHS ==="; export HOSTNAME; for p in / /work/ /books/ /mtg/ /mtg_legacy/ /minecraft/ /test/ /p/ /vids/; do probe "$p"; done
'''

    @staticmethod
    def _resolve_host(host):
        if not host:
            return host
        return ServerInventory.HOST_ALIASES.get(host.strip().lower(), host)

    def __init__(self):
        self._cfg = SSHRun._load_creds()
        # Fall back to sara_agent_key if the ssh block has no explicit key.
        self._cfg.setdefault("key_path", "~/.ssh/sara_agent_key")

    def run(self, arg: str) -> dict:
        arg = (arg or "").strip().strip("`\"'")
        if not arg:
            return {"ok": False, "error": "need a host — e.g. server_inventory website server"}
        # Forms: "website server" / "127.0.0.1" / "user@host"
        user = self._cfg.get("user")
        host = arg
        m = re.match(r"^([\w.-]+)@(.+)$", arg)
        if m:
            user, host = m.group(1), m.group(2)
        host = self._resolve_host(host)
        key = os.path.expanduser(self._cfg.get("key_path", "~/.ssh/sara_agent_key"))
        try:
            import paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            kwargs = {"hostname": host,
                      "port": int(self._cfg.get("port", 22)),
                      "username": user, "timeout": 30,
                      "look_for_keys": False, "allow_agent": False}
            if os.path.exists(key):
                kwargs["key_filename"] = key
            else:
                pw = self._cfg.get("password")
                if not pw:
                    return {"ok": False,
                            "error": "no SSH key and no password in creds"}
                kwargs["password"] = pw
            client.connect(**kwargs)
        except Exception as e:
            return {"ok": False, "error": f"ssh connect to {user}@{host} failed: {e}"}
        try:
            stdin, stdout, stderr = client.exec_command(
                "bash -s", timeout=120)
            stdin.write(self.PROBE)
            stdin.close()
            out = stdout.read().decode(errors="replace")
            err = stderr.read().decode(errors="replace")
            rc = stdout.channel.recv_exit_status()
            return {"ok": True, "host": f"{user}@{host}", "exit_code": rc,
                    "stdout": out, "stderr": err[:800], "error": None}
        except Exception as e:
            return {"ok": False, "error": f"ssh exec failed: {e}"}
        finally:
            client.close()

    def summary(self, r: dict) -> str:
        if not r.get("ok"):
            return f"inventory failed: {r.get('error')}"
        lines = (r.get("stdout") or "").strip().splitlines()
        return f"inventory of {r.get('host')}: {len(lines)} lines collected"


def build_registry(confirm=None) -> dict:
    tools = [ListDir(), FindPath(), ReadFile(), WriteFile(), AppendFile(),
             PatchFile(), EditSoul(),
             Shell(confirm=confirm), WebSearch(), WebFetch(),
             ScrapeCategories(), ScrapeJS(), WebBrowse(),
             MariaDB(), SSHRun(), WinRun(), DBImport(), SeeImage(),
             ConfigTool(), ModelList(), UpgradeTool(), Rewrite(),
             ServerInventory(), SendFile(),]
    return {t.name: t for t in tools}


def tool_help(registry: dict) -> str:
    return "\n".join(f"- {t.name}: {t.description}\n    usage: {t.usage}"
                     for t in registry.values())
