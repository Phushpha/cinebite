"""Dry-run the seed into a scratch database. Never touches cinebite.db."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import database as d   # noqa: E402

tmp = Path(tempfile.mkdtemp()) / "scratch.db"
d.DB_PATH = tmp

d.init_db()
d.seed()

with d.connect() as conn:
    c = lambda q: conn.execute(q).fetchone()[0]
    movies = c("SELECT COUNT(*) FROM movies")
    theatres = c("SELECT COUNT(*) FROM theatres")
    screens = c("SELECT COUNT(*) FROM screens")
    shows = c("SELECT COUNT(*) FROM shows")
    menu = c("SELECT COUNT(*) FROM menu_items")
    cities = c("SELECT COUNT(DISTINCT city) FROM theatres")
    no_show = c("SELECT COUNT(*) FROM movies m WHERE NOT EXISTS "
                "(SELECT 1 FROM shows s WHERE s.movie_id=m.id)")
    now_showing = c("SELECT COUNT(*) FROM movies WHERE release_date<=date('now')")
    double_booked = c(
        "SELECT COUNT(*) FROM (SELECT screen_id, starts_at, COUNT(*) n FROM shows "
        "GROUP BY screen_id, starts_at HAVING n>1)"
    )
    print(f"movies     {movies}   (in cinemas today: {now_showing}, no shows yet: {no_show})")
    print(f"cities     {cities}")
    print(f"theatres   {theatres}")
    print(f"screens    {screens}")
    print(f"shows      {shows}   over 7 days")
    print(f"menu       {menu}")
    print(f"double-booked halls (must be 0): {double_booked}")

    print("\n-- showtimes for movie 1 in each city, tomorrow --")
    from datetime import date, timedelta
    day = (date.today() + timedelta(days=1)).isoformat()
    rows = conn.execute(
        "SELECT t.city, COUNT(*) n, MIN(s.price) lo, MAX(s.price) hi "
        "FROM shows s JOIN screens sc ON sc.id=s.screen_id "
        "JOIN theatres t ON t.id=sc.theatre_id "
        "WHERE s.movie_id=1 AND s.day=? GROUP BY t.city ORDER BY MIN(t.sort_order)",
        (day,),
    ).fetchall()
    for r in rows:
        print(f"   {r[0]:12s} {r[1]:2d} shows   ₹{r[2]}–₹{r[3]}")

    print("\n-- one day, one city: which films play where --")
    rows = conn.execute(
        "SELECT t.name, GROUP_CONCAT(DISTINCT m.title) FROM shows s "
        "JOIN screens sc ON sc.id=s.screen_id JOIN theatres t ON t.id=sc.theatre_id "
        "JOIN movies m ON m.id=s.movie_id WHERE t.city='Mumbai' AND s.day=? "
        "GROUP BY t.id", (day,),
    ).fetchall()
    for r in rows:
        print(f"   {r[0]}: {r[1][:110]}...")

    print("\n-- seat layouts --")
    for r in conn.execute("SELECT DISTINCT name, total_seats FROM screens ORDER BY total_seats DESC"):
        print(f"   {r[0]:12s} {r[1]} seats")

print("\nSEED OK")
