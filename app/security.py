"""Dependency-free signed tokens (HMAC-SHA256) used for OTP flow + user sessions."""
import base64
import hashlib
import hmac
import json
import time

from .config import SECRET_KEY


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(payload_b64: str) -> str:
    return _b64(hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).digest())


def issue(payload: dict, ttl: int) -> str:
    body = dict(payload)
    body["exp"] = int(time.time()) + ttl
    body_b64 = _b64(json.dumps(body, separators=(",", ":")).encode())
    return f"{body_b64}.{_sign(body_b64)}"


def verify(token: str) -> dict | None:
    if not token or "." not in token:
        return None
    body_b64, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(signature, _sign(body_b64)):
        return None
    try:
        payload = json.loads(_unb64(body_b64))
    except (ValueError, TypeError):
        return None
    if int(payload.get("exp", 0)) < time.time():
        return None
    return payload
