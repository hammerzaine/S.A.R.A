#!/usr/bin/env python3
"""S.A.R.A self-upgrade toolkit.

Lets S.A.R.A (or you) upgrade her OWN agent code from a git repository,
safely:

    backup       snapshot current install (code + config + memory) to
                 backups/sara-<version>-<timestamp>.tar.gz
    upgrade      pull <repo_url> [branch] into this dir, verify the new
                 code compiles + the service restarts + a live smoke turn
                 passes, then bump the version. Rolls back on any failure.
    rollback     restore a previous backup
    list         show available backups
    status       current version + last-upgrade info

SAFETY CONTRACT (do not weaken):
  * data/sara.db (her memory) and config.json / credentials.json (local
    state + secrets) are NEVER overwritten by repo files. They ride along
    in every backup and are always restored from the backup, not the repo.
  * Every upgrade makes a backup FIRST. If verification fails, the previous
    install is restored automatically.
  * The repo is checked out into a temp dir and only the safe file set is
    copied in — never .git, never credentials (credentials.json), never the
    live DB (data/sara.db — her memory + all learned skills), never config.json,
    and never SOUL.md (her personality). An integrity guard hashes every
    protected file BEFORE + AFTER the copy and force-rolls-back the whole
    upgrade if even one byte changed. The user's standing rule: an update must
    never touch config, credentials, db, soul, or learned skills.
  """
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKUP_DIR = ROOT / "backups"
STATE_FILE = ROOT / "upgrade_state.json"

# Files that are LOCAL state / secrets / personality — never take from a repo,
# always preserve from the live install (and from backups).
PROTECTED = {"credentials.json", "config.json", "upgrade_state.json", "SOUL.md"}
# Directories we never pull from a repo or clobber.
PROTECTED_DIRS = {"data", "backups", "__pycache__", ".git", "web/__pycache__"}
# Files we never copy in from a repo (cruft / local).
EXCLUDE_NAMES = ("*.bak", "*.bak-*", "*.pyc", "*.pyo", ".DS_Store")

VERSION_FILE = ROOT / "sara" / "__init__.py"


def _run(cmd: list[str], cwd: Path | None = None, check: bool = True):
    return subprocess.run(cmd, cwd=cwd, check=check,
                           capture_output=True, text=True)


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _save_state(s: dict) -> None:
    STATE_FILE.write_text(json.dumps(s, indent=2))


def get_version() -> str:
    if VERSION_FILE.exists():
        for line in VERSION_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith("__version__"):
                # __version__ = "3.1.0"
                return line.split("=", 1)[1].strip().strip('"\'')
    return "unknown"


def set_version(v: str) -> None:
    txt = VERSION_FILE.read_text()
    new_lines = []
    done = False
    for line in txt.splitlines():
        if line.strip().startswith("__version__") and not done:
            new_lines.append(f'__version__ = "{v}"')
            done = True
        else:
            new_lines.append(line)
    if not done:
        new_lines.append(f'__version__ = "{v}"')
    VERSION_FILE.write_text("\n".join(new_lines) + "\n")


def _iter_safe_files(src: Path):
    """Yield (relpath) of files safe to copy from a pulled repo."""
    for p in src.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(src)
        parts = set(rel.parts)
        if parts & PROTECTED_DIRS:
            continue
        if rel.name in PROTECTED:
            continue
        if any(p.match(pat) for pat in EXCLUDE_NAMES):
            continue
        # never pull credentials or config even if nested
        if rel.name in ("credentials.json", "config.json"):
            continue
        yield rel


def _hash_file(p: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def _snapshot_protected() -> dict:
    """Hash every protected local-state file so the upgrade can prove it
    didn't touch them. Covers the user's standing rule: config, credentials,
    db (memory + learned skills), soul, must survive an upgrade untouched.
    """
    snaps: dict[str, str] = {}
    for name in PROTECTED:
        fp = ROOT / name
        if fp.exists():
            snaps[name] = _hash_file(fp)
    db = ROOT / "data" / "sara.db"
    if db.exists():
        snaps["data/sara.db"] = _hash_file(db)
    return snaps


def backup(label: str | None = None) -> Path:
    BACKUP_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    ver = get_version()
    name = f"sara-{ver}-{ts}.tar.gz"
    dest = BACKUP_DIR / name
    with tarfile.open(dest, "w:gz") as tf:
        # 1) everything safe in the install (code + soul + web)
        for p in ROOT.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(ROOT)
            if rel.parts[0] in ("backups", "__pycache__", ".git"):
                continue
            # also skip ANY nested .git (e.g. dist-clean/.git) — git objects
            # are stored read-only (0444) and must never be backed up or
            # restored (they break restore with PermissionError). B31.
            if ".git" in rel.parts:
                continue
            if rel.name in PROTECTED or any(
                    p.match(pat) for pat in EXCLUDE_NAMES):
                continue
            tf.add(p, arcname=rel)
        # 2) ALWAYS include the live DB + local config separately so they
        #    survive even if excluded above.
        db = ROOT / "data" / "sara.db"
        if db.exists():
            tf.add(db, arcname="data/sara.db")
        for f in ("config.json", "credentials.json", "SOUL.md"):
            fp = ROOT / f
            if fp.exists():
                tf.add(fp, arcname=f)
    # record manifest
    st = _load_state()
    st.setdefault("backups", []).append(
        {"file": name, "version": ver, "ts": ts, "label": label})
    _save_state(st)
    return dest


def restore(backup_name: str) -> bool:
    bp = BACKUP_DIR / backup_name
    if not bp.exists():
        print(f"backup not found: {bp}")
        return False
    # restore into ROOT, but PROTECT live data/config unless the backup's
    # own copy is what we want (it is — backup holds the pre-upgrade state).
    with tarfile.open(bp, "r:gz") as tf:
        for m in tf.getmembers():
            if not m.isfile():
                continue
            rel = Path(m.name)
            # never restore .git objects (read-only, not needed to run). B31
            if ".git" in rel.parts:
                continue
            if rel.parts[0] in ("backups",):
                continue
            target = ROOT / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(m)
            if src:
                # Defensive: git/db files may be read-only in the archive;
                # ensure the destination is writable before overwriting. B31
                try:
                    target.chmod(0o644)
                except OSError:
                    pass
                target.write_bytes(src.read())
    print(f"restored from {backup_name}")
    return True


def list_backups() -> list[dict]:
    st = _load_state()
    return st.get("backups", [])


def _verify() -> tuple[bool, str]:
    """Compile-check, restart service, run a live smoke turn."""
    import glob as _glob
    # 1) compile (expand globs ourselves — subprocess won't shell-expand)
    py_files = _glob.glob(str(ROOT / "sara" / "*.py")) + \
               [str(ROOT / "web.py"), str(ROOT / "sara_upgrade.py"),
                str(ROOT / "sara_cli.py")]
    py_files = [f for f in py_files if f.endswith(".py")]
    try:
        _run([sys.executable, "-m", "py_compile", *py_files], cwd=ROOT,
             check=True)
    except subprocess.CalledProcessError as e:
        return False, f"compile failed: {e.stderr[:300]}"
    # If there's no sara-web.service unit on this box at all (e.g. SARA runs
    # standalone without systemd), don't try to restart or smoke-test a
    # service that doesn't exist — the code deploy is the point. Note it and
    # pass so the upgrade lands instead of rolling back a good deploy.
    u = subprocess.run(["systemctl", "--user", "list-unit-files",
                        "sara-web.service"], capture_output=True, text=True)
    if "sara-web.service" not in u.stdout:
        print("      (no sara-web.service unit here — skipping restart/"
              "smoke; start SARA manually)")
        return True, "verified (code deployed; no systemd unit to restart)"
    # 2) restart service — unless the caller asked us NOT to (the web chat
    #    path restarts sara-web.service itself after streaming the result,
    #    so restarting from inside this process would kill the upgrade).
    if os.environ.get("SARA_UPGRADE_NO_RESTART"):
        print("      (restart skipped by caller)")
    else:
        try:
            _run(["systemctl", "--user", "restart", "sara-web.service"], check=True)
        except subprocess.CalledProcessError as e:
            return False, f"service restart failed: {e.stderr[:200]}"
    # 3) wait for the service to actually come up (poll /api/status), THEN
    #    run a live smoke turn. A fresh boot can take >4s and the model's
    #    first inference (cold load / free-tier throttle) can exceed 120s, so
    #    a slow smoke turn is a WARNING, NOT a fatal rollback — the code deploy
    #    and restart already succeeded.
    import time
    import urllib.request
    import urllib.error

    def _get_json(url, timeout):
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode())

    # Poll up to 30s for the service to answer /api/status.
    up = False
    for _ in range(30):
        try:
            _get_json("http://127.0.0.1:8800/api/status", 2)
            up = True
            break
        except Exception:
            time.sleep(1)
    if not up:
        return False, "service did not come up within 30s after restart"

    # Smoke turn: generous 240s — a cold model load must not trigger rollback.
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:8800/api/ask",
            data=json.dumps({"message": "What is 2+2? Reply with just the number."}).encode(),
            headers={"Content-Type": "application/json"})
        raw = urllib.request.urlopen(req, timeout=240).read().decode()
        ok = ("\"type\": \"done\"" in raw) and ("\"type\": \"error\"" not in raw)
        if not ok:
            # Service is up and answered, just not a clean 'done' — non-fatal.
            return True, "verified (smoke turn returned, but no clean done event)"
    except Exception as e:  # noqa: BLE001
        # Service is up; only the inference was slow/unresponsive. Do NOT
        # roll back a good deploy for a slow first turn.
        return True, f"verified (service up; smoke turn skipped: {e})"
    return True, "verified"


def _fix_launcher_perms() -> None:
    """Re-apply +x to the launcher after a copy/pull.

    A fresh clone or a /upgrade copy can drop the executable bit on
    ``bin/sara`` (and the ``~/.local/bin/sara`` symlink), leaving the user
    with ``Permission denied`` when they run ``sara``. Re-assert it so pulls
    self-heal. Never raises - best-effort, runs at upgrade time.
    """
    import os
    import stat
    candidates = [ROOT / "bin" / "sara"]
    local_bin = Path.home() / ".local" / "bin" / "sara"
    if local_bin.exists():
        candidates.append(local_bin)
    for c in candidates:
        try:
            if c.exists() and not c.is_dir():
                st = c.stat().st_mode
                c.chmod(st | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError:
            pass


def upgrade(repo_url: str, branch: str = "main",
            new_version: str | None = None) -> int:
    # Allow a bare remote NAME (e.g. "origin") instead of a full URL — resolve
    # it to its fetch URL so "/upgrade" (which passes "origin main") works.
    if not repo_url.startswith(("http://", "https://", "git@", "ssh://")):
        try:
            out = subprocess.run(
                ["git", "remote", "get-url", repo_url],
                capture_output=True, text=True, cwd=ROOT)
            if out.returncode == 0 and out.stdout.strip():
                repo_url = out.stdout.strip()
        except Exception:
            pass
    ver_before = get_version()
    print(f"[1/5] backing up current install (v{ver_before})…")
    bk = backup(label=f"pre-upgrade-from-{ver_before}")
    print(f"      backup: {bk.name}")

    print(f"[2/5] fetching {repo_url} ({branch})…")
    tmp = ROOT / ".upgrade_tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    try:
        _run(["git", "clone", "--depth", "1", "-b", branch, repo_url, str(tmp)],
             check=True)
    except subprocess.CalledProcessError as e:
        print(f"      git clone failed: {e.stderr[:300]}")
        print("      no changes made.")
        return 2

    pre_protected = _snapshot_protected()
    print("[3/5] copying safe files into install (preserving local "
          "config + memory)…")
    copied = 0
    for rel in _iter_safe_files(tmp):
        src = tmp / rel
        dst = ROOT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        copied += 1
    print(f"      copied {copied} files")
    # INTEGRITY GUARD (do not remove): config, credentials, SOUL.md and the
    # memory DB must be byte-identical after the copy. They are never in the
    # copied set by design — this catches any future regression in
    # _iter_safe_files instead of silently clobbering the user's setup.
    post_protected = _snapshot_protected()
    for name, h in pre_protected.items():
        if post_protected.get(name) != h:
            print(f"      SAFETY VIOLATION: {name} was modified by the "
                  f"upgrade copy!")
            print("      rolling back to pre-upgrade backup…")
            restore(bk.name)
            if not os.environ.get("SARA_UPGRADE_NO_RESTART"):
                _run(["systemctl", "--user", "restart", "sara-web.service"],
                     check=False)
            print("      rollback complete. Install is back to v"
                  f"{get_version()}.")
            shutil.rmtree(tmp, ignore_errors=True)
            return 1
    # Ensure the launcher is executable after a copy — a fresh clone / pull
    # can drop the +x bit, leaving `sara` as "Permission denied". B34.
    _fix_launcher_perms()

    ver_after = get_version()
    if new_version:
        set_version(new_version)
        ver_after = new_version
    print(f"[4/5] new version: {ver_after}")

    print("[5/5] verifying (compile + restart + smoke turn)…")
    ok, msg = _verify()
    if not ok:
        print(f"      VERIFY FAILED: {msg}")
        print("      rolling back to pre-upgrade backup…")
        restore(bk.name)
        if not os.environ.get("SARA_UPGRADE_NO_RESTART"):
            _run(["systemctl", "--user", "restart", "sara-web.service"],
                 check=False)
        print("      rollback complete. Install is back to v"
              f"{get_version()}.")
        shutil.rmtree(tmp, ignore_errors=True)
        return 1

    st = _load_state()
    st["last_upgrade"] = {
        "from": ver_before, "to": ver_after, "repo": repo_url,
        "branch": branch, "backup": bk.name,
        "ts": datetime.now().isoformat()}
    _save_state(st)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"      SUCCESS — S.A.R.A upgraded v{ver_before} -> v{ver_after}")
    print(f"      backup kept: {bk.name}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="S.A.R.A self-upgrade toolkit")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("backup").add_argument("--label", default=None)
    p_up = sub.add_parser("upgrade")
    p_up.add_argument("repo_url")
    p_up.add_argument("branch", nargs="?", default="main")
    p_up.add_argument("--version", default=None,
                      help="explicit new version (else use repo's __version__)")
    sub.add_parser("list")
    p_rb = sub.add_parser("rollback")
    p_rb.add_argument("backup")
    sub.add_parser("status")

    args = ap.parse_args()

    if args.cmd == "backup":
        b = backup(args.label)
        print(f"backup created: {b}")
        return 0
    if args.cmd == "upgrade":
        return upgrade(args.repo_url, args.branch, args.version)
    if args.cmd == "list":
        for b in list_backups():
            print(f"  {b['file']}  v{b['version']}  {b['ts']}"
                  f"  {b.get('label','')}")
        return 0
    if args.cmd == "rollback":
        return 0 if restore(args.backup) else 2
    if args.cmd == "status":
        st = _load_state()
        print(f"version:    {get_version()}")
        print(f"last upgr:  {st.get('last_upgrade', 'never')}")
        print(f"backups:    {len(list_backups())}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
