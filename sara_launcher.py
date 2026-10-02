#!/usr/bin/env python3
"""S.A.R.A Agent — Unified Launcher

This script launches the S.A.R.A agent with all components:
- CLI interface with Sara's branding
- Web UI for browser-based chat
- Authorization system for bypassing billing
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path

# Add the SaraAgent directory to the path
SARA_ROOT = Path(__file__).parent
sys.path.insert(0, str(SARA_ROOT))

def check_dependencies():
    """Check if required dependencies are installed."""
    required = ["fastapi", "uvicorn", "cryptography"]
    missing = []
    
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    
    if missing:
        print(f"Missing dependencies: {', '.join(missing)}")
        print("Install with: pip install " + " ".join(missing))
        return False
    return True

def launch_cli():
    """Launch the CLI interface."""
    print("Starting S.A.R.A CLI...")
    # Import and run the Hermes CLI with Sara's branding
    from cli import main
    main()

def launch_web(host="0.0.0.0", port=8800):
    """Launch the web UI."""
    print(f"Starting S.A.R.A Web UI on {host}:{port}...")
    from web_ui import start_web_server
    start_web_server(host=host, port=port)

def launch_both(web_port=8800):
    """Launch both CLI and web UI."""
    import threading
    
    # Start web server in a separate thread
    web_thread = threading.Thread(
        target=launch_web,
        args=("0.0.0.0", web_port),
        daemon=True
    )
    web_thread.start()
    
    # Start CLI in the main thread
    launch_cli()

def main():
    parser = argparse.ArgumentParser(description="S.A.R.A Agent Launcher")
    parser.add_argument(
        "--web-only",
        action="store_true",
        help="Launch only the web UI"
    )
    parser.add_argument(
        "--cli-only",
        action="store_true",
        help="Launch only the CLI"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Web server host (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8800,
        help="Web server port (default: 8800)"
    )
    
    args = parser.parse_args()
    
    if not check_dependencies():
        sys.exit(1)
    
    if args.web_only:
        launch_web(args.host, args.port)
    elif args.cli_only:
        launch_cli()
    else:
        launch_both(args.port)

if __name__ == "__main__":
    main()
