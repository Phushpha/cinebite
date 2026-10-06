"""Verify the configured Razorpay test keys by creating a real order."""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = "http://127.0.0.1:8000"


def call(path, method="GET", body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


# 1. config status
_, cfg = call("/api/config")
print("1) razorpay:", cfg["razorpay"])
assert cfg["razorpay"]["configured"], "keys not picked up from .env"

# 2. token + booking
from app import security
from app.database import connect

with connect() as conn:
    row = conn.execute("SELECT id FROM users WHERE email='test@example.com'").fetchone()
    uid = row["id"] if row else conn.execute(
        "INSERT INTO users (email) VALUES ('test@example.com')"
    ).lastrowid
    conn.execute(
        "DELETE FROM seat_holds WHERE booking_id IN "
        "(SELECT id FROM bookings WHERE user_id=? AND status='held')", (uid,))
    conn.execute("UPDATE bookings SET status='expired' WHERE user_id=? AND status='held'",
                 (uid,))
    conn.commit()

tok = security.issue({"uid": uid}, 3600)

from datetime import date as date_cls
from datetime import datetime

today = date_cls.today().isoformat()
now_iso = datetime.now().isoformat(timespec="seconds")
with connect() as conn:
    row = conn.execute(
        "SELECT id FROM shows WHERE day>=? AND starts_at>? ORDER BY day, starts_at LIMIT 1",
        (today, now_iso),
    ).fetchone()
    show_id = row["id"]

s, seats = call(f"/api/shows/{show_id}/seats", token=tok)
free = [x["seat"] for x in seats["seats"] if x["seat"] not in seats["taken"]][:2]
print("2) show:", show_id, "seats:", free)

s, b = call("/api/bookings", "POST", {"show_id": show_id, "seats": free,
                                       "items": [{"id": 11, "qty": 1}]}, tok)
print("3) booking:", s, b.get("code"), "amount:", b.get("amount"))
assert s == 200

# 4. create a REAL razorpay order
s, p = call(f"/api/bookings/{b['booking_id']}/pay", "POST", {}, tok)
print("4) pay:", s, json.dumps(p, indent=None)[:400])
assert s == 200 and p.get("order_id", "").startswith("order_"), "no real order created"
print("   -> REAL Razorpay order created:", p["order_id"],
      "| amount:", p["amount"], "| currency:", p["currency"],
      "| key:", p["key_id"])

# cleanup
s, _ = call(f"/api/bookings/{b['booking_id']}/cancel", "POST", {}, tok)
print("5) cleanup cancel:", s)
print("\nALL GOOD - Razorpay test keys are live.")
