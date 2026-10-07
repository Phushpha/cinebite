"""Real OTP delivery over Email (SMTP).

No console-printed codes anywhere: if the provider is not configured the
caller gets an explicit error instead of a fake success.
"""
import random
import smtplib
import ssl
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from . import config
from .database import connect


class OtpError(RuntimeError):
    pass


def generate_code() -> str:
    return f"{random.SystemRandom().randint(0, 999999):06d}"


def _hash_code(code: str) -> str:
    import hashlib
    return hashlib.sha256(f"{config.SECRET_KEY}:{code}".encode()).hexdigest()


# ------------------------------------------------------------------ rate limiting
def _check_limits(destination: str) -> None:
    now = int(time.time())
    with connect() as conn:
        row = conn.execute(
            "SELECT created_at FROM otps WHERE destination=? AND verified=0 "
            "ORDER BY id DESC LIMIT 1",
            (destination,),
        ).fetchone()
        if row:
            # sqlite datetime('now') is UTC string; convert crudely
            import calendar
            created = calendar.timegm(time.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S"))
            if now - created < config.OTP_RESEND_COOLDOWN:
                wait = config.OTP_RESEND_COOLDOWN - (now - created)
                raise OtpError(f"Please wait {wait}s before requesting another code.")
        recent = conn.execute(
            "SELECT COUNT(*) c FROM otps WHERE destination=? ORDER BY id DESC LIMIT ?",
            (destination, config.OTP_WINDOW_MAX),
        ).fetchone()["c"]
        if recent >= config.OTP_WINDOW_MAX:
            raise OtpError("Too many requests for this number/email. Try again later.")


# ------------------------------------------------------------------ delivery
def _send_email(destination: str, code: str) -> None:
    text = f"Your {config.APP_NAME} login code is {code}. It expires in 5 minutes."
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;padding:24px;
                border:1px solid #eee;border-radius:12px">
      <h2 style="color:#e11d48;margin-top:0">🍿 {config.APP_NAME}</h2>
      <p>Your one-time login code is:</p>
      <p style="font-size:32px;letter-spacing:10px;font-weight:bold">{code}</p>
      <p style="color:#666">Valid for 5 minutes. Never share this code with anyone.</p>
    </div>"""

    # Prefer Resend API if configured (works well on Render)
    if getattr(config, "RESEND_API_KEY", None):
        try:
            with httpx.Client(timeout=30.0) as client:
                from_email = getattr(config, "RESEND_FROM", None) or "onboarding@resend.dev"
                # Resend accepts either "email@domain.com" or "Name <email@domain.com>"
                # For onboarding@resend.dev, plain email usually works
                r = client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {config.RESEND_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "from": from_email,
                        "to": [destination],
                        "subject": f"{config.APP_NAME} login code: {code}",
                        "text": text,
                        "html": html,
                    },
                )
                if r.status_code >= 400:
                    raise OtpError(f"Failed to send email: {r.text}")
            return
        except httpx.HTTPError as exc:
            raise OtpError(f"Failed to send email via Resend: {exc}") from exc

    if not config.email_configured():
        raise OtpError(
            "Email OTP is not configured. Set SMTP_USER/SMTP_PASSWORD or RESEND_API_KEY."
        )
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{config.APP_NAME} login code: {code}"
    msg["From"] = config.SMTP_FROM
    msg["To"] = destination
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    try:
        context = ssl.create_default_context()
        if config.SMTP_SSL:
            with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=context, timeout=60) as server:
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
                server.sendmail(config.SMTP_FROM, [destination], msg.as_string())
        else:
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=60) as server:
                server.ehlo()
                if config.SMTP_STARTTLS:
                    server.starttls(context=context)
                    server.ehlo()
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
                server.sendmail(config.SMTP_FROM, [destination], msg.as_string())
    except smtplib.SMTPAuthenticationError as exc:
        raise OtpError("SMTP login failed.") from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise OtpError(f"Could not reach the mail server: {exc}") from exc


# ------------------------------------------------------------------ public API
def request_otp(channel: str, destination: str) -> int:
    """Generate + deliver an OTP. Returns the otp row id. Raises OtpError on failure."""
    destination = destination.strip()
    if channel == "email":
        destination = destination.lower()
    elif channel != "email":
        raise OtpError("Only email OTP login is available.")
    _check_limits(destination)
    code = generate_code()
    _send_email(destination, code)
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO otps (channel, destination, code_hash, expires_at) VALUES (?,?,?,?)",
            (channel, destination, _hash_code(code), int(time.time()) + config.OTP_TTL),
        )
        conn.commit()
        return cur.lastrowid


def verify_otp(destination: str, code: str) -> bool:
    now = int(time.time())
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM otps WHERE destination=? AND verified=0 AND expires_at>=? "
            "ORDER BY id DESC LIMIT 1",
            (destination.strip().lower(), now),
        ).fetchone() or conn.execute(
            "SELECT * FROM otps WHERE destination=? AND verified=0 AND expires_at>=? "
            "ORDER BY id DESC LIMIT 1",
            (destination.strip(), now),
        ).fetchone()
        if not row:
            return False
        if row["attempts"] >= config.OTP_MAX_ATTEMPTS:
            conn.execute("UPDATE otps SET expires_at=0 WHERE id=?", (row["id"],))
            conn.commit()
            return False
        if row["code_hash"] != _hash_code(code):
            conn.execute("UPDATE otps SET attempts=attempts+1 WHERE id=?", (row["id"],))
            conn.commit()
            return False
        conn.execute("UPDATE otps SET verified=1 WHERE id=?", (row["id"],))
        conn.commit()
        return True
