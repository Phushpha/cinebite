"""Check email OTP config status, then send a REAL OTP to the user's inbox."""
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"


def call(path, method="GET", body=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


s, cfg = call("/api/config")
print("1) config:", json.dumps(cfg["otp_channels"]), "| razorpay:", cfg["razorpay"]["mode"])
assert cfg["otp_channels"]["email"] is True, "SMTP not configured"

# real delivery - a genuine email leaves the server here
s, r = call("/api/auth/send-otp", "POST", {"channel": "email",
                                           "destination": "deepakkrsingh4114@gmail.com"})
print("2) send-otp:", s, r)
assert s == 200, "real email send failed"

# whatsapp must be rejected now
s, r = call("/api/auth/send-otp", "POST", {"channel": "whatsapp", "destination": "+919999999999"})
print("3) whatsapp attempt:", s, r.get("detail"))
assert s in (400, 502), "whatsapp should no longer be accepted"

print("\nEMAIL OTP IS LIVE - check the inbox for the 6-digit code.")
