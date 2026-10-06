"""Print a session token for a test user (used by the browser smoke test)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import security
from app.database import connect

with connect() as conn:
    row = conn.execute("SELECT id FROM users WHERE email='test@example.com'").fetchone()
    uid = row["id"] if row else conn.execute(
        "INSERT INTO users (email) VALUES ('test@example.com')"
    ).lastrowid
    conn.commit()

print(security.issue({"uid": uid}, 7200))
