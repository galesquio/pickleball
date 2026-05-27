from sqlalchemy.orm import Session

from auth import hash_password
from models import Court, Promo, Racket, RentalTimeOption, SystemSettings, User
from overtime_service import ensure_settings
from promo_service import PROMO_BONUS_MINUTES, PROMO_DISCOUNT_PERCENT


def seed_database(db: Session) -> bool:
    """Seed default data. Returns True if admin was newly created."""
    ensure_settings(db)
    admin_created = False

    if not db.query(User).filter(User.username == "admin").first():
        db.add(
            User(
                username="admin",
                password_hash=hash_password("admin123"),
                role="admin",
            )
        )
        db.add(
            User(
                username="cashier1",
                password_hash=hash_password("cashier123"),
                role="cashier",
            )
        )
        admin_created = True

    if db.query(Court).count() == 0:
        db.add(Court(name="Court A", description="Main court"))
        db.add(Court(name="Court B", description="Secondary court"))

    if db.query(Racket).count() == 0:
        for i in range(1, 7):
            db.add(Racket(name=f"Racket {i}", rf_chip_id=f"RF-PLACEHOLDER-{i}"))

    if db.query(RentalTimeOption).count() == 0:
        court_options = [
            ("3 Hours", 180, 300),
            ("6 Hours", 360, 500),
            ("12 Hours", 720, 800),
        ]
        for label, minutes, price in court_options:
            db.add(
                RentalTimeOption(
                    type="court",
                    label=label,
                    duration_minutes=minutes,
                    price=price,
                )
            )

        racket_options = [
            ("1 Hour", 60, 50),
            ("3 Hours", 180, 120),
            ("5 Hours", 300, 180),
        ]
        for label, minutes, price in racket_options:
            db.add(
                RentalTimeOption(
                    type="racket",
                    label=label,
                    duration_minutes=minutes,
                    price=price,
                )
            )

    if db.query(Promo).count() == 0:
        court_3h = (
            db.query(RentalTimeOption)
            .filter(RentalTimeOption.type == "court", RentalTimeOption.label == "3 Hours")
            .first()
        )
        racket_3h = (
            db.query(RentalTimeOption)
            .filter(RentalTimeOption.type == "racket", RentalTimeOption.label == "3 Hours")
            .first()
        )
        if court_3h:
            db.add(
                Promo(
                    name="Morning Bonus Hour",
                    description="Rent 3 hours in the morning, get 1 extra hour free.",
                    rental_type="court",
                    time_option_id=court_3h.id,
                    promo_kind=PROMO_BONUS_MINUTES,
                    bonus_minutes=60,
                    window_start="07:00",
                    window_end="12:00",
                    priority=10,
                    is_active=True,
                )
            )
        if racket_3h:
            db.add(
                Promo(
                    name="Afternoon Racket Deal",
                    description="15% off 3-hour racket rentals during slow afternoon hours.",
                    rental_type="racket",
                    time_option_id=racket_3h.id,
                    promo_kind=PROMO_DISCOUNT_PERCENT,
                    discount_percent=15,
                    window_start="14:00",
                    window_end="17:00",
                    priority=5,
                    is_active=True,
                )
            )
        db.add(
            Promo(
                name="Weekend Court Extension",
                description="Saturday & Sunday: any court rental gets 30 extra minutes.",
                rental_type="court",
                time_option_id=None,
                promo_kind=PROMO_BONUS_MINUTES,
                bonus_minutes=30,
                window_start="00:00",
                window_end="24:00",
                days_of_week="5,6",
                priority=1,
                is_active=True,
            )
        )

    db.commit()
    return admin_created


def print_default_credentials():
    print("=" * 60)
    print("  DEFAULT CREDENTIALS (change immediately after login)")
    print("  Admin:   admin / admin123")
    print("  Cashier: cashier1 / cashier123")
    print("=" * 60)


def notify_default_credentials():
    """Show default login credentials on first run (console or dialog)."""
    import sys

    if getattr(sys, "frozen", False):
        try:
            import ctypes

            msg = (
                "Default credentials (change after login):\n\n"
                "Admin:   admin / admin123\n"
                "Cashier: cashier1 / cashier123"
            )
            ctypes.windll.user32.MessageBoxW(0, msg, "Pickleball - First Run", 0x40)
        except Exception:
            print_default_credentials()
    else:
        print_default_credentials()
