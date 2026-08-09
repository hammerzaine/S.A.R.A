# S.A.R.A — Cross-Platform Install Bundle

S.A.R.A (Smart AI Research Assistant) is a self-upgrading research agent with
visible reasoning, persistent memory, and a web UI. This bundle installs it on
**Linux, macOS, and Windows** with one command.

## What's in the box
- `install-bundle/`    — the OS install scripts + requirements + self-contained source
- `install-bundle/src/` — bundled `sara.py`, `sara/`, and `web/` (so a bare copy installs with no network/SSH)

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
1. verifies that `sara.py`, `sara/`, and `web/` exist in the install dir,
2. if not, bootstraps them from `install-bundle/src` (always present) or another local source bundle,
3. creates a local `.venv` (no system-Python changes),
4. installs dependencies from `install-bundle/requirements.txt`,
5. writes a `bin/sara` (or `bin\\sara.bat`) launcher.

The bundle is **self-contained**: `install-bundle/src` ships the full source, so
`bash install-bundle/install.sh` works from a bare `install-bundle/` copy with
no network access and no SSH to any server.

### Machine-readable source-bundle lookup order

When the installer needs to bootstrap core files, it checks these paths in order
and copies `sara.py`, `sara/`, and `web/` from the first match:

- `install-bundle/src`  ← bundled, always present
- `~/SARA`
- `~/sara`
- `.upgrade_tmp`
- `dist-clean`
- `../SARA`
- `../sara`
- `/srv/SARA`
- `/srv/sara`
- `/opt/SARA`
- `/opt/sara`

If nothing is found, the installer prints the missing-file checklist and exits.

### Shared server path (optional, same-machine/LAN NFS only)

For setups where the source repo lives on a server filesystem that users can read
but should not SSH into, expose it at `/srv/SARA`. The bundled installer already
checks that path. Permissions on `/srv/SARA` should be world-readable:

```bash
sudo mkdir -p /srv/SARA
sudo git clone /path/to/SARA /srv/SARA
sudo chmod -R a+rX /srv/SARA
```

Note: `/srv/SARA` only helps if that path is already visible on the target
machine (shared mount or same host). It does NOT reach across the network on its
own — that's what `install-bundle/src` is for.

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
  "model": "tencent/hy3:free",
  "fallback_models": ["stepfun/step-3.7-flash:free"]
}
```
Edit `config.json` to swap providers or point at a local Ollama if you prefer.

## Notes
- `credentials.json`, `config.json`, and the memory DB (`data/sara.db`) are
  git-ignored and never shipped in the repo. They're created locally on first
  run / first upgrade.
- To upgrade later: `bin/sara upgrade <repo-url> [branch]`
  (uses `sara_upgrade.py` — backs up, pulls, verifies, rolls back on failure).
