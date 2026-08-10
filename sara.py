#!/usr/bin/env python3
"""S.A.R.A unified launcher — cross-platform entry point.

Boot the agent as either:
  python sara.py            -> interactive CLI
  python sara.py "ask..."   -> one-shot answer
  python sara.py web         -> web UI on :8800 (--host/--port supported)
  python sara.py status      -> model/connection check

This single script is the only thing the install scripts need to invoke, so
Linux / macOS / Windows all share one boot path.
"""
from __future__ import annotations
import sys
from pathlib import Path

# Make sure we import the bundled agent, not any system-installed copy.
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _boot_cli() -> int:
    from sara_cli import main as cli_main
    return cli_main()


def _boot_web() -> int:
    import argparse
    from web import main as web_main
    # web.py has its own argparse, but we strip our own subcommand first.
    sys.argv = [sys.argv[0]] + sys.argv[2:] or [sys.argv[0]]
    return web_main()


def main() -> int:
    sub = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    if sub == "web":
        return _boot_web()
    if sub in ("status", "upgrade", "skills", "memory",
               "forget", "rename", "quiet", "verbose", "help", "clear"):
        # Delegate everything else to the CLI (it handles all /commands).
        return _boot_cli()
    # default + one-shot questions -> CLI
    return _boot_cli()


if __name__ == "__main__":
    sys.exit(main())
