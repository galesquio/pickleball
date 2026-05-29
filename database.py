import os
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).parent
    RESOURCE_DIR = Path(sys._MEIPASS)
else:
    APP_DIR = Path(__file__).resolve().parent
    RESOURCE_DIR = APP_DIR


def _normalize_database_url(url: str) -> str:
    """Render and some hosts use postgres://; SQLAlchemy 2.x expects postgresql://."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and "sslmode=" not in url and ".render.com" in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url


def _sqlite_database_url() -> str:
    data_dir = os.getenv("DATA_DIR", "").strip()
    if data_dir:
        db_dir = Path(data_dir)
    elif Path("/var/data").is_dir():
        db_dir = Path("/var/data")
    else:
        db_dir = APP_DIR
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "pickleball.db"
    return f"sqlite:///{db_path.as_posix()}"


def resolve_database_url() -> str:
    explicit = os.getenv("DATABASE_URL", "").strip()
    if explicit:
        return _normalize_database_url(explicit)
    return _sqlite_database_url()


SQLALCHEMY_DATABASE_URL = resolve_database_url()
_is_sqlite = SQLALCHEMY_DATABASE_URL.startswith("sqlite")

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=not _is_sqlite,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_db():
    """Add columns/tables for existing SQLite databases."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    tables = set(insp.get_table_names())

    with engine.begin() as conn:
        if "promos" not in tables:
            from models import Promo  # noqa: F401

            Promo.__table__.create(bind=conn)
            insp = inspect(engine)
            tables = set(insp.get_table_names())

        if "system_settings" not in tables:
            from models import SystemSettings  # noqa: F401

            SystemSettings.__table__.create(bind=conn)
            conn.execute(
                text(
                    "INSERT INTO system_settings (id, court_overtime_rate, racket_overtime_rate, "
                    "overtime_grace_minutes, warning_minutes, allow_cancel_unpaid_booking, "
                    "allow_cancel_paid_booking) VALUES (1, 50.0, 20.0, 10, 15, 1, 0)"
                )
            )
            insp = inspect(engine)
            tables = set(insp.get_table_names())

        rental_completion_cols = [
            ("court_rentals", "completed_at", "DATETIME"),
            ("court_rentals", "overtime_minutes", "INTEGER DEFAULT 0"),
            ("court_rentals", "overtime_hours_charged", "INTEGER DEFAULT 0"),
            ("court_rentals", "overtime_charge", "REAL DEFAULT 0"),
            ("court_rentals", "checkout_payment", "REAL DEFAULT 0"),
            ("court_rentals", "checkout_change", "REAL DEFAULT 0"),
            ("court_rentals", "payment_pending", "INTEGER DEFAULT 0"),
            ("court_rentals", "payment_pending_amount", "REAL DEFAULT 0"),
            ("court_rentals", "auto_completed", "INTEGER DEFAULT 0"),
            ("racket_rentals", "completed_at", "DATETIME"),
            ("racket_rentals", "overtime_minutes", "INTEGER DEFAULT 0"),
            ("racket_rentals", "overtime_hours_charged", "INTEGER DEFAULT 0"),
            ("racket_rentals", "overtime_charge", "REAL DEFAULT 0"),
            ("racket_rentals", "checkout_payment", "REAL DEFAULT 0"),
            ("racket_rentals", "checkout_change", "REAL DEFAULT 0"),
            ("racket_rentals", "payment_pending", "INTEGER DEFAULT 0"),
            ("racket_rentals", "payment_pending_amount", "REAL DEFAULT 0"),
            ("racket_rentals", "auto_completed", "INTEGER DEFAULT 0"),
        ]
        amount_billed_migrated: list[str] = []
        for table, column, ddl in [
            ("court_rentals", "promo_id", "INTEGER"),
            ("court_rentals", "bonus_minutes", "INTEGER DEFAULT 0"),
            ("court_rentals", "amount_billed", "REAL"),
            ("racket_rentals", "promo_id", "INTEGER"),
            ("racket_rentals", "bonus_minutes", "INTEGER DEFAULT 0"),
            ("racket_rentals", "amount_billed", "REAL"),
            *rental_completion_cols,
        ]:
            if table not in tables:
                continue
            cols = {c["name"] for c in insp.get_columns(table)}
            if column not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                if column == "amount_billed":
                    amount_billed_migrated.append(table)

        for table in amount_billed_migrated:
            conn.execute(
                text(
                    f"UPDATE {table} SET amount_billed = amount_paid "
                    "WHERE amount_billed IS NULL"
                )
            )
            conn.execute(
                text(
                    f"UPDATE {table} SET amount_paid = amount_billed + COALESCE(checkout_payment, 0) "
                    "WHERE status IN ('completed', 'swapped')"
                )
            )
            conn.execute(
                text(f"UPDATE {table} SET amount_paid = 0 WHERE status = 'active'")
            )

        for table in ("court_rentals", "racket_rentals"):
            if table not in tables:
                continue
            cols = {c["name"] for c in insp.get_columns(table)}
            if "auto_completed" in cols and "payment_pending" in cols:
                conn.execute(
                    text(
                        f"UPDATE {table} SET auto_completed = 1 "
                        "WHERE status = 'completed' AND payment_pending = 1"
                    )
                )

        if "system_settings" in tables:
            settings_cols = {c["name"] for c in insp.get_columns("system_settings")}
            booking_policy_cols = [
                ("allow_cancel_unpaid_booking", "INTEGER DEFAULT 1"),
                ("allow_cancel_paid_booking", "INTEGER DEFAULT 0"),
            ]
            for column, ddl in booking_policy_cols:
                if column not in settings_cols:
                    conn.execute(
                        text(f"ALTER TABLE system_settings ADD COLUMN {column} {ddl}")
                    )

        # Prepaid auto-completions were incorrectly flagged for overtime-only collection.
        for table in ("court_rentals", "racket_rentals"):
            if table not in tables:
                continue
            cols = {c["name"] for c in insp.get_columns(table)}
            if "payment_pending" not in cols:
                continue
            conn.execute(
                text(
                    f"UPDATE {table} SET payment_pending = 0, payment_pending_amount = 0 "
                    "WHERE payment_pending = 1 AND auto_completed = 1 "
                    "AND COALESCE(overtime_charge, 0) > 0 "
                    "AND payment_pending_amount <= COALESCE(overtime_charge, 0) + 0.01 "
                    "AND payment_pending_amount < COALESCE(amount_billed, 0) - 0.01"
                )
            )


def init_db():
    from models import (  # noqa: F401
        Court,
        CourtRental,
        Promo,
        Racket,
        RacketRental,
        RacketSwap,
        RentalTimeOption,
        SystemLog,
        SystemSettings,
        User,
    )

    Base.metadata.create_all(bind=engine)
    migrate_db()
