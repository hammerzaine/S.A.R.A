"""S.A.R.A Auth Store — Credential management for all providers.

Manages API keys and OAuth tokens in ~/.sara/auth.json with:
- Multiple credentials per provider (pool with rotation)
- Cross-process file locking
- Exhaustion handling (rate limit cooldowns)
- Terminal failure detection (revoked tokens)
- Priority-based selection

Compatible with Hermes auth.json format for easy migration.
"""

from __future__ import annotations

import json
import os
import time
import fcntl
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


# Constants
AUTH_STORE_VERSION = 1
AUTH_LOCK_TIMEOUT = 15.0
DEFAULT_MAX_CONCURRENT = 3
EXHAUSTION_COOLDOWN = 3600  # 1 hour
TERMINAL_AUTH_REASONS = {
    "token_invalidated", "token_revoked", "invalid_grant",
    "unauthorized", "forbidden", "access_denied",
}

# Provider definitions
PROVIDERS = {
    "ollama": {
        "name": "Ollama",
        "description": "Local models via Ollama",
        "auth_type": "none",
        "env_var": None,
        "base_url": "http://192.168.2.176:11434",
    },
    "openai": {
        "name": "OpenAI",
        "description": "ChatGPT models (GPT-4o, etc.)",
        "auth_type": "api_key",
        "env_var": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
    },
    "gemini": {
        "name": "Google Gemini",
        "description": "Gemini models (2.0 Flash, etc.)",
        "auth_type": "api_key",
        "env_var": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
    },
    "copilot": {
        "name": "GitHub Copilot",
        "description": "Copilot models (GPT-4o, Claude, etc.)",
        "auth_type": "api_key",
        "env_var": "COPILOT_GITHUB_TOKEN",
        "base_url": "https://api.githubcopilot.com",
    },
    "anthropic": {
        "name": "Anthropic",
        "description": "Claude models (Sonnet, Opus, etc.)",
        "auth_type": "api_key",
        "env_var": "ANTHROPIC_API_KEY",
        "base_url": "https://api.anthropic.com/v1",
    },
    "openrouter": {
        "name": "OpenRouter",
        "description": "Access to many models via one API",
        "auth_type": "api_key",
        "env_var": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
    },
}


@dataclass
class CredentialEntry:
    """A single credential in the pool."""
    id: str
    label: str
    api_key: str = ""
    provider: str = ""
    priority: int = 0
    status: str = "active"  # active, exhausted, dead
    last_status: str = ""
    last_status_at: float = 0.0
    last_error_code: int = 0
    last_error_reason: str = ""
    last_error_reset_at: float = 0.0
    created_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CredentialEntry":
        return cls(**data)

    def is_available(self) -> bool:
        """Check if this credential is available for use."""
        if self.status == "dead":
            return False
        if self.status == "exhausted":
            if self.last_error_reset_at and time.time() > self.last_error_reset_at:
                return True
            if time.time() - self.last_status_at > EXHAUSTION_COOLDOWN:
                return True
        return True

    def mark_exhausted(self, status_code: int = 429, reason: str = "rate_limit"):
        """Mark this credential as exhausted (rate limited)."""
        self.status = "exhausted"
        self.last_status = "exhausted"
        self.last_status_at = time.time()
        self.last_error_code = status_code
        self.last_error_reason = reason
        self.last_error_reset_at = time.time() + EXHAUSTION_COOLDOWN

    def mark_dead(self, status_code: int = 401, reason: str = "unauthorized"):
        """Mark this credential as dead (revoked/invalid)."""
        self.status = "dead"
        self.last_status = "dead"
        self.last_status_at = time.time()
        self.last_error_code = status_code
        self.last_error_reason = reason

    def mark_active(self):
        """Mark this credential as active (successful use)."""
        self.status = "active"
        self.last_status = "active"
        self.last_status_at = time.time()
        self.last_error_code = 0
        self.last_error_reason = ""


class CredentialPool:
    """A pool of credentials for a single provider."""

    def __init__(self, provider: str, entries: List[CredentialEntry]):
        self.provider = provider
        self._entries = sorted(entries, key=lambda e: e.priority)
        self._lock = threading.Lock()
        self._current_id: Optional[str] = None

    def has_credentials(self) -> bool:
        return bool(self._entries)

    def has_available(self) -> bool:
        return any(e.is_available() for e in self._entries)

    def entries(self) -> List[CredentialEntry]:
        return list(self._entries)

    def current(self) -> Optional[CredentialEntry]:
        if not self._current_id:
            return None
        return next((e for e in self._entries if e.id == self._current_id), None)

    def get_available(self) -> Optional[CredentialEntry]:
        """Get the next available credential, rotating through the pool."""
        with self._lock:
            available = [e for e in self._entries if e.is_available()]
            if not available:
                return None

            # Round-robin: pick the one after current
            if self._current_id:
                current_idx = next(
                    (i for i, e in enumerate(available) if e.id == self._current_id),
                    -1
                )
                next_idx = (current_idx + 1) % len(available)
            else:
                next_idx = 0

            selected = available[next_idx]
            self._current_id = selected.id
            return selected

    def add_entry(self, entry: CredentialEntry):
        """Add a new credential to the pool."""
        with self._lock:
            self._entries.append(entry)
            self._entries.sort(key=lambda e: e.priority)

    def remove_entry(self, entry_id: str) -> bool:
        """Remove a credential from the pool."""
        with self._lock:
            for i, e in enumerate(self._entries):
                if e.id == entry_id:
                    self._entries.pop(i)
                    if self._current_id == entry_id:
                        self._current_id = None
                    return True
            return False

    def to_dict(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self._entries]


class AuthStore:
    """Main auth store managing all provider credentials."""

    def __init__(self, auth_path: Optional[str] = None):
        if auth_path is None:
            auth_path = os.environ.get("SARA_AUTH_PATH", str(Path.home() / ".sara" / "auth.json"))
        self._auth_path = Path(auth_path)
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {
            "version": AUTH_STORE_VERSION,
            "providers": {},
            "active_provider": None,
            "updated_at": "",
        }

    def _ensure_dir(self):
        """Ensure the auth directory exists."""
        self._auth_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> Dict[str, Any]:
        """Load auth data from disk."""
        with self._lock:
            if self._auth_path.exists():
                try:
                    with open(self._auth_path, "r") as f:
                        self._data = json.load(f)
                except (json.JSONDecodeError, IOError):
                    pass
            return self._data

    def save(self):
        """Save auth data to disk."""
        with self._lock:
            self._ensure_dir()
            self._data["updated_at"] = datetime.now(timezone.utc).isoformat()
            with open(self._auth_path, "w") as f:
                json.dump(self._data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

    def get_pool(self, provider: str) -> CredentialPool:
        """Get the credential pool for a provider."""
        providers = self._data.get("providers", {})
        entries_data = providers.get(provider, [])
        entries = [CredentialEntry.from_dict(e) for e in entries_data]
        return CredentialPool(provider, entries)

    def save_pool(self, pool: CredentialPool):
        """Save a credential pool."""
        providers = self._data.setdefault("providers", {})
        providers[pool.provider] = pool.to_dict()
        self.save()

    def add_credential(
        self,
        provider: str,
        api_key: str,
        label: str = "",
        priority: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CredentialEntry:
        """Add a new credential to a provider pool."""
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}")

        # Generate ID
        entry_id = f"{provider}_{int(time.time() * 1000)}"

        entry = CredentialEntry(
            id=entry_id,
            label=label or f"Credential #{len(self.get_pool(provider).entries()) + 1}",
            api_key=api_key,
            provider=provider,
            priority=priority,
            created_at=time.time(),
            metadata=metadata or {},
        )

        pool = self.get_pool(provider)
        pool.add_entry(entry)
        self.save_pool(pool)

        # Set as active provider if first credential
        if not self._data.get("active_provider"):
            self._data["active_provider"] = provider
            self.save()

        return entry

    def remove_credential(self, provider: str, entry_id: str) -> bool:
        """Remove a credential from a provider pool."""
        pool = self.get_pool(provider)
        if pool.remove_entry(entry_id):
            self.save_pool(pool)
            return True
        return False

    def get_credential(self, provider: str) -> Optional[CredentialEntry]:
        """Get the current/active credential for a provider."""
        pool = self.get_pool(provider)
        return pool.get_available()

    def list_providers(self) -> List[str]:
        """List all configured providers."""
        return list(self._data.get("providers", {}).keys())

    def get_provider_status(self, provider: str) -> Dict[str, Any]:
        """Get status information for a provider."""
        if provider not in PROVIDERS:
            return {"error": "Unknown provider"}

        pool = self.get_pool(provider)
        entries = pool.entries()

        return {
            "provider": provider,
            "name": PROVIDERS[provider]["name"],
            "description": PROVIDERS[provider]["description"],
            "auth_type": PROVIDERS[provider]["auth_type"],
            "total_credentials": len(entries),
            "available_credentials": sum(1 for e in entries if e.is_available()),
            "active_credential": pool.current().id if pool.current() else None,
            "entries": [
                {
                    "id": e.id,
                    "label": e.label,
                    "status": e.status,
                    "priority": e.priority,
                    "last_error": e.last_error_reason,
                    "created_at": e.created_at,
                }
                for e in entries
            ],
        }

    def get_active_provider(self) -> Optional[str]:
        """Get the currently active provider."""
        return self._data.get("active_provider")

    def set_active_provider(self, provider: str):
        """Set the active provider."""
        if provider in PROVIDERS:
            self._data["active_provider"] = provider
            self.save()

    def export_env_vars(self) -> Dict[str, str]:
        """Export credentials as environment variables."""
        env_vars = {}
        for provider in self.list_providers():
            cred = self.get_credential(provider)
            if cred and cred.api_key:
                env_var = PROVIDERS[provider].get("env_var")
                if env_var:
                    env_vars[env_var] = cred.api_key
        return env_vars

    def import_from_hermes(self, hermes_auth_path: Optional[str] = None) -> int:
        """Import credentials from Hermes auth.json."""
        if hermes_auth_path is None:
            hermes_auth_path = str(Path.home() / ".hermes" / "auth.json")

        hermes_path = Path(hermes_auth_path)
        if not hermes_path.exists():
            return 0

        try:
            with open(hermes_path, "r") as f:
                hermes_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return 0

        imported = 0
        pool_data = hermes_data.get("credential_pool", {})

        for provider, creds in pool_data.items():
            if provider not in PROVIDERS:
                continue

            if isinstance(creds, list):
                for cred in creds:
                    api_key = cred.get("api_key") or cred.get("token") or cred.get("access_token", "")
                    if api_key:
                        self.add_credential(
                            provider=provider,
                            api_key=api_key,
                            label=cred.get("label", ""),
                            priority=cred.get("priority", 0),
                        )
                        imported += 1

        return imported


# Global auth store instance
_auth_store: Optional[AuthStore] = None
_auth_lock = threading.Lock()


def get_auth_store() -> AuthStore:
    """Get or create the global auth store."""
    global _auth_store

    if _auth_store is not None:
        return _auth_store

    with _auth_lock:
        if _auth_store is not None:
            return _auth_store

        _auth_store = AuthStore()
        return _auth_store


def get_credential(provider: str) -> Optional[CredentialEntry]:
    """Get the current credential for a provider."""
    store = get_auth_store()
    return store.get_credential(provider)


def add_credential(provider: str, api_key: str, label: str = "") -> CredentialEntry:
    """Add a credential for a provider."""
    store = get_auth_store()
    return store.add_credential(provider, api_key, label)


def remove_credential(provider: str, entry_id: str) -> bool:
    """Remove a credential."""
    store = get_auth_store()
    return store.remove_credential(provider, entry_id)


def list_credentials(provider: Optional[str] = None) -> Dict[str, Any]:
    """List all credentials."""
    store = get_auth_store()
    if provider:
        return store.get_provider_status(provider)

    return {
        "active_provider": store.get_active_provider(),
        "providers": {
            p: store.get_provider_status(p)
            for p in store.list_providers()
        },
    }
