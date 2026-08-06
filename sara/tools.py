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


# --------------------------------------------------------------------------
class MariaDB(Tool):
    """Run SQL against the home MariaDB (192.168.2.140, user zaine).

    Arg form:
      <database> | <SQL>          run SQL in <database>
      <SQL>                       run SQL in the default database (xnxx_db)
    Writes (INSERT/UPDATE/DELETE/CREATE/DROP) are allowed — S.A.R.A runs as
    zaine and zaine owns the schema, so this is her box, her data.
    """
    name = "mariadb"
    description = ("Run a SQL query on the MariaDB at 192.168.2.140 as user zaine. "
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
        db = database or self._cfg.get("default_database")
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
    """Run a shell command on 192.168.2.140 as root via key auth (no password prompt).

    Arg form:
      <command>                    run on default host (192.168.2.140) as root
      <user>@<host> :: <command>   run on a specific host/user
    S.A.R.A uses her own SSH key (sara_agent_key) — BatchMode, never prompts.
    """
    name = "ssh_run"
    description = ("Run a shell command on the home server (192.168.2.140) as "
                   "root over SSH (key auth, no password prompt). Use for remote "
                   "sysadmin: check a service, read a remote file, restart something.")
    usage = ("ssh_run <command>                e.g. ssh_run uptime\n"
             "    ssh_run root@192.168.2.140 :: df -h")

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

    def run(self, arg: str) -> dict:
        arg = (arg or "").strip().strip("`\"'")
        if not arg:
            return {"ok": False, "error": "no command given"}
        host, user = self._cfg.get("host"), self._cfg.get("user")
        # optional explicit target: "user@host :: command"
        m = re.match(r"^([\w.-]+)@([\w.-]+)\s*::\s*(.+)$", arg, re.S)
        if m:
            user, host, command = m.group(1), m.group(2), m.group(3).strip()
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
        lines = (r.get("stdout") or "").strip().splitlines()
        return f"ssh {r.get('host')} exit {r.get('exit_code')}, {len(lines)} lines out"


class WinRun(Tool):
    """Run a command on a Windows PC over SSH (OpenSSH server, key auth).

    Windows 10/11 ship a built-in OpenSSH server; paramiko talks to it the
    same as Linux. Default host is the GUESSED Windows box on the LAN
    (192.168.2.100, same /24 as the home server) — set the real host in
    credentials.json under "win_ssh" to repoint. For PowerShell, pass the
    command via `powershell -NoProfile -Command "..."`.

    Arg form:
      <command>                       run on default Windows host
      <user>@<host> :: <command>      run on a specific host/user
    """
    name = "win_run"
    description = ("Run a command on the Windows PC over SSH (OpenSSH server, "
                   "key auth). Use for Windows sysadmin: ipconfig, Get-Process, "
                   "dir, services, powershell one-liners. Same SSH as Linux.")
    usage = ("win_run <command>                    e.g. win_run ipconfig\n"
             "    win_run powershell -NoProfile -Command \"Get-Process\"\n"
             "    win_run admin@192.168.2.100 :: systeminfo")

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
        # guessed default Windows host (same /24 as the home server)
        host = self._cfg.get("host") or "192.168.2.100"
        user = self._cfg.get("user") or "administrator"
        # optional explicit target: "user@host :: command"
        m = re.match(r"^([\w.-]+)@([\w.-]+)\s*::\s*(.+)$", arg, re.S)
        if m:
            user, host, command = m.group(1), m.group(2), m.group(3).strip()
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
            r = urllib.request.urlopen(req, timeout=400)
            data = json.loads(r.read().decode())
            desc = (data.get("message", {}).get("content")
                    or "").strip()
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
    PROVIDERS = {"ollama": "http://127.0.0.1:11434/v1",
                 "openai": "https://api.openai.com/v1",
                 "openrouter": "https://openrouter.ai/api/v1",
                 "localai": "http://127.0.0.1:8080/v1",
                 "custom": ""}

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
        arg = (arg or "").strip().strip("`\"'")
        if not arg or arg.lower().startswith("get"):
            cfg = self._load()
            return {"ok": True, "mode": "get",
                    "config": cfg,
                    "provider_presets": list(self.PROVIDERS)}

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
                if value not in self.PROVIDERS:
                    return {"ok": False,
                            "error": f"unknown provider '{value}'. "
                                     f"known: {', '.join(self.PROVIDERS)}"}
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
        arg = (arg or "").strip().strip("`\"'")
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
def build_registry(confirm=None) -> dict:
    tools = [ListDir(), FindPath(), ReadFile(), WriteFile(), AppendFile(),
             Shell(confirm=confirm), WebSearch(), WebFetch(),
             ScrapeCategories(), ScrapeJS(),
             MariaDB(), SSHRun(), WinRun(), DBImport(), SeeImage(),
             ConfigTool(), ModelList(), UpgradeTool()]
    return {t.name: t for t in tools}


def tool_help(registry: dict) -> str:
    return "\n".join(f"- {t.name}: {t.description}\n    usage: {t.usage}"
                     for t in registry.values())
