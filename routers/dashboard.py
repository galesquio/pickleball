from datetime import timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from auth import (
    SESSION_COOKIE,
    create_session_token,
    get_current_user,
    require_user,
    session_cookie_kwargs,
)
from config import facility_now
from database import RESOURCE_DIR, get_db
from models import Court, CourtRental, Racket, RacketRental, RentalTimeOption, User
from promo_service import active_promos_for_type, promo_hints_for_options
from overtime_service import get_settings, rental_timing_payload
from services import (
    auto_complete_expired_rentals,
    get_active_court_rental,
    get_active_racket_rental,
    rental_amount_billed,
    rental_balance_due,
    rental_cash_pending,
)

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory=str(RESOURCE_DIR / "templates"))


def _ctx(request: Request, user: User, **extra):
    return {
        "request": request,
        "user": user,
        "currency": "₱",
        "is_admin": user.role == "admin",
        **extra,
    }


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    if get_current_user(request, db):
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    from auth import verify_password

    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid username or password"},
            status_code=401,
        )
    token = create_session_token(user)
    response = RedirectResponse("/dashboard", status_code=302)
    response.set_cookie(SESSION_COOKIE, token, **session_cookie_kwargs())
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE, **session_cookie_kwargs())
    return response


@router.get("/", response_class=HTMLResponse)
def root():
    return RedirectResponse("/dashboard", status_code=302)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    auto_complete_expired_rentals(db)
    settings = get_settings(db)
    now = facility_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)

    # ── Court status ──────────────────────────────────────────────────────────
    courts = db.query(Court).filter(Court.is_active.is_(True)).all()
    active_court_rentals = (
        db.query(CourtRental)
        .options(joinedload(CourtRental.court), joinedload(CourtRental.time_option))
        .filter(CourtRental.status == "active")
        .all()
    )
    courts_busy = len({r.court_id for r in active_court_rentals})
    courts_total = len(courts)
    courts_free = courts_total - courts_busy

    # ── Racket status ─────────────────────────────────────────────────────────
    rackets = db.query(Racket).filter(Racket.is_active.is_(True)).all()
    active_racket_rentals = (
        db.query(RacketRental)
        .options(joinedload(RacketRental.racket), joinedload(RacketRental.time_option))
        .filter(RacketRental.status == "active")
        .all()
    )
    rackets_busy = len(active_racket_rentals)
    rackets_damaged = sum(1 for r in rackets if r.status == "damaged")
    rackets_total = len(rackets)
    rackets_free = rackets_total - rackets_busy - rackets_damaged

    # ── Today's revenue (started_at is facility local time) ───────────────────
    today_court = (
        db.query(CourtRental)
        .filter(CourtRental.started_at >= today_start, CourtRental.started_at < tomorrow_start)
        .all()
    )
    today_racket = (
        db.query(RacketRental)
        .filter(RacketRental.started_at >= today_start, RacketRental.started_at < tomorrow_start)
        .all()
    )
    all_today = today_court + today_racket
    total_billed = sum(float(r.amount_billed or 0) for r in all_today)
    total_collected = sum(float(r.amount_paid or 0) for r in all_today)
    total_balance = round(sum(rental_cash_pending(r) for r in all_today), 2)
    pending_collection = round(
        sum(float(r.payment_pending_amount or 0) for r in all_today if r.payment_pending),
        2,
    )
    today_count = len(all_today)

    completed_today = (
        db.query(CourtRental)
        .filter(
            CourtRental.completed_at >= today_start,
            CourtRental.completed_at < tomorrow_start,
            CourtRental.status == "completed",
        )
        .count()
    ) + (
        db.query(RacketRental)
        .filter(
            RacketRental.completed_at >= today_start,
            RacketRental.completed_at < tomorrow_start,
            RacketRental.status == "completed",
        )
        .count()
    )

    # ── Active rentals unified list ───────────────────────────────────────────
    active_now = []
    for r in active_court_rentals:
        balance = rental_balance_due(r)
        active_now.append({
            "type": "court",
            "item_name": r.court.name if r.court else f"Court #{r.court_id}",
            "customer": r.customer_name,
            "started_at": r.started_at,
            "ends_at": r.ends_at,
            "balance": balance,
            "is_paid": balance <= 0.009,
            "rental_id": r.id,
        })
    for r in active_racket_rentals:
        balance = rental_balance_due(r)
        active_now.append({
            "type": "racket",
            "item_name": r.racket.name if r.racket else f"Racket #{r.racket_id}",
            "customer": r.customer_name,
            "started_at": r.started_at,
            "ends_at": r.ends_at,
            "balance": balance,
            "is_paid": balance <= 0.009,
            "rental_id": r.id,
        })
    active_now.sort(key=lambda x: x["ends_at"])

    active_promos = active_promos_for_type(db, "court") + active_promos_for_type(db, "racket")

    ctx = _ctx(
        request,
        user,
        today_str=now.strftime("%A, %d %b %Y"),
        courts_total=courts_total,
        courts_busy=courts_busy,
        courts_free=courts_free,
        rackets_total=rackets_total,
        rackets_busy=rackets_busy,
        rackets_free=rackets_free,
        rackets_damaged=rackets_damaged,
        total_billed=total_billed,
        total_collected=total_collected,
        total_balance=total_balance,
        pending_collection=pending_collection,
        today_count=today_count,
        completed_today=completed_today,
        active_now=active_now,
        active_promos=active_promos,
    )
    ctx.pop("request", None)
    return templates.TemplateResponse(request, "dashboard.html", ctx)


def _build_full_ctx(request: Request, db: Session):
    """Shared data builder for pages that need courts + rackets data."""
    user = require_user(request, db)
    auto_complete_expired_rentals(db)
    settings = get_settings(db)
    courts = db.query(Court).filter(Court.is_active.is_(True)).order_by(Court.name).all()
    rackets = db.query(Racket).filter(Racket.is_active.is_(True)).order_by(Racket.name).all()

    court_cards = []
    for court in courts:
        rental = get_active_court_rental(db, court.id)
        timing = rental_timing_payload(rental.ends_at, settings) if rental else None
        court_cards.append({
            "court": court,
            "status": "rented" if rental else "available",
            "rental": rental,
            "time_remaining": timing["time_remaining_seconds"] if timing else 0,
            "timing_state": timing["timing_state"] if timing else "ok",
            "excess_minutes": timing["excess_minutes"] if timing else 0,
            "payment_billed": rental_amount_billed(rental) if rental else 0,
            "payment_paid": float(rental.amount_paid or 0) if rental else 0,
            "payment_balance": rental_balance_due(rental) if rental else 0,
        })

    racket_cards = []
    for racket in rackets:
        rental = get_active_racket_rental(db, racket.id)
        if racket.status == "damaged":
            status = "damaged"
        elif rental:
            status = "rented"
        else:
            status = "available"
        timing = rental_timing_payload(rental.ends_at, settings) if rental else None
        racket_cards.append({
            "racket": racket,
            "status": status,
            "rental": rental,
            "time_remaining": timing["time_remaining_seconds"] if timing else 0,
            "timing_state": timing["timing_state"] if timing else "ok",
            "excess_minutes": timing["excess_minutes"] if timing else 0,
            "payment_billed": rental_amount_billed(rental) if rental else 0,
            "payment_paid": float(rental.amount_paid or 0) if rental else 0,
            "payment_balance": rental_balance_due(rental) if rental else 0,
        })

    court_options = (
        db.query(RentalTimeOption)
        .filter(RentalTimeOption.type == "court", RentalTimeOption.is_active.is_(True))
        .order_by(RentalTimeOption.duration_minutes)
        .all()
    )
    racket_options = (
        db.query(RentalTimeOption)
        .filter(RentalTimeOption.type == "racket", RentalTimeOption.is_active.is_(True))
        .order_by(RentalTimeOption.duration_minutes)
        .all()
    )
    available_courts = [c for c in courts if not get_active_court_rental(db, c.id)]
    available_rackets = [
        r for r in rackets if r.status == "available" and not get_active_racket_rental(db, r.id)
    ]

    active_rentals = (
        db.query(RacketRental)
        .options(joinedload(RacketRental.racket), joinedload(RacketRental.time_option))
        .filter(RacketRental.status == "active")
        .all()
    )

    court_promo_hints = promo_hints_for_options(db, "court", court_options)
    racket_promo_hints = promo_hints_for_options(db, "racket", racket_options)
    active_promos = active_promos_for_type(db, "court") + active_promos_for_type(db, "racket")

    return user, _ctx(
        request,
        user,
        court_cards=court_cards,
        racket_cards=racket_cards,
        court_options=court_options,
        racket_options=racket_options,
        court_promo_hints=court_promo_hints,
        racket_promo_hints=racket_promo_hints,
        active_promos=active_promos,
        available_courts=available_courts,
        available_rackets=available_rackets,
        active_racket_rentals=active_rentals,
        warning_minutes=int(settings.warning_minutes or 15),
    )


@router.get("/courts", response_class=HTMLResponse)
def courts_page(request: Request, db: Session = Depends(get_db)):
    _user, ctx = _build_full_ctx(request, db)
    ctx.pop("request", None)
    return templates.TemplateResponse(request, "courts.html", ctx)


@router.get("/rackets", response_class=HTMLResponse)
def rackets_page(request: Request, db: Session = Depends(get_db)):
    _user, ctx = _build_full_ctx(request, db)
    ctx.pop("request", None)
    return templates.TemplateResponse(request, "rackets.html", ctx)
