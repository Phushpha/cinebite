"""CineBite - movie seat booking + popcorn & drinks pre-order.

FastAPI application: REST API + static frontend on one local server.
"""
import json
import re
import secrets
import time
from datetime import date as date_cls
from datetime import datetime

from fastapi import Body, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, otp as otp_mod, payments, security
from .database import connect, init_db, seed, seed_info

app = FastAPI(title=config.APP_NAME, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()
seed()


# ------------------------------------------------------------------ helpers
def _json_list(value) -> list:
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except (ValueError, TypeError):
        return []


def _cleanup_expired() -> None:
    now = int(time.time())
    with connect() as conn:
        conn.execute(
            "UPDATE bookings SET status='expired' WHERE status='held' AND expires_at<?",
            (now,),
        )
        conn.execute("DELETE FROM seat_holds WHERE expires_at<?", (now,))
        conn.commit()


def _current_user(authorization: str = Header(default="")) -> dict:
    token = authorization.replace("Bearer ", "").strip()
    payload = security.verify(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Login required.")
    with connect() as conn:
        user = conn.execute(
            "SELECT id, phone, email, name, created_at FROM users WHERE id=?",
            (payload.get("uid"),),
        ).fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="Login required.")
    return dict(user)


def _layout(screen_row) -> dict:
    return json.loads(screen_row["layout"])


def _seat_price(seat: str, layout: dict, base: int) -> int:
    row = seat[0]
    tier = next(
        (t for t in layout["tiers"] if row in t["rows"]),
        layout["tiers"][-1],
    )
    return int(round(base * tier["multiplier"]))


def _taken_seats(show_id: int) -> list[str]:
    now = int(time.time())
    taken = set()
    with connect() as conn:
        for r in conn.execute(
            "SELECT seat FROM seat_holds WHERE show_id=? AND expires_at>?", (show_id, now)
        ):
            taken.add(r["seat"])
        for r in conn.execute(
            "SELECT seats FROM bookings WHERE show_id=? AND status='paid'", (show_id,)
        ):
            taken.update(_json_list(r["seats"]))
    return sorted(taken)


# ------------------------------------------------------------------ request models
class OtpRequest(BaseModel):
    channel: str          # 'email' | 'whatsapp'
    destination: str


class OtpVerify(BaseModel):
    channel: str
    destination: str
    code: str


class BookingRequest(BaseModel):
    show_id: int | None = None
    seats: list[str] = []
    items: list[dict] = []     # [{"id": 3, "qty": 2}]


class VerifyPayment(BaseModel):
    order_id: str
    payment_id: str
    signature: str


# ------------------------------------------------------------------ status / config
@app.get("/api/config")
def api_config():
    report = config.status_report()
    return {
        "app": config.APP_NAME,
        "otp_channels": {
            "email": report["email"],
        },
        "razorpay": {
            "configured": report["razorpay"],
            "mode": report["razorpay_mode"],
            "key_id": config.RAZORPAY_KEY_ID if report["razorpay"] else None,
        },
        "booking_hold_seconds": config.BOOKING_HOLD_SECONDS,
    }


@app.get("/api/stats")
def api_stats():
    """Counts for the home page header - real numbers, not decoration."""
    return seed_info()


@app.get("/health")
def health():
    """Readiness probe for hosting platforms (Render, load balancers)."""
    with connect() as conn:
        movies = conn.execute("SELECT COUNT(*) c FROM movies").fetchone()["c"]
    return {"status": "ok", "movies": movies}


# ------------------------------------------------------------------ auth
@app.post("/api/auth/send-otp")
def send_otp(req: OtpRequest):
    channel = req.channel.lower().strip()
    destination = req.destination.strip()
    if channel == "email":
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$", destination):
            raise HTTPException(400, "Enter a valid email address.")
        destination = destination.lower()
    else:
        raise HTTPException(400, "Only email OTP login is available.")
    try:
        otp_mod.request_otp(channel, destination)
    except otp_mod.OtpError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "destination": destination, "expires_in": config.OTP_TTL}


@app.post("/api/auth/verify-otp")
def verify_otp(req: OtpVerify):
    channel = req.channel.lower().strip()
    destination = req.destination.strip()
    if channel == "email":
        destination = destination.lower()
    elif channel == "whatsapp":
        digits = re.sub(r"\D", "", destination)
        if len(digits) == 10:
            digits = "91" + digits
        destination = digits
    if not re.match(r"^\d{6}$", req.code.strip()):
        raise HTTPException(400, "Enter the 6-digit code.")
    if not otp_mod.verify_otp(destination, req.code.strip()):
        raise HTTPException(400, "Incorrect or expired code.")
    with connect() as conn:
        if channel == "email":
            user = conn.execute("SELECT * FROM users WHERE email=?", (destination,)).fetchone()
            if user:
                conn.execute("UPDATE users SET last_login=datetime('now') WHERE id=?", (user["id"],))
            else:
                cur = conn.execute(
                    "INSERT INTO users (email, last_login) VALUES (?, datetime('now'))",
                    (destination,),
                )
                user = {"id": cur.lastrowid}
        else:
            user = conn.execute("SELECT * FROM users WHERE phone=?", (destination,)).fetchone()
            if user:
                conn.execute("UPDATE users SET last_login=datetime('now') WHERE id=?", (user["id"],))
            else:
                cur = conn.execute(
                    "INSERT INTO users (phone, last_login) VALUES (?, datetime('now'))",
                    (destination,),
                )
                user = {"id": cur.lastrowid}
        conn.commit()
    token = security.issue({"uid": user["id"]}, config.SESSION_TTL)
    return {"ok": True, "token": token, "user_id": user["id"]}


@app.get("/api/me")
def get_me(authorization: str = Header(default="")):
    payload = security.verify(authorization.replace("Bearer ", "").strip())
    if not payload:
        raise HTTPException(401, "Login required.")
    with connect() as conn:
        user = conn.execute(
            "SELECT id, phone, email, name, created_at FROM users WHERE id=?",
            (payload.get("uid"),),
        ).fetchone()
        if not user:
            raise HTTPException(401, "Login required.")
        count = conn.execute(
            "SELECT COUNT(*) c FROM bookings WHERE user_id=? AND status='paid'",
            (user["id"],),
        ).fetchone()["c"]
    return {**dict(user), "bookings": count}


# ------------------------------------------------------------------ movies & shows
def _release_state(m: dict) -> dict:
    """releasing = on screens today. Everything else is a dated coming-soon."""
    today = date_cls.today()
    rel = (m.get("release_date") or "").strip()
    if not rel:
        m["releasing"], m["days_until"] = True, 0
        return m
    try:
        released = date_cls.fromisoformat(rel)
    except ValueError:
        m["releasing"], m["days_until"] = True, 0
        return m
    m["releasing"] = released <= today
    m["days_until"] = (released - today).days
    return m


@app.get("/api/movies")
def list_movies(genre: str | None = None, language: str | None = None,
                status: str | None = None):
    """status: 'now' (in cinemas) | 'soon' (dated releases) | omitted (all)."""
    _cleanup_expired()
    today = date_cls.today().isoformat()
    with connect() as conn:
        all_movies = [
            _release_state(dict(r))
            for r in conn.execute("SELECT * FROM movies ORDER BY sort_order")
        ]
        for m in all_movies:
            row = conn.execute(
                "SELECT MIN(day) d FROM shows WHERE movie_id=? AND day>=?",
                (m["id"], today),
            ).fetchone()
            m["next_day"] = row["d"]

    genres, languages = {}, {}
    for m in all_movies:
        for g in m["genres"].split(","):
            if g.strip():
                genres.setdefault(g.strip(), None)
        for l in m["languages"].split(","):
            if l.strip():
                languages.setdefault(l.strip(), None)

    movies = all_movies
    if genre:
        want = genre.strip().lower()
        movies = [m for m in movies
                  if want in [g.strip().lower() for g in m["genres"].split(",")]]
    if language:
        want = language.strip().lower()
        movies = [m for m in movies
                  if want in [l.strip().lower() for l in m["languages"].split(",")]]
    if status == "now":
        movies = [m for m in movies if m["releasing"]]
    elif status == "soon":
        movies = [m for m in movies if not m["releasing"]]

    return {
        "movies": movies,
        "genres": list(genres),
        "languages": list(languages),
        "total": len(all_movies),
    }


@app.get("/api/cities")
def list_cities():
    """Every city CineBite operates in, with theatre + screen counts."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT t.city city, COUNT(DISTINCT t.id) theatres, COUNT(sc.id) screens "
            "FROM theatres t LEFT JOIN screens sc ON sc.theatre_id=t.id "
            "GROUP BY t.city ORDER BY MIN(t.sort_order)",
        ).fetchall()
    return {"cities": [dict(r) for r in rows]}


@app.get("/api/theatres")
def list_theatres(city: str):
    with connect() as conn:
        rows = conn.execute(
            "SELECT t.id, t.name, t.city, t.area, COUNT(sc.id) screens, "
            "COALESCE(SUM(sc.total_seats),0) seats "
            "FROM theatres t LEFT JOIN screens sc ON sc.theatre_id=t.id "
            "WHERE t.city=? GROUP BY t.id ORDER BY t.sort_order",
            (city,),
        ).fetchall()
    return {"city": city, "theatres": [dict(r) for r in rows]}


@app.get("/api/movies/{movie_id}")
def get_movie(movie_id: int, city: str | None = None):
    """Days with upcoming shows - optionally only the ones in one city."""
    with connect() as conn:
        movie = conn.execute("SELECT * FROM movies WHERE id=?", (movie_id,)).fetchone()
        if not movie:
            raise HTTPException(404, "Movie not found.")
        movie = _release_state(dict(movie))
        sql = (
            "SELECT DISTINCT s.day d FROM shows s "
            "JOIN screens sc ON sc.id=s.screen_id "
            "JOIN theatres t ON t.id=sc.theatre_id "
            "WHERE s.movie_id=? AND s.day>=?"
        )
        params: list = [movie_id, date_cls.today().isoformat()]
        if city:
            sql += " AND t.city=?"
            params.append(city)
        sql += " ORDER BY s.day LIMIT 7"
        rows = conn.execute(sql, params).fetchall()
        # only keep days that still have a show yet to start
        now_iso = datetime.now().isoformat(timespec="seconds")
        days = []
        for r in rows:
            upcoming = conn.execute(
                "SELECT 1 FROM shows WHERE movie_id=? AND day=? AND starts_at>? LIMIT 1",
                (movie_id, r["d"], now_iso),
            ).fetchone()
            if upcoming:
                days.append(r["d"])
    return {"movie": movie, "days": days}


@app.get("/api/shows")
def list_shows(movie_id: int, day: str | None = None, city: str | None = None):
    """Showtimes for a film, grouped by theatre in the selected city."""
    _cleanup_expired()
    day = day or date_cls.today().isoformat()
    now_iso = datetime.now().isoformat(timespec="seconds")
    sql = (
        "SELECT s.*, sc.name screen_name, sc.total_seats total_seats, "
        "m.title movie_title, m.release_date release_date, "
        "t.name theatre_name, t.area theatre_area, t.city city "
        "FROM shows s "
        "JOIN screens sc ON sc.id=s.screen_id "
        "JOIN theatres t ON t.id=sc.theatre_id "
        "JOIN movies m ON m.id=s.movie_id "
        "WHERE s.movie_id=? AND s.day=? AND s.starts_at>?"
    )
    params: list = [movie_id, day, now_iso]
    if city:
        sql += " AND t.city=?"
        params.append(city)
    sql += " ORDER BY t.sort_order, s.starts_at"
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
        shows = []
        for r in rows:
            item = dict(r)
            item["taken_count"] = len(_taken_seats(r["id"]))
            shows.append(item)
    return {"day": day, "city": city, "shows": shows}


@app.get("/api/shows/{show_id}/seats")
def show_seats(show_id: int):
    """Seat map with live availability - the frontend polls this while selecting."""
    _cleanup_expired()
    with connect() as conn:
        show = conn.execute(
            "SELECT s.*, sc.name screen_name, sc.layout, sc.total_seats total_seats, "
            "m.title movie_title, t.name theatre_name, t.area theatre_area, t.city city "
            "FROM shows s JOIN screens sc ON sc.id=s.screen_id "
            "JOIN movies m ON m.id=s.movie_id "
            "JOIN theatres t ON t.id=sc.theatre_id "
            "WHERE s.id=?",
            (show_id,),
        ).fetchone()
    if not show:
        raise HTTPException(404, "Show not found.")
    layout = json.loads(show["layout"])
    taken = _taken_seats(show_id)
    priced = [
        {"seat": s, "price": _seat_price(s, layout, show["price"])}
        for s in _all_seats(layout)
    ]
    return {
        "show": {
            "id": show["id"],
            "movie_title": show["movie_title"],
            "screen_name": show["screen_name"],
            "theatre_name": show["theatre_name"],
            "theatre_area": show["theatre_area"],
            "city": show["city"],
            "starts_at": show["starts_at"],
            "price": show["price"],
            "total_seats": show["total_seats"],
        },
        "layout": layout,
        "seats": priced,
        "taken": taken,
        "server_time": int(time.time()),
    }


def _all_seats(layout: dict) -> list[str]:
    return [
        f"{row}{n}"
        for row in layout["rows"]
        for n in range(1, layout["seats_per_row"] + 1)
    ]


# ------------------------------------------------------------------ menu
@app.get("/api/menu")
def list_menu(category: str | None = None):
    with connect() as conn:
        if category:
            rows = conn.execute(
                "SELECT * FROM menu_items WHERE available=1 AND category=? ORDER BY price",
                (category,),
            )
        else:
            rows = conn.execute(
                "SELECT * FROM menu_items WHERE available=1 ORDER BY category, price"
            )
        items = [dict(r) for r in rows]
    return {"items": items}


# ------------------------------------------------------------------ bookings
@app.post("/api/bookings")
def create_booking(req: BookingRequest, authorization: str = Header(default="")):
    """Hold seats + price the cart. Seats are locked for 10 minutes (BOOKING_HOLD_SECONDS)."""
    user = _current_user(authorization)
    _cleanup_expired()

    if req.show_id is None and not req.items:
        raise HTTPException(400, "Select seats or add snacks to continue.")
    if req.show_id is not None and not req.seats:
        raise HTTPException(400, "Select at least one seat.")

    seats = [s.upper() for s in req.seats]
    if len(set(seats)) != len(seats):
        raise HTTPException(400, "Duplicate seats in selection.")
    if len(seats) > 10:
        raise HTTPException(400, "You can book up to 10 seats at a time.")

    with connect() as conn:
        # ---- price snacks from the database, never from the client
        items, items_total = [], 0
        for raw in req.items:
            try:
                item_id, qty = int(raw["id"]), max(1, min(int(raw.get("qty", 1)), 20))
            except (KeyError, TypeError, ValueError):
                raise HTTPException(400, "Invalid snack selection.")
            row = conn.execute(
                "SELECT * FROM menu_items WHERE id=? AND available=1", (item_id,)
            ).fetchone()
            if not row:
                raise HTTPException(400, "One of the selected snacks is unavailable.")
            items.append(
                {"id": row["id"], "name": row["name"], "size": row["size"],
                 "qty": qty, "price": row["price"]}
            )
            items_total += row["price"] * qty

        show = None
        seats_total = 0
        fee = 0
        if req.show_id is not None:
            show = conn.execute(
                "SELECT s.*, sc.layout FROM shows s JOIN screens sc ON sc.id=s.screen_id "
                "WHERE s.id=?",
                (req.show_id,),
            ).fetchone()
            if not show:
                raise HTTPException(404, "Show not found.")
            if show["starts_at"] <= datetime.now().isoformat(timespec="seconds"):
                raise HTTPException(400, "This show has already started.")
            layout = json.loads(show["layout"])
            valid = set(_all_seats(layout))
            for seat in seats:
                if seat not in valid:
                    raise HTTPException(400, f"Invalid seat {seat}.")
                seats_total += _seat_price(seat, layout, show["price"])
            fee = 25 * len(seats)   # convenience fee, shown in the UI breakdown

        booking_code = "CB" + secrets.token_hex(4).upper()
        expires_at = int(time.time()) + config.BOOKING_HOLD_SECONDS
        try:
            cur = conn.execute(
                "INSERT INTO bookings (code, user_id, show_id, seats, items, amount, "
                "status, otp_verified, expires_at) VALUES (?,?,?,?,?,?, 'held', 1, ?)",
                (
                    booking_code, user["id"], req.show_id,
                    json.dumps(seats), json.dumps(items),
                    seats_total + items_total + fee, expires_at,
                ),
            )
            booking_id = cur.lastrowid
            if req.show_id is not None:
                conn.executemany(
                    "INSERT INTO seat_holds (show_id, seat, booking_id, expires_at) "
                    "VALUES (?,?,?,?)",
                    [(req.show_id, seat, booking_id, expires_at) for seat in seats],
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise HTTPException(
                status_code=409,
                detail="Those seats were just booked by someone else. Please pick different seats.",
            )

    return {
        "booking_id": booking_id,
        "code": booking_code,
        "amount": seats_total + items_total + fee,
        "breakdown": {
            "seats": seats_total,
            "snacks": items_total,
            "convenience_fee": fee,
        },
        "expires_at": expires_at,
        "seats": seats,
        "items": items,
    }


@app.get("/api/bookings")
def my_bookings(authorization: str = Header(default="")):
    user = _current_user(authorization)
    _cleanup_expired()
    with connect() as conn:
        rows = conn.execute(
            "SELECT b.*, s.starts_at, s.screen_id, m.title movie_title, sc.name screen_name, "
            "t.name theatre_name, t.city city "
            "FROM bookings b "
            "LEFT JOIN shows s ON s.id=b.show_id "
            "LEFT JOIN movies m ON m.id=s.movie_id "
            "LEFT JOIN screens sc ON sc.id=s.screen_id "
            "LEFT JOIN theatres t ON t.id=sc.theatre_id "
            "WHERE b.user_id=? ORDER BY b.id DESC",
            (user["id"],),
        ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item["seats"] = _json_list(item["seats"])
        item["items"] = _json_list(item["items"])
        out.append(item)
    return {"bookings": out}


@app.post("/api/bookings/{booking_id}/pay")
def start_payment(booking_id: int, authorization: str = Header(default="")):
    """Create the Razorpay order for a held booking and hand the client the keys."""
    user = _current_user(authorization)
    _cleanup_expired()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM bookings WHERE id=? AND user_id=?",
            (booking_id, user["id"]),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Booking not found.")
    if row["status"] == "paid":
        raise HTTPException(400, "This booking is already paid.")
    if row["status"] != "held" or (row["expires_at"] or 0) < int(time.time()):
        raise HTTPException(400, "Your seat hold expired. Please book again.")
    try:
        order = payments.create_order(
            row["amount"], row["code"],
            {"booking_id": str(row["id"]), "user_id": str(user["id"])},
        )
    except payments.PaymentError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    with connect() as conn:
        conn.execute(
            "UPDATE bookings SET rzp_order_id=? WHERE id=?", (order["id"], row["id"])
        )
        conn.commit()
    return {
        "order_id": order["id"],
        "amount": order["amount"],
        "currency": order["currency"],
        "key_id": config.RAZORPAY_KEY_ID,
        "booking_code": row["code"],
    }


@app.post("/api/payments/verify")
def verify_payment(req: VerifyPayment, authorization: str = Header(default="")):
    _current_user(authorization)
    if not payments.verify_payment_signature(req.order_id, req.payment_id, req.signature):
        raise HTTPException(400, "Payment signature verification failed.")
    booking = payments.settle_booking(req.order_id, req.payment_id)
    if not booking:
        raise HTTPException(404, "No booking found for that order.")
    return {"ok": True, "booking_id": booking["id"], "code": booking["code"]}


@app.post("/api/payments/webhook")
async def razorpay_webhook(request: Request):
    """Server-to-server confirmation - booking settles even if the browser closed."""
    body = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")
    if not payments.verify_webhook_signature(body, signature):
        return JSONResponse({"detail": "invalid signature"}, status_code=400)
    try:
        payments.handle_webhook(json.loads(body))
    except ValueError:
        return JSONResponse({"detail": "bad payload"}, status_code=400)
    return {"ok": True}


@app.post("/api/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: int, authorization: str = Header(default="")):
    user = _current_user(authorization)
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM bookings WHERE id=? AND user_id=?",
            (booking_id, user["id"]),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Booking not found.")
        if row["status"] != "held":
            raise HTTPException(400, "Paid bookings cannot be cancelled here.")
        conn.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (booking_id,))
        conn.execute("DELETE FROM seat_holds WHERE booking_id=?", (booking_id,))
        conn.commit()
    return {"ok": True}


# ------------------------------------------------------------------ static frontend (mounted last)
app.mount("/", StaticFiles(directory=str(config.BASE_DIR / "static"), html=True), name="static")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
