"""Encrypt/decrypt user API keys at rest."""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


def _fernet() -> Fernet:
    secret = os.getenv("FINLONGRAG_SECRET_KEY") or os.getenv("SECRET_KEY") or "finlongrag-dev-secret"
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(stored: str) -> str:
    """Decrypt Fernet payload; fall back to legacy base64 for migrated rows."""
    try:
        return _fernet().decrypt(stored.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return base64.b64decode(stored.encode("utf-8")).decode("utf-8")
