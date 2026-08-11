# S.A.R.A — Smart AI Resource Assistant

S.A.R.A is an **agent loop, not an LLM wrapper**. A model answers a prompt;
an agent *does* something about it. S.A.R.A's model is the reasoning engine
inside a loop that acts through tools, observes real results, and decides the
next step — she is not a chatbot with a tool plugin bolted on.

## The loop (read this first)

Everything else in this document is a consequence of this cycle:

```
User request
    ↓
Reason            — decide what needs doing, pick a tool
    ↓
Announce action   — print the action BEFORE it runs (never after)
    ↓
Tool execution    — run the tool for real
    ↓
Real observation  — capture the actual result (stdout, exit code, rows)
    ↓
Reason over observation
    ↓
Answer  /  additional action  →  (loop)
    ↓
Learn if warranted — save a skill / fact when something is worth keeping
```

That single shape explains every design rule below: announce-before-acting,
the one-tool contract, the non-fabrication rule, memory, skills, and the
"observe, don't guess" discipline. A technically competent reader can infer
the loop from the pieces, but it is the spine — so it goes first.

## Run her

```bash
python3 sara.py                 # interactive CLI (default)
python3 sara.py "reboot the nas"   # one-shot answer, then exit
python3 sara.py web             # web UI on http://localhost:8800
python3 sara.py status          # model + connection check
python3 sara.py --help          # delegates to the CLI /commands
```

The unified launcher (`sara.py`) is the only boot path — Linux, macOS, and
Windows all share it. The web server defaults to port `8800` (`--port <n>`
to change).

## What she does differently

**1. You always see the agent working.** Every turn surfaces *visible agent
activity* — what she is actually doing, not the model's private reasoning.
Amber `[n]` lines announce each action *before* it runs; the real
result comes back green/red. For example:

```
· Inspecting the Apache configuration
[1] shell: grep -R "ProxyPass" /etc/apache2
✓ found 3 matching directives
```

That is a stronger claim than merely showing a model's reasoning: S.A.R.A
exposes *what the agent did* — each action and its real result, grounded in
tool output. `/quiet` hides activity, `/verbose` restores it.

**2. She learns, and you can see the ledger.** When she solves something
worth keeping she saves a skill and says so:

```
++ LEARNED: apache-vhost-subpath
   new skill saved
```

`/skills` lists every self-taught skill with a use counter, so growth is
measurable. Hot skills re-inject into her prompt when relevant.

**3. She looks things up.** When she doesn't know, she says so, then uses
`web_search` / `web_fetch` to find out, forms a view, and saves what was
worth keeping. No bluffing.

**4. She won't fabricate.** The protocol forces her to emit an action and
stop, then answer from the *real* result. She asks for credentials rather
than guessing them, and reports failures exactly as they happened. The loop
above is why: an answer must be traceable to a real observation, or it isn't
allowed.

## Commands (chat — CLI and web)

Slash commands are intercepted locally; the model never sees them.

```
/factoryreset    wipe memory + SOUL.md + config/credentials (needs --yes)
/skills          everything she's taught herself (with use counts)
/memory          durable facts she remembers about you + your systems
/forget <text>   drop a fact
/status          model + connection
/upgrade         pull her code from a git repo (or backup/rollback)
/rename <old> <new>   rename a saved skill
/quiet /verbose  agent-activity visibility
/clear           redraw the screen
/help            this list
/quit            goodbye
```

`/factoryreset` is destructive. Bare `/factoryreset` shows what will be wiped
and asks for confirmation; `/factoryreset --yes` performs it.

## Factory reset

`/factoryreset --yes` (chat command, CLI + web) — or the Python API
`s.reset_state(confirm=True)` — performs a full factory reset by wiping
learned state and returning her to a blank slate.

What it wipes:
- **Memory DB** — every store: turns, facts, skills, procedures. The
  `data/sara.db` file is kept (schema re-created on next boot) but all learned
  content is dropped.
- **SOUL.md** — blanked to 0 bytes. The agent falls back to the hard-coded
  `DEFAULT_SOUL` so she still has a voice.
- **config.json** — deleted. The agent falls back to `DEFAULT_CONFIG` on next
  boot (no provider/endpoint set).
- **credentials.json** — deleted. All stored secrets (e.g. GitHub PAT) are
  gone; the loader tolerates a missing file and returns an empty store.

What it preserves:
- The **code** itself and **upgrade_state.json**.

After wiping, if the `sara-web.service` systemd unit exists it is restarted
so the running service picks up the blank state. The restart is skipped when
`SARA_UPGRADE_NO_RESTART` is set (the web path owns its own restart).

> Warning: a factory reset is irreversible for config + credentials. There is
> no undo — re-enter your provider/keys afterwards via `config.json` or the
> config tool.

## Layout

```
SARA/
  sara.py            unified launcher (CLI / web / status)
  sara_cli.py        CLI entry point + chat command loop
  sara_upgrade.py    self-upgrade from git
  sara_trainer.py    offline capability trainer
  web.py             FastAPI web UI (port 8800) + chat command interception
  SOUL.md            personality layer — edit to change who she is
  config.json        model + endpoint (deleted by factory reset)
  credentials.json   stored secrets, chmod 600 (deleted by factory reset)
  sara/
    agent.py         the reason→act→observe→learn loop + reset_state()
    brain.py         LLM client + protocol parsing
    tools.py         every capability (shell, files, web, ssh, ...)
    memory.py        turns, facts, skills, procedures (SQLite)
    evolution.py     seed brain — baseline facts/skills on first boot
    version_check.py upgrade availability against a git remote
    console.py       all output formatting
  data/sara.db        her memory (wiped to empty by factory reset)
```

## Configuration

`config.json` (deleted by factory reset; regenerated from defaults):

```json
{
  "provider": "nous",
  "base_url": "https://portal.nousresearch.com/v1",
  "model": "stepfun/step-3.7-flash:free",
  "max_steps": 6,
  "verbose": true
}
```

Provider presets (`ollama`, `openai`, `openrouter`, `nous`, `fireworks`,
…) fill `base_url` for you when you set the `provider` key. A custom
`base_url` is preserved.

`credentials.json` holds secrets such as `github.token` for the upgrade
check. It is git-ignored and never baked into the install bundle.

**Model choice matters more than anything else here.** The agent loop is
only as good as the model's ability to emit an action and *wait*. Models
under ~7B routinely emit a correct tool call and then hallucinate the
answer in the same breath instead of pausing for the real result. Use a
7B+ instruct model.

## Design rules (don't undo these)

1. **One tool contract.** Every tool has `run(arg) -> dict`. A previous
   build dispatched some tools via `.run()` and others via `.list()`/
   `.read()`, so any tool whose entrypoint wasn't `run` silently returned
   `None`.
2. **Never log a failure as an `assistant` turn.** Assistant turns are
   replayed as context; the model then parrots stale errors back forever.
   `memory.log()` enforces this — failures become role `system`.
3. **Announce before acting**, never after. (A direct consequence of the
   loop: the action is printed *before* execution so the user sees intent,
   not a retrospective.)
4. **Prune heavy directories** when walking the filesystem, or `find_path`
   hangs for a minute on `.ollama` blobs and `.venv`s.
5. **Factory reset is destructive by design** — it erases config *and*
   credentials, not just memory. That is intentional: "reset" means reset.
