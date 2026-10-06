"""Inspect current bookings/holds state."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import connect

with connect() as conn:
    print("bookings:")
    for r in conn.execute(
        "SELECT id, code, user_id, show_id, seats, status, expires_at FROM bookings ORDER BY id DESC LIMIT 6"
    ):
        print("  ", dict(r))
    print("holds:")
    for r in conn.execute("SELECT * FROM seat_holds"):
        print("  ", dict(r))
