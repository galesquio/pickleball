from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload

from config import facility_now

from models import (
    Court,
    CourtRental,
    Racket,
    RacketRental,
    RacketSwap,
    RentalTimeOption,
    SystemLog,
    User,
)
from overtime_service import (
    compute_overtime,
    format_duration_minutes,
    get_settings,
    rental_timing_payload,
)
from promo_service import compute_rental_terms, find_best_promo, promo_summary, quote_rental_by_duration


def log_event(
    db: Session,
    event_type: str,
    description: str,
    user_id: Optional[int] = None,
    entity_type: str = "",
    entity_id: Optional[int] = None,
):
    db.add(
        SystemLog(
            event_type=event_type,
            description=description,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    )


def time_remaining_seconds(ends_at: datetime) -> int:
    delta = ends_at - facility_now()
    return max(0, int(delta.total_seconds()))


def rental_amount_billed(rental) -> float:
    billed = getattr(rental, "amount_billed", None)
    if billed is not None:
        return float(billed)
    return float(rental.amount_paid or 0)


def rental_balance_due(rental) -> float:
    return round(max(0.0, rental_amount_billed(rental) - float(rental.amount_paid or 0)), 2)


def rental_cash_pending(rental) -> float:
    if getattr(rental, "payment_pending", False):
        return round(float(rental.payment_pending_amount or 0), 2)
    if rental.status == "active":
        return rental_balance_due(rental)
    return 0.0


def rental_total_amount(rental) -> float:
    return round(rental_amount_billed(rental) + float(rental.overtime_charge or 0), 2)


def rental_sales_revenue(rental) -> float:
    """Revenue counted in sales (independent of physical cash collection)."""
    return rental_total_amount(rental)


def sales_period_filter(query, model, start, end, statuses):
    """Include rentals booked or completed/swap-finished in the date range."""
    completed_statuses = [s for s in statuses if s in ("completed", "swapped")]
    period = or_(
        and_(model.created_at >= start, model.created_at < end),
    )
    if completed_statuses:
        period = or_(
            period,
            and_(
                model.completed_at.isnot(None),
                model.completed_at >= start,
                model.completed_at < end,
                model.status.in_(completed_statuses),
            ),
        )
    return query.filter(period, model.status.in_(statuses))


def validate_rental_payment(amount_billed: float, payment_received: float) -> float:
    payment = round(max(0.0, float(payment_received)), 2)
    billed = round(float(amount_billed), 2)
    if payment > billed + 0.009:
        raise ValueError(
            f"Payment received ({payment:.2f}) cannot exceed billed amount ({billed:.2f})"
        )
    return payment


def apply_active_rental_payment(rental, payment_received: float) -> float:
    """Apply payment toward the base rental balance while the rental is still active."""
    balance = rental_balance_due(rental)
    payment = round(max(0.0, float(payment_received)), 2)
    if payment <= 0:
        raise ValueError("Payment amount must be greater than zero")
    if balance <= 0.009:
        raise ValueError("Base rental is already paid in full")
    if payment > balance + 0.009:
        raise ValueError(
            f"Payment ({payment:.2f}) exceeds remaining balance ({balance:.2f})"
        )
    rental.amount_paid = round(float(rental.amount_paid or 0) + payment, 2)
    return payment


def build_payment_preview(rental, rental_type: str, item_name: str) -> dict:
    billed = rental_amount_billed(rental)
    paid = float(rental.amount_paid or 0)
    balance_due = rental_balance_due(rental)
    label = rental.time_option.label if rental.time_option else ""
    return {
        "rental_id": rental.id,
        "rental_type": rental_type,
        "item_name": item_name,
        "customer": rental.customer_name,
        "time_option_label": label,
        "base_amount_billed": billed,
        "base_amount_paid": paid,
        "balance_due": balance_due,
        "paid_in_full": balance_due <= 0.009,
    }


def get_active_court_rental(db: Session, court_id: int) -> Optional[CourtRental]:
    return (
        db.query(CourtRental)
        .options(joinedload(CourtRental.time_option), joinedload(CourtRental.promo))
        .filter(
            CourtRental.court_id == court_id,
            CourtRental.status == "active",
        )
        .first()
    )


def get_active_racket_rental(db: Session, racket_id: int) -> Optional[RacketRental]:
    return (
        db.query(RacketRental)
        .options(joinedload(RacketRental.time_option), joinedload(RacketRental.promo))
        .filter(
            RacketRental.racket_id == racket_id,
            RacketRental.status == "active",
        )
        .first()
    )


def rental_to_dict(rental, rental_type: str, db: Session) -> dict:
    label = rental.time_option.label if rental.time_option else ""
    if getattr(rental, "bonus_minutes", 0):
        label = f"{label} (+{rental.bonus_minutes // 60}h bonus)" if rental.bonus_minutes >= 60 else f"{label} (+{rental.bonus_minutes}m bonus)"
    promo_name = rental.promo.name if getattr(rental, "promo", None) and rental.promo else ""
    settings = get_settings(db)
    timing = rental_timing_payload(rental.ends_at, settings)
    preview = compute_overtime(rental.ends_at, rental_type, settings)
    billed = rental_amount_billed(rental)
    paid = float(rental.amount_paid or 0)
    return {
        "rental_id": rental.id,
        "customer": rental.customer_name,
        "ends_at": rental.ends_at.isoformat(),
        "time_remaining_seconds": timing["time_remaining_seconds"],
        "timing_state": timing["timing_state"],
        "excess_seconds": timing["excess_seconds"],
        "excess_minutes": timing["excess_minutes"],
        "excess_label": format_duration_minutes(timing["excess_minutes"]),
        "estimated_overtime_charge": preview.overtime_charge,
        "time_option_label": label,
        "amount_billed": billed,
        "amount_paid": paid,
        "balance_due": rental_balance_due(rental),
        "promo_name": promo_name,
        "type": rental_type,
    }


def court_status_payload(db: Session, court: Court) -> dict:
    rental = get_active_court_rental(db, court.id)
    status = "rented" if rental else "available"
    payload = {
        "id": court.id,
        "name": court.name,
        "description": court.description,
        "status": status,
        "rental": rental_to_dict(rental, "court", db) if rental else None,
    }
    return payload


def racket_status_payload(db: Session, racket: Racket) -> dict:
    if racket.status == "damaged":
        status = "damaged"
        rental = None
    else:
        rental = get_active_racket_rental(db, racket.id)
        if rental:
            status = "rented"
        elif racket.status == "rented":
            status = "available"
            racket.status = "available"
            db.commit()
        else:
            status = "available"
    payload = {
        "id": racket.id,
        "name": racket.name,
        "rf_chip_id": racket.rf_chip_id,
        "status": status,
        "rental": rental_to_dict(rental, "racket", db) if rental else None,
    }
    return payload


def create_court_rental(
    db: Session,
    court_id: int,
    time_option_id: int,
    customer_name: str,
    cashier: User,
    payment_received: float = 0.0,
) -> CourtRental:
    court = db.query(Court).filter(Court.id == court_id, Court.is_active.is_(True)).first()
    if not court:
        raise ValueError("Court not found or inactive")
    if get_active_court_rental(db, court_id):
        raise ValueError("Court is already rented")

    option = (
        db.query(RentalTimeOption)
        .filter(
            RentalTimeOption.id == time_option_id,
            RentalTimeOption.type == "court",
            RentalTimeOption.is_active.is_(True),
        )
        .first()
    )
    if not option:
        raise ValueError("Invalid time option")

    started_at = facility_now()
    promo = find_best_promo(db, "court", option, started_at)
    terms = compute_rental_terms(option, promo, db)
    if terms.amount_billed <= 0:
        raise ValueError("Time option has no price configured")
    payment = validate_rental_payment(terms.amount_billed, payment_received)
    ends_at = started_at + timedelta(minutes=terms.play_duration_minutes)
    rental = CourtRental(
        court_id=court_id,
        time_option_id=time_option_id,
        promo_id=promo.id if promo else None,
        cashier_id=cashier.id,
        customer_name=customer_name.strip(),
        started_at=started_at,
        ends_at=ends_at,
        status="active",
        amount_billed=terms.amount_billed,
        amount_paid=payment,
        bonus_minutes=terms.bonus_minutes,
    )
    db.add(rental)
    db.commit()
    db.refresh(rental)
    promo_note = f" ({promo.name})" if promo else ""
    balance = rental_balance_due(rental)
    pay_note = f", paid {payment:.2f}"
    if balance > 0:
        pay_note += f", balance {balance:.2f}"
    log_event(
        db,
        "COURT_RENTED",
        f"Court {court.name} rented to {customer_name} for {promo_summary(promo, option, terms) if promo else option.label}{promo_note} "
        f"(billed {terms.amount_billed:.2f}{pay_note})",
        cashier.id,
        "court_rental",
        rental.id,
    )
    db.commit()
    return rental


def compute_greedy_amount(db: Session, duration_hours: int, rental_type: str = "court") -> tuple:
    """Price by duration with promos when eligible, otherwise greedy option stacking."""
    quote = quote_rental_by_duration(db, rental_type, duration_hours)
    return quote.amount_billed, quote.breakdown, quote.primary_option


def create_court_rental_schedule(
    db: Session,
    court_id: int,
    customer_name: str,
    start_time: datetime,
    duration_hours: int,
    cashier: User,
    payment_received: float = 0.0,
) -> CourtRental:
    court = db.query(Court).filter(Court.id == court_id, Court.is_active.is_(True)).first()
    if not court:
        raise ValueError("Court not found or inactive")

    quote = quote_rental_by_duration(db, "court", duration_hours, start_time)
    play_minutes = quote.play_duration_minutes
    ends_at = start_time + timedelta(minutes=play_minutes)

    overlap = (
        db.query(CourtRental)
        .filter(
            CourtRental.court_id == court_id,
            CourtRental.status == "active",
            CourtRental.started_at < ends_at,
            CourtRental.ends_at > start_time,
        )
        .first()
    )
    if overlap:
        raise ValueError(f"Court already has an active booking that overlaps this time slot")

    payment = validate_rental_payment(quote.amount_billed, payment_received)

    rental = CourtRental(
        court_id=court_id,
        time_option_id=quote.primary_option.id,
        promo_id=quote.promo.id if quote.promo else None,
        cashier_id=cashier.id,
        customer_name=customer_name.strip(),
        started_at=start_time,
        ends_at=ends_at,
        status="active",
        amount_billed=quote.amount_billed,
        amount_paid=payment,
        bonus_minutes=quote.bonus_minutes,
    )
    db.add(rental)
    db.commit()
    db.refresh(rental)

    balance = rental_balance_due(rental)
    promo_note = f" ({quote.promo.name})" if quote.promo else ""
    log_event(
        db,
        "COURT_RENTED",
        f"Court {court.name} rented to {customer_name} for {quote.plan_label}{promo_note} "
        f"(billed {quote.amount_billed:.2f}, paid {payment:.2f}"
        + (f", balance {balance:.2f}" if balance > 0 else "")
        + ")",
        cashier.id,
        "court_rental",
        rental.id,
    )
    db.commit()
    return rental


def rental_is_upcoming(rental) -> bool:
    return rental.started_at > facility_now()


def can_cancel_court_booking(rental, settings) -> tuple[bool, str]:
    if rental.status != "active":
        return False, "Only active bookings can be cancelled"
    if not rental_is_upcoming(rental):
        return False, "Cannot cancel a booking that has already started"
    paid = rental_balance_due(rental) <= 0.009
    if paid and not settings.allow_cancel_paid_booking:
        return False, "Paid bookings cannot be cancelled (facility policy)"
    if not paid and not settings.allow_cancel_unpaid_booking:
        return False, "Unpaid bookings cannot be cancelled (facility policy)"
    return True, ""


def cancel_court_rental(db: Session, rental_id: int, cashier: User) -> CourtRental:
    rental = (
        db.query(CourtRental)
        .options(joinedload(CourtRental.court))
        .filter(CourtRental.id == rental_id)
        .first()
    )
    if not rental:
        raise ValueError("Booking not found")

    settings = get_settings(db)
    allowed, reason = can_cancel_court_booking(rental, settings)
    if not allowed:
        raise ValueError(reason)

    court_name = rental.court.name if rental.court else f"Court #{rental.court_id}"
    paid = float(rental.amount_paid or 0)
    rental.status = "cancelled"
    log_event(
        db,
        "COURT_BOOKING_CANCELLED",
        (
            f"Cancelled upcoming booking for {rental.customer_name} on {court_name} "
            f"({rental.started_at.strftime('%Y-%m-%d %H:%M')} – "
            f"{rental.ends_at.strftime('%H:%M')}, billed {rental.amount_billed:.2f}, "
            f"paid {paid:.2f})"
        ),
        cashier.id,
        "court_rental",
        rental.id,
    )
    db.commit()
    db.refresh(rental)
    return rental


def create_racket_rental(
    db: Session,
    racket_id: int,
    customer_name: str,
    cashier: User,
    payment_received: float = 0.0,
    time_option_id: int | None = None,
    duration_hours: int | None = None,
) -> RacketRental:
    racket = (
        db.query(Racket)
        .filter(Racket.id == racket_id, Racket.is_active.is_(True))
        .first()
    )
    if not racket:
        raise ValueError("Racket not found or inactive")
    if racket.status != "available":
        raise ValueError("Racket is not available")
    if get_active_racket_rental(db, racket_id):
        raise ValueError("Racket is already rented")

    if duration_hours is not None and time_option_id is not None:
        raise ValueError("Provide either duration_hours or time_option_id, not both")
    if duration_hours is None and time_option_id is None:
        raise ValueError("duration_hours or time_option_id is required")

    started_at = facility_now()
    promo = None
    bonus_minutes = 0

    if duration_hours is not None:
        quote = quote_rental_by_duration(db, "racket", duration_hours, started_at)
        if quote.amount_billed <= 0:
            raise ValueError("No price configured for this duration")
        promo = quote.promo
        amount_billed = quote.amount_billed
        duration_minutes = quote.play_duration_minutes
        bonus_minutes = quote.bonus_minutes
        time_option_id = quote.primary_option.id
        plan_label = quote.plan_label
    else:
        option = (
            db.query(RentalTimeOption)
            .filter(
                RentalTimeOption.id == time_option_id,
                RentalTimeOption.type == "racket",
                RentalTimeOption.is_active.is_(True),
            )
            .first()
        )
        if not option:
            raise ValueError("Invalid time option")
        promo = find_best_promo(db, "racket", option, started_at)
        terms = compute_rental_terms(option, promo, db)
        if terms.amount_billed <= 0:
            raise ValueError("Time option has no price configured")
        amount_billed = terms.amount_billed
        duration_minutes = terms.play_duration_minutes
        bonus_minutes = terms.bonus_minutes
        plan_label = promo_summary(promo, option, terms) if promo else option.label

    payment = validate_rental_payment(amount_billed, payment_received)
    ends_at = started_at + timedelta(minutes=duration_minutes)
    rental = RacketRental(
        racket_id=racket_id,
        time_option_id=time_option_id,
        promo_id=promo.id if promo else None,
        cashier_id=cashier.id,
        customer_name=customer_name.strip(),
        started_at=started_at,
        ends_at=ends_at,
        status="active",
        amount_billed=amount_billed,
        amount_paid=payment,
        bonus_minutes=bonus_minutes,
    )
    racket.status = "rented"
    db.add(rental)
    db.commit()
    db.refresh(rental)
    promo_note = f" ({promo.name})" if promo else ""
    balance = rental_balance_due(rental)
    pay_note = f", paid {payment:.2f}"
    if balance > 0:
        pay_note += f", balance {balance:.2f}"
    log_event(
        db,
        "RACKET_RENTED",
        f"Racket {racket.name} rented to {customer_name} for {plan_label}{promo_note} "
        f"(billed {amount_billed:.2f}{pay_note})",
        cashier.id,
        "racket_rental",
        rental.id,
    )
    db.commit()
    return rental


def swap_racket(
    db: Session,
    rental_id: int,
    new_racket_id: int,
    reason: str,
    cashier: User,
) -> RacketRental:
    rental = (
        db.query(RacketRental)
        .options(joinedload(RacketRental.racket))
        .filter(RacketRental.id == rental_id, RacketRental.status == "active")
        .first()
    )
    if not rental:
        raise ValueError("Active rental not found")

    new_racket = (
        db.query(Racket)
        .filter(Racket.id == new_racket_id, Racket.is_active.is_(True))
        .first()
    )
    if not new_racket or new_racket.status != "available":
        raise ValueError("New racket is not available")

    old_racket = rental.racket
    old_racket_id = rental.racket_id

    swap = RacketSwap(
        original_rental_id=rental.id,
        old_racket_id=old_racket_id,
        new_racket_id=new_racket_id,
        reason=reason.strip(),
        swapped_by=cashier.id,
    )
    old_racket.status = "damaged"
    new_racket.status = "rented"
    rental.racket_id = new_racket_id
    db.add(swap)
    db.commit()
    log_event(
        db,
        "RACKET_SWAPPED",
        f"Swapped {old_racket.name} → {new_racket.name}: {reason}",
        cashier.id,
        "racket_rental",
        rental.id,
    )
    db.commit()
    return rental


def build_completion_preview(db: Session, rental, rental_type: str, item_name: str) -> dict:
    settings = get_settings(db)
    overtime = compute_overtime(rental.ends_at, rental_type, settings)
    label = rental.time_option.label if rental.time_option else ""
    billed = rental_amount_billed(rental)
    paid = float(rental.amount_paid or 0)
    balance_due = rental_balance_due(rental)
    amount_due_now = round(balance_due + overtime.overtime_charge, 2)
    return {
        "rental_id": rental.id,
        "rental_type": rental_type,
        "item_name": item_name,
        "customer": rental.customer_name,
        "time_option_label": label,
        "ends_at": rental.ends_at.isoformat(),
        "base_amount_billed": billed,
        "base_amount_paid": paid,
        "balance_due": balance_due,
        "excess_minutes": overtime.excess_minutes,
        "excess_label": format_duration_minutes(overtime.excess_minutes),
        "grace_minutes": overtime.grace_minutes,
        "overtime_hours_charged": overtime.overtime_hours_charged,
        "rate_per_hour": overtime.rate_per_hour,
        "overtime_charge": overtime.overtime_charge,
        "amount_due_now": amount_due_now,
        "total_revenue": billed + overtime.overtime_charge,
    }


def _finalize_completion(
    db: Session,
    rental,
    rental_type: str,
    user: User,
    payment_received: float,
    item_name: str,
    event_type: str,
    entity_type: str,
):
    settings = get_settings(db)
    completed_at = facility_now()
    overtime = compute_overtime(rental.ends_at, rental_type, settings, completed_at)

    balance_due = rental_balance_due(rental)
    amount_due = round(balance_due + overtime.overtime_charge, 2)
    payment = round(max(0.0, float(payment_received)), 2)
    if amount_due > 0 and payment < amount_due - 0.009:
        raise ValueError(
            f"Payment received ({payment:.2f}) is less than amount due ({amount_due:.2f})"
        )

    change = round(max(0.0, payment - amount_due), 2)
    rental.amount_paid = round(float(rental.amount_paid or 0) + payment, 2)
    rental.completed_at = completed_at
    rental.overtime_minutes = overtime.excess_minutes
    rental.overtime_hours_charged = overtime.overtime_hours_charged
    rental.overtime_charge = overtime.overtime_charge
    rental.checkout_payment = payment
    rental.checkout_change = change
    rental.status = "completed"

    total = rental_total_amount(rental)
    overtime_note = ""
    if overtime.has_charge:
        overtime_note = (
            f"; overtime {overtime.overtime_hours_charged}h @ {overtime.rate_per_hour:.0f} "
            f"= {overtime.overtime_charge:.2f}, paid {payment:.2f}, change {change:.2f}"
        )
    elif balance_due > 0:
        overtime_note = f"; balance paid {payment:.2f}, change {change:.2f}"
    log_event(
        db,
        event_type,
        f"{item_name} rental #{rental.id} completed for {rental.customer_name} "
        f"(total {total:.2f}{overtime_note})",
        user.id,
        entity_type,
        rental.id,
    )
    return rental, overtime, change


def complete_court_rental(
    db: Session, rental_id: int, user: User, payment_received: float = 0.0
) -> CourtRental:
    rental = (
        db.query(CourtRental)
        .options(joinedload(CourtRental.court), joinedload(CourtRental.time_option))
        .filter(CourtRental.id == rental_id)
        .first()
    )
    if not rental:
        raise ValueError("Rental not found")
    if rental.status != "active":
        raise ValueError("Rental is not active")
    item_name = rental.court.name if rental.court else f"Court #{rental.court_id}"
    _finalize_completion(
        db,
        rental,
        "court",
        user,
        payment_received,
        item_name,
        "COURT_COMPLETED",
        "court_rental",
    )
    db.commit()
    return rental


def complete_racket_rental(
    db: Session, rental_id: int, user: User, payment_received: float = 0.0
) -> RacketRental:
    rental = (
        db.query(RacketRental)
        .options(joinedload(RacketRental.racket), joinedload(RacketRental.time_option))
        .filter(RacketRental.id == rental_id)
        .first()
    )
    if not rental:
        raise ValueError("Rental not found")
    if rental.status != "active":
        raise ValueError("Rental is not active")
    if rental.racket:
        rental.racket.status = "available"
    item_name = rental.racket.name if rental.racket else f"Racket #{rental.racket_id}"
    _finalize_completion(
        db,
        rental,
        "racket",
        user,
        payment_received,
        item_name,
        "RACKET_COMPLETED",
        "racket_rental",
    )
    db.commit()
    return rental


def record_court_rental_payment(
    db: Session, rental_id: int, user: User, payment_received: float
) -> CourtRental:
    rental = (
        db.query(CourtRental)
        .options(joinedload(CourtRental.court), joinedload(CourtRental.time_option))
        .filter(CourtRental.id == rental_id, CourtRental.status == "active")
        .first()
    )
    if not rental:
        raise ValueError("Active rental not found")
    payment = apply_active_rental_payment(rental, payment_received)
    item_name = rental.court.name if rental.court else f"Court #{rental.court_id}"
    balance = rental_balance_due(rental)
    log_event(
        db,
        "COURT_PAYMENT",
        f"{item_name} rental #{rental.id}: +{payment:.2f} toward base rental "
        f"(paid {rental.amount_paid:.2f} / {rental_amount_billed(rental):.2f}"
        f"{', balance ' + f'{balance:.2f}' if balance > 0 else ', paid in full'})",
        user.id,
        "court_rental",
        rental.id,
    )
    db.commit()
    return rental


def record_racket_rental_payment(
    db: Session, rental_id: int, user: User, payment_received: float
) -> RacketRental:
    rental = (
        db.query(RacketRental)
        .options(joinedload(RacketRental.racket), joinedload(RacketRental.time_option))
        .filter(RacketRental.id == rental_id, RacketRental.status == "active")
        .first()
    )
    if not rental:
        raise ValueError("Active rental not found")
    payment = apply_active_rental_payment(rental, payment_received)
    item_name = rental.racket.name if rental.racket else f"Racket #{rental.racket_id}"
    balance = rental_balance_due(rental)
    log_event(
        db,
        "RACKET_PAYMENT",
        f"{item_name} rental #{rental.id}: +{payment:.2f} toward base rental "
        f"(paid {rental.amount_paid:.2f} / {rental_amount_billed(rental):.2f}"
        f"{', balance ' + f'{balance:.2f}' if balance > 0 else ', paid in full'})",
        user.id,
        "racket_rental",
        rental.id,
    )
    db.commit()
    return rental


def preview_court_payment(db: Session, rental_id: int) -> dict:
    rental = (
        db.query(CourtRental)
        .options(joinedload(CourtRental.court), joinedload(CourtRental.time_option))
        .filter(CourtRental.id == rental_id, CourtRental.status == "active")
        .first()
    )
    if not rental:
        raise ValueError("Active rental not found")
    name = rental.court.name if rental.court else f"Court #{rental.court_id}"
    return build_payment_preview(rental, "court", name)


def preview_racket_payment(db: Session, rental_id: int) -> dict:
    rental = (
        db.query(RacketRental)
        .options(joinedload(RacketRental.racket), joinedload(RacketRental.time_option))
        .filter(RacketRental.id == rental_id, RacketRental.status == "active")
        .first()
    )
    if not rental:
        raise ValueError("Active rental not found")
    name = rental.racket.name if rental.racket else f"Racket #{rental.racket_id}"
    return build_payment_preview(rental, "racket", name)


def preview_court_completion(db: Session, rental_id: int) -> dict:
    rental = (
        db.query(CourtRental)
        .options(joinedload(CourtRental.court), joinedload(CourtRental.time_option))
        .filter(CourtRental.id == rental_id, CourtRental.status == "active")
        .first()
    )
    if not rental:
        raise ValueError("Active rental not found")
    name = rental.court.name if rental.court else f"Court #{rental.court_id}"
    return build_completion_preview(db, rental, "court", name)


def preview_racket_completion(db: Session, rental_id: int) -> dict:
    rental = (
        db.query(RacketRental)
        .options(joinedload(RacketRental.racket), joinedload(RacketRental.time_option))
        .filter(RacketRental.id == rental_id, RacketRental.status == "active")
        .first()
    )
    if not rental:
        raise ValueError("Active rental not found")
    name = rental.racket.name if rental.racket else f"Racket #{rental.racket_id}"
    return build_completion_preview(db, rental, "racket", name)


def _auto_complete_expired_rental(
    db: Session,
    rental,
    rental_type: str,
    settings,
) -> bool:
    """Complete a rental past its end time.

    Only rentals with an unpaid base balance at expiry are flagged for cash collection
    (payment_pending). Prepaid bookings complete without a collect-cash tag even if overtime applies.
    """
    if rental.status != "active" or rental.ends_at > facility_now():
        return False

    balance_due = rental_balance_due(rental)
    completed_at = facility_now()
    overtime = compute_overtime(rental.ends_at, rental_type, settings, completed_at)
    unpaid_base = balance_due > 0.009
    cash_still_owed = round(balance_due + overtime.overtime_charge, 2) if unpaid_base else 0.0

    rental.auto_completed = True
    rental.completed_at = completed_at
    rental.overtime_minutes = overtime.excess_minutes
    rental.overtime_hours_charged = overtime.overtime_hours_charged
    rental.overtime_charge = overtime.overtime_charge

    if unpaid_base and cash_still_owed > 0.009:
        rental.amount_paid = rental_total_amount(rental)
        rental.payment_pending = True
        rental.payment_pending_amount = cash_still_owed
    rental.checkout_payment = 0
    rental.checkout_change = 0
    rental.status = "completed"

    if rental_type == "racket" and rental.racket:
        rental.racket.status = "available"

    if rental_type == "court":
        item_name = rental.court.name if rental.court else f"Court #{rental.court_id}"
        event_type = "COURT_AUTO_COMPLETED"
        entity_type = "court_rental"
    else:
        item_name = rental.racket.name if rental.racket else f"Racket #{rental.racket_id}"
        event_type = "RACKET_AUTO_COMPLETED"
        entity_type = "racket_rental"

    total = rental_total_amount(rental)
    note = f"{item_name} rental #{rental.id} auto-completed for {rental.customer_name} (total {total:.2f})"
    if unpaid_base and cash_still_owed > 0.009:
        note += (
            f"; system marked paid — collect {cash_still_owed:.2f} cash from customer"
        )
    log_event(db, event_type, note, None, entity_type, rental.id)
    return True


def auto_complete_expired_rentals(db: Session) -> int:
    """Auto-complete active rentals past end time. Returns count completed."""
    settings = get_settings(db)
    count = 0

    court_rentals = (
        db.query(CourtRental)
        .options(joinedload(CourtRental.court))
        .filter(CourtRental.status == "active", CourtRental.ends_at <= facility_now())
        .all()
    )
    for rental in court_rentals:
        if _auto_complete_expired_rental(db, rental, "court", settings):
            count += 1

    racket_rentals = (
        db.query(RacketRental)
        .options(joinedload(RacketRental.racket))
        .filter(RacketRental.status == "active", RacketRental.ends_at <= facility_now())
        .all()
    )
    for rental in racket_rentals:
        if _auto_complete_expired_rental(db, rental, "racket", settings):
            count += 1

    if count:
        db.commit()
    return count


def confirm_court_collection(db: Session, rental_id: int, user: User) -> CourtRental:
    rental = (
        db.query(CourtRental)
        .options(joinedload(CourtRental.court))
        .filter(CourtRental.id == rental_id, CourtRental.status == "completed")
        .first()
    )
    if not rental:
        raise ValueError("Completed rental not found")
    if not rental.payment_pending:
        raise ValueError("No pending collection on this rental")
    amount = float(rental.payment_pending_amount or 0)
    rental.payment_pending = False
    rental.payment_pending_amount = 0
    item_name = rental.court.name if rental.court else f"Court #{rental.court_id}"
    log_event(
        db,
        "COURT_COLLECTION",
        f"{item_name} rental #{rental.id}: collected {amount:.2f} cash from {rental.customer_name}",
        user.id,
        "court_rental",
        rental.id,
    )
    db.commit()
    return rental


def confirm_racket_collection(db: Session, rental_id: int, user: User) -> RacketRental:
    rental = (
        db.query(RacketRental)
        .options(joinedload(RacketRental.racket))
        .filter(RacketRental.id == rental_id, RacketRental.status == "completed")
        .first()
    )
    if not rental:
        raise ValueError("Completed rental not found")
    if not rental.payment_pending:
        raise ValueError("No pending collection on this rental")
    amount = float(rental.payment_pending_amount or 0)
    rental.payment_pending = False
    rental.payment_pending_amount = 0
    item_name = rental.racket.name if rental.racket else f"Racket #{rental.racket_id}"
    log_event(
        db,
        "RACKET_COLLECTION",
        f"{item_name} rental #{rental.id}: collected {amount:.2f} cash from {rental.customer_name}",
        user.id,
        "racket_rental",
        rental.id,
    )
    db.commit()
    return rental
