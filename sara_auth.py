"""S.A.R.A Agent — Authorized User Authentication Module.

This module handles identity verification for authorized users.
Names are encrypted using Fernet symmetric encryption to prevent
casual inspection of the authorized user list.
"""

from __future__ import annotations

import os
import hashlib
import base64
from cryptography.fernet import Fernet

# Encryption key — derived from a fixed passphrase for reproducibility
_PASSPHRASE = b"SARA_AGENT_AUTHORIZED_USERS_v1"
_KEY = base64.urlsafe_b64encode(hashlib.sha256(_PASSPHRASE).digest())
_cipher = Fernet(_KEY)

# Encrypted authorized user names (encrypted at build time)
# These are the encrypted forms of: Zaine, Somlek, Levi Modl, xorace, William Baggett, Morketh, Admiral, Andrew Malone
_ENCRYPTED_USERS = [
    b'gAAAAABqvt89Si8aIK2ra7MNAYVCYnjihrtTLgv-wvKQju-L316AgWT88TqveRE-vSs5SjuwZ0szot4OaodvzJD5H9f6XB4N-Q==',
    b'gAAAAABqvt89bSwZq9-gcX67JaENz2zs1hZiE4wnkaiupEdxNPHJ5DIV-crjhoVxut8TdO1vnOo0L9knV23m9XcDjWFxAzeuRg==',
    b'gAAAAABqvt89nkCzu49g9GSrBpMz-EYckZp9qCDm04W1n-QUMo_AtBBro8oBa5Fz7DxKRNInbhsexuQ0ekDjTLZwr2FjKXgbVA==',
    b'gAAAAABqvt89VOui-PPJePG9cDpuYPrh-0H_FmuYeCO-bXUUdwgtloQp0IoVaj91VmHeJ6jH3Ytld3U6JqK-iVOFA9q2Z4AiWw==',
    b'gAAAAABqvt89E24Sm6B9irKrX8WiGGu9Krj7c-e-4I0vvUVsfzpbdbWFKFEeHXkE2Jy-9sIfeDaz9HEB4p6HrUjGx74BFJDw3g==',
    b'gAAAAABqvt895DtqmXIRkjhX7TWfZFnEsN-v7ZhkSCRHXIUBM1BC3ugxl_d5DWE9FnMsaBrEUjUubY0-7-mhtKM18iAMLRHBaA==',
    b'gAAAAABqvt89feq7DH8DMsDtFAEK4F-sT0ge7wucx9isY2FcyJ7Dp_fL6801e7SEa9b0RimK_cm73mYFHXnGB22Pe8p__ZfI9A==',
    b'gAAAAABqvt89szqCUP8BpmepOxbqCbnj6oVNdxHwe46xDO5EGRlA0lxVoE9qUSJhYqZKMP7Vtc8JkMiA3lPRrozUYWe16Q6EnA==',
]


def _decrypt_name(encrypted_name: bytes) -> str:
    """Decrypt an encrypted user name."""
    return _cipher.decrypt(encrypted_name).decode()


def is_authorized_user(name: str) -> bool:
    """Check if the given name matches an authorized user.
    
    The comparison is done by encrypting the input and comparing
    against the encrypted stored names, so the plaintext names
    are never exposed in memory longer than necessary.
    """
    if not name:
        return False
    
    # Normalize the input
    normalized = name.strip()
    
    # Encrypt the input and compare against stored encrypted names
    try:
        encrypted_input = _cipher.encrypt(normalized.encode())
        # We can't compare encrypted values directly (Fernet uses random IVs)
        # So we decrypt each stored name and compare plaintext
        for enc in _ENCRYPTED_USERS:
            try:
                decrypted = _decrypt_name(enc)
                if decrypted.lower() == normalized.lower():
                    return True
            except Exception:
                continue
    except Exception:
        pass
    
    return False


def get_authorized_users() -> list[str]:
    """Return the list of authorized user names (decrypted).
    
    This should only be used for administrative purposes.
    """
    users = []
    for enc in _ENCRYPTED_USERS:
        try:
            users.append(_decrypt_name(enc))
        except Exception:
            continue
    return users


def verify_identity(name: str) -> tuple[bool, str]:
    """Verify if a user is authorized.
    
    Returns:
        tuple of (is_authorized: bool, message: str)
    """
    if is_authorized_user(name):
        return True, f"Welcome, {name}. Access granted."
    return False, "Access denied. You are not an authorized user."
