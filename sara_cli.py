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

from sara.agent import Sara
from sara.console import Console

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
    ("/skills", "everything she's taught herself"),
    ("/memory", "facts she remembers"),
    ("/status", "model + connection"),
    ("/forget", "drop a fact"),
    ("/upgrade", "upgrade her code from a git repo"),
    ("/rename", "rename a skill"),
    ("/quiet", "hide her reasoning"),
    ("/verbose", "show her reasoning"),
    ("/clear", "redraw the screen"),
    ("/help", "this list"),
    ("/quit", "goodbye"),
]


def show_splash(sara: Sara, console: Console) -> None:
    st = sara.status()
    console.splash(model=st["model"],
                   skills=sara.memory.all_skills(),
                   facts=st["facts"],
                   online=st["online"],
                   commands=COMMANDS)
    if not st["online"]:
        console.warn(f"the model at {sara.cfg['base_url']} isn't answering — "
                     "start it with:  ollama serve")


def main() -> int:
    console = Console()
    try:
        sara = Sara(console=console)
    except Exception as e:
        console.error(f"couldn't start: {e}")
        return 1

    # One-shot mode
    if len(sys.argv) > 1:
        q = " ".join(sys.argv[1:])
        console.user_echo(q)
        console.speak(sara.ask(q))
        return 0

    show_splash(sara, console)
    setup_history()

    while True:
        try:
            line = input(console.prompt()).strip()
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
        if low.startswith("/upgrade"):
            import subprocess
            cargs = line[len("/upgrade"):].strip() or "status"
            r = subprocess.run([sys.executable, "sara_upgrade.py", *cargs.split()],
                               capture_output=True, text=True)
            (console.info if r.returncode == 0 else console.warn)(
                r.stdout.strip() or r.stderr.strip())
            if low == "/upgrade":
                console.info("usage: /upgrade <repo-url> [branch] | backup | "
                             "list | rollback <name>")
            continue
        if low.startswith("/"):
            console.warn(f"no such command: {line.split()[0]} — /help")
            continue

        console.user_echo(line)
        console.speak(sara.ask(line))


if __name__ == "__main__":
    sys.exit(main())
