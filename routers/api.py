import csv
import io
from datetime import date, datetime, time as dtime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from auth import require_user
from config import facility_now
from database import get_db
from overtime_service import get_settings
from models import Court, CourtRental, Racket, RacketRental, RentalTimeOption
from schemas import (
    CompleteRentalRequest,
    CourtRentRequest,
    CourtScheduleRentRequest,
    RacketRentRequest,
    RacketSwapRequest,
    RecordPaymentRequest,
)
from promo_service import active_promos_for_type, promo_hints_for_options
from services import (
    auto_complete_expired_rentals,
    complete_court_rental,
    complete_racket_rental,
    compute_greedy_amount,
    confirm_court_collection,
    confirm_racket_collection,
    court_status_payload,
    create_court_rental,
    cancel_court_rental,
    can_cancel_court_booking,
    create_court_rental_schedule,
    create_racket_rental,
    rental_is_upcoming,
    preview_court_completion,
    preview_court_payment,
    preview_racket_completion,
    preview_racket_payment,
    racket_status_payload,
    record_court_rental_payment,
    record_racket_rental_payment,
    rental_amount_billed,
    rental_balance_due,
    rental_cash_pending,
    rental_sales_revenue,
    rental_total_amount,
    sales_period_filter,
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
    auto_complete_expired_rentals(db)
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
            db,
            body.court_id,
            body.time_option_id,
            body.customer_name,
            user,
            body.payment_received,
        )
        return {
            "success": True,
            "rental_id": rental.id,
            "amount_billed": rental.amount_billed,
            "amount_paid": rental.amount_paid,
            "balance_due": rental_balance_due(rental),
        }
    except ValueError as e:
        return _error(str(e))


@router.get("/rent/racket/price")
def api_racket_rent_price(
    request: Request,
    db: Session = Depends(get_db),
    duration_hours: int = Query(..., ge=1, le=24),
):
    require_user(request, db)
    try:
        from promo_service import quote_rental_by_duration

        quote = quote_rental_by_duration(db, "racket", duration_hours)
        return {
            "total_amount": quote.amount_billed,
            "breakdown": quote.breakdown,
            "duration_hours": duration_hours,
            "play_duration_minutes": quote.play_duration_minutes,
            "bonus_minutes": quote.bonus_minutes,
            "promo": {
                "id": quote.promo.id,
                "name": quote.promo.name,
                "summary": quote.plan_label,
            }
            if quote.promo
            else None,
        }
    except ValueError as e:
        return _error(str(e))


@router.post("/rent/racket")
def api_rent_racket(request: Request, body: RacketRentRequest, db: Session = Depends(get_db)):
    user = require_user(request, db)
    try:
        rental = create_racket_rental(
            db,
            body.racket_id,
            body.customer_name,
            user,
            body.payment_received,
            time_option_id=body.time_option_id,
            duration_hours=body.duration_hours,
        )
        return {
            "success": True,
            "rental_id": rental.id,
            "amount_billed": rental.amount_billed,
            "amount_paid": rental.amount_paid,
            "balance_due": rental_balance_due(rental),
        }
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


@router.get("/payment/court/{rental_id}/preview")
def api_preview_payment_court(rental_id: int, request: Request, db: Session = Depends(get_db)):
    require_user(request, db)
    try:
        return preview_court_payment(db, rental_id)
    except ValueError as e:
        return _error(str(e))


@router.get("/payment/racket/{rental_id}/preview")
def api_preview_payment_racket(rental_id: int, request: Request, db: Session = Depends(get_db)):
    require_user(request, db)
    try:
        return preview_racket_payment(db, rental_id)
    except ValueError as e:
        return _error(str(e))


@router.post("/payment/court/{rental_id}")
def api_payment_court(
    rental_id: int,
    request: Request,
    body: RecordPaymentRequest,
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    try:
        rental = record_court_rental_payment(db, rental_id, user, body.payment_received)
        return {
            "success": True,
            "amount_billed": rental.amount_billed,
            "amount_paid": rental.amount_paid,
            "balance_due": rental_balance_due(rental),
        }
    except ValueError as e:
        return _error(str(e))


@router.post("/payment/racket/{rental_id}")
def api_payment_racket(
    rental_id: int,
    request: Request,
    body: RecordPaymentRequest,
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    try:
        rental = record_racket_rental_payment(db, rental_id, user, body.payment_received)
        return {
            "success": True,
            "amount_billed": rental.amount_billed,
            "amount_paid": rental.amount_paid,
            "balance_due": rental_balance_due(rental),
        }
    except ValueError as e:
        return _error(str(e))


@router.post("/payment/court/{rental_id}/collect")
def api_collect_court(
    rental_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    try:
        rental = confirm_court_collection(db, rental_id, user)
        return {"success": True, "rental_id": rental.id}
    except ValueError as e:
        return _error(str(e))


@router.post("/payment/racket/{rental_id}/collect")
def api_collect_racket(
    rental_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    try:
        rental = confirm_racket_collection(db, rental_id, user)
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
    auto_complete_expired_rentals(db)
    start, end = _parse_dates(from_date, to_date)

    court_statuses = ["active", "completed"]
    racket_statuses = ["active", "completed", "swapped"]

    court_rentals = []
    racket_rentals = []
    if type in ("all", "court"):
        court_rentals = sales_period_filter(
            db.query(CourtRental), CourtRental, start, end, court_statuses
        ).all()
    if type in ("all", "racket"):
        racket_rentals = sales_period_filter(
            db.query(RacketRental), RacketRental, start, end, racket_statuses
        ).all()

    court_total = sum(rental_sales_revenue(r) for r in court_rentals)
    racket_total = sum(rental_sales_revenue(r) for r in racket_rentals)
    pending_collection = round(
        sum(float(r.payment_pending_amount or 0) for r in court_rentals + racket_rentals if r.payment_pending),
        2,
    )

    court_count = len(court_rentals)
    racket_count = len(racket_rentals)

    active_courts = db.query(CourtRental).filter(CourtRental.status == "active").count()
    active_rackets = db.query(RacketRental).filter(RacketRental.status == "active").count()

    return {
        "total": court_total + racket_total,
        "court_total": court_total,
        "racket_total": racket_total,
        "transaction_count": court_count + racket_count,
        "active_count": active_courts + active_rackets,
        "pending_collection": pending_collection,
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
    auto_complete_expired_rentals(db)
    start, end = _parse_dates(from_date, to_date)
    per_page = 25
    items = []

    if type in ("all", "court"):
        court_rentals = sales_period_filter(
            db.query(CourtRental)
            .options(
                joinedload(CourtRental.court),
                joinedload(CourtRental.time_option),
                joinedload(CourtRental.cashier),
            ),
            CourtRental,
            start,
            end,
            ["active", "completed", "cancelled"],
        ).all()
        for r in court_rentals:
            duration = r.time_option.label if r.time_option else ""
            if r.bonus_minutes:
                duration = f"{duration} (+{r.bonus_minutes}m promo)"
            total = rental_sales_revenue(r)
            overtime = float(r.overtime_charge or 0)
            items.append(
                {
                    "datetime": (r.completed_at or r.created_at).isoformat(),
                    "type": "court",
                    "item": r.court.name if r.court else "",
                    "customer": r.customer_name,
                    "duration": duration,
                    "amount": total,
                    "base_amount": rental_amount_billed(r),
                    "amount_paid": float(r.amount_paid or 0),
                    "balance_due": rental_balance_due(r) if r.status == "active" else 0,
                    "overtime_charge": overtime,
                    "checkout_payment": float(r.checkout_payment or 0),
                    "checkout_change": float(r.checkout_change or 0),
                    "cashier": r.cashier.username if r.cashier else "",
                    "status": r.status,
                    "payment_pending": bool(r.payment_pending),
                    "payment_pending_amount": float(r.payment_pending_amount or 0),
                    "in_sales": True,
                }
            )

    if type in ("all", "racket"):
        racket_rentals = sales_period_filter(
            db.query(RacketRental)
            .options(
                joinedload(RacketRental.racket),
                joinedload(RacketRental.time_option),
                joinedload(RacketRental.cashier),
            ),
            RacketRental,
            start,
            end,
            ["active", "completed", "swapped", "cancelled"],
        ).all()
        for r in racket_rentals:
            duration = r.time_option.label if r.time_option else ""
            if r.bonus_minutes:
                duration = f"{duration} (+{r.bonus_minutes}m promo)"
            total = rental_sales_revenue(r)
            overtime = float(r.overtime_charge or 0)
            items.append(
                {
                    "datetime": (r.completed_at or r.created_at).isoformat(),
                    "type": "racket",
                    "item": r.racket.name if r.racket else "",
                    "customer": r.customer_name,
                    "duration": duration,
                    "amount": total,
                    "base_amount": rental_amount_billed(r),
                    "amount_paid": float(r.amount_paid or 0),
                    "balance_due": rental_balance_due(r) if r.status == "active" else 0,
                    "overtime_charge": overtime,
                    "checkout_payment": float(r.checkout_payment or 0),
                    "checkout_change": float(r.checkout_change or 0),
                    "cashier": r.cashier.username if r.cashier else "",
                    "status": r.status,
                    "payment_pending": bool(r.payment_pending),
                    "payment_pending_amount": float(r.payment_pending_amount or 0),
                    "in_sales": True,
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
    auto_complete_expired_rentals(db)
    start, end = _parse_dates(from_date, to_date)

    rows = []

    if type in ("all", "court"):
        court_rentals = sales_period_filter(
            db.query(CourtRental)
            .options(
                joinedload(CourtRental.court),
                joinedload(CourtRental.time_option),
                joinedload(CourtRental.cashier),
            ),
            CourtRental,
            start,
            end,
            ["active", "completed", "cancelled"],
        ).all()
        for r in court_rentals:
            rows.append(
                (
                    (r.completed_at or r.created_at).isoformat(),
                    "Court",
                    r.court.name if r.court else "",
                    r.customer_name,
                    r.time_option.label if r.time_option else "",
                    rental_sales_revenue(r),
                    rental_amount_billed(r),
                    float(r.amount_paid or 0),
                    float(r.overtime_charge or 0),
                    float(r.checkout_payment or 0),
                    float(r.checkout_change or 0),
                    r.cashier.username if r.cashier else "",
                    r.status,
                    "Yes" if r.payment_pending else "",
                    float(r.payment_pending_amount or 0) if r.payment_pending else "",
                )
            )

    if type in ("all", "racket"):
        racket_rentals = sales_period_filter(
            db.query(RacketRental)
            .options(
                joinedload(RacketRental.racket),
                joinedload(RacketRental.time_option),
                joinedload(RacketRental.cashier),
            ),
            RacketRental,
            start,
            end,
            ["active", "completed", "swapped", "cancelled"],
        ).all()
        for r in racket_rentals:
            rows.append(
                (
                    (r.completed_at or r.created_at).isoformat(),
                    "Racket",
                    r.racket.name if r.racket else "",
                    r.customer_name,
                    r.time_option.label if r.time_option else "",
                    rental_sales_revenue(r),
                    rental_amount_billed(r),
                    float(r.amount_paid or 0),
                    float(r.overtime_charge or 0),
                    float(r.checkout_payment or 0),
                    float(r.checkout_change or 0),
                    r.cashier.username if r.cashier else "",
                    r.status,
                    "Yes" if r.payment_pending else "",
                    float(r.payment_pending_amount or 0) if r.payment_pending else "",
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
            "Billed",
            "Collected",
            "Overtime",
            "Paid at checkout",
            "Change",
            "Cashier",
            "Status",
            "Collect cash",
            "Amount to collect",
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


@router.get("/schedule/courts/price")
def api_schedule_price(
    request: Request,
    db: Session = Depends(get_db),
    duration_hours: int = Query(..., ge=1, le=24),
    start_time: Optional[str] = Query(None, description="ISO start time for promo window check"),
):
    require_user(request, db)
    try:
        from datetime import datetime as dt

        from promo_service import quote_rental_by_duration

        at = dt.fromisoformat(start_time) if start_time else None
        quote = quote_rental_by_duration(db, "court", duration_hours, at)
        return {
            "total_amount": quote.amount_billed,
            "breakdown": quote.breakdown,
            "duration_hours": duration_hours,
            "play_duration_hours": round(quote.play_duration_minutes / 60, 2),
            "bonus_minutes": quote.bonus_minutes,
            "promo": {
                "id": quote.promo.id,
                "name": quote.promo.name,
                "summary": quote.plan_label,
            }
            if quote.promo
            else None,
        }
    except ValueError as e:
        return _error(str(e))


@router.post("/rent/court/schedule")
def api_rent_court_schedule(
    request: Request,
    body: CourtScheduleRentRequest,
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    try:
        rental = create_court_rental_schedule(
            db,
            body.court_id,
            body.customer_name,
            body.start_time,
            body.duration_hours,
            user,
            body.payment_received,
        )
        return {
            "success": True,
            "rental_id": rental.id,
            "amount_billed": rental.amount_billed,
            "amount_paid": rental.amount_paid,
            "balance_due": rental_balance_due(rental),
        }
    except ValueError as e:
        return _error(str(e))


@router.post("/rent/court/{rental_id}/cancel")
def api_cancel_court_booking(
    request: Request,
    rental_id: int,
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    try:
        rental = cancel_court_rental(db, rental_id, user)
        return {
            "success": True,
            "rental_id": rental.id,
            "status": rental.status,
        }
    except ValueError as e:
        return _error(str(e))


def _court_schedule_day_segment(rental: CourtRental, target_date: date) -> dict | None:
    """Map a rental to grid hours for one calendar day (handles cross-midnight)."""
    day_start = datetime.combine(target_date, dtime.min)
    day_end = day_start + timedelta(days=1)
    if rental.ends_at <= day_start or rental.started_at >= day_end:
        return None

    seg_start = max(rental.started_at, day_start)
    seg_end = min(rental.ends_at, day_end)
    start_h = seg_start.hour

    if seg_end.time() == dtime.min and seg_end.date() > seg_start.date():
        end_h = 24
    else:
        end_h = seg_end.hour
        if seg_end.minute > 0 or seg_end.second > 0 or seg_end.microsecond > 0:
            end_h += 1
        if end_h <= start_h:
            end_h = start_h + 1

    end_h = min(end_h, 24)
    span = max(1, end_h - start_h)
    continued = rental.started_at.date() < target_date
    return {
        "start_hour": start_h,
        "end_hour": end_h,
        "span": span,
        "continued_from_previous": continued,
    }


@router.get("/schedule/courts")
def api_court_schedule(
    request: Request,
    db: Session = Depends(get_db),
    view_date: str = Query(None),
):
    require_user(request, db)
    auto_complete_expired_rentals(db)
    today = date.today()
    max_date = today + timedelta(days=7)

    if view_date:
        try:
            target_date = date.fromisoformat(view_date)
        except ValueError:
            target_date = today
    else:
        target_date = today

    # Clamp to allowed window: today … today+7
    if target_date < today:
        target_date = today
    elif target_date > max_date:
        target_date = max_date

    is_today = target_date == today
    day_start = datetime.combine(target_date, dtime.min)
    day_end = day_start + timedelta(days=1)

    courts = db.query(Court).filter(Court.is_active.is_(True)).order_by(Court.name).all()
    rentals = (
        db.query(CourtRental)
        .options(joinedload(CourtRental.time_option))
        .filter(
            CourtRental.started_at < day_end,
            CourtRental.ends_at > day_start,
            CourtRental.status.in_(["active", "completed"]),
        )
        .all()
    )

    now = facility_now()
    settings = get_settings(db)
    rental_list = []
    for r in rentals:
        segment = _court_schedule_day_segment(r, target_date)
        if not segment:
            continue
        billed = float(r.amount_billed or 0)
        paid = float(r.amount_paid or 0)
        balance = rental_balance_due(r)
        is_upcoming = rental_is_upcoming(r)
        can_cancel, cancel_reason = can_cancel_court_booking(r, settings)
        rental_list.append(
            {
                "id": r.id,
                "court_id": r.court_id,
                "customer_name": r.customer_name,
                "started_at": r.started_at.isoformat(),
                "ends_at": r.ends_at.isoformat(),
                "start_hour": segment["start_hour"],
                "end_hour": segment["end_hour"],
                "span": segment["span"],
                "continued_from_previous": segment["continued_from_previous"],
                "status": r.status,
                "amount_billed": billed,
                "amount_paid": paid,
                "balance_due": balance,
                "is_paid": balance <= 0.009,
                "is_upcoming": is_upcoming,
                "can_cancel": can_cancel,
                "cancel_blocked_reason": cancel_reason if not can_cancel else "",
                "payment_pending": bool(r.payment_pending),
                "payment_pending_amount": float(r.payment_pending_amount or 0),
                "auto_completed": bool(getattr(r, "auto_completed", False)),
                "time_option_label": r.time_option.label if r.time_option else "",
            }
        )

    return {
        "courts": [{"id": c.id, "name": c.name} for c in courts],
        "date": target_date.isoformat(),
        "is_today": is_today,
        "now_iso": now.isoformat(),
        # current_hour: used to mark past cells — only meaningful for today
        "current_hour": now.hour if is_today else -1,
        "rentals": rental_list,
        "cancellation_policy": {
            "allow_cancel_unpaid": bool(settings.allow_cancel_unpaid_booking),
            "allow_cancel_paid": bool(settings.allow_cancel_paid_booking),
        },
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
