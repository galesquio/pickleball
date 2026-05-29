import logging
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

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
    """PostgreSQL when DATABASE_URL is set (Render); SQLite for local desktop dev."""
    explicit = os.getenv("DATABASE_URL", "").strip()
    if explicit:
        return _normalize_database_url(explicit)
    if os.getenv("RENDER", "").lower() == "true":
        raise RuntimeError(
            "DATABASE_URL is required on Render. Link a PostgreSQL database in render.yaml."
        )
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


def database_backend_label() -> str:
    return "SQLite" if _is_sqlite else "PostgreSQL"


def _migration_types() -> dict[str, str]:
    if _is_sqlite:
        return {
            "datetime": "DATETIME",
            "real": "REAL",
            "int": "INTEGER",
            "bool_false": "INTEGER DEFAULT 0",
            "bool_true": "INTEGER DEFAULT 1",
        }
    return {
        "datetime": "TIMESTAMP",
        "real": "DOUBLE PRECISION",
        "int": "INTEGER",
        "bool_false": "BOOLEAN DEFAULT FALSE",
        "bool_true": "BOOLEAN DEFAULT TRUE",
    }


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_db():
    """Add columns/tables for databases created before schema changes."""
    t = _migration_types()
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
            if _is_sqlite:
                conn.execute(
                    text(
                        "INSERT INTO system_settings (id, court_overtime_rate, racket_overtime_rate, "
                        "overtime_grace_minutes, warning_minutes, allow_cancel_unpaid_booking, "
                        "allow_cancel_paid_booking) VALUES (1, 50.0, 20.0, 10, 15, 1, 0)"
                    )
                )
            else:
                conn.execute(
                    text(
                        "INSERT INTO system_settings (id, court_overtime_rate, racket_overtime_rate, "
                        "overtime_grace_minutes, warning_minutes, allow_cancel_unpaid_booking, "
                        "allow_cancel_paid_booking) VALUES (1, 50.0, 20.0, 10, 15, TRUE, FALSE)"
                    )
                )
            insp = inspect(engine)
            tables = set(insp.get_table_names())

        rental_completion_cols = [
            ("court_rentals", "completed_at", t["datetime"]),
            ("court_rentals", "overtime_minutes", f"{t['int']} DEFAULT 0"),
            ("court_rentals", "overtime_hours_charged", f"{t['int']} DEFAULT 0"),
            ("court_rentals", "overtime_charge", f"{t['real']} DEFAULT 0"),
            ("court_rentals", "checkout_payment", f"{t['real']} DEFAULT 0"),
            ("court_rentals", "checkout_change", f"{t['real']} DEFAULT 0"),
            ("court_rentals", "payment_pending", t["bool_false"]),
            ("court_rentals", "payment_pending_amount", f"{t['real']} DEFAULT 0"),
            ("court_rentals", "auto_completed", t["bool_false"]),
            ("racket_rentals", "completed_at", t["datetime"]),
            ("racket_rentals", "overtime_minutes", f"{t['int']} DEFAULT 0"),
            ("racket_rentals", "overtime_hours_charged", f"{t['int']} DEFAULT 0"),
            ("racket_rentals", "overtime_charge", f"{t['real']} DEFAULT 0"),
            ("racket_rentals", "checkout_payment", f"{t['real']} DEFAULT 0"),
            ("racket_rentals", "checkout_change", f"{t['real']} DEFAULT 0"),
            ("racket_rentals", "payment_pending", t["bool_false"]),
            ("racket_rentals", "payment_pending_amount", f"{t['real']} DEFAULT 0"),
            ("racket_rentals", "auto_completed", t["bool_false"]),
        ]
        amount_billed_migrated: list[str] = []
        for table, column, ddl in [
            ("court_rentals", "promo_id", t["int"]),
            ("court_rentals", "bonus_minutes", f"{t['int']} DEFAULT 0"),
            ("court_rentals", "amount_billed", t["real"]),
            ("racket_rentals", "promo_id", t["int"]),
            ("racket_rentals", "bonus_minutes", f"{t['int']} DEFAULT 0"),
            ("racket_rentals", "amount_billed", t["real"]),
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
                if _is_sqlite:
                    conn.execute(
                        text(
                            f"UPDATE {table} SET auto_completed = 1 "
                            "WHERE status = 'completed' AND payment_pending = 1"
                        )
                    )
                else:
                    conn.execute(
                        text(
                            f"UPDATE {table} SET auto_completed = TRUE "
                            "WHERE status = 'completed' AND payment_pending = TRUE"
                        )
                    )

        if "system_settings" in tables:
            settings_cols = {c["name"] for c in insp.get_columns("system_settings")}
            booking_policy_cols = [
                ("allow_cancel_unpaid_booking", t["bool_true"]),
                ("allow_cancel_paid_booking", t["bool_false"]),
            ]
            for column, ddl in booking_policy_cols:
                if column not in settings_cols:
                    conn.execute(
                        text(f"ALTER TABLE system_settings ADD COLUMN {column} {ddl}")
                    )

        for table in ("court_rentals", "racket_rentals"):
            if table not in tables:
                continue
            cols = {c["name"] for c in insp.get_columns(table)}
            if "payment_pending" not in cols:
                continue
            pending_true = "payment_pending = 1" if _is_sqlite else "payment_pending = TRUE"
            pending_false = "payment_pending = 0" if _is_sqlite else "payment_pending = FALSE"
            auto_true = "auto_completed = 1" if _is_sqlite else "auto_completed = TRUE"
            conn.execute(
                text(
                    f"UPDATE {table} SET {pending_false}, payment_pending_amount = 0 "
                    f"WHERE {pending_true} AND {auto_true} "
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
    logger.info("Database ready (%s)", database_backend_label())
