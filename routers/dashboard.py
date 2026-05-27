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
from database import RESOURCE_DIR, get_db
from models import Court, Racket, RacketRental, RentalTimeOption, User
from promo_service import active_promos_for_type, promo_hints_for_options
from overtime_service import get_settings, rental_timing_payload
from services import (
    get_active_court_rental,
    get_active_racket_rental,
    rental_amount_billed,
    rental_balance_due,
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
    settings = get_settings(db)
    courts = db.query(Court).filter(Court.is_active.is_(True)).order_by(Court.name).all()
    rackets = db.query(Racket).filter(Racket.is_active.is_(True)).order_by(Racket.name).all()

    court_cards = []
    for court in courts:
        rental = get_active_court_rental(db, court.id)
        timing = rental_timing_payload(rental.ends_at, settings) if rental else None
        court_cards.append(
            {
                "court": court,
                "status": "rented" if rental else "available",
                "rental": rental,
                "time_remaining": timing["time_remaining_seconds"] if timing else 0,
                "timing_state": timing["timing_state"] if timing else "ok",
                "excess_minutes": timing["excess_minutes"] if timing else 0,
                "payment_billed": rental_amount_billed(rental) if rental else 0,
                "payment_paid": float(rental.amount_paid or 0) if rental else 0,
                "payment_balance": rental_balance_due(rental) if rental else 0,
            }
        )

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
        racket_cards.append(
            {
                "racket": racket,
                "status": status,
                "rental": rental,
                "time_remaining": timing["time_remaining_seconds"] if timing else 0,
                "timing_state": timing["timing_state"] if timing else "ok",
                "excess_minutes": timing["excess_minutes"] if timing else 0,
                "payment_billed": rental_amount_billed(rental) if rental else 0,
                "payment_paid": float(rental.amount_paid or 0) if rental else 0,
                "payment_balance": rental_balance_due(rental) if rental else 0,
            }
        )

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

    ctx = _ctx(
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
    ctx.pop("request", None)
    return templates.TemplateResponse(request, "dashboard.html", ctx)
