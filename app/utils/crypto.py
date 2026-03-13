"""Fernet symmetric encryption for sensitive fields (API tokens, credentials)."""

import os
from cryptography.fernet import Fernet, InvalidToken


def _get_cipher() -> Fernet:
    """Get Fernet cipher from A7_ENCRYPTION_KEY env var."""
    key = os.environ.get("A7_ENCRYPTION_KEY", "").strip()
    if not key:
        return None
    return Fernet(key.encode())


def encrypt_field(plaintext: str) -> str:
    """Encrypt a string field. Returns plaintext unchanged if no key configured."""
    if not plaintext:
        return plaintext
    cipher = _get_cipher()
    if cipher is None:
        return plaintext  # encryption disabled — backward compatible
    return cipher.encrypt(plaintext.encode()).decode()


def decrypt_field(value: str) -> str:
    """Decrypt a string field. Returns value unchanged if not encrypted or no key."""
    if not value:
        return value
    cipher = _get_cipher()
    if cipher is None:
        return value  # encryption disabled
    try:
        return cipher.decrypt(value.encode()).decode()
    except (InvalidToken, Exception):
        return value  # not encrypted (e.g., legacy plaintext) — return as-is
