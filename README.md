# 🍿 CineBite — Movie Seat Booking + Popcorn & Drinks

A working (non-demo) PVR-style movie booking site: pick **city → theatre → seats**, add
popcorn / Pepsi / combo snacks, log in with a **real email OTP**, and pay with **real
Razorpay** — bookable online today.

**Stack:** Python · FastAPI · SQLite · vanilla HTML/CSS/JS (no Node.js needed)

---

## What's inside

- **2026 slate** — 27 films across Bollywood, Hollywood, Telugu, Tamil, Malayalam and
  Kannada (titles & release dates are real; ratings/durations are seeded sample metadata).
- **📍 Location-based theatres** — 8 cities · 24 theatres · 48 halls. The city follows you
  between pages; showtimes are grouped by theatre and hall.
- **Now Showing vs Coming Soon** — near-term releases show the exact release date and turn
  bookable from their release day onwards.
- **Filters** — genre · language · Now/Soon, server-side (`/api/movies?genre=&language=`).
- **Posters** — real key art where available; a designed title card is drawn automatically
  for the rest (never a broken image).

## 1. Run it

```bat
py run.py
```

(or double-click `start.bat`, or `py -m uvicorn app.main:app --host 127.0.0.1 --port 8000`)

Open **http://127.0.0.1:8000** — `cinebite.db` is created and seeded automatically on first
start (27 movies, 8 cities, 24 theatres, 7 days of shows, 29 menu items). To reset data:
stop the server, delete `cinebite.db`, start again.

## 2. Configure `.env` (required for OTP + payments)

Copy/edit `.env` in the project root. Three secrets unlock real functionality.
(Email-only login — WhatsApp was removed.)

### a) Email OTP — Gmail App Password
1. In your Google Account enable **2-Step Verification**.
2. https://myaccount.google.com/apppasswords → create an app password (name it `cinebite`).
3. Fill:
```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=yourgmail@gmail.com
SMTP_PASSWORD=xxxxxxxxxxxxxxxx
OTP_FROM=CineBite OTP <yourgmail@gmail.com>
```

### b) Razorpay — Test keys now, live keys later
1. https://dashboard.razorpay.com → **Test Mode** toggle → Settings → API Keys → Generate Key.
2. Fill:
```env
RAZORPAY_KEY_ID=rzp_test_xxxxxxxx
RAZORPAY_KEY_SECRET=xxxxxxxxxxxx
```
Test card `4111 1111 1111 1111`, any future expiry, CVV `123`, OTP `1234`;
UPI `success@razorpay` (fails with `failure@razorpay`).

**Going live:** swap the keys for **Live** ones in `.env` (mode is read from the
`rzp_test_` / `rzp_live_` prefix). Nothing else changes.

### c) SECRET_KEY (sessions)
Generated automatically into `.env` on first run. Set it explicitly when deploying so
sessions survive restarts.

### Unconfigured behaviour (by design)
`GET /api/config` reports exactly what's set. Missing keys never fake success:
OTP send returns **502** naming the missing `.env` fields; checkout disables **Pay**.

## 3. Deploy permanently (Render)

The repo is deployment-ready:

```yaml
# render.yaml — or paste these fields in the Render dashboard
services:
  - type: web
    name: cinebite
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: python run.py
    envVars:
      - key: HOST          value: 0.0.0.0
      - key: SECRET_KEY    generateValue: true
      - key: SMTP_USER / SMTP_PASSWORD / SMTP_FROM      (your Gmail)
      - key: RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET      (test keys)
```

How:
1. Push this folder to a GitHub repo (`.gitignore` already excludes `.env` and `cinebite.db`).
2. render.com → **New + → Blueprint** (pick the repo) — or **New Web Service** with the
   values above.
3. Free tier is enough. **Note on data:** Render's free plan has *no persistent disk*, so
   `cinebite.db` is rebuilt from the seed on every deploy/restart — fine for demos and
   reviews. To keep bookings between restarts, add a paid instance with a disk.

## 4. Share while it runs locally

```bat
start.bat     # server on :8000
share.bat     # restarts server + Cloudflare quick tunnel, prints your public URL
```

## 5. What's real

| Feature | How it works |
|---|---|
| OTP login | 6-digit code, hashed in DB, 5-min expiry, 45-s cooldown, 5 attempts. Delivered by **SMTP email**. Never printed to console. |
| Session | HMAC-SHA256 signed token (`Authorization: Bearer …`), 7-day expiry. |
| Seat locking | Server-side holds, 10 min, unique `(show_id, seat)` constraint → double-booking impossible (409). |
| Pricing | Computed server-side from DB (tier × slot × city price). Client prices are display-only. |
| Payments | Real Razorpay Orders API → Checkout.js → HMAC signature verify server-side → webhook settles. |
| Snacks-first | Pay for popcorn/Pepsi/combo **without seats**, or seats + snacks together. |
| Cities | `/api/cities`, `/api/theatres`, shows filtered by `city`; seat maps carry theatre + hall. |

## 6. API map

```
GET  /api/config /api/stats                → configuration + live catalogue counts
GET  /api/cities                           → cities with theatre/screen counts
GET  /api/theatres?city=                   → theatres in a city
POST /api/auth/send-otp                    {channel: "email", destination}
POST /api/auth/verify-otp                  {channel, destination, code} → token
GET  /api/me                               → current user
GET  /api/movies?genre=&language=&status=  → catalogue (all / now / soon)
GET  /api/movies/{id}?city=                → movie + bookable days for that city
GET  /api/shows?movie_id&day&city          → showtimes (grouped per theatre in UI)
GET  /api/shows/{id}/seats                 → layout, prices, taken seats
GET  /api/menu?category=                   → popcorn/drinks/combos/sides
POST /api/bookings                         → hold seats/snacks, server-priced
GET  /api/bookings                         → my bookings
POST /api/bookings/{id}/cancel             → release hold
POST /api/bookings/{id}/pay                → create Razorpay order
POST /api/payments/verify                  → verify checkout signature, confirm
POST /api/payments/webhook                 → Razorpay webhook (signed)
GET  /health                               → readiness probe for hosts
```

## 7. Tests

```bat
py tests\test_flow.py
```
Covers: shows → booking → **409 on duplicate seats** → holds → cancel frees seats → menu →
**OTP verify (wrong/correct code) → token → /api/me** — end-to-end against the live server.

## 8. Files

```
app/            config · database (schema+seed) · security (tokens) · otp · payments · main (routes)
static/         index (home+filters) · movie (theatres/showtimes/seats) · menu · checkout ·
                orders · login · settings · privacy · terms
tools/          seed helpers (poster lookup, seed dry-run) — not needed to run the site
tests/          test_flow.py (end-to-end)
.env            your secrets (never commit)
run.py          = uvicorn app.main:app on 127.0.0.1:8000
render.yaml     Render free-tier blueprint
```

> The older demo files at the repo root (`server.py`) are leftovers from a previous
> prototype and are **not used** by CineBite.