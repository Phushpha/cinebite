"""Razorpay integration: order creation, signature verification, webhook auth.

Works against test keys now (rzp_test_...) and live keys later - only the .env
values change, this code path is identical.
"""
import hashlib
import hmac
import json

import httpx

from . import config
from .database import connect

API_BASE = "https://api.razorpay.com/v1"


class PaymentError(RuntimeError):
    pass


def _auth() -> tuple[str, str]:
    if not config.razorpay_configured():
        raise PaymentError(
            "Razorpay keys are missing. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET "
            "to the .env file (Dashboard → Settings → API Keys)."
        )
    return (config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET)


def create_order(amount_inr: int, receipt: str, notes: dict | None = None) -> dict:
    """Create a Razorpay order. Amount is in rupees; API expects paise."""
    try:
        resp = httpx.post(
            f"{API_BASE}/orders",
            auth=_auth(),
            json={
                "amount": amount_inr * 100,
                "currency": "INR",
                "receipt": receipt,
                "notes": notes or {},
            },
            timeout=20,
        )
    except httpx.HTTPError as exc:
        raise PaymentError(f"Could not reach Razorpay: {exc}") from exc
    if resp.status_code != 200:
        raise PaymentError(f"Razorpay order failed: {resp.text[:300]}")
    return resp.json()


def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    expected = hmac.new(
        config.RAZORPAY_KEY_SECRET.encode(),
        f"{order_id}|{payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_webhook_signature(body: bytes, signature: str) -> bool:
    if not config.RAZORPAY_WEBHOOK_SECRET:
        return False
    expected = hmac.new(config.RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def settle_booking(order_id: str, payment_id: str) -> dict | None:
    """Mark booking paid after signature verification passed."""
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM bookings WHERE rzp_order_id=?", (order_id,)
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE bookings SET status='paid', rzp_payment_id=?, paid_at=datetime('now') "
            "WHERE id=?",
            (payment_id, row["id"]),
        )
        conn.execute("DELETE FROM seat_holds WHERE booking_id=?", (row["id"],))
        conn.commit()
        return dict(row)


def handle_webhook(event: dict) -> None:
    """Razorpay calls this server-side so bookings settle even if the browser closed."""
    event_type = event.get("event", "")
    payment = (
        event.get("payload", {}).get("payment", {}).get("entity", {})
    )
    if not payment:
        return
    order_id = payment.get("order_id")
    payment_id = payment.get("id")
    status = payment.get("status")
    if not order_id or not payment_id:
        return
    if event_type == "payment.captured" or status == "captured":
        settle_booking(order_id, payment_id)
    elif status == "failed":
        with connect() as conn:
            conn.execute(
                "UPDATE bookings SET status='cancelled' WHERE rzp_order_id=? AND status='held'",
                (order_id,),
            )
            conn.commit()
