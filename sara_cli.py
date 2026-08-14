#!/usr/bin/env python3
"""S.A.R.A command-line interface."""

from __future__ import annotations

import atexit
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# readline gives us up/down history, ctrl-R search, and line editing at the
# prompt. Without importing it, bare input() prints raw escape codes (^[[A)
# when you press the arrow keys.
try:
    import readline
except ImportError:  # pragma: no cover - readline is stdlib on Linux
    readline = None

# prompt_toolkit gives the Hermes-style "/"-command menu: type "/", get a live,
# narrowing list of commands; Tab/Enter autofills; Up/Down navigate. We fall
# back to plain input() if it isn't installed.
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.formatted_text import ANSI
    from prompt_toolkit.history import FileHistory
    _PTK = True
except Exception:  # pragma: no cover - optional dependency
    _PTK = False

from sara.agent import Sara, DEFAULT_UPGRADE_REPO, DEFAULT_UPGRADE_BRANCH
from sara.console import Console
from sara.version_check import start_version_watch
from sara import evolution as sara_evolution

HISTFILE = Path.home() / ".sara_history"


def setup_history(limit: int = 2000) -> None:
    """Persistent up/down-arrow history across sessions."""
    if readline is None:
        return
    try:
        readline.read_history_file(HISTFILE)
    except (FileNotFoundError, OSError):
        pass
    readline.set_history_length(limit)
    # Emacs-style editing: up/down = history, ctrl-A/E = line start/end,
    # ctrl-R = reverse search.
    readline.parse_and_bind("set editing-mode emacs")
    readline.parse_and_bind('"\\e[A": previous-history')
    readline.parse_and_bind('"\\e[B": next-history')
    readline.parse_and_bind("set enable-bracketed-paste on")
    atexit.register(save_history)


def save_history() -> None:
    if readline is None:
        return
    try:
        HISTFILE.touch(exist_ok=True)
        os.chmod(HISTFILE, 0o600)
        readline.write_history_file(HISTFILE)
    except OSError:
        pass

COMMANDS = [
    ("/model", "switch model + connection"),
    ("/skills", "everything she's taught herself"),
    ("/memory", "facts she remembers"),
    ("/status", "model + connection"),
    ("/forget", "drop a fact"),
    ("/setup", "connect a provider (URL + key, pick a model)"),
    ("/upgrade", "upgrade her code from a git repo"),
    ("/update", "alias for /upgrade"),
    ("/factoryreset", "wipe memory + config (needs --yes)"),
    ("/rename", "rename a skill"),
    ("/quiet", "hide her reasoning"),
    ("/verbose", "show her reasoning"),
    ("/clear", "redraw the screen"),
    ("/help", "this list"),
    ("/quit", "goodbye"),
]


# --- Hermes-style "/"-command menu (prompt_toolkit) -----------------------
_CMD_WORDS = [c for c, _ in COMMANDS]


class _CommandCompleter(Completer):
    """Complete against the command list while typing a '/'-token.

    WordCompleter drops the leading slash (treats it as a word boundary), so
    '/fa' would match against 'fa' and never hit '/factoryreset'. We instead
    complete on the whole '/...' token, mirroring the web palette behaviour.
    """

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/") or " " in text:
            return
        for cmd in _CMD_WORDS:
            if cmd.startswith(text):
                yield Completion(cmd, start_position=-len(text),
                                 display=cmd)


_CMD_COMPLETER = _CommandCompleter() if _PTK else None


def _cli_prompt(console: "Console"):
    """ANSI prompt for prompt_toolkit (its own escape handling, no \\001 marks)."""
    if console.colour:
        return ANSI("\n  \x1b[38;5;75m\x1b[1myou\x1b[0m \x1b[38;5;240m›\x1b[0m ")
    return "\n  you > "


def build_session():
    """Return a PromptSession with command completion, or None if ptk missing.

    Migrates any legacy readline-format history so it isn't lost on first run.
    """
    if not _PTK:
        return None
    sess = PromptSession(
        history=FileHistory(HISTFILE),
        completer=_CMD_COMPLETER,
        complete_while_typing=True,
    )
    try:
        raw = HISTFILE.read_text(encoding="utf-8").splitlines()
        # ptk history is JSON-per-line; a plain line means legacy readline fmt.
        if raw and not raw[0].lstrip().startswith("{"):
            for ln in raw:
                if ln.strip():
                    sess.history.append_string(ln)
    except (OSError, ValueError):
        pass
    return sess


def read_line(session, console: "Console") -> str:
    """Read one command line. Uses the ptk session when available, else input()."""
    if session is None:
        return input(console.prompt()).strip()
    try:
        return session.prompt(_cli_prompt(console)).strip()
    except (EOFError, KeyboardInterrupt):
        raise


def show_splash(sara: Sara, console: Console) -> None:
    st = sara.status()
    up = getattr(sara, "_upgrade", None) or {}
    console.splash(model=st["model"],
                   skills=sara.memory.all_skills(),
                   facts=st["facts"],
                   online=st["online"],
                   commands=COMMANDS,
                   version=st.get("version", "unknown"),
                   upgrade=up if up.get("available") else None)
    if not st["online"]:
        console.warn(f"the model at {sara.cfg['base_url']} isn't answering — "
                     "start it with:  ollama serve")
    if up.get("available"):
        console.info("★ a newer version is available — type /upgrade to pull it")


def main() -> int:
    console = Console()
    try:
        sara = Sara(console=console)
    except Exception as e:
        console.error(f"couldn't start: {e}")
        return 1

    # Startup upgrade check + hourly re-check (offline-safe, background thread).
    # The first check runs synchronously so /status and the splash can show
    # "upgrade available" immediately when one exists.
    start_version_watch(lambda r: setattr(sara, "_upgrade", r))

    # One-shot mode
    if len(sys.argv) > 1:
        q = " ".join(sys.argv[1:])
        console.user_echo(q)
        console.speak(sara.ask(q))
        return 0

    show_splash(sara, console)
    setup_history()
    session = build_session()

    while True:
        try:
            line = read_line(session, console)
        except (EOFError, KeyboardInterrupt):
            console.speak("Right then. Talk soon.")
            return 0
        if not line:
            continue

        low = line.lower()
        if low in ("/quit", "/exit", "quit", "exit"):
            console.speak("Right then. Talk soon.")
            return 0
        if low in ("/help", "/?"):
            console.rule("commands")
            print()
            for c, d in COMMANDS:
                console.info(f"  \033[38;5;51m{c:<10}\033[0m \033[38;5;245m{d}")
            print()
            continue
        if low == "/clear":
            print("\033[2J\033[H", end="")
            show_splash(sara, console)
            continue
        if low == "/quiet":
            console.verbose = False
            console.info("reasoning hidden")
            continue
        if low == "/verbose":
            console.verbose = True
            console.info("reasoning shown")
            continue
        if low == "/status":
            s = sara.status()
            console.rule("status")
            print()
            console.info(f"  model     {s['model']}")
            console.info(f"  endpoint  {sara.cfg['base_url']}")
            console.info(f"  online    {'yes' if s['online'] else 'no'}")
            console.info(f"  turns     {s['turns']}")
            console.info(f"  facts     {s['facts']}")
            console.info(f"  skills    {s['skills']}")
            print()
            continue
        if low == "/skills":
            console.skill_table(sara.memory.all_skills())
            continue
        if low == "/evolve":
            # Hard-coded evolution on demand: re-seed the baseline brain (in case
            # it was wiped) and auto-promote repeated actions to real skills.
            seeded = sara_evolution.seed_brain(sara.memory)
            promoted = sara_evolution.promote_procedures(sara.memory, min_uses=2)
            console.info(f"evolved — reseeded {seeded['added_skills']} skills / "
                         f"{seeded['added_facts']} facts; promoted {promoted} "
                         f"repeated action(s) to skill(s)")
            continue
        if low == "/memory":
            console.fact_list(sara.memory.facts(60))
            continue
        if low.startswith("/rename "):
            parts = line[8:].split()
            if len(parts) != 2:
                console.warn("usage: /rename <old-name> <new-name>")
                continue
            ok, why = sara.memory.rename_skill(parts[0], parts[1])
            (console.info if ok else console.warn)(why)
            continue
        if low.startswith("/forget "):
            n = sara.memory.forget(line[8:].strip())
            console.info(f"dropped {n} fact(s)")
            continue
        if low.startswith("/update"):
            # /update is a synonym for /upgrade; rewrite and fall through
            line = "/upgrade" + line[6:]
            low = line.lower()
        if low.startswith("/setup"):
            arg = line[len("/setup"):].strip()
            res = sara.cmd_setup(arg, console=console)
            if res.get("ok"):
                console.info(res.get("msg", "done"))
                if res.get("models"):
                    console.info(f"  {len(res['models'])} model(s) available @ "
                                 f"{res.get('base_url')}")
            else:
                console.warn(res.get("error", "setup failed"))
            continue
        if low.startswith("/upgrade"):
            import subprocess
            rest = line[len("/upgrade"):].strip()
            if not rest or rest.lower() in ("status", "help"):
                # bare /upgrade and /update → pull the canonical source (in code)
                cargs = ["upgrade", DEFAULT_UPGRADE_REPO,
                         DEFAULT_UPGRADE_BRANCH]
            elif rest.split()[0] in ("backup", "list", "rollback", "status"):
                # explicit subcommand: /upgrade backup | list | rollback <name>
                cargs = rest.split()
            else:
                # /upgrade <repo-url> [branch]  (or a bare remote name)
                cargs = ["upgrade", *rest.split()]
            r = subprocess.run([sys.executable, "sara_upgrade.py", *cargs],
                               capture_output=True, text=True)
            out = (r.stdout.strip() or r.stderr.strip())
            (console.info if r.returncode == 0 else console.warn)(out)
            if r.returncode != 0:
                console.info("usage: /upgrade [<repo-url> [branch]] | "
                             "backup | list | rollback <name>")
            continue
        if low.startswith("/factoryreset"):
            rest = line[len("/factoryreset"):].strip().lower()
            if rest not in ("--yes", "confirm", "-y", "yes"):
                console.rule("factory reset")
                print()
                console.warn("This wipes EVERYTHING:")
                console.warn("  · memory DB (turns / facts / skills / procedures)")
                console.warn("  · SOUL.md (personality)")
                console.warn("  · config.json + credentials.json (secrets)")
                console.warn("Code + upgrade_state.json are preserved.")
                console.info("To proceed, type:  /factoryreset --yes")
                print()
                continue
            res = sara.reset_state(confirm=True)
            if res.get("ok"):
                console.info("factory reset complete — she's a blank slate.")
                console.info("restart sara-web to pick up the blank state "
                             "(or it restarts automatically if running as a service).")
            else:
                console.warn(f"reset failed: {res.get('error', res)}")
            continue
        if low == "/model" or low.startswith("/model "):
            arg = line[len("/model"):].strip()
            res = sara.cmd_model(arg)
            if res.get("show"):
                console.rule("connection")
                console.info(f"  provider  {res['provider']}")
                console.info(f"  endpoint  {res['base_url']}")
                console.info(f"  model     {res['model']}")
                console.info(f"  api key   {'set' if res['api_key_set'] else 'empty'}")
                console.info("  presets: " + ", ".join(res['presets']))
            elif res.get("ok"):
                console.info(res.get("msg", "done"))
            else:
                console.warn(res.get("error", "failed"))
            continue
        if low.startswith("/"):
            console.warn(f"no such command: {line.split()[0]} — /help")
            continue

        console.user_echo(line)
        console.speak(sara.ask(line))


if __name__ == "__main__":
    sys.exit(main())
