"""Promotion eligibility and rental term calculation."""

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Optional

from sqlalchemy.orm import Session

from config import facility_now
from models import Promo, RentalTimeOption

PROMO_BONUS_MINUTES = "bonus_minutes"
PROMO_DISCOUNT_PERCENT = "discount_percent"


@dataclass
class RentalTerms:
    """Resolved play time and billing for a rental."""

    play_duration_minutes: int
    amount_billed: float
    bonus_minutes: int
    is_extended_bundle: bool = False


@dataclass
class DurationQuote:
    play_duration_minutes: int
    amount_billed: float
    bonus_minutes: int
    promo: Optional[Promo]
    primary_option: RentalTimeOption
    breakdown: list
    plan_label: str


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
    return start_m <= now_m or now_m < end_m


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


def get_promo_base_option(db: Session, promo: Promo) -> Optional[RentalTimeOption]:
    if not promo.time_option_id:
        return None
    return db.query(RentalTimeOption).filter(RentalTimeOption.id == promo.time_option_id).first()


def promo_matches_option(db: Session, promo: Promo, option: RentalTimeOption) -> bool:
    """True if this promo applies to the selected time option."""
    if promo.time_option_id is None:
        return True
    if promo.time_option_id == option.id:
        return True
    if promo.promo_kind != PROMO_BONUS_MINUTES:
        return False
    bonus = promo.bonus_minutes or 0
    if bonus <= 0:
        return False
    base = get_promo_base_option(db, promo)
    if not base:
        return False
    return option.duration_minutes == base.duration_minutes + bonus


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
    option: RentalTimeOption,
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
        if not promo_matches_option(db, promo, option):
            continue
        return promo
    return None


def find_bundle_promo_for_duration(
    db: Session,
    rental_type: str,
    duration_minutes: int,
    at: Optional[datetime] = None,
) -> tuple[Optional[Promo], Optional[RentalTimeOption]]:
    """Promo where play duration equals base option + bonus (e.g. 4h = 3h + 1h free)."""
    at = at or facility_now()
    promos = (
        db.query(Promo)
        .filter(
            Promo.rental_type == rental_type,
            Promo.is_active.is_(True),
            Promo.promo_kind == PROMO_BONUS_MINUTES,
        )
        .order_by(Promo.priority.desc(), Promo.id.asc())
        .all()
    )
    for promo in promos:
        if not is_promo_active_now(promo, at):
            continue
        base = get_promo_base_option(db, promo)
        if not base:
            continue
        bonus = promo.bonus_minutes or 0
        if bonus <= 0:
            continue
        if duration_minutes == base.duration_minutes + bonus:
            return promo, base
    return None, None


def compute_rental_terms(
    option: RentalTimeOption,
    promo: Optional[Promo],
    db: Session,
) -> RentalTerms:
    """Resolve play duration, billed amount, and bonus minutes."""
    if not promo:
        return RentalTerms(option.duration_minutes, option.price, 0)

    base = get_promo_base_option(db, promo) if promo.time_option_id else None

    if promo.promo_kind == PROMO_BONUS_MINUTES:
        bonus = promo.bonus_minutes or 0
        bill_price = base.price if base else option.price

        if base and option.id != base.id and option.duration_minutes == base.duration_minutes + bonus:
            return RentalTerms(option.duration_minutes, bill_price, 0, is_extended_bundle=True)

        return RentalTerms(option.duration_minutes + bonus, bill_price, bonus)

    if promo.promo_kind == PROMO_DISCOUNT_PERCENT:
        pct = max(0, min(100, promo.discount_percent or 0))
        discounted = round(option.price * (1 - pct / 100), 2)
        return RentalTerms(option.duration_minutes, discounted, 0)

    return RentalTerms(option.duration_minutes, option.price, 0)


def format_duration_minutes(minutes: int) -> str:
    hours = minutes // 60
    mins = minutes % 60
    if mins == 0:
        return f"{hours}h"
    if hours == 0:
        return f"{mins}m"
    return f"{hours}h {mins}m"


def promo_summary(promo: Promo, option: RentalTimeOption, terms: Optional[RentalTerms] = None) -> str:
    if promo.promo_kind == PROMO_BONUS_MINUTES and promo.bonus_minutes:
        if terms and terms.is_extended_bundle:
            base = promo.time_option
            base_label = base.label if base else "promo rate"
            return f"Pay {base_label}, play {option.label}"
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
        promo = find_best_promo(db, rental_type, opt, at)
        if promo:
            terms = compute_rental_terms(opt, promo, db)
            hints[opt.id] = {
                "promo_id": promo.id,
                "name": promo.name,
                "summary": promo_summary(promo, opt, terms),
                "kind": promo.promo_kind,
                "bonus_minutes": terms.bonus_minutes,
                "discount_percent": promo.discount_percent or 0,
                "original_price": opt.price,
                "effective_price": terms.amount_billed,
                "effective_duration_minutes": terms.play_duration_minutes,
                "has_discount": terms.amount_billed < opt.price,
                "duration_label": format_duration_minutes(terms.play_duration_minutes),
                "is_extended_bundle": terms.is_extended_bundle,
            }
    return hints


def _greedy_breakdown(
    options: list[RentalTimeOption],
    duration_minutes: int,
) -> tuple[float, list, Optional[RentalTimeOption]]:
    remaining = duration_minutes
    total_amount = 0.0
    breakdown = []
    primary_option = None

    sorted_opts = sorted(options, key=lambda o: o.duration_minutes, reverse=True)

    while remaining > 0:
        best = next((o for o in sorted_opts if o.duration_minutes <= remaining), sorted_opts[-1])
        if primary_option is None:
            primary_option = best
        total_amount += best.price
        last = breakdown[-1] if breakdown else None
        if last and last["option_id"] == best.id:
            last["count"] += 1
        else:
            breakdown.append({
                "option_id": best.id,
                "label": best.label,
                "price": best.price,
                "duration_minutes": best.duration_minutes,
                "count": 1,
            })
        remaining = max(0, remaining - best.duration_minutes)

    return total_amount, breakdown, primary_option


def quote_rental_by_duration(
    db: Session,
    rental_type: str,
    duration_hours: int,
    at: Optional[datetime] = None,
) -> DurationQuote:
    """Price a rental by hours, applying promos before greedy option stacking."""
    at = at or facility_now()
    duration_minutes = duration_hours * 60

    options = (
        db.query(RentalTimeOption)
        .filter(
            RentalTimeOption.type == rental_type,
            RentalTimeOption.is_active.is_(True),
        )
        .order_by(RentalTimeOption.duration_minutes.desc())
        .all()
    )
    if not options:
        raise ValueError(f"No active {rental_type} time options configured")

    exact = next((o for o in options if o.duration_minutes == duration_minutes), None)
    if exact:
        promo = find_best_promo(db, rental_type, exact, at)
        terms = compute_rental_terms(exact, promo, db)
        label = promo_summary(promo, exact, terms) if promo else exact.label
        return DurationQuote(
            play_duration_minutes=terms.play_duration_minutes,
            amount_billed=terms.amount_billed,
            bonus_minutes=terms.bonus_minutes,
            promo=promo,
            primary_option=exact,
            breakdown=[],
            plan_label=label,
        )

    promo, base = find_bundle_promo_for_duration(db, rental_type, duration_minutes, at)
    if promo and base:
        terms = RentalTerms(duration_minutes, base.price, 0, is_extended_bundle=True)
        bundle_option = next((o for o in options if o.duration_minutes == duration_minutes), base)
        label = promo_summary(promo, bundle_option, terms)
        return DurationQuote(
            play_duration_minutes=terms.play_duration_minutes,
            amount_billed=terms.amount_billed,
            bonus_minutes=0,
            promo=promo,
            primary_option=bundle_option,
            breakdown=[],
            plan_label=label,
        )

    total_amount, breakdown, primary_option = _greedy_breakdown(options, duration_minutes)
    breakdown_str = " + ".join(
        item["label"] + (f" ×{item['count']}" if item["count"] > 1 else "")
        for item in breakdown
    )
    return DurationQuote(
        play_duration_minutes=duration_minutes,
        amount_billed=total_amount,
        bonus_minutes=0,
        promo=None,
        primary_option=primary_option,
        breakdown=breakdown,
        plan_label=f"{duration_hours}h ({breakdown_str})",
    )
