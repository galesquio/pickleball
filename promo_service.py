"""Promotion eligibility and rental term calculation."""

from datetime import date, datetime, time
from typing import Optional

from sqlalchemy.orm import Session

from config import facility_now
from models import Promo, RentalTimeOption

PROMO_BONUS_MINUTES = "bonus_minutes"
PROMO_DISCOUNT_PERCENT = "discount_percent"


def parse_hhmm(value: str) -> time:
    parts = value.strip().split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    if hour == 24 and minute == 0:
        hour, minute = 23, 59
    return time(hour=hour, minute=minute)


def minutes_from_hhmm(value: str) -> int:
    if value.strip() == "24:00":
        return 24 * 60
    return minutes_of_day(datetime.combine(date.min, parse_hhmm(value)))


def minutes_of_day(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def _in_time_window(dt: datetime, start: str, end: str) -> bool:
    """True if dt's clock time is in [start, end). Overnight windows supported."""
    start_m = minutes_from_hhmm(start)
    end_m = minutes_from_hhmm(end)
    now_m = minutes_of_day(dt)
    if start_m < end_m:
        return start_m <= now_m < end_m
    return now_m >= start_m or now_m < end_m


def _in_date_range(dt: datetime, valid_from: Optional[date], valid_until: Optional[date]) -> bool:
    d = dt.date()
    if valid_from and d < valid_from:
        return False
    if valid_until and d > valid_until:
        return False
    return True


def _matches_day(dt: datetime, days_of_week: str) -> bool:
    if not days_of_week or not days_of_week.strip():
        return True
    allowed = {int(x.strip()) for x in days_of_week.split(",") if x.strip().isdigit()}
    return dt.weekday() in allowed


def promo_applies_to_option(promo: Promo, time_option_id: int) -> bool:
    if promo.time_option_id is None:
        return True
    return promo.time_option_id == time_option_id


def is_promo_active_now(promo: Promo, at: Optional[datetime] = None) -> bool:
    if not promo.is_active:
        return False
    at = at or facility_now()
    if not _in_date_range(at, promo.valid_from, promo.valid_until):
        return False
    if not _matches_day(at, promo.days_of_week or ""):
        return False
    return _in_time_window(at, promo.window_start, promo.window_end)


def find_best_promo(
    db: Session,
    rental_type: str,
    time_option_id: int,
    at: Optional[datetime] = None,
) -> Optional[Promo]:
    at = at or facility_now()
    promos = (
        db.query(Promo)
        .filter(Promo.rental_type == rental_type, Promo.is_active.is_(True))
        .order_by(Promo.priority.desc(), Promo.id.asc())
        .all()
    )
    for promo in promos:
        if not is_promo_active_now(promo, at):
            continue
        if not promo_applies_to_option(promo, time_option_id):
            continue
        return promo
    return None


def compute_rental_terms(
    option: RentalTimeOption,
    promo: Optional[Promo],
) -> tuple[int, float, int]:
    """Returns (total_duration_minutes, amount_billed, bonus_minutes)."""
    duration = option.duration_minutes
    price = option.price
    bonus = 0

    if not promo:
        return duration, price, bonus

    if promo.promo_kind == PROMO_BONUS_MINUTES:
        bonus = promo.bonus_minutes or 0
        return duration + bonus, price, bonus

    if promo.promo_kind == PROMO_DISCOUNT_PERCENT:
        pct = max(0, min(100, promo.discount_percent or 0))
        discounted = round(price * (1 - pct / 100), 2)
        return duration, discounted, 0

    return duration, price, bonus


def format_duration_minutes(minutes: int) -> str:
    hours = minutes // 60
    mins = minutes % 60
    if mins == 0:
        return f"{hours}h"
    if hours == 0:
        return f"{mins}m"
    return f"{hours}h {mins}m"


def promo_summary(promo: Promo, option: RentalTimeOption) -> str:
    if promo.promo_kind == PROMO_BONUS_MINUTES and promo.bonus_minutes:
        hours = promo.bonus_minutes // 60
        mins = promo.bonus_minutes % 60
        extra = f"+{hours}h" if mins == 0 else f"+{hours}h {mins}m" if hours else f"+{mins}m"
        return f"{option.label} {extra} free"
    if promo.promo_kind == PROMO_DISCOUNT_PERCENT and promo.discount_percent:
        return f"{int(promo.discount_percent)}% off {option.label}"
    return promo.name


def active_promos_for_type(db: Session, rental_type: str, at: Optional[datetime] = None) -> list[Promo]:
    at = at or facility_now()
    return [p for p in db.query(Promo).filter(Promo.rental_type == rental_type).all() if is_promo_active_now(p, at)]


def promo_hints_for_options(
    db: Session,
    rental_type: str,
    options: list[RentalTimeOption],
    at: Optional[datetime] = None,
) -> dict[int, dict]:
    """Map time_option_id -> display hint for options that have an active promo now."""
    at = at or facility_now()
    hints: dict[int, dict] = {}
    for opt in options:
        promo = find_best_promo(db, rental_type, opt.id, at)
        if promo:
            duration_mins, effective_price, bonus = compute_rental_terms(opt, promo)
            hints[opt.id] = {
                "promo_id": promo.id,
                "name": promo.name,
                "summary": promo_summary(promo, opt),
                "kind": promo.promo_kind,
                "bonus_minutes": bonus,
                "discount_percent": promo.discount_percent or 0,
                "original_price": opt.price,
                "effective_price": effective_price,
                "effective_duration_minutes": duration_mins,
                "has_discount": effective_price < opt.price,
                "duration_label": format_duration_minutes(duration_mins),
            }
    return hints
