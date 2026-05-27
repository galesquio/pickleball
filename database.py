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

DB_PATH = APP_DIR / "pickleball.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
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

        for table, column, ddl in [
            ("court_rentals", "promo_id", "INTEGER"),
            ("court_rentals", "bonus_minutes", "INTEGER DEFAULT 0"),
            ("racket_rentals", "promo_id", "INTEGER"),
            ("racket_rentals", "bonus_minutes", "INTEGER DEFAULT 0"),
        ]:
            if table not in tables:
                continue
            cols = {c["name"] for c in insp.get_columns(table)}
            if column not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


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
        User,
    )

    Base.metadata.create_all(bind=engine)
    migrate_db()
