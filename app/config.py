"""Central configuration for CineBite.

Everything comes from the .env file sitting next to this project folder so the
same code runs unchanged in test mode or live mode - you only swap keys.
"""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"


def _load_env() -> None:
    if not ENV_PATH.exists():
        return
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _ensure_secret_key() -> str:
    """Generate and persist a strong secret on first run (used for OTP/session tokens)."""
    existing = os.environ.get("SECRET_KEY", "").strip()
    if existing:
        return existing
    generated = secrets.token_hex(32)
    os.environ["SECRET_KEY"] = generated
    try:
        with ENV_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"\n# Auto-generated on first run - do not share\nSECRET_KEY={generated}\n")
    except OSError:
        pass
    return generated


_load_env()
SECRET_KEY = _ensure_secret_key()


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


# ---------------------------------------------------------------- app
APP_NAME = "CineBite"
APP_URL = env("APP_URL", "http://localhost:8000")
HOST = env("HOST", "0.0.0.0")
PORT = int(env("PORT", "8000"))

# ---------------------------------------------------------------- OTP via Email (SMTP)
SMTP_HOST = env("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(env("SMTP_PORT", "587"))
SMTP_USER = env("SMTP_USER")
SMTP_PASSWORD = env("SMTP_PASSWORD")
SMTP_FROM = env("SMTP_FROM") or SMTP_USER
SMTP_STARTTLS = env("SMTP_STARTTLS", "true").lower() == "true"
SMTP_SSL = env("SMTP_SSL", "false").lower() == "true"


def email_configured() -> bool:
    return bool(SMTP_USER and SMTP_PASSWORD)


# ---------------------------------------------------------------- Razorpay (test mode now, live keys later)
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET")


def razorpay_configured() -> bool:
    return bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)


# ---------------------------------------------------------------- timings (seconds)
OTP_TTL = int(env("OTP_TTL", "300"))            # 5 minutes
OTP_MAX_ATTEMPTS = int(env("OTP_MAX_ATTEMPTS", "5"))
OTP_RESEND_COOLDOWN = int(env("OTP_RESEND_COOLDOWN", "45"))
OTP_WINDOW = int(env("OTP_WINDOW", "600"))      # sliding window for rate limit
OTP_WINDOW_MAX = int(env("OTP_WINDOW_MAX", "4"))
BOOKING_HOLD_SECONDS = int(env("BOOKING_HOLD_SECONDS", "600"))  # seats held 10 min before payment
SESSION_TTL = int(env("SESSION_TTL", str(60 * 24 * 30)))        # 30 days


def status_report() -> dict:
    """Used by the frontend to show honest setup status - never a fake success."""
    return {
        "email": email_configured(),
        "razorpay": razorpay_configured(),
        "razorpay_mode": "test" if RAZORPAY_KEY_ID.startswith("rzp_test_") else (
            "live" if RAZORPAY_KEY_ID.startswith("rzp_live_") else "unconfigured"
        ),
    }
