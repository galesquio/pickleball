import csv
import io
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from auth import require_user
from database import get_db
from models import Court, CourtRental, Racket, RacketRental, RentalTimeOption
from schemas import CompleteRentalRequest, CourtRentRequest, RacketRentRequest, RacketSwapRequest
from promo_service import active_promos_for_type, promo_hints_for_options
from services import (
    complete_court_rental,
    complete_racket_rental,
    court_status_payload,
    create_court_rental,
    create_racket_rental,
    preview_court_completion,
    preview_racket_completion,
    racket_status_payload,
    rental_total_amount,
    swap_racket,
)

router = APIRouter(prefix="/api", tags=["api"])


def _error(message: str, status: int = 400):
    return JSONResponse({"error": message}, status_code=status)


def _parse_dates(from_date: Optional[str], to_date: Optional[str]):
    if from_date:
        start = datetime.strptime(from_date, "%Y-%m-%d")
    else:
        start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    if to_date:
        end = datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1)
    else:
        end = start + timedelta(days=1)
    return start, end


@router.get("/status")
def api_status(request: Request, db: Session = Depends(get_db)):
    require_user(request, db)
    courts = db.query(Court).filter(Court.is_active.is_(True)).order_by(Court.name).all()
    rackets = db.query(Racket).filter(Racket.is_active.is_(True)).order_by(Racket.name).all()
    return {
        "courts": [court_status_payload(db, c) for c in courts],
        "rackets": [racket_status_payload(db, r) for r in rackets],
    }


@router.post("/rent/court")
def api_rent_court(request: Request, body: CourtRentRequest, db: Session = Depends(get_db)):
    user = require_user(request, db)
    try:
        rental = create_court_rental(
            db, body.court_id, body.time_option_id, body.customer_name, user
        )
        return {"success": True, "rental_id": rental.id}
    except ValueError as e:
        return _error(str(e))


@router.post("/rent/racket")
def api_rent_racket(request: Request, body: RacketRentRequest, db: Session = Depends(get_db)):
    user = require_user(request, db)
    try:
        rental = create_racket_rental(
            db, body.racket_id, body.time_option_id, body.customer_name, user
        )
        return {"success": True, "rental_id": rental.id}
    except ValueError as e:
        return _error(str(e))


@router.post("/swap/racket")
def api_swap_racket(request: Request, body: RacketSwapRequest, db: Session = Depends(get_db)):
    user = require_user(request, db)
    try:
        rental = swap_racket(db, body.rental_id, body.new_racket_id, body.reason, user)
        return {"success": True, "rental_id": rental.id}
    except ValueError as e:
        return _error(str(e))


@router.get("/complete/court/{rental_id}/preview")
def api_preview_complete_court(rental_id: int, request: Request, db: Session = Depends(get_db)):
    require_user(request, db)
    try:
        return preview_court_completion(db, rental_id)
    except ValueError as e:
        return _error(str(e))


@router.get("/complete/racket/{rental_id}/preview")
def api_preview_complete_racket(rental_id: int, request: Request, db: Session = Depends(get_db)):
    require_user(request, db)
    try:
        return preview_racket_completion(db, rental_id)
    except ValueError as e:
        return _error(str(e))


@router.post("/complete/court/{rental_id}")
def api_complete_court(
    rental_id: int,
    request: Request,
    body: CompleteRentalRequest,
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    try:
        rental = complete_court_rental(db, rental_id, user, body.payment_received)
        return {
            "success": True,
            "overtime_charge": rental.overtime_charge,
            "checkout_change": rental.checkout_change,
            "total_revenue": rental_total_amount(rental),
        }
    except ValueError as e:
        return _error(str(e))


@router.post("/complete/racket/{rental_id}")
def api_complete_racket(
    rental_id: int,
    request: Request,
    body: CompleteRentalRequest,
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    try:
        rental = complete_racket_rental(db, rental_id, user, body.payment_received)
        return {
            "success": True,
            "overtime_charge": rental.overtime_charge,
            "checkout_change": rental.checkout_change,
            "total_revenue": rental_total_amount(rental),
        }
    except ValueError as e:
        return _error(str(e))


@router.get("/sales/summary")
def api_sales_summary(
    request: Request,
    db: Session = Depends(get_db),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    type: str = Query("all"),
):
    require_user(request, db)
    start, end = _parse_dates(from_date, to_date)

    court_q = db.query(CourtRental).filter(
        CourtRental.created_at >= start,
        CourtRental.created_at < end,
        CourtRental.status.in_(["active", "completed"]),
    )
    racket_q = db.query(RacketRental).filter(
        RacketRental.created_at >= start,
        RacketRental.created_at < end,
        RacketRental.status.in_(["active", "completed", "swapped"]),
    )

    court_total = 0.0
    racket_total = 0.0
    if type in ("all", "court"):
        court_base = (
            court_q.with_entities(func.coalesce(func.sum(CourtRental.amount_paid), 0)).scalar() or 0
        )
        court_overtime = (
            court_q.with_entities(func.coalesce(func.sum(CourtRental.overtime_charge), 0)).scalar()
            or 0
        )
        court_total = court_base + court_overtime
    if type in ("all", "racket"):
        racket_base = (
            racket_q.with_entities(func.coalesce(func.sum(RacketRental.amount_paid), 0)).scalar()
            or 0
        )
        racket_overtime = (
            racket_q.with_entities(func.coalesce(func.sum(RacketRental.overtime_charge), 0)).scalar()
            or 0
        )
        racket_total = racket_base + racket_overtime

    court_count = court_q.count() if type in ("all", "court") else 0
    racket_count = racket_q.count() if type in ("all", "racket") else 0

    active_courts = db.query(CourtRental).filter(CourtRental.status == "active").count()
    active_rackets = db.query(RacketRental).filter(RacketRental.status == "active").count()

    return {
        "total": court_total + racket_total,
        "court_total": court_total,
        "racket_total": racket_total,
        "transaction_count": court_count + racket_count,
        "active_count": active_courts + active_rackets,
    }


@router.get("/sales/transactions")
def api_sales_transactions(
    request: Request,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    type: str = Query("all"),
):
    require_user(request, db)
    start, end = _parse_dates(from_date, to_date)
    per_page = 25
    items = []

    if type in ("all", "court"):
        court_rentals = (
            db.query(CourtRental)
            .options(
                joinedload(CourtRental.court),
                joinedload(CourtRental.time_option),
                joinedload(CourtRental.cashier),
            )
            .filter(
                CourtRental.created_at >= start,
                CourtRental.created_at < end,
                CourtRental.status.in_(["active", "completed", "cancelled"]),
            )
            .all()
        )
        for r in court_rentals:
            duration = r.time_option.label if r.time_option else ""
            if r.bonus_minutes:
                duration = f"{duration} (+{r.bonus_minutes}m promo)"
            total = rental_total_amount(r)
            overtime = float(r.overtime_charge or 0)
            items.append(
                {
                    "datetime": (r.completed_at or r.created_at).isoformat(),
                    "type": "court",
                    "item": r.court.name if r.court else "",
                    "customer": r.customer_name,
                    "duration": duration,
                    "amount": total,
                    "base_amount": r.amount_paid,
                    "overtime_charge": overtime,
                    "checkout_payment": float(r.checkout_payment or 0),
                    "checkout_change": float(r.checkout_change or 0),
                    "cashier": r.cashier.username if r.cashier else "",
                    "status": r.status,
                }
            )

    if type in ("all", "racket"):
        racket_rentals = (
            db.query(RacketRental)
            .options(
                joinedload(RacketRental.racket),
                joinedload(RacketRental.time_option),
                joinedload(RacketRental.cashier),
            )
            .filter(
                RacketRental.created_at >= start,
                RacketRental.created_at < end,
                RacketRental.status.in_(["active", "completed", "swapped", "cancelled"]),
            )
            .all()
        )
        for r in racket_rentals:
            duration = r.time_option.label if r.time_option else ""
            if r.bonus_minutes:
                duration = f"{duration} (+{r.bonus_minutes}m promo)"
            total = rental_total_amount(r)
            overtime = float(r.overtime_charge or 0)
            items.append(
                {
                    "datetime": (r.completed_at or r.created_at).isoformat(),
                    "type": "racket",
                    "item": r.racket.name if r.racket else "",
                    "customer": r.customer_name,
                    "duration": duration,
                    "amount": total,
                    "base_amount": r.amount_paid,
                    "overtime_charge": overtime,
                    "checkout_payment": float(r.checkout_payment or 0),
                    "checkout_change": float(r.checkout_change or 0),
                    "cashier": r.cashier.username if r.cashier else "",
                    "status": r.status,
                }
            )

    items.sort(key=lambda x: x["datetime"], reverse=True)
    count = len(items)
    amount_total = sum(item["amount"] for item in items)
    total_pages = max(1, (count + per_page - 1) // per_page)
    start_idx = (page - 1) * per_page
    page_items = items[start_idx : start_idx + per_page]

    return {
        "items": page_items,
        "total_pages": total_pages,
        "current_page": page,
        "total": count,
        "amount_total": amount_total,
    }


@router.get("/sales/export")
def api_sales_export(
    request: Request,
    db: Session = Depends(get_db),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    type: str = Query("all"),
):
    require_user(request, db)
    start, end = _parse_dates(from_date, to_date)

    rows = []

    if type in ("all", "court"):
        court_rentals = (
            db.query(CourtRental)
            .options(
                joinedload(CourtRental.court),
                joinedload(CourtRental.time_option),
                joinedload(CourtRental.cashier),
            )
            .filter(
                CourtRental.created_at >= start,
                CourtRental.created_at < end,
                CourtRental.status.in_(["active", "completed", "cancelled"]),
            )
            .all()
        )
        for r in court_rentals:
            rows.append(
                (
                    (r.completed_at or r.created_at).isoformat(),
                    "Court",
                    r.court.name if r.court else "",
                    r.customer_name,
                    r.time_option.label if r.time_option else "",
                    rental_total_amount(r),
                    r.amount_paid,
                    float(r.overtime_charge or 0),
                    float(r.checkout_payment or 0),
                    float(r.checkout_change or 0),
                    r.cashier.username if r.cashier else "",
                    r.status,
                )
            )

    if type in ("all", "racket"):
        racket_rentals = (
            db.query(RacketRental)
            .options(
                joinedload(RacketRental.racket),
                joinedload(RacketRental.time_option),
                joinedload(RacketRental.cashier),
            )
            .filter(
                RacketRental.created_at >= start,
                RacketRental.created_at < end,
                RacketRental.status.in_(["active", "completed", "swapped", "cancelled"]),
            )
            .all()
        )
        for r in racket_rentals:
            rows.append(
                (
                    (r.completed_at or r.created_at).isoformat(),
                    "Racket",
                    r.racket.name if r.racket else "",
                    r.customer_name,
                    r.time_option.label if r.time_option else "",
                    rental_total_amount(r),
                    r.amount_paid,
                    float(r.overtime_charge or 0),
                    float(r.checkout_payment or 0),
                    float(r.checkout_change or 0),
                    r.cashier.username if r.cashier else "",
                    r.status,
                )
            )

    rows.sort(key=lambda r: r[0], reverse=True)
    amount_total = sum(r[5] for r in rows)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Date/Time",
            "Type",
            "Item",
            "Customer",
            "Duration",
            "Total",
            "Base",
            "Overtime",
            "Paid at checkout",
            "Change",
            "Cashier",
            "Status",
        ]
    )
    writer.writerows(rows)
    writer.writerow([])
    writer.writerow(["", "", "", "", "Total", amount_total, "", ""])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sales_export.csv"},
    )


@router.get("/time-options")
def api_time_options(request: Request, db: Session = Depends(get_db), type: str = Query(...)):
    require_user(request, db)
    options = (
        db.query(RentalTimeOption)
        .filter(RentalTimeOption.type == type, RentalTimeOption.is_active.is_(True))
        .order_by(RentalTimeOption.duration_minutes)
        .all()
    )
    hints = promo_hints_for_options(db, type, options)
    return {
        "options": [
            {
                "id": o.id,
                "label": o.label,
                "duration_minutes": o.duration_minutes,
                "price": o.price,
                "promo": hints.get(o.id),
            }
            for o in options
        ]
    }


@router.get("/promos/active")
def api_active_promos(request: Request, db: Session = Depends(get_db), type: str = Query("all")):
    require_user(request, db)
    result = []
    for rental_type in ("court", "racket"):
        if type not in ("all", rental_type):
            continue
        for promo in active_promos_for_type(db, rental_type):
            result.append(
                {
                    "id": promo.id,
                    "name": promo.name,
                    "description": promo.description,
                    "rental_type": promo.rental_type,
                    "window_start": promo.window_start,
                    "window_end": promo.window_end,
                    "promo_kind": promo.promo_kind,
                }
            )
    return {"promos": result}
