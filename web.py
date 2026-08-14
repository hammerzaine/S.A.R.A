#!/usr/bin/env python3
"""S.A.R.A web server — the browser chat interface.

Streams her work as it happens (reasoning, actions, results, growth) over
Server-Sent Events, so the web UI shows exactly what the terminal shows.

    python3 web.py            # listens on 0.0.0.0:8800
    python3 web.py --port 9000
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from sara.agent import Sara, DEFAULT_UPGRADE_REPO, DEFAULT_UPGRADE_BRANCH
from sara.console import Console
from sara.version_check import start_version_watch

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "web"


class EventConsole(Console):
    """A Console that emits structured events instead of printing ANSI.

    Subclassing means the agent needs zero changes: every think/act/result/
    learned call it already makes becomes a browser event.
    """

    def __init__(self, sink: queue.Queue):
        super().__init__(verbose=True, colour=False)
        self.sink = sink

    def _emit(self, kind: str, **data):
        self.sink.put({"type": kind, **data})

    def think(self, text: str) -> None:
        cleaned = str(text).replace("```", "").strip(" \n\t`")
        if len(cleaned) >= 3:
            self._emit("think", text=cleaned)

    def act(self, tool: str, detail: str = "") -> None:
        self._emit("act", tool=tool, detail=detail)

    def result(self, summary: str, ok: bool = True) -> None:
        self._emit("result", text=summary, ok=bool(ok))

    def learned(self, what: str, detail: str = "") -> None:
        self._emit("learned", what=what, detail=detail)

    def warn(self, text: str) -> None:
        self._emit("warn", text=text)

    def error(self, text: str) -> None:
        self._emit("error", text=text)

    # Everything below is terminal furniture — silent on the web.
    def speak(self, text: str) -> None:
        pass

    def user_echo(self, text: str) -> None:
        pass

    def info(self, text: str) -> None:
        pass

    def rule(self, label: str = "") -> None:
        pass

    def splash(self, *a, upgrade: dict | None = None, **k) -> None:
        # Surface an available upgrade as a chat event so the web UI shows it
        # as a message in conversation (mirrors the CLI post-splash line).
        if upgrade and upgrade.get("available"):
            self._emit("upgrade", available=True,
                       latest=upgrade.get("latest"),
                       remote=upgrade.get("remote"))

    class _NullSpin:
        def __enter__(self):
            return self

        def tick(self):
            pass

        def __exit__(self, *a):
            pass

    def thinking(self, label: str = "thinking"):
        return EventConsole._NullSpin()


app = FastAPI(title="S.A.R.A")
_lock = threading.Lock()          # one turn at a time — she has one brain
_sink: queue.Queue = queue.Queue()
_console = EventConsole(_sink)
_sara = Sara(console=_console)

# Startup self-upgrade check (offline-safe). Runs once now, then re-checks
# every hour on a daemon thread, storing the latest result on the agent so
# /api/status can report it. Compares the local git HEAD against the remote
# 'main' HEAD (works for private repos via the existing deploy key / PAT).
start_version_watch(lambda r: setattr(_sara, "_upgrade", r))

# Surface a pending upgrade as a chat event on boot (the browser renders it as
# an in-conversation notice). EventConsole.splash is a no-op unless an upgrade
# is available, so this is safe to call unconditionally.
_console.splash(upgrade=_sara._upgrade)

# Announce at boot (goes to the service journal / stdout).
_up = _sara._upgrade or {}
if _up.get("available"):
    print(f"[S.A.R.A] UPGRADE AVAILABLE: local {_up.get('local_commit','?')[:8]} "
          f"-> remote {_up.get('latest_commit','?')[:8]} ({_up.get('remote')})",
          flush=True)
elif _up.get("checked"):
    print(f"[S.A.R.A] version check ok — up to date ({_up.get('local_commit','?')[:8]})",
          flush=True)
else:
    print(f"[S.A.R.A] version check skipped ({_up.get('error')})", flush=True)


class Ask(BaseModel):
    message: str


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html",
                        headers={"Cache-Control": "no-store"})


@app.get("/api/status")
def status():
    st = _sara.status()
    skills = _sara.memory.all_skills()
    cfg = _sara.get_config().get("config", {})
    return {
        "name": "S.A.R.A",
        "subtitle": "Smart AI Resource Assistant",
        "version": st.get("version", "unknown"),
        "provider": st.get("provider", "ollama"),
        "base_url": st.get("base_url"),
        "no_research": st.get("no_research", False),
        "provider_presets": _sara.get_config().get("provider_presets", []),
        "upgrade": _sara._upgrade or {"available": False, "local": st.get("version"),
                                       "latest": None, "checked": False, "error": None},
        "model": st["model"],
        "online": st["online"],
        "turns": st["turns"],
        "facts": st["facts"],
        "skill_count": len(skills),
        "skills": [
            {"name": s["name"],
             "description": (s.get("description") or "").strip()
                            or (s.get("body") or "").strip().split("\n")[0]
                            or "no description recorded",
             "uses": s.get("uses", 0)}
            for s in skills
        ],
        "memories": _sara.memory.facts(60),
        "tools": sorted(_sara.tools.keys()),
        "task_state": st.get("task_state"),
        "resume_available": st.get("resume_available", False),
    }


@app.get("/api/models")
def models():
    """List models from the configured endpoint WITHOUT going through the
    chat loop. The 'List models' button used POST /api/ask 'list_models',
    which let the small local model re-invoke the tool forever and hang the
    UI on 'loading…'. This returns the list directly."""
    try:
        from sara.tools import ModelList
        res = ModelList(ROOT).run("")
        if not res.get("ok"):
            return {"ok": False, "error": res.get("error", "unknown error"),
                    "models": [], "current": None}
        return {"ok": True, "models": res.get("models", []),
                "current": res.get("current"),
                "base_url": res.get("base_url")}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}",
                "models": [], "current": None}


class Rename(BaseModel):
    old: str
    new: str


class ConfigSet(BaseModel):
    key: str
    value: str


@app.post("/api/config/set")
def config_set(r: ConfigSet):
    res = _sara.set_config(r.key, r.value)
    return res


@app.get("/api/config")
def config_get():
    return _sara.get_config()



@app.post("/api/rename")
def rename(r: Rename):
    ok, why = _sara.memory.rename_skill(r.old, r.new)
    return {"ok": ok, "message": why}


@app.post("/api/forget")
def forget(a: Ask):
    return {"dropped": _sara.memory.forget(a.message)}


@app.post("/api/ask")
def ask(a: Ask):
    """Run one turn, streaming her working out as it happens."""
    msg = a.message.strip()
    if not msg:
        return StreamingResponse(iter([]), media_type="text/event-stream")

    # Slash command? Intercept locally so the small model never sees it.
    if msg.startswith("/update"):
        # /update is a synonym for /upgrade
        msg = "/upgrade" + msg[6:]
    if msg.startswith("/setup"):
        return _stream_setup(msg)
    if msg.startswith("/upgrade"):
        return _stream_upgrade(msg)
    if msg.startswith("/factoryreset"):
        return _stream_factoryreset(msg)
    if msg.startswith("/model"):
        return _stream_model(msg)

    def run():
        with _lock:
            try:
                answer = _sara.ask(msg)
                _sink.put({"type": "answer", "text": answer})
            except Exception as e:                       # noqa: BLE001
                _sink.put({"type": "error", "text": f"{type(e).__name__}: {e}"})
            finally:
                _sink.put({"type": "done"})

    threading.Thread(target=run, daemon=True).start()

    def stream():
        while True:
            ev = _sink.get()
            yield f"data: {json.dumps(ev)}\n\n"
            if ev.get("type") == "done":
                return

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def _stream_upgrade(msg: str):
    """Run /upgrade from the web chat, streaming progress as SSE events.

    Bare ``/upgrade`` pulls origin/main. ``/upgrade <repo-url> [branch]``
    pulls a specific source. ``/upgrade backup|list|rollback <name>`` run the
    matching toolkit subcommand. The service is restarted here (the web
    process survives because we set SARA_UPGRADE_NO_RESTART so the toolkit
    doesn't restart it mid-upgrade), then the result is streamed.
    """
    rest = msg[len("/upgrade"):].strip()
    if not rest or rest.lower() in ("status", "help"):
        # bare /upgrade and /update → pull the canonical source (in code)
        cargs = ["upgrade", DEFAULT_UPGRADE_REPO, DEFAULT_UPGRADE_BRANCH]
    elif rest.split()[0] in ("backup", "list", "rollback", "status"):
        cargs = rest.split()
    else:
        cargs = ["upgrade", *rest.split()]

    def run():
        try:
            env = dict(os.environ)
            env["SARA_UPGRADE_NO_RESTART"] = "1"
            proc = subprocess.run(
                [sys.executable, str(ROOT / "sara_upgrade.py"), *cargs],
                capture_output=True, text=True, env=env, timeout=600,
            )
            out = (proc.stdout or proc.stderr).strip()
            success = proc.returncode == 0
            # The toolkit skipped the restart, so do it here (the web process
            # survives its own restart — systemd --user re-launches it).
            # A no-op "already up to date" does not warrant a restart.
            if success and "Already up to date" not in out:
                try:
                    subprocess.run(
                        ["systemctl", "--user", "restart", "sara-web.service"],
                        check=False, timeout=30)
                except Exception:  # noqa: BLE001
                    pass
            # Stream the toolkit output line-by-line as 'result' events.
            for line in out.splitlines() or ["(no output)"]:
                _sink.put({"type": "result", "text": line,
                           "ok": success})
            _sink.put({
                "type": "answer",
                "text": ("✅ Upgrade done — S.A.R.A restarted. " + out
                         if success else
                         "❌ Upgrade failed (rolled back). " + out),
            })
        except subprocess.TimeoutExpired:
            _sink.put({"type": "error",
                       "text": "upgrade timed out after 10m"})
        except Exception as e:  # noqa: BLE001
            _sink.put({"type": "error", "text": f"{type(e).__name__}: {e}"})
        finally:
            _sink.put({"type": "done"})

    threading.Thread(target=run, daemon=True).start()

    def stream():
        while True:
            ev = _sink.get()
            yield f"data: {json.dumps(ev)}\n\n"
            if ev.get("type") == "done":
                return

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def _stream_setup(msg: str):
    """Run /setup from the web chat, streaming progress as SSE events.

    The web runs headless (no TTY), so /setup must be given inline:
        /setup <url> [key:KEY] [model:NAME]
    It connects, fetches the live model list, and selects the model (a
    specific one via model:<name>, or the first free-tier model otherwise).
    """
    rest = msg[len("/setup"):].strip()

    def run():
        try:
            res = _sara.cmd_setup(rest)
            ok = res.get("ok", False)
            if res.get("models"):
                shown = ", ".join(res["models"][:30])
                _sink.put({"type": "result",
                           "text": f"{len(res['models'])} models @ "
                                   f"{res.get('base_url')}: {shown}",
                           "ok": ok})
            _sink.put({"type": "result",
                       "text": (res.get("msg") or res.get("error", "")),
                       "ok": ok})
            _sink.put({
                "type": "answer",
                "text": (("✅ " + (res.get("msg") or "")) if ok
                         else ("❌ " + (res.get("error") or "setup failed"))),
            })
        except Exception as e:  # noqa: BLE001
            _sink.put({"type": "error", "text": f"{type(e).__name__}: {e}"})
        finally:
            _sink.put({"type": "done"})

    threading.Thread(target=run, daemon=True).start()

    def stream():
        while True:
            ev = _sink.get()
            yield f"data: {json.dumps(ev)}\n\n"
            if ev.get("type") == "done":
                return

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def _stream_factoryreset(msg: str):
    """Run /factoryreset from the web chat, streaming progress as SSE events.

    Bare ``/factoryreset`` shows the warning and asks for confirmation
    (``/factoryreset --yes``). The wipe is destructive: it drops the memory
    DB, blanks SOUL.md, and deletes config.json + credentials.json. Code and
    upgrade_state.json are preserved. The web service is restarted afterwards
    (with SARA_UPGRADE_NO_RESTART so we don't kill our own process mid-reset).
    """
    rest = msg[len("/factoryreset"):].strip().lower()
    confirm = rest in ("--yes", "confirm", "-y", "yes")

    def run():
        if not confirm:
            _sink.put({"type": "result",
                       "text": "⚠ Factory reset wipes memory + SOUL.md + "
                               "config/credentials.", "ok": False})
            _sink.put({"type": "answer",
                       "text": "To proceed, type:  /factoryreset --yes"})
            return
        try:
            env = dict(os.environ)
            env["SARA_UPGRADE_NO_RESTART"] = "1"
            res = _sara.reset_state(confirm=True)
            if res.get("ok"):
                try:
                    subprocess.run(
                        ["systemctl", "--user", "restart",
                         "sara-web.service"], check=False, timeout=30)
                except Exception:  # noqa: BLE001
                    pass
                _sink.put({"type": "result",
                           "text": "memory + SOUL.md + config/credentials wiped",
                           "ok": True})
                _sink.put({"type": "answer",
                           "text": "✅ Factory reset complete — she's a blank "
                                   "slate, and the web service restarted."})
            else:
                _sink.put({"type": "answer",
                           "text": f"❌ Reset failed: {res.get('error', res)}"})
        except Exception as e:  # noqa: BLE001
            _sink.put({"type": "error", "text": f"{type(e).__name__}: {e}"})
        finally:
            _sink.put({"type": "done"})

    threading.Thread(target=run, daemon=True).start()

    def stream():
        while True:
            ev = _sink.get()
            yield f"data: {json.dumps(ev)}\n\n"
            if ev.get("type") == "done":
                return

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def _stream_model(msg: str):
    """Run /model from the web chat, streaming progress as SSE events.

    /model                -> show current provider/model + preset list
    /model <provider>     -> switch connection to that preset
    /model <provider> <model> -> switch + set model
    /model custom <url> [model] -> custom OpenAI-compatible endpoint
    Optional trailing `key:VALUE` sets the api key. The change is live
    (set_config rebuilds the LLM) and persisted to config.json.
    """
    arg = msg[len("/model"):].strip()

    def run():
        try:
            res = _sara.cmd_model(arg)
            if res.get("show"):
                _sink.put({"type": "result",
                           "text": f"provider {res['provider']} · "
                                   f"{res['base_url']} · model {res['model']}",
                           "ok": True})
                _sink.put({"type": "result",
                           "text": "presets: " + ", ".join(res["presets"]),
                           "ok": True})
                _sink.put({"type": "answer",
                           "text": "Pick a connection above, or type e.g. "
                                   "`/model ollama` or `/model custom "
                                   "https://.../v1`. Add `key:YOURKEY` for "
                                   "authenticated providers."})
            elif res.get("ok"):
                _sink.put({"type": "result", "text": res.get("msg", "done"),
                           "ok": True})
                _sink.put({"type": "answer",
                           "text": "✅ connection switched — next turn uses "
                                   "the new model."})
            else:
                _sink.put({"type": "answer",
                           "text": "❌ " + res.get("error", "failed")})
        except Exception as e:  # noqa: BLE001
            _sink.put({"type": "error", "text": f"{type(e).__name__}: {e}"})
        finally:
            _sink.put({"type": "done"})

    threading.Thread(target=run, daemon=True).start()

    def stream():
        while True:
            ev = _sink.get()
            yield f"data: {json.dumps(ev)}\n\n"
            if ev.get("type") == "done":
                return

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8800)
    args = p.parse_args()
    import uvicorn
    print(f"S.A.R.A web UI  ->  http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
