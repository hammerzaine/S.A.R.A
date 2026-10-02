"""S.A.R.A Auth CLI — Command-line credential management.

Usage:
    sara auth                          # Show status
    sara auth list [PROVIDER]          # List credentials
    sara auth add PROVIDER KEY [LABEL] # Add a credential
    sara auth remove PROVIDER ID       # Remove a credential
    sara auth set-active PROVIDER      # Set active provider
    sara auth import-hermes            # Import from ~/.hermes/auth.json
    sara auth test PROVIDER            # Test a provider connection
"""

from __future__ import annotations

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Optional

# Add the SaraAgent directory to the path
SARA_ROOT = Path(__file__).parent
sys.path.insert(0, str(SARA_ROOT))

from sara_auth_store import (
    get_auth_store,
    PROVIDERS,
    list_credentials,
    add_credential,
    remove_credential,
)


def cmd_status(args):
    """Show auth status."""
    store = get_auth_store()
    store.load()

    active = store.get_active_provider()
    providers = store.list_providers()

    print("S.A.R.A Auth Store")
    print("=" * 50)
    print(f"Active provider: {active or '(none)'}")
    print(f"Configured providers: {len(providers)}")
    print()

    for provider in providers:
        status = store.get_provider_status(provider)
        name = status["name"]
        total = status["total_credentials"]
        available = status["available_credentials"]
        print(f"  {name} ({provider})")
        print(f"    Credentials: {available}/{total} available")

        for entry in status["entries"]:
            status_icon = "✓" if entry["status"] == "active" else "✗"
            print(f"    [{status_icon}] {entry['label']} ({entry['id']})")
        print()


def cmd_list(args):
    """List credentials for a provider."""
    store = get_auth_store()
    store.load()

    provider = args.provider
    if provider:
        if provider not in PROVIDERS:
            print(f"Unknown provider: {provider}")
            print(f"Available: {', '.join(PROVIDERS.keys())}")
            return

        status = store.get_provider_status(provider)
        print(f"{status['name']} ({provider})")
        print(f"  {status['description']}")
        print(f"  Auth type: {status['auth_type']}")
        print()

        if not status["entries"]:
            print("  No credentials configured.")
            return

        for entry in status["entries"]:
            status_icon = "✓" if entry["status"] == "active" else "✗"
            print(f"  [{status_icon}] {entry['label']}")
            print(f"      ID: {entry['id']}")
            print(f"      Status: {entry['status']}")
            if entry["last_error"]:
                print(f"      Last error: {entry['last_error']}")
            print()
    else:
        # List all providers
        result = list_credentials()
        print("Configured providers:")
        for provider, status in result["providers"].items():
            name = status["name"]
            total = status["total_credentials"]
            available = status["available_credentials"]
            print(f"  {provider}: {name} ({available}/{total} available)")


def cmd_add(args):
    """Add a credential."""
    provider = args.provider
    api_key = args.key
    label = args.label or ""

    if provider not in PROVIDERS:
        print(f"Unknown provider: {provider}")
        print(f"Available: {', '.join(PROVIDERS.keys())}")
        return

    if not api_key:
        print("Error: API key is required")
        return

    # Check if key is from environment
    if api_key.startswith("$"):
        env_var = api_key[1:]
        api_key = os.environ.get(env_var, "")
        if not api_key:
            print(f"Error: Environment variable {env_var} not set")
            return

    store = get_auth_store()
    store.load()

    entry = store.add_credential(provider, api_key, label)
    print(f"Added {PROVIDERS[provider]['name']} credential: {entry.label}")
    print(f"  ID: {entry.id}")


def cmd_remove(args):
    """Remove a credential."""
    provider = args.provider
    entry_id = args.id

    store = get_auth_store()
    store.load()

    if store.remove_credential(provider, entry_id):
        print(f"Removed credential {entry_id} from {provider}")
    else:
        print(f"Credential {entry_id} not found in {provider}")


def cmd_set_active(args):
    """Set the active provider."""
    provider = args.provider

    if provider not in PROVIDERS:
        print(f"Unknown provider: {provider}")
        return

    store = get_auth_store()
    store.load()
    store.set_active_provider(provider)
    print(f"Active provider set to: {PROVIDERS[provider]['name']}")


def cmd_import_hermes(args):
    """Import credentials from Hermes auth.json."""
    store = get_auth_store()
    store.load()

    count = store.import_from_hermes()
    print(f"Imported {count} credential(s) from Hermes auth.json")


def cmd_test(args):
    """Test a provider connection."""
    provider = args.provider

    if provider not in PROVIDERS:
        print(f"Unknown provider: {provider}")
        return

    store = get_auth_store()
    store.load()

    cred = store.get_credential(provider)
    if not cred:
        print(f"No credential configured for {provider}")
        return

    print(f"Testing {PROVIDERS[provider]['name']}...")

    # Import the provider and test
    from agent_bridge import PROVIDERS as BRIDGE_PROVIDERS

    if provider not in BRIDGE_PROVIDERS:
        print(f"Provider {provider} not available in agent bridge")
        return

    provider_class = BRIDGE_PROVIDERS[provider]
    config = {
        "api_key": cred.api_key,
        "base_url": PROVIDERS[provider]["base_url"],
    }

    instance = provider_class(config)
    if instance.initialize():
        print(f"  ✓ Connection successful!")
    else:
        print(f"  ✗ Connection failed: {instance._init_error}")


def main():
    parser = argparse.ArgumentParser(description="S.A.R.A Auth Management")
    subparsers = parser.add_subparsers(dest="command")

    # status
    subparsers.add_parser("status", help="Show auth status")

    # list
    list_parser = subparsers.add_parser("list", help="List credentials")
    list_parser.add_argument("provider", nargs="?", help="Provider name")

    # add
    add_parser = subparsers.add_parser("add", help="Add a credential")
    add_parser.add_argument("provider", help="Provider name")
    add_parser.add_argument("key", help="API key (or $ENV_VAR)")
    add_parser.add_argument("--label", "-l", default="", help="Credential label")

    # remove
    remove_parser = subparsers.add_parser("remove", help="Remove a credential")
    remove_parser.add_argument("provider", help="Provider name")
    remove_parser.add_argument("id", help="Credential ID")

    # set-active
    active_parser = subparsers.add_parser("set-active", help="Set active provider")
    active_parser.add_argument("provider", help="Provider name")

    # import-hermes
    subparsers.add_parser("import-hermes", help="Import from Hermes auth.json")

    # test
    test_parser = subparsers.add_parser("test", help="Test provider connection")
    test_parser.add_argument("provider", help="Provider name")

    args = parser.parse_args()

    if args.command == "status":
        cmd_status(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "add":
        cmd_add(args)
    elif args.command == "remove":
        cmd_remove(args)
    elif args.command == "set-active":
        cmd_set_active(args)
    elif args.command == "import-hermes":
        cmd_import_hermes(args)
    elif args.command == "test":
        cmd_test(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
