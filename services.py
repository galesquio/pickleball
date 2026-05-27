from datetime import datetime, timedelta
from typing import Optional

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
from promo_service import compute_rental_terms, find_best_promo, promo_summary


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


def rental_to_dict(rental, rental_type: str) -> dict:
    label = rental.time_option.label if rental.time_option else ""
    if getattr(rental, "bonus_minutes", 0):
        label = f"{label} (+{rental.bonus_minutes // 60}h bonus)" if rental.bonus_minutes >= 60 else f"{label} (+{rental.bonus_minutes}m bonus)"
    promo_name = rental.promo.name if getattr(rental, "promo", None) and rental.promo else ""
    return {
        "rental_id": rental.id,
        "customer": rental.customer_name,
        "ends_at": rental.ends_at.isoformat(),
        "time_remaining_seconds": time_remaining_seconds(rental.ends_at),
        "time_option_label": label,
        "amount_paid": rental.amount_paid,
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
        "rental": rental_to_dict(rental, "court") if rental else None,
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
        "rental": rental_to_dict(rental, "racket") if rental else None,
    }
    return payload


def create_court_rental(
    db: Session,
    court_id: int,
    time_option_id: int,
    customer_name: str,
    cashier: User,
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
    promo = find_best_promo(db, "court", time_option_id, started_at)
    duration_minutes, amount_paid, bonus_minutes = compute_rental_terms(option, promo)
    ends_at = started_at + timedelta(minutes=duration_minutes)
    rental = CourtRental(
        court_id=court_id,
        time_option_id=time_option_id,
        promo_id=promo.id if promo else None,
        cashier_id=cashier.id,
        customer_name=customer_name.strip(),
        started_at=started_at,
        ends_at=ends_at,
        status="active",
        amount_paid=amount_paid,
        bonus_minutes=bonus_minutes,
    )
    db.add(rental)
    db.commit()
    db.refresh(rental)
    promo_note = f" ({promo.name})" if promo else ""
    log_event(
        db,
        "COURT_RENTED",
        f"Court {court.name} rented to {customer_name} for {promo_summary(promo, option) if promo else option.label}{promo_note}",
        cashier.id,
        "court_rental",
        rental.id,
    )
    db.commit()
    return rental


def create_racket_rental(
    db: Session,
    racket_id: int,
    time_option_id: int,
    customer_name: str,
    cashier: User,
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

    started_at = facility_now()
    promo = find_best_promo(db, "racket", time_option_id, started_at)
    duration_minutes, amount_paid, bonus_minutes = compute_rental_terms(option, promo)
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
        amount_paid=amount_paid,
        bonus_minutes=bonus_minutes,
    )
    racket.status = "rented"
    db.add(rental)
    db.commit()
    db.refresh(rental)
    promo_note = f" ({promo.name})" if promo else ""
    log_event(
        db,
        "RACKET_RENTED",
        f"Racket {racket.name} rented to {customer_name} for {promo_summary(promo, option) if promo else option.label}{promo_note}",
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


def complete_court_rental(db: Session, rental_id: int, user: User) -> CourtRental:
    rental = db.query(CourtRental).filter(CourtRental.id == rental_id).first()
    if not rental:
        raise ValueError("Rental not found")
    if rental.status != "active":
        raise ValueError("Rental is not active")
    rental.status = "completed"
    log_event(
        db,
        "COURT_COMPLETED",
        f"Court rental #{rental_id} completed",
        user.id,
        "court_rental",
        rental.id,
    )
    db.commit()
    return rental


def complete_racket_rental(db: Session, rental_id: int, user: User) -> RacketRental:
    rental = (
        db.query(RacketRental)
        .options(joinedload(RacketRental.racket))
        .filter(RacketRental.id == rental_id)
        .first()
    )
    if not rental:
        raise ValueError("Rental not found")
    if rental.status != "active":
        raise ValueError("Rental is not active")
    rental.status = "completed"
    if rental.racket:
        rental.racket.status = "available"
    log_event(
        db,
        "RACKET_COMPLETED",
        f"Racket rental #{rental_id} completed",
        user.id,
        "racket_rental",
        rental.id,
    )
    db.commit()
    return rental
