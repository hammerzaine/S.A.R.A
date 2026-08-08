# S.A.R.A — Cross-Platform Install Bundle

S.A.R.A (Smart AI Research Assistant) is a self-upgrading research agent with
visible reasoning, persistent memory, and a web UI. This bundle installs it on
**Linux, macOS, and Windows** with one command.

## What's in the box
- `sara.py`            — unified launcher (CLI + web)
- `sara_cli.py`        — interactive terminal client
- `web.py`             — FastAPI web UI (SSE streaming)
- `sara/`              — the agent core (agent loop, LLM client, tools, memory)
- `sara_upgrade.py`    — safe git-based self-upgrade toolkit
- `web/`               — the browser UI assets
- `install-bundle/`    — the OS install scripts + requirements

## Install (one command per OS)

**Linux / macOS**
```bash
bash install-bundle/install.sh
```

**Windows (PowerShell)**
```powershell
powershell -ExecutionPolicy Bypass -File install-bundle\install.ps1
```

Each installer:
1. creates a local `.venv` (no system-Python changes),
2. installs dependencies from `install-bundle/requirements.txt`,
3. writes a `bin/sara` (or `bin\sara.bat`) launcher.

## Run
```bash
bin/sara                 # interactive CLI
bin/sara "your question" # one-shot answer
bin/sara web             # web UI -> http://localhost:8800
bin/sara status          # model / connection check
```

## Requirements
- Python 3.10 or newer.
- An OpenAI-compatible model endpoint — **Nous Portal** is the recommended
  option (`https://portal.nousresearch.com/v1`). Set it in `config.json`
  (`base_url` / `model`) or via the web UI's config panel.

## Default config after install
```json
{
  "provider": "nous",
  "base_url": "https://portal.nousresearch.com/v1",
  "model": "stepfun/step-3.7-flash:free",
  "fallback_models": ["stepfun/step-3.5-flash:free"]
}
```
Edit `config.json` to swap providers or point at a local Ollama if you prefer.

## Notes
- `credentials.json`, `config.json`, and the memory DB (`data/sara.db`) are
  git-ignored and never shipped in the repo. They're created locally on first
  run / first upgrade.
- To upgrade later: `bin/sara upgrade <repo-url> [branch]`
  (uses `sara_upgrade.py` — backs up, pulls, verifies, rolls back on failure).
