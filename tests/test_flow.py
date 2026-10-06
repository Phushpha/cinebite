"""End-to-end API test: auth token, booking hold, seat locking, payment error path."""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import security
from app.database import connect

# create the test user (in the real flow, OTP verification creates it)
with connect() as conn:
    row = conn.execute("SELECT id FROM users WHERE email='test@example.com'").fetchone()
    uid = row["id"] if row else conn.execute(
        "INSERT INTO users (email, last_login) VALUES ('test@example.com', datetime('now'))"
    ).lastrowid
    # clear holds from a previous run so the test is repeatable
    conn.execute("DELETE FROM seat_holds WHERE booking_id IN "
                 "(SELECT id FROM bookings WHERE user_id=? AND status='held')", (uid,))
    conn.execute("UPDATE bookings SET status='expired' WHERE user_id=? AND status='held'",
                 (uid,))
    conn.commit()

tok = security.issue({"uid": uid}, 3600)
BASE = "http://127.0.0.1:8000"


def call(path, method="GET", body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        BASE + path, method=method,
        data=json.dumps(body).encode() if body else None,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# 1. first day that still has shows (movie id comes from the live catalogue,
#    so the test keeps working after the slate is reseeded)
s, listing = call("/api/movies")
movie_id = listing["movies"][0]["id"]
s, movie = call(f"/api/movies/{movie_id}")
day = movie["days"][0]
s, shows = call(f"/api/shows?movie_id={movie_id}&day={day}")
print(f"1) {movie['movie']['title']!r} day={day} shows:", len(shows["shows"]),
      [x["starts_at"][11:16] for x in shows["shows"]])
assert shows["shows"], "expected at least one upcoming show"

# 2. create booking: 2 seats + snacks (auth required)
#    menu ids are looked up live so the test survives a reseed
s, menu0 = call("/api/menu")
by_cat = {c: [i for i in menu0["items"] if i["category"] == c] for c in
          ("popcorn", "drinks", "combos")}
snack_ids = [by_cat["popcorn"][0]["id"], by_cat["drinks"][0]["id"]]
s, b = call("/api/bookings", "POST", {
    "show_id": shows["shows"][0]["id"],
    "seats": ["A1", "A2"],
    "items": [{"id": snack_ids[0], "qty": 2}, {"id": snack_ids[1], "qty": 1}],
}, tok)
print("2) booking:", s, "code=" + b.get("code", ""), "amount=", b.get("amount"),
      "breakdown=", b.get("breakdown"))
assert s == 200 and b.get("booking_id"), f"booking should be created, got {b}"

# 3. duplicate seat must be blocked
s2, b2 = call("/api/bookings", "POST", {
    "show_id": shows["shows"][0]["id"],
    "seats": ["A1"], "items": [],
}, tok)
print("3) duplicate seat attempt:", s2, b2.get("detail", ""))

# 4. seats now locked
s, seats = call(f"/api/shows/{shows['shows'][0]['id']}/seats")
print("4) taken now:", seats["taken"])

# 5. payment start -> honest error (keys not configured yet)
s5, p5 = call(f"/api/bookings/{b['booking_id']}/pay", "POST", {}, tok)
print("5) pay attempt:", s5, p5.get("detail", ""))

# 6. booking list
s6, l6 = call("/api/bookings", token=tok)
print("6) my bookings:", s6, [(x["code"], x["status"]) for x in l6["bookings"]])

# 7. cancel frees seats
s7, c7 = call(f"/api/bookings/{b['booking_id']}/cancel", "POST", {}, tok)
s8, seats2 = call(f"/api/shows/{shows['shows'][0]['id']}/seats")
print("7) cancel:", s7, "| taken after cancel:", seats2["taken"])

# 8. menu intact
s8, menu = call("/api/menu")
print("8) menu items:", s8, len(menu["items"]))

# 9. OTP verification path (the code hash is created exactly like the send step
#    does after a real email/WhatsApp delivery; delivery itself needs SMTP keys)
import time
from app.otp import _hash_code
code = "123456"
dest = "otptest@example.com"
with connect() as conn:
    conn.execute(
        "INSERT INTO otps (channel, destination, code_hash, expires_at) VALUES (?,?,?,?)",
        ("email", dest, _hash_code(code), int(time.time()) + 300),
    )
    conn.commit()
s9a, v_bad = call("/api/auth/verify-otp", "POST",
                  {"channel": "email", "destination": dest, "code": "000000"})
s9b, v_ok = call("/api/auth/verify-otp", "POST",
                 {"channel": "email", "destination": dest, "code": code})
print("9) wrong code:", s9a, "| correct code:", s9b,
      "token issued:", bool(v_ok.get("token")))
# token must work on an authenticated route
s9c, me = call("/api/me", token=v_ok["token"])
print("10) token -> /api/me:", s9c, "email:", me.get("email"))
