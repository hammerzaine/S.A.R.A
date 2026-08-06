# S.A.R.A — Smart AI Research Assistant

A conversational research agent with visible reasoning, persistent memory, and
web-backed self-teaching. Built to feel like a colleague, not a command parser.

## Run her

```bash
~/bin/sara                    # interactive
~/bin/sara "find the mtg folder"   # one-shot
```

## The four things she does differently

**1. You always see what she's doing.** Every turn narrates itself:

```
  · checking whether that host is reachable first
  [1] shell  ping -c2 192.168.2.225
      ok — exit 0, 4 lines of output
  · it's up, so the problem is auth not networking
```

Grey `·` lines are her reasoning. Amber `[n]` lines are real actions, printed
**before** they run. Green/red is the real result. `/quiet` hides reasoning,
`/verbose` restores it.

**2. She learns, and you can see the ledger.** When she solves something worth
keeping she saves a skill and says so loudly:

```
  ++ LEARNED: apache-vhost-subpath
     new skill saved
```

`/skills` shows every self-taught skill with a use counter, so growth is
measurable rather than a vibe. Skills that keep getting used float to the top
and are re-injected into her prompt when relevant.

**3. She looks things up.** When she doesn't know something she says so, then
uses `web_search` / `web_fetch` to go find out, forms a view, and saves what
was worth keeping. No bluffing.

**4. She won't fabricate.** The protocol forces her to emit an action and stop,
then answer from the *real* result. She asks for credentials rather than
guessing them, and reports failures exactly as they happened.

## Commands

```
/skills          what she has taught herself, and how often it's been used
/memory          durable facts she's picked up about you and your systems
/forget <text>   drop a fact
/status          model, connectivity, counts
/quiet /verbose  reasoning visibility
/help  /quit
```

## Tools

| tool | does |
|---|---|
| `list_dir` | list folders and files |
| `find_path` | find a file/folder by name anywhere |
| `read_file` | read a text file |
| `write_file` | write a file |
| `shell` | run a command (destructive ones need confirmation) |
| `web_search` | search the web |
| `web_fetch` | read a page |

## Layout

```
~/SARA/
  sara_cli.py        entry point
  SOUL.md            personality — edit to change who she is
  config.json        model + endpoint
  sara/
    agent.py         the reason→act→observe→learn loop
    brain.py         LLM client + protocol parsing
    tools.py         every capability
    memory.py        turns, facts, skills (SQLite)
    console.py       all output formatting
  data/sara.db       her memory
```

## Configuration

`config.json`:

```json
{
  "base_url": "http://127.0.0.1:11434/v1",
  "model": "qwen2.5:7b-instruct-q4_K_M",
  "max_steps": 6,
  "verbose": true
}
```

**Model choice matters more than anything else here.** The agent loop is only
as good as the model's ability to emit an action and *wait*. Models under ~7B
routinely emit a correct tool call and then hallucinate the answer in the same
breath instead of pausing for the real result. Use a 7B+ instruct model.

## Design rules (don't undo these)

1. **One tool contract.** Every tool has `run(arg) -> dict`. The previous build
   dispatched some tools via `.run()` and others via `.list()`/`.read()`, so
   any tool whose entrypoint wasn't `run` silently returned `None`.
2. **Never log a failure as an `assistant` turn.** Assistant turns are replayed
   as context; the model then parrots stale errors back forever. `memory.log()`
   enforces this — failures become role `system`.
3. **Announce before acting**, never after.
4. **Prune heavy directories** when walking the filesystem, or `find_path`
   hangs for a minute on `.ollama` blobs and `.venv`s.
