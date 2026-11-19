"""Authentication primitives (stdlib only, no extra crypto dependencies).

* Passwords: scrypt with a per-user random salt (``hashlib.scrypt``).
* Operator sessions: HMAC-SHA256 signed, expiring bearer tokens.
* Devices: random opaque tokens; only a SHA-256 hash is stored server-side.

Roles: ``viewer`` (read-only) < ``operator`` (scans, approvals, e-stop) <
``admin`` (policy, users, e-stop reset, device deletion).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from enum import Enum


class Role(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


ROLE_RANK = {Role.VIEWER: 0, Role.OPERATOR: 1, Role.ADMIN: 2}

_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), **_SCRYPT)
        return hmac.compare_digest(expected, actual)
    except (ValueError, TypeError):
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def create_token(subject: str, role: str, secret: str, ttl_seconds: int) -> str:
    payload = {"sub": subject, "role": role, "exp": int(time.time()) + ttl_seconds}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def decode_token(token: str, secret: str) -> dict | None:
    """Return the payload if the signature is valid and not expired, else None."""
    try:
        body, sig = token.split(".")
        expected = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_unb64(body))
        if int(payload.get("exp", 0)) < time.time():
            return None
        return payload
    except (ValueError, json.JSONDecodeError):
        return None


def generate_device_token() -> str:
    return "agd_" + secrets.token_urlsafe(32)


def hash_device_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
