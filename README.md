# S.A.R.A Agent

**Smart AI Resource Assistant** — A personalized AI agent built on the Hermes Agent framework.

## Features

- **CLI Interface** — Full-featured command-line interface with Sara's custom branding
- **Web UI** — Built-in web interface for browser-based chat
- **Authorization System** — Bypass billing for authorized users
- **Encrypted Names** — Authorized user names are encrypted in the source code
- **Upgrade System** — Built-in upgrade mechanism

## Quick Start

### Install Dependencies

```bash
pip install fastapi uvicorn cryptography
```

### Launch

```bash
# Launch both CLI and Web UI
python sara_launcher.py

# Launch only CLI
python sara_launcher.py --cli-only

# Launch only Web UI
python sara.py --web-only --port 8800
```

### Access Web UI

Open your browser and navigate to:
```
http://localhost:8800
```

## Configuration

Edit `config.yaml` to configure:
- Model provider and settings
- Tool permissions
- Display preferences
- Memory settings

## Authorization

Authorized users (names encrypted in `sara_auth.py`) can bypass billing checks.
To add or modify authorized users, edit the `_ENCRYPTED_USERS` list in `sara_auth.py`.

## Upgrade

The agent supports upgrades via the `/upgrade` command in the CLI or web interface.

## License

MIT License — Based on Hermes Agent by Nous Research
