"""Startup self-upgrade check.

On boot, S.A.R.A compares her local git HEAD against the remote's ``main``
HEAD. If the remote has a newer commit, she flags ``upgrade_available`` so the
UI / chat can tell the user ("a newer version is available - say 'upgrade'").

Remote source of truth:
  The canonical repo (hammerzaine/S.A.R.A) is PRIVATE. The most reliable check
  is the GitHub REST API authenticated with a Personal Access Token (PAT):
      GET /repos/{owner}/{repo}/commits/{branch}   (Authorization: Bearer <PAT>)
  The PAT lives in repo-root ``credentials.json`` (git-ignored) under
  ``github.token`` - it is NEVER hard-coded in this file, so it can't leak into
  the install bundle / git history.
  Fallback: ``git ls-remote`` over the existing deploy key / SSH remotes
  (``origin`` = the .local mirror, ``github`` = git@github.com) - no token needed,
  works for boxes that already have key auth.

Design rules:
  * OFFLINE-SAFE. Any network failure, timeout, API error, or git error is
    swallowed and reported as ``available=False`` / ``checked=False``. This must
    NEVER block startup or crash the service.
  * READ-ONLY. The API is a GET of one commit; ``git ls-remote`` fetches refs
    only. Neither pulls, merges, or touches local files.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

_REMOTE = "origin"
_BRANCH = "main"
_TIMEOUT = 15  # seconds - fail fast, don't hang boot
_DEFAULT_GH_REPO = "hammerzaine/S.A.R.A"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_github_creds() -> dict:
    """Read the GitHub PAT + repo slug from repo-root credentials.json.

    Returns {} when the file is missing or has no ``github`` section. Never
    raises - this runs at startup and must be safe to call even on a bare
    install that hasn't been configured yet.
    """
    try:
        creds_path = _repo_root() / "credentials.json"
        if not creds_path.exists():
            return {}
        data = json.loads(creds_path.read_text())
        gh = data.get("github") or {}
        if not isinstance(gh, dict):
            return {}
        return gh
    except Exception:
        return {}


def _github_latest_commit(owner_repo: str, branch: str, token: str, timeout: int) -> str | None:
    """Return the latest commit SHA on ``branch`` via the GitHub API, or None."""
    url = f"https://api.github.com/repos/{owner_repo}/commits/{branch}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "S.A.R.A-version-check",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        sha = payload.get("sha")
        return sha if isinstance(sha, str) and sha else None
    except Exception:
        return None


def _ls_remote_commit(remote: str, branch: str, timeout: int) -> str | None:
    """Return the remote branch HEAD commit hash, or None on any failure."""
    try:
        out = subprocess.run(
            ["git", "ls-remote", remote, f"refs/heads/{branch}"],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(_repo_root()),
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        return out.stdout.split()[0].strip()
    except Exception:
        return None


def check_for_upgrade(local_commit: str | None = None) -> dict:
    """Compare local HEAD against the remote ``main`` HEAD.

    Tries, in order:
      1. GitHub REST API with the configured PAT (canonical private repo).
      2. ``git ls-remote origin`` (the .local deploy mirror, key-auth).
      3. ``git ls-remote github`` (git@github.com, key-auth).

    Returns a dict:
        {"available": bool, "local_commit": str|None,
         "latest_commit": str|None, "checked": bool, "error": str|None,
         "remote": str}
    """
    result = {
        "available": False,
        "local_commit": local_commit,
        "latest_commit": None,
        "checked": False,
        "error": None,
        "remote": "none",
    }

    # 1) GitHub API (preferred - works against the private repo with a PAT)
    gh = _load_github_creds()
    token = gh.get("token")
    if token:
        repo = gh.get("repo") or _DEFAULT_GH_REPO
        commit = _github_latest_commit(repo, _BRANCH, token, _TIMEOUT)
        if commit:
            result["remote"] = "github-api"
            result["checked"] = True
            result["latest_commit"] = commit
            if local_commit and commit != local_commit:
                result["available"] = True
            return result

    # 2) Fall back to git ls-remote (key-auth, no token needed)
    for remote in (_REMOTE, "github"):
        commit = _ls_remote_commit(remote, _BRANCH, _TIMEOUT)
        if commit:
            result["remote"] = remote
            result["checked"] = True
            result["latest_commit"] = commit
            if local_commit and commit != local_commit:
                result["available"] = True
            return result

    result["error"] = "could not reach any remote (offline? no token?)"
    return result


def _local_commit() -> str | None:
    """Best-effort local git HEAD; None when not a git work tree (e.g. a
    bare extracted install bundle)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            timeout=_TIMEOUT, cwd=str(_repo_root()),
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def start_version_watch(on_result, interval: int = 3600) -> threading.Thread | None:
    """Run an upgrade check once now, then every ``interval`` seconds, in a
    background daemon thread. Each result (a dict from ``check_for_upgrade``)
    is handed to ``on_result`` so the caller can store it on the agent.

    OFFLINE-SAFE: any failure is swallowed by ``check_for_upgrade`` and
    reported as ``available=False`` — this never raises and never blocks
    startup. Returns the thread (already started) or None if threading is
    available. The first check runs synchronously so ``/api/status`` and the
    splash have a result immediately at boot.
    """
    def tick() -> None:
        try:
            on_result(check_for_upgrade(_local_commit()))
        except Exception:
            pass

    tick()  # first check now (synchronous, fast — timeouts are 15s max)

    def loop() -> None:
        while True:
            time.sleep(interval)
            tick()

    t = threading.Thread(target=loop, name="sara-version-watch", daemon=True)
    t.start()
    return t

