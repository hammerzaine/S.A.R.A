"""Tools — everything S.A.R.A can actually DO.

Contract for every tool:
  * a `run(arg: str) -> dict` method — ONE uniform entrypoint, no exceptions.
  * returns a dict with at minimum {"ok": bool}
  * a `summary(result)` giving a one-line human description for the console.

The uniform `run()` contract is deliberate: the v2/v3 builds dispatched some
tools via `.run()` and others via `.list()`/`.read()`/`.search()`, so any tool
whose entrypoint wasn't named `run` silently returned None and the model saw
"(no output)". One signature, no special cases.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

HOME = Path.home()

# Directories that are enormous and never interesting to a name search.
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
                    "size": p.stat().st_size, "note": "that's a file"}
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
            pat, where = pat.split(" in ", 1)
            root = Path(where.strip().strip("`\"'")).expanduser()
        if not root.exists():
            return {"ok": False, "error": f"{root} does not exist"}
        hits = []
        for dirpath, dirnames, filenames in _walk(root):
            dirnames[:] = [d for d in dirnames if d not in PRUNE]
            for name in filenames + dirnames:
                if pat in name.lower():
                    hits.append(str(Path(dirpath) / name))
                    if len(hits) >= 30:
                        return {"ok": True, "matches": hits,
                                "count": "30+"}
        return {"ok": True, "matches": hits, "count": len(hits)}

    def summary(self, r):
        if not r.get("ok"):
            return r.get("error", "failed")
        return f"{r['count']} match(es): " + ", ".join(r["matches"][:8])


def _walk(root: Path):
    import os
    for dp, dn, fn in os.walk(root):
        yield dp, dn, fn


class ReadFile(Tool):
    name = "read_file"
    description = "Read a text file (optionally a range of lines)."
    usage = "read_file <path> [offset] [limit]   e.g. read_file ~/x.txt 1 50"

    def run(self, arg: str) -> dict:
        arg = (arg or "").strip().strip("`\"'")
        toks = arg.split()
        if not toks:
            return {"ok": False, "error": "need a path"}
        p = Path(toks[0]).expanduser()
        offset, limit = 1, 500
        if len(toks) > 1:
            try:
                offset = int(toks[1])
            except ValueError:
                pass
        if len(toks) > 2:
            try:
                limit = int(toks[2])
            except ValueError:
                pass
        if not p.exists():
            return {"ok": False, "error": f"{p} does not exist"}
        try:
            lines = p.read_text(errors="replace").splitlines()
        except OSError as e:
            return {"ok": False, "error": str(e)}
        chunk = lines[offset - 1: offset - 1 + limit]
        return {"ok": True, "path": str(p), "total_lines": len(lines),
                "offset": offset, "shown": len(chunk),
                "content": "\n".join(chunk)}

    def summary(self, r):
        if not r.get("ok"):
            return r.get("error", "failed")
        return f"{r['shown']} of {r['total_lines']} lines from {r['path']}"


class WriteFile(Tool):
    name = "write_file"
    description = "Write a file. First line is the path, the rest is content."
    usage = "write_file <path>\n<content>"

    def run(self, arg: str) -> dict:
        cleaned = (arg or "").strip()
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
    description = "Append text to the END of a file (or create it)."
    usage = "append_file <path>\n<content to add>"

    def run(self, arg: str) -> dict:
        cleaned = (arg or "").strip()
        if "\n" not in cleaned and "\\n" in cleaned:
            cleaned = cleaned.replace("\\n", "\n", 1)
        if "\n" not in cleaned:
            return {"ok": False, "error": "need a path line then content"}
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
        return {"ok": True, "path": str(p), "bytes": len(content),
                "size": p.stat().st_size}

    def summary(self, r):
        return (f"appended {r['bytes']} bytes to {r['path']} "
                f"(now {r['size']} bytes)"
                if r.get("ok") else r.get("error"))


class PatchFile(Tool):
    name = "patch_file"
    description = "Edit a file IN PLACE with find-and-replace."
    usage = ("patch_file <path> [replace_all]\n<<<OLD>>>\n<old>\n"
             "<<<NEW>>>\n<new>\n<<<END>>>")

    def run(self, arg: str) -> dict:
        import re as _re
        cleaned = (arg or "").strip()
        if "\n" not in cleaned and "\\n" in cleaned:
            cleaned = cleaned.replace("\\n", "\n", 1)
        m = _re.search(r"<<<\s*OLD\s*>>>", cleaned)
        if not m:
            return {"ok": False, "error": "need path line + <<<OLD>>> block"}
        head = cleaned[:m.start()].strip().strip("`\"'")
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
            return {"ok": False, "error": "OLD text not found verbatim"}
        count = text.count(old) if replace_all else 1
        text = text.replace(old, new, -1 if replace_all else 1)
        try:
            p.write_text(text)
        except OSError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "path": str(p), "replacements": count}

    def summary(self, r):
        return (f"patched {r['replacements']} spot(s) in {r['path']}"
                if r.get("ok") else r.get("error"))


class Shell(Tool):
    name = "shell"
    description = "Run a shell command and return its output."
    usage = "shell <command>            e.g. shell df -h"

    DANGER = ()

    def run(self, arg: str) -> dict:
        cmd = (arg or "").strip()
        for q in ('"', "'", "`"):
            if cmd.startswith(q) and cmd.endswith(q) and len(cmd) > 1:
                inner = cmd[1:-1]
                if q != "`" and (q in inner):
                    break
                cmd = inner
                break
        cmd = cmd.strip()
        if not cmd:
            return {"ok": False, "error": "empty command"}
        cmd = self._harden_ssh(cmd)
        try:
            r = subprocess.run(cmd, shell=True, cwd=str(HOME),
                               capture_output=True, text=True, timeout=120,
                               stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "timed out after 120s"}
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        return {"ok": r.returncode == 0, "exit_code": r.returncode,
                "stdout": out[:4000], "stderr": err[:1000],
                "error": err[:300] if r.returncode else None}

    _SSH_BINS = ("ssh ", "scp ", "sftp ", "rsync ")

    @staticmethod
    def _harden_ssh(cmd: str) -> str:
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
            if "-e " in cmd:
                return cmd
            return cmd.replace("rsync ", f"rsync -e 'ssh {flags}' ", 1)
        return stripped.replace(bin_name, f"{bin_name} {flags}", 1)

    def summary(self, r):
        if r.get("ok"):
            n = len((r.get("stdout") or "").splitlines())
            return f"exit 0, {n} lines of output"
        return f"exit {r.get('exit_code', '?')}: {r.get('error') or 'failed'}"


# -------------------------------------------------------------------------
# Web tools — built on requests + beautifulsoup4 (no headless browser needed).
# Adult-site scraping is permitted; only unambiguously illegal material is
# refused (hard-coded blocklist, deliberately narrow).
# -------------------------------------------------------------------------
ILLEGAL_BLOCK = ("child", "lolita", "preteen", "underage", "cp ")


class WebSearch(Tool):
    name = "web_search"
    description = "Search the web for a query and return result snippets."
    usage = "web_search <query>       e.g. web_search best python http server"

    def run(self, arg: str) -> dict:
        from ddgs import DDGS
        q = (arg or "").strip().strip("`\"'")
        if not q:
            return {"ok": False, "error": "need a search query"}
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(q, max_results=8))
        except Exception as e:
            return {"ok": False, "error": f"search failed: {e}"}
        if not results:
            return {"ok": False, "error": "no results"}
        return {"ok": True, "query": q, "results": [
            {"title": r.get("title", ""), "href": r.get("href", ""),
             "body": (r.get("body") or "")[:400]} for r in results]}

    def summary(self, r):
        if not r.get("ok"):
            return r.get("error", "failed")
        return f"{len(r['results'])} results for '{r['query']}'"


class WebFetch(Tool):
    name = "web_fetch"
    description = "Fetch a web page and return its readable text."
    usage = "web_fetch <url>           e.g. web_fetch https://example.com"

    def run(self, arg: str) -> dict:
        import requests as _r
        from bs4 import BeautifulSoup
        url = (arg or "").strip().strip("`\"'")
        if not url or not url.startswith("http"):
            return {"ok": False, "error": "need an http(s) URL"}
        try:
            resp = _r.get(url, timeout=30, headers={
                "User-Agent": "Mozilla/5.0 (compatible; SARA/4.0)"})
            resp.raise_for_status()
        except Exception as e:
            return {"ok": False, "error": f"fetch failed: {e}"}
        soup = BeautifulSoup(resp.text, "html.parser")
        for t in soup(["script", "style", "noscript"]):
            t.decompose()
        text = "\n".join(l.strip() for l in soup.get_text("\n").splitlines()
                         if l.strip())
        title = soup.title.get_text(strip=True) if soup.title else ""
        return {"ok": True, "url": url, "title": title,
                "text": text[:4000], "length": len(text)}

    def summary(self, r):
        if not r.get("ok"):
            return r.get("error", "failed")
        return f"fetched {r['url']} — {r['length']} chars of text"


class ScrapeCategories(Tool):
    name = "scrape_categories"
    description = "Extract category/topic links from a web page (menu, nav)."
    usage = "scrape_categories <url>   e.g. scrape_categories https://site.com"

    def run(self, arg: str) -> dict:
        import requests as _r
        from bs4 import BeautifulSoup
        url = (arg or "").strip().strip("`\"'")
        if not url or not url.startswith("http"):
            return {"ok": False, "error": "need an http(s) URL"}
        # unambiguous-illegal guard (narrow, as requested)
        if any(b in url.lower() for b in ILLEGAL_BLOCK):
            return {"ok": False,
                    "error": "refused — that content is unambiguously illegal"}
        try:
            resp = _r.get(url, timeout=30, headers={
                "User-Agent": "Mozilla/5.0 (compatible; SARA/4.0)"})
            resp.raise_for_status()
        except Exception as e:
            return {"ok": False, "error": f"fetch failed: {e}"}
        soup = BeautifulSoup(resp.text, "html.parser")
        cats = []
        seen = set()
        for a in soup.find_all("a", href=True):
            label = a.get_text(strip=True)
            href = a["href"]
            if not label or len(label) > 60:
                continue
            if href.startswith("#") or href.startswith("javascript:"):
                continue
            low = label.lower()
            if any(k in low for k in ("category", "cat", "topic", "channel",
                                      "genre", "/c/", "/cat")):
                key = (label, href)
                if key not in seen:
                    seen.add(key)
                    cats.append({"label": label, "href": href})
            if len(cats) >= 40:
                break
        return {"ok": True, "url": url, "categories": cats,
                "count": len(cats)}

    def summary(self, r):
        if not r.get("ok"):
            return r.get("error", "failed")
        return f"{r['count']} categories on {r['url']}"


class ScrapeJS(Tool):
    name = "scrape_js"
    description = ("Extract visible text or links from a page (JS-rendered "
                  "content included when available).")
    usage = "scrape_js <url> [categories|text]"

    def run(self, arg: str) -> dict:
        import re as _re
        from bs4 import BeautifulSoup
        import requests as _r
        arg = (arg or "").strip().strip("`\"'")
        mode = "text"
        m = _re.match(r"^(.*?)\s+(categories|text)\s*$", arg, _re.I)
        if m:
            url = m.group(1)
            mode = m.group(2).lower()
        else:
            url = arg
        if not url or not url.startswith("http"):
            return {"ok": False, "error": "need an http(s) URL"}
        if any(b in url.lower() for b in ILLEGAL_BLOCK):
            return {"ok": False,
                    "error": "refused — that content is unambiguously illegal"}
        try:
            resp = _r.get(url, timeout=30, headers={
                "User-Agent": "Mozilla/5.0 (compatible; SARA/4.0)"})
            resp.raise_for_status()
        except Exception as e:
            return {"ok": False, "error": f"fetch failed: {e}"}
        soup = BeautifulSoup(resp.text, "html.parser")
        for t in soup(["script", "style", "noscript"]):
            t.decompose()
        if mode == "categories":
            cats = []
            seen = set()
            for a in soup.find_all("a", href=True):
                label = a.get_text(strip=True)
                href = a["href"]
                if not label or len(label) > 60:
                    continue
                key = (label, href)
                if key not in seen:
                    seen.add(key)
                    cats.append({"label": label, "href": href})
                if len(cats) >= 60:
                    break
            return {"ok": True, "url": url, "categories": cats,
                    "count": len(cats)}
        text = "\n".join(l.strip() for l in soup.get_text("\n").splitlines()
                         if l.strip())
        return {"ok": True, "url": url, "text": text[:6000],
                "length": len(text)}

    def summary(self, r):
        if not r.get("ok"):
            return r.get("error", "failed")
        if "categories" in r:
            return f"{r['count']} links on {r['url']}"
        return f"extracted {r['length']} chars from {r['url']}"


class Remember(Tool):
    name = "remember"
    description = "Save a durable fact about the user or their systems."
    usage = "remember <fact>           e.g. remember the DB lives at 192.168.2.140"

    def run(self, arg: str) -> dict:
        fact = (arg or "").strip().strip("`\"'")
        if not fact:
            return {"ok": False, "error": "nothing to remember"}
        # Wired up at registration time (see build_registry).
        if self._memory is None:
            return {"ok": False, "error": "memory not attached"}
        ok = self._memory.remember(fact)
        return {"ok": True, "stored": ok, "fact": fact}

    def summary(self, r):
        if not r.get("ok"):
            return r.get("error", "failed")
        return "remembered" if r.get("stored") else "already known"

    _memory = None  # set by build_registry


# -------------------------------------------------------------------------
def build_registry(memory=None) -> dict:
    """Construct the tool registry. The prompt is generated from this, so a
    registered tool is ALWAYS visible to the model (v2/v3 drift bug avoided)."""
    tools = [
        ListDir(), FindPath(), ReadFile(), WriteFile(), AppendFile(),
        PatchFile(), Shell(), WebSearch(), WebFetch(), ScrapeCategories(),
        ScrapeJS(), Remember(),
    ]
    if memory is not None:
        Remember._memory = memory
    return {t.name: t for t in tools}


def tool_help(registry: dict) -> str:
    """Render the tool catalogue for injection into the system prompt."""
    lines = []
    for name in sorted(registry):
        t = registry[name]
        lines.append(f"- {name}: {t.description}")
        if t.usage:
            lines.append(f"    usage: {t.usage}")
    return "\n".join(lines)
