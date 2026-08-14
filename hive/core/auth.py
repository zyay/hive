"""
JWT Authentication for Hive API.
"""

import os
import time
import json
import hashlib
import hmac
import base64
import secrets
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SECRET_KEY_FILE = Path("hive_secret.key")
TOKEN_EXPIRY = 7 * 86400  # 7 days


def _get_secret_key() -> str:
    """Get or generate the JWT secret key."""
    # First check environment variable
    env_key = os.getenv("HIVE_SECRET_KEY")
    if env_key:
        return env_key
    # Then check file
    if SECRET_KEY_FILE.exists():
        return SECRET_KEY_FILE.read_text().strip()
    # Generate new random key and save
    new_key = secrets.token_hex(32)
    SECRET_KEY_FILE.write_text(new_key)
    logger.info("Generated new JWT secret key (saved to hive_secret.key)")
    return new_key


SECRET_KEY = _get_secret_key()


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _base64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def create_token(user_id: str, role: str = "user") -> str:
    """Create a JWT token."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_EXPIRY,
    }

    header_b64 = _base64url_encode(json.dumps(header).encode())
    payload_b64 = _base64url_encode(json.dumps(payload).encode())
    signature = hmac.new(
        SECRET_KEY.encode(),
        f"{header_b64}.{payload_b64}".encode(),
        hashlib.sha256,
    ).digest()
    sig_b64 = _base64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{sig_b64}"


def verify_token(token: str) -> dict | None:
    """Verify a JWT token. Returns payload if valid, None if invalid."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None

        header_b64, payload_b64, sig_b64 = parts

        # Verify signature
        expected_sig = hmac.new(
            SECRET_KEY.encode(),
            f"{header_b64}.{payload_b64}".encode(),
            hashlib.sha256,
        ).digest()
        actual_sig = _base64url_decode(sig_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        # Decode payload
        payload = json.loads(_base64url_decode(payload_b64))

        # Check expiry
        if payload.get("exp", 0) < time.time():
            return None

        return payload

    except Exception as e:
        logger.debug(f"Token verification failed: {e}")
        return None


def create_api_token(name: str, permissions: list[str] = None) -> str:
    """Create a long-lived API token."""
    return create_token(user_id=name, role="api")
