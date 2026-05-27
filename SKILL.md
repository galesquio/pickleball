---
name: pickleball-management
description: >
  Use this skill whenever building, extending, or modifying the Pickleball Court & Racket
  Management System. Triggers include: any mention of the pickleball app, court/racket rentals,
  cashier dashboard, RF chip integration stubs, sales analytics page, admin time-window config,
  racket swapping, or PyInstaller packaging for this project. Also use when adding new routes,
  models, templates, or fixing bugs inside the pickleball/ folder.
---

# Pickleball Management System — Developer Skill

This skill encodes all architecture decisions, conventions, and constraints for the
Pickleball Court & Racket Management System. Always read this before writing any code
for this project.

---

## Stack & Environment

| Layer       | Choice                                      |
|-------------|---------------------------------------------|
| Language    | Python 3.11+                                |
| Framework   | FastAPI (sync routes, not async)            |
| Templates   | Jinja2 (server-rendered HTML)               |
| Styling     | TailwindCSS via CDN (no build step)         |
| JS          | Vanilla JS only (no npm, no bundler)        |
| Database    | SQLite via SQLAlchemy ORM (sync engine)     |
| Auth        | `itsdangerous` signed sessions (cookie)     |
| Packaging   | PyInstaller → single `.exe`                 |
| Charts      | Chart.js via CDN                            |
| Port        | `8765` (hardcoded, opened in browser on launch) |

> ⚠️ Never introduce async SQLAlchemy, React, Vue, npm, or any build tools.
> The app must run as a single exe with zero external dependencies after compile.

---

## Project Layout

```
pickleball/
├── main.py          # Entry: starts uvicorn, opens browser
├── app.py           # FastAPI app factory, mounts routers, sets up sessions
├── database.py      # engine, SessionLocal, Base, get_db dependency
├── models.py        # All SQLAlchemy models
├── schemas.py       # Pydantic v2 schemas (request/response)
├── auth.py          # Password hashing (passlib/bcrypt), session helpers
├── seed.py          # Seeds default data on first run
├── routers/
│   ├── dashboard.py # GET /dashboard, modal rental endpoints
│   ├── admin.py     # GET/POST /admin (tabs: time options, rackets, courts, users, logs)
│   ├── sales.py     # GET /sales
│   └── api.py       # All /api/* JSON endpoints
├── templates/
│   ├── base.html         # Sidebar nav, toast container, modal slot
│   ├── login.html
│   ├── dashboard.html    # Imports court_card + racket_card partials
│   ├── admin.html        # Tab-based admin panel
│   ├── sales.html        # Charts + transactions table
│   └── partials/
│       ├── court_card.html
│       ├── racket_card.html
│       └── modals.html   # All modal HTML (rent court, rent racket, swap racket)
├── static/
│   └── js/
│       ├── countdown.js  # setInterval countdown + /api/status polling
│       └── modals.js     # Open/close modal logic, form submission via fetch
├── pickleball.spec       # PyInstaller spec
└── requirements.txt
```

---

## Models (models.py)

Always import from `database.py` Base. All timestamps use `datetime.utcnow`.

```
User            → id, username, password_hash, role, created_at
Court           → id, name, description, is_active
Racket          → id, name, rf_chip_id, status, is_active
RentalTimeOption→ id, type, label, duration_minutes, price, is_active
CourtRental     → id, court_id, time_option_id, cashier_id, customer_name,
                   started_at, ends_at, status, amount_paid, created_at
RacketRental    → id, racket_id, time_option_id, cashier_id, customer_name,
                   started_at, ends_at, status, amount_paid, created_at
RacketSwap      → id, original_rental_id, old_racket_id, new_racket_id,
                   reason, swapped_by, swapped_at
SystemLog       → id, event_type, description, user_id, entity_type, entity_id, created_at
```

**Status enums (use plain strings, not Python Enum):**
- Racket.status: `available` | `rented` | `damaged`
- CourtRental.status / RacketRental.status: `active` | `completed` | `cancelled` | `swapped`
- RentalTimeOption.type: `court` | `racket`
- User.role: `admin` | `cashier`

---

## Auth & Sessions

- Use `itsdangerous.URLSafeTimedSerializer` for signing session cookies
- Cookie name: `pb_session`
- Session payload: `{ "user_id": int, "role": str, "username": str }`
- Helper: `get_current_user(request) → User | None`
- Helper: `require_role(request, role)` → raises 403 if not matching
- Login sets cookie; logout clears it
- All routes except `/login` require valid session

---

## Color Identity Rules (CRITICAL)

The UI must make courts and rackets visually unmistakable at a glance.

```
Courts  → Teal  (#0d9488)  bg-teal-600  / teal-tinted cards (#f0fdfa)
Rackets → Amber (#d97706)  bg-amber-500 / amber-tinted cards (#fffbeb)
```

- Section headers: large, bold, colored icon prefix (🏟️ for courts, 🏓 for rackets)
- Status badges must always show color + text + icon together
- Countdown timers: `font-mono text-lg`, turn `text-red-600 animate-pulse` when < 15 min

---

## Dashboard Behavior

1. Page loads with all courts + rackets rendered server-side
2. `countdown.js` polls `GET /api/status` every 10 seconds to refresh state
3. Each card has `data-rental-id`, `data-ends-at` attributes for JS targeting
4. Modals are pre-rendered in `modals.html`, shown/hidden via JS class toggle
5. Form submissions inside modals use `fetch` POST → on success, close modal + show toast + refresh cards

---

## API Endpoints (api.py)

All return JSON. Auth required on all.

```
GET  /api/status
     → { courts: [...], rackets: [...] }
     Each item includes: id, name, status, rental (null or { customer, ends_at, time_remaining_seconds, rental_id })

GET  /api/sales/summary?from=YYYY-MM-DD&to=YYYY-MM-DD&type=all|court|racket
     → { total, court_total, racket_total, transaction_count, active_count, daily_breakdown: [...] }

GET  /api/sales/transactions?page=1&from=...&to=...&type=...
     → { items: [...], total_pages, current_page }

POST /api/rent/court        body: { court_id, customer_name, time_option_id }
POST /api/rent/racket       body: { racket_id, customer_name, time_option_id }
POST /api/swap/racket       body: { rental_id, new_racket_id, reason }
POST /api/complete/court/{id}
POST /api/complete/racket/{id}
```

---

## Business Logic Rules

1. **No double-renting**: Before creating any rental, verify status is `available`
2. **Rental end time**: `started_at + timedelta(minutes=duration_minutes)`
3. **Swap preserves timer**: New racket rental inherits original `ends_at`, old racket → `damaged`
4. **Cashier ID always logged**: Every rental/swap writes `cashier_id = current_user.id`
5. **All mutations write to SystemLog**: event_type (e.g. `COURT_RENTED`), description, user_id, entity_type, entity_id
6. **Time options are role-gated**: Only admin can create/edit/delete `RentalTimeOption`
7. **Racket "Mark Available"** (from damaged): admin only

---

## Admin Panel Tabs

Render as a single `/admin` page with JS-toggled tab panels (no page reload per tab).

| Tab | Content |
|-----|---------|
| Time Options | Two sub-tables: Court options + Racket options. Add/edit/delete rows. |
| Rackets | Full list, add new, edit name, toggle status, mark damaged/available |
| Courts | Full list, add new, edit name/description, toggle active |
| Users | List, add cashier, reset password (no delete self) |
| Audit Log | Paginated SystemLog table, filter by event type |
| Camera (stub) | Disabled toggle UI, "Coming Soon" badge |
| RF Devices (stub) | Disabled toggle UI, "Coming Soon" badge |

---

## Sales Page

- Default view: Today
- Charts rendered with Chart.js on `<canvas>` elements
- Data fetched on page load via `/api/sales/summary` + `/api/sales/transactions`
- Date preset buttons: Today / This Week / This Month / Custom range
- Table pagination: 25 rows per page, client-side page buttons
- Export CSV: admin only, calls `/api/sales/export?from=...&to=...` → streamed CSV response
- Court rows: `bg-teal-50`, Racket rows: `bg-amber-50`

---

## PyInstaller Notes

- `main.py` must use `uvicorn.run(app, host="127.0.0.1", port=8765)`
- Wrap in `if __name__ == "__main__"` and `multiprocessing.freeze_support()`
- On launch: run `seed.py` (idempotent), then open browser with `webbrowser.open`
- `pickleball.spec` must include:
  - `datas`: templates/, static/, any .db file
  - `hiddenimports`: sqlalchemy dialects, passlib, jinja2, fastapi internals
  - `console=True` for debug; flip to `False` for production build
- DB path must use `sys._MEIPASS` fallback for bundled mode:
  ```python
  BASE_DIR = getattr(sys, '_MEIPASS', Path(__file__).parent)
  DB_PATH = BASE_DIR / "pickleball.db"
  ```

---

## Seed Data (seed.py — idempotent)

Run on every startup. Skip inserts if records already exist.

```
Admin:    username=admin,    password=admin123, role=admin
Cashier:  username=cashier1, password=cashier123, role=cashier

Courts:   Court A, Court B
Rackets:  Racket 1 … Racket 6

Court time options:
  3 Hours  → 180 min → ₱300
  6 Hours  → 360 min → ₱500
  12 Hours → 720 min → ₱800

Racket time options:
  1 Hour  →  60 min → ₱50
  3 Hours → 180 min → ₱120
  5 Hours → 300 min → ₱180
```

Print to console on first run (when admin is newly created):
```
============================================================
  DEFAULT CREDENTIALS (change immediately after login)
  Admin:   admin / admin123
  Cashier: cashier1 / cashier123
============================================================
```

---

## Do NOT Implement (Stubs Only)

- Camera-based court presence detection
- RF chip serial communication / RFID reader logic
- Any payment gateway integration
- Email/SMS notifications

These must appear as disabled UI elements with "Coming Soon" labels only.

---

## Code Style

- Follow PEP 8
- Use f-strings, not `.format()`
- SQLAlchemy: always close sessions with `finally: db.close()` or use `with` context
- Jinja2: use `{% block %}` inheritance from `base.html`
- JS: no jQuery, no frameworks — pure DOM API + fetch
- Error handling: all API endpoints return `{ "error": "message" }` with appropriate HTTP status
- Never hardcode currency symbol in Python — pass it via Jinja2 context as `₱`
