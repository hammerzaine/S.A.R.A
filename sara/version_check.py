"""Startup self-upgrade check.

On boot, S.A.R.A compares her local git HEAD against the remote's ``main`` HEAD.
If the remote has a newer commit, she flags ``upgrade_available`` so the UI /
chat can tell the user ("a newer version is available — say 'upgrade'").

Why commit comparison (not a version-string fetch):
  * The canonical repo (hammerzaine/S.A.R.A) is PRIVATE, so raw GitHub URLs and
    the API return 404 without a token. ``git ls-remote`` over the existing
    deploy key works fine — no token needed.
  * A newer *commit* is the real signal that "someone has an older version".
  * It works for both remotes (origin/.225 and github) since both use key auth.

Design rules:
  * OFFLINE-SAFE. Any network failure, timeout, or git error is swallowed and
    reported as ``available=False`` / ``checked=False``. This must NEVER block
    startup or crash the service — an old box with no internet still boots.
  * READ-ONLY. ``git ls-remote`` is a fetch of refs only; it never pulls,
    merges, or touches local files.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# Remote + branch to treat as the source of truth. ``origin`` is the .225
# deploy mirror (key-auth already works); fall back to ``github`` if origin
# is unreachable.
_REMOTE = "origin"
_BRANCH = "main"
_TIMEOUT = 15  # seconds — fail fast, don't hang boot


def _ls_remote_commit(remote: str, branch: str, timeout: int) -> str | None:
    """Return the remote branch HEAD commit hash, or None on any failure."""
    try:
        # Run from the repo root (parent of the sara/ package dir).
        repo_root = str(Path(__file__).resolve().parent.parent)
        out = subprocess.run(
            ["git", "ls-remote", remote, f"refs/heads/{branch}"],
            capture_output=True, text=True, timeout=timeout,
            cwd=repo_root,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        return out.stdout.split()[0].strip()
    except Exception:
        return None


def check_for_upgrade(local_commit: str | None = None) -> dict:
    """Compare local HEAD against the remote ``main`` HEAD.

    Returns a dict:
        {"available": bool, "local_commit": str|None,
         "latest_commit": str|None, "checked": bool, "error": str|None,
         "remote": str}
    ``checked`` is False when the remote couldn't be reached (offline/private
    without auth). ``available`` is True when the remote HEAD differs from local.
    """
    result = {
        "available": False,
        "local_commit": local_commit,
        "latest_commit": None,
        "checked": False,
        "error": None,
        "remote": _REMOTE,
    }
    remote = _REMOTE
    commit = _ls_remote_commit(remote, _BRANCH, _TIMEOUT)
    if commit is None:
        # Try the github remote as a fallback before giving up.
        remote = "github"
        commit = _ls_remote_commit(remote, _BRANCH, _TIMEOUT)
    result["remote"] = remote
    if commit is None:
        result["error"] = "could not reach any remote (offline?)"
        return result
    result["checked"] = True
    result["latest_commit"] = commit
    if local_commit and commit != local_commit:
        result["available"] = True
    return result
