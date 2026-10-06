"""SQLite database: schema, connection helpers and seed data.

One file, no server to install. The data lives in cinebite.db next to the app.

The seed is versioned (app_meta.seed_version): when the version is older than
SEED_VERSION the schedule side is rebuilt from scratch. User accounts and login
sessions are never touched - only movies, theatres, shows, seats and the snack
list are regenerated.
"""
import json
import sqlite3
import threading
from datetime import date, datetime, timedelta

from .config import BASE_DIR

DB_PATH = BASE_DIR / "cinebite.db"
_local = threading.Lock()

SEED_VERSION = "3"          # v3 = city / theatre / 2026 release slate

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    phone       TEXT UNIQUE,
    email       TEXT UNIQUE,
    name        TEXT DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now')),
    last_login  TEXT
);

CREATE TABLE IF NOT EXISTS otps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    channel     TEXT NOT NULL,              -- 'email'
    destination TEXT NOT NULL,              -- email address
    code_hash   TEXT NOT NULL,
    verified    INTEGER DEFAULT 0,
    attempts    INTEGER DEFAULT 0,
    expires_at  INTEGER NOT NULL,
    created_at  INTEGER DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_otps_dest ON otps(destination, created_at);

CREATE TABLE IF NOT EXISTS movies (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    tagline      TEXT DEFAULT '',
    description  TEXT DEFAULT '',
    genres       TEXT DEFAULT '',
    languages    TEXT DEFAULT 'Hindi',
    duration_min INTEGER DEFAULT 150,
    certificate  TEXT DEFAULT 'UA',
    rating       REAL DEFAULT 7.5,
    poster_url   TEXT DEFAULT '',
    accent       TEXT DEFAULT '#e11d48',
    release_date TEXT DEFAULT '',           -- YYYY-MM-DD ("" = always running)
    releasing    INTEGER DEFAULT 1,
    sort_order   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS theatres (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    city       TEXT NOT NULL,
    area       TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS screens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    layout      TEXT NOT NULL,              -- JSON: rows/cols/pricing tiers
    theatre_id  INTEGER DEFAULT 0,
    total_seats INTEGER DEFAULT 140
);

CREATE TABLE IF NOT EXISTS shows (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    movie_id    INTEGER NOT NULL REFERENCES movies(id),
    screen_id   INTEGER NOT NULL REFERENCES screens(id),
    starts_at   TEXT NOT NULL,              -- ISO local time
    day         TEXT NOT NULL,              -- YYYY-MM-DD
    price       INTEGER NOT NULL            -- base seat price in INR
);

CREATE TABLE IF NOT EXISTS bookings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT UNIQUE NOT NULL,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    show_id     INTEGER REFERENCES shows(id),
    seats       TEXT DEFAULT '[]',          -- JSON array of seat labels
    items       TEXT DEFAULT '[]',          -- JSON array {id,name,qty,price}
    amount      INTEGER NOT NULL,
    status      TEXT DEFAULT 'held',        -- held | paid | expired | cancelled
    otp_verified INTEGER DEFAULT 0,
    rzp_order_id TEXT,
    rzp_payment_id TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    expires_at  INTEGER,
    paid_at     TEXT
);

CREATE TABLE IF NOT EXISTS menu_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT NOT NULL,              -- popcorn | drinks | combos | sides
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    price       INTEGER NOT NULL,
    size        TEXT DEFAULT '',
    veg         INTEGER DEFAULT 1,
    bestseller  INTEGER DEFAULT 0,
    available   INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS seat_holds (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    show_id     INTEGER NOT NULL,
    seat        TEXT NOT NULL,
    booking_id  INTEGER NOT NULL REFERENCES bookings(id),
    expires_at  INTEGER NOT NULL,
    UNIQUE(show_id, seat)
);

CREATE TABLE IF NOT EXISTS app_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

# ---------------------------------------------------------------- layouts
GRANDE = {
    "rows": ["J", "I", "H", "G", "F", "E", "D", "C", "B", "A"],
    "seats_per_row": 14,
    "aisle_after": [6, 12],
    "tiers": [
        {"name": "Premium Recliner", "rows": ["J", "I"], "multiplier": 1.8},
        {"name": "Prime", "rows": ["H", "G", "F", "E"], "multiplier": 1.35},
        {"name": "Classic", "rows": ["D", "C", "B", "A"], "multiplier": 1.0},
    ],
}
COSY = {
    "rows": ["G", "F", "E", "D", "C", "B", "A"],
    "seats_per_row": 12,
    "aisle_after": [6],
    "tiers": [
        {"name": "Premium Recliner", "rows": ["G", "F"], "multiplier": 1.8},
        {"name": "Prime", "rows": ["E", "D", "C"], "multiplier": 1.35},
        {"name": "Classic", "rows": ["B", "A"], "multiplier": 1.0},
    ],
}


def _seats(layout: dict) -> int:
    return len(layout["rows"]) * layout["seats_per_row"]


# ---------------------------------------------------------------- cities / theatres
# city, ticket price multiplier, [(theatre, area, [hall, hall])]
CITIES = [
    ("Mumbai", 1.20, [
        ("PVR ICON Infiniti Mall", "Andheri West", ["IMAX", "AUD 2"]),
        ("INOX Megaplex", "Phoenix Palladium", ["4DX", "AUD 3"]),
        ("Cinepolis Viviana Mall", "Thane West", ["DX ONE", "AUD 2"]),
    ]),
    ("Delhi NCR", 1.15, [
        ("PVR Select Citywalk", "Saket", ["IMAX", "AUD 2"]),
        ("PVR Logix Mall", "Noida Sector 32", ["AUD 1", "AUD 2"]),
        ("INOX Nehru Place", "Kailash Colony", ["RECLINER", "AUD 3"]),
    ]),
    ("Bengaluru", 1.10, [
        ("PVR Orion Mall", "Rajajinagar", ["IMAX", "AUD 2"]),
        ("Cinepolis Royal Meenakshi", "Bannerghatta Road", ["AUD 1", "AUD 2"]),
        ("INOX Forum Mall", "Koramangala", ["4DX", "AUD 3"]),
    ]),
    ("Pune", 1.05, [
        ("PVR Amanora Mall", "Hadapsar", ["AUD 1", "AUD 2"]),
        ("INOX Carnival", "Katraj", ["4DX", "AUD 3"]),
        ("Cinepolis Seasons", "Baner", ["AUD 1", "AUD 2"]),
    ]),
    ("Hyderabad", 1.00, [
        ("AMB Cinemas", "Gachibowli", ["AUD 1", "AUD 2"]),
        ("PVR Icon Platinum", "Banjara Hills", ["IMAX", "AUD 2"]),
        ("Cinepolis Mantra Mall", "Nandyal Road", ["AUD 1", "AUD 3"]),
    ]),
    ("Chennai", 1.00, [
        ("SPI Palazzo", "Phoenix Marketcity", ["IMAX", "AUD 2"]),
        ("PVR VR Mall", "Anna Nagar", ["AUD 1", "AUD 2"]),
        ("INOX Express Avenue", "Royapettah", ["AUD 1", "AUD 3"]),
    ]),
    ("Kolkata", 0.90, [
        ("INOX South City", "Jadavpur", ["AUD 1", "AUD 2"]),
        ("PVR Mani Square", "Hatibagan", ["AUD 1", "AUD 3"]),
        ("Cinepolis Diamond Plaza", "New Town", ["AUD 1", "AUD 2"]),
    ]),
    ("Jaipur", 0.85, [
        ("Raj Mandir Cinema", "Ashok Marg", ["GOLD CLASS", "AUD 2"]),
        ("PVR Malls Mall", "Vaishali Nagar", ["AUD 1", "AUD 2"]),
        ("Cinepolis World Trade Park", "Malviya Nagar", ["AUD 1", "AUD 3"]),
    ]),
]

# ---------------------------------------------------------------- 2026 slate
# title, tagline, description, genres, languages, minutes, cert, rating,
# poster, accent, release_date
MOVIES = [
    # ------------------------------------------------ now showing
    ("Drishyam 3", "The past never stays silent",
     "Six years later the Gandhi family's carefully buried secret is dug up again, and the man who buried it must outthink everyone once more.",
     "Crime, Thriller", "Hindi, Malayalam", 160, "UA", 8.2,
     "https://upload.wikimedia.org/wikipedia/en/a/a1/Drishyam_3_poster.jpg",
     "#0f766e", "2026-10-02"),
    ("Pooja Meri Jaan", "Love has an alibi",
     "Two sisters on the run and a detective who is always one step behind — a sharp, twisty crime thriller.",
     "Crime, Thriller, Drama", "Hindi", 132, "A", 7.6,
     "", "#be123c", "2026-10-02"),
    ("Prem Keetanu", "Some love stories start late",
     "A small-town romantic comedy about two people who keep meeting at the worst possible moments.",
     "Comedy, Romance, Drama", "Hindi", 137, "UA", 7.2,
     "https://upload.wikimedia.org/wikipedia/en/2/2c/Prem_Keetanu_poster.jpg",
     "#ec4899", "2026-10-02"),
    ("Verity", "Every word is a trap",
     "A young writer takes a job in the remote home of a bestselling novelist and discovers the manuscript she is editing is a confession.",
     "Thriller, Drama", "English", 118, "A", 7.8,
     "https://upload.wikimedia.org/wikipedia/en/6/60/Verity_poster.jpg",
     "#7c3aed", "2026-10-02"),
    ("Soulm8te", "Love. Upgraded.",
     "A grieving man builds an AI companion who learns a little too well — a cold, sleek new chapter of the M3GAN universe.",
     "Sci-Fi, Thriller, Horror", "English", 106, "A", 7.1,
     "https://upload.wikimedia.org/wikipedia/en/a/a0/Soulm8te_poster.jpg",
     "#06b6d4", "2026-10-01"),
    ("Tom and Jerry: Forbidden Compass", "Chase. Map. Repeat.",
     "Tom and Jerry wash up on a forgotten island and race a pirate crew to a treasure neither of them can agree on.",
     "Animation, Comedy, Adventure", "English, Hindi", 98, "U", 6.9,
     "https://upload.wikimedia.org/wikipedia/en/a/a7/Tom_and_Jerry%2C_Forbidden_Compass_poster.jpeg",
     "#f59e0b", "2026-10-03"),
    ("Line of Control", "Nowhere is safe",
     "An avalanche traps a patrol on the border while a hostile unit closes in — a taut survival thriller.",
     "Thriller, Action, Drama", "Hindi", 126, "UA", 7.3,
     "", "#38bdf8", "2026-10-06"),
    ("Insidious: Out of the Further", "The door swings both ways",
     "A young woman who can speak with the dead opens a path into the Further — and something follows her home.",
     "Horror, Supernatural", "English", 112, "A", 7.4,
     "https://upload.wikimedia.org/wikipedia/en/5/5c/Insidious-out-of-the-further-poster.png",
     "#8b5cf6", "2026-10-06"),
    ("Mirzapur: The Movie", "The throne remembers",
     "From the lanes of Mirzapur to the top of the empire — the gangster saga reaches its bloody finale.",
     "Action, Crime, Drama", "Hindi", 155, "A", 8.0,
     "https://upload.wikimedia.org/wikipedia/en/4/40/Mirzapur_%28film%29.jpg",
     "#dc2626", "2026-09-04"),
    ("Lust Stories 3", "Four stories. No apologies.",
     "Four directors, four confessions about modern relationships — the anthology returns bolder than before.",
     "Drama, Romance", "Hindi", 148, "A", 7.0,
     "https://upload.wikimedia.org/wikipedia/en/9/93/Lust_Stories_3.jpg",
     "#db2777", "2026-09-18"),
    ("Bhediya 2", "The beast is back",
     "The forest takes a new shape, and the shapeshifter returns to a town that no longer believes the legend.",
     "Horror, Comedy", "Hindi", 134, "UA", 7.1,
     "", "#f97316", "2026-08-14"),
    ("The Paradise", "One city. Two futures.",
     "A dream city built on borrowed memories hides one family's buried truth.",
     "Sci-Fi, Drama, Thriller", "Telugu, Hindi", 152, "UA", 7.7,
     "", "#14b8a6", "2026-09-24"),
    ("Fall 2: Deadpoint", "Don't look down",
     "Two climbers stranded on a forbidden radio tower must out-climb a storm, a sabotage and their own nerve.",
     "Thriller, Adventure", "English", 109, "UA", 7.2,
     "https://upload.wikimedia.org/wikipedia/en/d/db/Fall_2_Deadpoint.jpg",
     "#ef4444", "2026-09-11"),
    ("Heart of the Beast", "58 miles to home",
     "A retired Special Forces veteran and his military dog fight across hostile wilderness to reach safety.",
     "Action, Drama", "English", 124, "A", 7.5,
     "https://upload.wikimedia.org/wikipedia/en/4/49/Heart_of_the_Beast_film_poster.jpg",
     "#84cc16", "2026-09-25"),
    ("Primetime", "Live. Caught. Cancelled.",
     "The making of America's most controversial reality show — and the host who became its biggest story.",
     "Thriller, Drama", "English", 121, "A", 7.6,
     "https://upload.wikimedia.org/wikipedia/en/f/f2/Primetime_poster.jpeg",
     "#6366f1", "2026-09-25"),
    ("Bail", "The bull never bows",
     "A Kannada village drama about land, loyalty and one man who refuses to bend.",
     "Drama, Action", "Kannada", 146, "UA", 7.3,
     "", "#a16207", "2026-10-02"),
    # ------------------------------------------------ releasing soon
    ("Bokshi", "The omen bird",
     "A folk-horror tale of a mountain village where a spirit bird arrives before every tragedy.",
     "Horror, Folk, Drama", "Hindi", 119, "A", 7.4,
     "https://upload.wikimedia.org/wikipedia/en/1/10/Bokshi_poster.jpg",
     "#7c2d12", "2026-10-09"),
    ("Udta Teer", "Aim small, dream big",
     "A small-town archer and a city girl take aim at family expectations, careers and love.",
     "Comedy, Drama", "Hindi", 128, "UA", 7.0,
     "", "#84cc16", "2026-10-09"),
    ("Practical Magic 2", "The sisters return",
     "The Owens sisters are pulled back to the house where love and witchcraft never stayed buried.",
     "Fantasy, Romance, Drama", "English", 124, "UA", 7.3,
     "https://upload.wikimedia.org/wikipedia/en/4/47/Practical_Magic_2_%28film_poster%29.png",
     "#a855f7", "2026-10-13"),
    ("Jailer 2", "The legend loads again",
     "The retired jailer is pulled back for one last mission — bigger, louder and deadlier than before.",
     "Action, Comedy, Thriller", "Tamil, Telugu, Hindi", 165, "UA", 7.9,
     "https://upload.wikimedia.org/wikipedia/en/d/dc/Jailer_2_poster.jpg",
     "#f59e0b", "2026-10-15"),
    ("Raftaar", "Full speed, no brakes",
     "Two strangers in a cut-throat startup race each other to the finish — and fall for each other on the way.",
     "Romance, Drama, Comedy", "Hindi", 131, "UA", 7.1,
     "", "#ec4899", "2026-10-16"),
    ("Ranabaali", "The queen of war",
     "A warrior princess rides against an empire that underestimated her.",
     "Action, Drama, History", "Telugu, Hindi", 158, "UA", 7.6,
     "", "#ef4444", "2026-10-16"),
    ("OM Chapter 1: The Blood Wood", "The forest keeps its promises",
     "A young man inherits a cursed forest, a blood oath and an enemy who never really left.",
     "Action, Thriller, Drama", "Tamil, Telugu, Hindi", 149, "UA", 7.8,
     "https://upload.wikimedia.org/wikipedia/en/5/5e/Om_2026_poster.jpg",
     "#dc2626", "2026-10-16"),
    ("Ramayana: Part 1", "An era begins",
     "The story of Rama, Sita and the kingdom of Ayodhya — India's oldest epic told on the biggest screen ever built.",
     "Epic, Mythology, Drama", "Hindi, Tamil, Telugu", 187, "U", 8.6,
     "https://upload.wikimedia.org/wikipedia/en/4/48/Ramayana_Part_1_%28poster%29.jpg",
     "#f59e0b", "2026-11-08"),
    ("Tumbbad 2", "Greed has a sequel",
     "The house of Hastin still demands its dues — greed returns in a colder, hungrier age.",
     "Horror, Fantasy, Drama", "Hindi", 139, "A", 8.1,
     "", "#b91c1c", "2026-12-03"),
    ("Ranger", "Strictly out of office",
     "A park ranger, a minister and a very lost tiger stumble into the biggest scandal of the year.",
     "Comedy, Adventure", "Hindi", 133, "UA", 7.0,
     "", "#22c55e", "2026-12-04"),
    ("King", "The throne is his",
     "A business tycoon and his daughter take on an empire — action, style and a family at war.",
     "Action, Thriller, Drama", "Hindi", 154, "UA", 7.7,
     "https://upload.wikimedia.org/wikipedia/en/f/fd/King_%28Hindi_film%29.jpg",
     "#0ea5e9", "2026-12-24"),
]

MENU = [
    # category, name, description, price, size, veg, bestseller
    ("popcorn", "Classic Salted Popcorn", "Freshly popped kernels with rock salt and butter", 159, "Regular", 1, 0),
    ("popcorn", "Classic Salted Popcorn", "The big tub - butter, salt, cinema nostalgia", 249, "Large", 1, 0),
    ("popcorn", "Cheese Blast Popcorn", "Loaded with liquid cheddar and a hint of pepper", 219, "Regular", 1, 1),
    ("popcorn", "Cheese Blast Popcorn", "Double cheese for serious cheese lovers", 329, "Large", 1, 1),
    ("popcorn", "Caramel Crunch Popcorn", "Sweet caramel glaze with sea salt finish", 229, "Regular", 1, 0),
    ("popcorn", "Caramel Crunch Popcorn", "Extra large sharing tub of caramel heaven", 349, "Large", 1, 0),
    ("popcorn", "Peri Peri Popcorn", "Crunchy coating with African peri peri spice", 219, "Regular", 1, 1),
    ("popcorn", "Peri Peri Popcorn", "Fire-severe peri peri in a jumbo tub", 329, "Large", 1, 1),
    ("popcorn", "Butter Cheese Masala", "Desi style - butter, cheese powder and chaat masala", 239, "Regular", 1, 0),
    ("popcorn", "White Cheddar Truffle", "Premium truffle oil with aged white cheddar", 299, "Regular", 1, 0),
    ("drinks", "Pepsi", "Ice chilled Pepsi", 99, "350 ml", 1, 1),
    ("drinks", "Pepsi", "Share-sized Pepsi", 149, "600 ml", 1, 1),
    ("drinks", "Pepsi Black", "Zero sugar, all cola punch", 109, "350 ml", 1, 0),
    ("drinks", "Mirinda Orange", "Bright orange fizz", 99, "350 ml", 1, 0),
    ("drinks", "7Up", "Clear lemon-lime refreshment", 99, "350 ml", 1, 0),
    ("drinks", "Mountain Dew", "Darr ke aage jeet hai", 99, "350 ml", 1, 0),
    ("drinks", "Slice Mango", "Thick mango nectar drink", 109, "350 ml", 1, 0),
    ("drinks", "Sting Energy", "Berry energy boost", 119, "250 ml", 1, 0),
    ("drinks", "Sprite", "Clear lemon refreshment", 99, "350 ml", 1, 0),
    ("drinks", "Thums Up", "Strong, masala, grown-up cola", 99, "350 ml", 1, 0),
    ("combos", "Solo Combo", "Large Classic popcorn + 350 ml Pepsi", 329, "For 1", 1, 1),
    ("combos", "Couple Combo", "2 Large popcorns of choice + 2 Pepsi + nachos", 749, "For 2", 1, 1),
    ("combos", "Family Combo", "4 Regular popcorns + 4 drinks + 1 nachos tub", 1299, "For 4", 1, 0),
    ("combos", "Cheese Lovers Combo", "Large Cheese Blast + Peri Peri + 2 Pepsi Black", 699, "For 2", 1, 0),
    ("combos", "Kids Combo", "Small popcorn + 250 ml Mirinda + toy surprise", 249, "For 1", 1, 0),
    ("sides", "Nachos & Cheese", "Tortilla chips with warm cheese dip", 249, "Regular", 1, 0),
    ("sides", "French Fries", "Crispy golden fries with peri peri", 179, "Regular", 1, 0),
    ("sides", "Chocolate Brownie", "Warm brownie with vanilla scoop", 199, "Single", 1, 0),
    ("sides", "Masala Peanuts", "Roasted peanuts with chatpata masala", 99, "Regular", 1, 0),
]

SLOTS = ["10:30", "13:45", "17:15", "21:00"]
BASE_PRICE = {"10:30": 199, "13:45": 249, "17:15": 349, "21:00": 399}


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _columns(conn, table: str) -> set:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def _migrate(conn) -> None:
    """Add columns introduced after the table was first created."""
    if "theatre_id" not in _columns(conn, "screens"):
        conn.execute("ALTER TABLE screens ADD COLUMN theatre_id INTEGER DEFAULT 0")
    if "total_seats" not in _columns(conn, "screens"):
        conn.execute("ALTER TABLE screens ADD COLUMN total_seats INTEGER DEFAULT 140")
    if "release_date" not in _columns(conn, "movies"):
        conn.execute("ALTER TABLE movies ADD COLUMN release_date TEXT DEFAULT ''")


def init_db() -> None:
    with _local, connect() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        row = conn.execute(
            "SELECT value FROM app_meta WHERE key='seed_version'"
        ).fetchone()
        version = row["value"] if row else "0"
        if version != SEED_VERSION:
            # rebuild the schedule side only - accounts and logins survive
            conn.executescript(
                "DELETE FROM seat_holds;"
                "DELETE FROM bookings;"
                "DELETE FROM shows;"
                "DELETE FROM screens;"
                "DELETE FROM theatres;"
                "DELETE FROM movies;"
                "DELETE FROM menu_items;"
                # restart the id counters so a rebuilt catalogue always starts at 1
                "DELETE FROM sqlite_sequence WHERE name IN "
                "('movies','theatres','screens','shows','bookings','menu_items');"
            )
        conn.commit()


def _price(base: int, multiplier: float) -> int:
    """Cinema style pricing: round to the nearest ten, then back to a ...9."""
    return int(round(base * multiplier / 10.0) * 10) - 1


def seed() -> None:
    """Idempotent seed: movies, cities, theatres, 7 days of shows, snack menu."""
    with _local, connect() as conn:
        if conn.execute("SELECT COUNT(*) c FROM movies").fetchone()["c"]:
            return

        # ---- movies ------------------------------------------------------
        conn.executemany(
            "INSERT INTO movies (title, tagline, description, genres, languages, "
            "duration_min, certificate, rating, poster_url, accent, release_date, "
            "releasing, sort_order) VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?)",
            [(*m, i) for i, m in enumerate(MOVIES)],
        )

        # ---- cities, theatres, halls -------------------------------------
        screens = []                       # {id, city, multiplier}
        for city_i, (city, multiplier, theatres) in enumerate(CITIES):
            for th_i, (name, area, halls) in enumerate(theatres):
                cur = conn.execute(
                    "INSERT INTO theatres (name, city, area, sort_order) VALUES (?,?,?,?)",
                    (name, city, area, city_i * 10 + th_i),
                )
                theatre_id = cur.lastrowid
                for hall_i, hall in enumerate(halls):
                    layout = GRANDE if hall_i == 0 else COSY
                    cur = conn.execute(
                        "INSERT INTO screens (name, layout, theatre_id, total_seats) "
                        "VALUES (?,?,?,?)",
                        (hall, json.dumps(layout), theatre_id, _seats(layout)),
                    )
                    screens.append(
                        {"id": cur.lastrowid, "city": city, "mult": multiplier}
                    )

        # ---- 7 days of shows --------------------------------------------
        # Every (hall, time-slot) cell holds exactly one movie, so a screen is
        # never double-booked. Films join the rotation from their release date.
        today = date.today()
        movie_rows = [
            dict(r) for r in conn.execute(
                "SELECT id, release_date FROM movies ORDER BY sort_order"
            )
        ]
        rows = []
        for day_offset in range(7):
            day = today + timedelta(days=day_offset)
            day_iso = day.isoformat()
            pool = [
                m for m in movie_rows
                if not m["release_date"] or m["release_date"] <= day_iso
            ]
            if not pool:
                continue
            for si, screen in enumerate(screens):
                for slot_i, slot in enumerate(SLOTS):
                    idx = (si * 5 + day_offset * 3 + slot_i * 7) % len(pool)
                    rows.append((
                        pool[idx]["id"], screen["id"],
                        f"{day_iso}T{slot}:00", day_iso,
                        _price(BASE_PRICE[slot], screen["mult"]),
                    ))
        conn.executemany(
            "INSERT INTO shows (movie_id, screen_id, starts_at, day, price) "
            "VALUES (?,?,?,?,?)", rows,
        )

        # ---- snack counter ----------------------------------------------
        conn.executemany(
            "INSERT INTO menu_items (category, name, description, price, size, "
            "veg, bestseller) VALUES (?,?,?,?,?,?,?)", MENU,
        )

        conn.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('seed_version', ?)",
            (SEED_VERSION,),
        )
        conn.commit()


def seed_info() -> dict:
    """Small summary used by the home page stats and /api/config."""
    with connect() as conn:
        cities = conn.execute("SELECT COUNT(DISTINCT city) c FROM theatres").fetchone()["c"]
        theatres = conn.execute("SELECT COUNT(*) c FROM theatres").fetchone()["c"]
        movies = conn.execute("SELECT COUNT(*) c FROM movies").fetchone()["c"]
        snacks = conn.execute(
            "SELECT COUNT(*) c FROM menu_items WHERE available=1"
        ).fetchone()["c"]
    return {"cities": cities, "theatres": theatres, "movies": movies, "snacks": snacks}
