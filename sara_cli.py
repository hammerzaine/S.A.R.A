#!/usr/bin/env python3
"""S.A.R.A command-line interface (v4)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import readline
except ImportError:  # pragma: no cover
    readline = None

from sara.agent import Sara, PROVIDERS
from sara.console import Console
from sara.memory import Memory

HISTFILE = Path.home() / ".sara_history"
ROOT = Path(__file__).resolve().parent


def setup_history(limit: int = 2000) -> None:
    if readline is None:
        return
    try:
        readline.read_history_file(HISTFILE)
    except (FileNotFoundError, OSError):
        pass
    readline.set_history_length(limit)
    readline.parse_and_bind("set editing-mode emacs")
    readline.parse_and_bind('"\e[A": previous-history')
    readline.parse_and_bind('"\e[B": next-history')
    readline.parse_and_bind("set enable-bracketed-paste on")
    import atexit
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


def print_help() -> None:
    print("""S.A.R.A v4 commands:
  /help            this message
  /status          model, skills, memories, online state
  /skills          skills she has taught herself
  /facts           durable facts she remembers
  /model           list available models, or switch: /model <n|name|provider [model]>
  /set <k> <v>     change a setting (model, max_steps, verbose, no_research…)
  /reset           wipe memory (requires /reset confirm)
  /quit            exit
Anything else is sent to S.A.R.A as a question or task.""")


GPU_SERVER_URL = "http://127.0.0.1:8081/v1"


def _switch_to_model(agent: "Sara", sel: dict) -> None:
    """Apply a model chosen from the /model menu to the live config."""
    name = sel["name"]
    src = sel["source"]
    if src == "local":
        # a ~/models/*.gguf: serve it via the CUDA GPU server
        agent.set_config("provider", "custom")
        agent.set_config("base_url", GPU_SERVER_URL)
        agent.set_config("model", name)
        where = "GPU server (:8081)"
    elif src == "ollama":
        agent.set_config("provider", "ollama")
        agent.set_config("model", name)
        where = "Ollama (:11434)"
    elif src == "endpoint":
        # already on a custom/endpoint; just pick the model id
        if agent.cfg.get("provider") != "custom":
            agent.set_config("provider", "custom")
        if sel.get("endpoint"):
            agent.set_config("base_url", sel["endpoint"])
        agent.set_config("model", name)
        where = sel.get("endpoint") or "endpoint"
    else:
        agent.set_config("model", name)
        where = "config"
    agent.console.info(f"switched -> {name}  ({where})")


def main() -> None:
    console = Console()
    if len(sys.argv) > 1:
        # one-shot mode: run a single question and exit
        agent = Sara(console=console)
        question = " ".join(sys.argv[1:])
        answer = agent.ask(question)
        console.speak(answer)
        return

    agent = Sara(console=console)
    from sara import __version__
    console.info(f"S.A.R.A v{__version__} — type /help or ask me anything.")
    st = agent.status()
    online = "online" if st["online"] else "offline"
    console.info(f"brain: {st['model']} ({online})  |  "
                 f"{st['skills']} skills, {st['facts']} facts")
    setup_history()

    while True:
        try:
            line = input(console.prompt())
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line.strip():
            continue
        if line.startswith("/"):
            parts = line[1:].split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""
            if cmd in ("quit", "exit", "q"):
                break
            elif cmd == "help":
                print_help()
            elif cmd == "status":
                import json as _j
                console.rule("status")
                console.info(_j.dumps(agent.status(), indent=2))
            elif cmd == "skills":
                agent.console.skill_table(agent.memory.list_skills())
            elif cmd == "facts":
                agent.console.fact_list(agent.memory.list_facts())
            elif cmd == "model":
                if not arg:
                    models = agent.model_list()
                    agent.console.model_menu(models)
                else:
                    toks = arg.split()
                    # /model <n>  -> select by menu index
                    if len(toks) == 1 and toks[0].isdigit():
                        models = agent.model_list()
                        idx = int(toks[0])
                        if 1 <= idx <= len(models):
                            sel = models[idx - 1]
                            _switch_to_model(agent, sel)
                        else:
                            console.warn(f"no model #{idx} — "
                                         f"/model to see the list")
                    # /model <provider> [model]  -> switch endpoint
                    elif toks[0] in PROVIDERS:
                        agent.set_config("provider", toks[0])
                        if len(toks) > 1:
                            agent.set_config("model", " ".join(toks[1:]))
                        console.info(f"switched -> {toks[0]} "
                                     f"{' '.join(toks[1:])}".strip())
                    # /model <name>  -> select by exact/partial name
                    else:
                        models = agent.model_list()
                        name = " ".join(toks)
                        match = None
                        for m in models:
                            if m["name"].lower() == name.lower():
                                match = m
                                break
                        if match is None:
                            for m in models:
                                if name.lower() in m["name"].lower():
                                    match = m
                                    break
                        if match:
                            _switch_to_model(agent, match)
                        else:
                            console.warn(f"no model matching '{name}' — "
                                         f"/model to see the list")
            elif cmd == "set":
                kv = arg.split(maxsplit=1)
                if len(kv) != 2:
                    console.warn("usage: /set <key> <value>")
                else:
                    r = agent.set_config(kv[0], kv[1])
                    if r.get("ok"):
                        console.info(r["msg"])
                    else:
                        console.warn(r.get("error", "failed"))
            elif cmd == "reset":
                if arg.strip() == "confirm":
                    r = agent.memory.reset()
                    console.info(f"memory wiped: {r}")
                else:
                    console.warn("this wipes memory — run `/reset confirm`")
            else:
                console.warn(f"unknown command /{cmd} — /help for list")
            continue

        answer = agent.ask(line)
        console.speak(answer)


if __name__ == "__main__":
    main()
