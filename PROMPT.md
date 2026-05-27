# Pickleball Court & Racket Management System — Master Prompt

## Project Overview
Build a **desktop-ready Python web application** for managing a pickleball facility. It monitors court usage and racket rentals, prevents cashier fraud, and provides sales analytics. The stack is **FastAPI + Jinja2 + TailwindCSS + SQLite**, compiled to a standalone `.exe` via PyInstaller.

---

## Tech Stack
- **Backend**: Python 3.11+, FastAPI, Uvicorn
- **Frontend**: Jinja2 templates + TailwindCSS (CDN) + Vanilla JS (no build step)
- **Database**: SQLite via SQLAlchemy (sync, not async)
- **Auth**: Simple session-based login (cashier vs admin roles)
- **Packaging**: PyInstaller (single-file exe, bundled with static assets and DB)

---

## Roles
| Role | Access |
|------|--------|
| **Admin** | Full access: configure time windows, view all sales, manage rackets/courts, view logs |
| **Cashier** | Transact rentals, view dashboard, swap damaged rackets — cannot change config |

---

## Database Models (SQLite via SQLAlchemy)

### `users`
- id, username, password_hash, role (`admin` / `cashier`), created_at

### `courts`
- id, name (e.g. "Court A"), description, is_active

### `rackets`
- id, name (e.g. "Racket 1"), rf_chip_id (placeholder), status (`available` / `rented` / `damaged`), is_active

### `rental_time_options`
- id, type (`court` / `racket`), label (e.g. "3 Hours"), duration_minutes, price, is_active

### `court_rentals`
- id, court_id, time_option_id, cashier_id, customer_name, started_at, ends_at, status (`active` / `completed` / `cancelled`), amount_paid, created_at

### `racket_rentals`
- id, racket_id, time_option_id, cashier_id, customer_name, started_at, ends_at, status (`active` / `completed` / `swapped` / `cancelled`), amount_paid, created_at

### `racket_swaps`
- id, original_rental_id, old_racket_id, new_racket_id, reason, swapped_by (cashier_id), swapped_at

### `system_logs`
- id, event_type, description, user_id, entity_type, entity_id, created_at

---

## Pages & Routes

### `/login` — Login Page
- Username + password form
- Redirect to `/dashboard` on success
- Role stored in session

---

### `/dashboard` — Main Dashboard (Cashier + Admin)

This is the primary operational view. Split into two clearly distinguished sections:

#### 🟢 COURT SECTION (green/teal color identity)
- Grid of all active courts
- Each court card shows:
  - Court name
  - Status: **Available** (green) or **Rented** (red with countdown timer)
  - If rented: customer name, time option, time remaining (live countdown in HH:MM:SS), ends at
  - Button: **Rent Court** (if available) or **View Details** (if rented)

#### 🟡 RACKET SECTION (amber/yellow color identity)
- Grid of all active rackets
- Each racket card shows:
  - Racket name (e.g. Racket 1, Racket 2)
  - Status badge: **Available** (green), **Rented** (amber with countdown), **Damaged** (red)
  - If rented: customer name, time option, time remaining (live countdown), ends at
  - Button: **Rent Racket** (if available), **Swap Racket** (if rented), or **Mark Available** (if damaged, admin only)
- RF chip status placeholder: show a small icon with tooltip "RF Monitoring: Pending Integration"

---

### `/rent/court` — Rent a Court (Modal or Page)
- Select court (dropdown, only available courts)
- Customer name (text input)
- Select time option (radio buttons showing label + price, pulled from DB)
- Confirm button → creates `court_rental`, logs event
- Cashier cannot proceed if court is already rented

---

### `/rent/racket` — Rent a Racket (Modal or Page)
- Select racket (dropdown, only available rackets)
- Customer name (text input)
- Select time option (radio buttons showing label + price)
- Confirm → creates `racket_rental`, updates racket status to `rented`, logs event

---

### `/swap/racket/<rental_id>` — Swap Damaged Racket (Cashier)
- Shows current rental info (customer, time remaining)
- Select new racket from available rackets
- Enter reason for swap
- Confirm → creates `racket_swap` record, old racket marked `damaged`, new racket marked `rented`, rental updated, logs event
- Time continues from original rental (no reset)

---

### `/admin` — Admin Panel
Tabs or sections:

#### ⚙️ Time Window Configuration
- Two tables: Court Time Options + Racket Time Options
- Each row: Label, Duration (minutes), Price, Active toggle
- Add / Edit / Delete options
- Changes logged

#### 🏓 Racket Management
- List all rackets with status
- Add new racket (name, RF chip ID placeholder)
- Mark as Active / Inactive / Damaged
- Edit racket name

#### 🏟️ Court Management
- List all courts
- Add new court (name, description)
- Toggle active status

#### 👤 User Management
- List users (username, role)
- Add new cashier account
- Reset password
- Cannot delete own account

---

### `/sales` — Sales & Analytics Page (Admin + Cashier view-only)

#### Filter Bar
- Date range picker (presets: Today, This Week, This Month, Custom)
- Filter by: All / Courts / Rackets

#### Summary Cards (top)
- Total Revenue
- Court Revenue
- Racket Revenue
- Total Transactions
- Active Rentals Now

#### Charts (use Chart.js via CDN)
- Bar chart: Revenue by day (for week/month view)
- Pie/donut: Court vs Racket revenue split
- Line chart: Transaction volume over time

#### Transactions Table
- Columns: Date/Time, Type (Court/Racket), Item, Customer, Duration, Amount, Cashier, Status
- Sortable, paginated (25 per page)
- Color coded: Court rows = teal tint, Racket rows = amber tint
- Export to CSV button (admin only)

---

## UI Design System

### Color Identity (CRITICAL — must be visually distinct)
```
Courts  → Teal/Green family  (#0d9488 primary, #ccfbf1 bg tint)
Rackets → Amber/Yellow family (#d97706 primary, #fef3c7 bg tint)
```

### General Theme
- Dark sidebar navigation with facility name/logo placeholder
- White main content area
- Card-based layout with subtle shadows
- Status badges: pill-shaped with color + icon
- Countdown timers: monospace font, color shifts red when < 15 minutes remain
- Responsive grid: 2–4 columns for court/racket cards depending on screen width

### Typography
- Use a clean, professional font (e.g. Geist, DM Sans, or similar via Google Fonts)
- Dashboard headings bold and large
- Status text uses icons (✅ ⏱️ 🔴 🟡) for quick scanning

### Animations / Interactivity
- Live countdowns update every second via `setInterval` + JS fetch to `/api/status`
- Rental forms open as modals (no full page reload)
- Toasts/alerts for success/error feedback
- Smooth hover transitions on cards

---

## API Endpoints (FastAPI)

```
GET  /api/status              → Returns all courts + rackets with live rental state
GET  /api/sales/summary       → Summary stats with date filter
GET  /api/sales/transactions  → Paginated transaction list
POST /api/rent/court          → Create court rental
POST /api/rent/racket         → Create racket rental
POST /api/swap/racket         → Swap racket
POST /api/complete/court/{id} → Mark court rental complete
POST /api/complete/racket/{id}→ Mark racket rental complete
```

---

## Future Integration Placeholders (Do NOT implement logic, only UI stubs)

### Camera / Court Presence Detection
- In each court card, show a small camera icon
- Tooltip: "AI Presence Detection: Coming Soon"
- In admin panel, show a "Camera Integration" section with placeholder toggle (disabled)

### RF Chip / Racket Tracking
- In each racket card, show RF icon
- Tooltip: "RF Chip Tracking: Coming Soon"
- In admin panel, show "RF Device Integration" section with placeholder (disabled)

---

## Business Logic Rules

1. A court or racket cannot be rented if already in `active` rental status
2. Rental end time = `started_at + duration_minutes`
3. Swapping a racket does NOT reset the rental timer
4. Cashiers can only swap rackets on active rentals they can see on dashboard
5. All financial transactions are logged with cashier ID — no anonymous transactions
6. Admin can view all logs in `/admin` → Audit Log tab
7. Completed rentals are auto-detected when countdown hits zero (via JS, manual confirm still required from cashier)
8. Time options for courts and rackets are configured separately and independently

---

## PyInstaller Packaging Requirements

- Use `uvicorn` programmatically inside `main.py` (not CLI)
- Bundle: templates/, static/, pickleball.db (empty seed DB)
- Entry point: `main.py` → `app.py` (FastAPI app)
- `spec` file should include all hidden imports for SQLAlchemy + FastAPI
- On first run, auto-create DB tables and seed default admin user
- Default admin credentials printed to console on first run only
- App opens browser automatically on `http://localhost:8765`

---

## Seed Data (auto-inserted on first run if DB is empty)

### Default Users
- admin / admin123 (role: admin) ← print to console, prompt to change
- cashier1 / cashier123 (role: cashier)

### Default Courts
- Court A, Court B

### Default Rackets
- Racket 1 through Racket 6

### Default Time Options

**Courts:**
- 3 Hours — ₱300
- 6 Hours — ₱500
- 12 Hours — ₱800

**Rackets:**
- 1 Hour — ₱50
- 3 Hours — ₱120
- 5 Hours — ₱180

---

## File Structure
```
pickleball/
├── main.py                  # Entry point (launches uvicorn + opens browser)
├── app.py                   # FastAPI app factory
├── database.py              # SQLAlchemy setup, Base, engine
├── models.py                # All ORM models
├── schemas.py               # Pydantic schemas
├── auth.py                  # Session auth, password hashing
├── routers/
│   ├── dashboard.py         # Dashboard + rental pages
│   ├── admin.py             # Admin panel routes
│   ├── sales.py             # Sales/analytics routes
│   └── api.py               # JSON API endpoints
├── templates/
│   ├── base.html            # Layout with sidebar nav
│   ├── login.html
│   ├── dashboard.html
│   ├── admin.html
│   ├── sales.html
│   └── partials/
│       ├── court_card.html
│       ├── racket_card.html
│       └── modals.html
├── static/
│   └── js/
│       └── countdown.js     # Live countdown + status polling
├── pickleball.spec          # PyInstaller spec file
└── requirements.txt
```

---

## Requirements.txt
```
fastapi
uvicorn[standard]
jinja2
sqlalchemy
passlib[bcrypt]
python-multipart
itsdangerous
pyinstaller
```
