from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from auth import hash_password, require_role
from database import RESOURCE_DIR, get_db
from models import Court, Promo, Racket, RentalTimeOption, SystemLog, SystemSettings, User
from overtime_service import ensure_settings
from promo_service import PROMO_BONUS_MINUTES, PROMO_DISCOUNT_PERCENT
from services import log_event

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=str(RESOURCE_DIR / "templates"))


def _promo_form_fields(
    name: str,
    description: str,
    rental_type: str,
    promo_kind: str,
    window_start: str,
    window_end: str,
    time_option_id: str,
    bonus_minutes: int,
    discount_percent: float,
    days_of_week: str,
    priority: int,
) -> dict:
    opt_id: Optional[int] = int(time_option_id) if time_option_id.strip() else None
    return {
        "name": name.strip(),
        "description": description.strip(),
        "rental_type": rental_type,
        "time_option_id": opt_id,
        "promo_kind": promo_kind,
        "bonus_minutes": bonus_minutes,
        "discount_percent": discount_percent,
        "window_start": window_start.strip(),
        "window_end": window_end.strip(),
        "days_of_week": days_of_week.strip(),
        "priority": priority,
    }


def _promos_edit_json(promos: list[Promo]) -> list[dict]:
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description or "",
            "rental_type": p.rental_type,
            "promo_kind": p.promo_kind,
            "time_option_id": p.time_option_id or "",
            "bonus_minutes": p.bonus_minutes or 0,
            "discount_percent": p.discount_percent or 0,
            "window_start": p.window_start,
            "window_end": p.window_end,
            "days_of_week": p.days_of_week or "",
            "priority": p.priority or 0,
            "is_active": p.is_active,
        }
        for p in promos
    ]


def _ctx(request: Request, user: User, **extra):
    return {
        "request": request,
        "user": user,
        "currency": "₱",
        "is_admin": True,
        **extra,
    }


@router.get("", response_class=HTMLResponse)
def admin_panel(request: Request, db: Session = Depends(get_db)):
    user = require_role(request, db, "admin")
    court_options = (
        db.query(RentalTimeOption)
        .filter(RentalTimeOption.type == "court")
        .order_by(RentalTimeOption.duration_minutes)
        .all()
    )
    racket_options = (
        db.query(RentalTimeOption)
        .filter(RentalTimeOption.type == "racket")
        .order_by(RentalTimeOption.duration_minutes)
        .all()
    )
    rackets = db.query(Racket).order_by(Racket.name).all()
    courts = db.query(Court).order_by(Court.name).all()
    users = db.query(User).order_by(User.username).all()
    logs = (
        db.query(SystemLog)
        .order_by(SystemLog.created_at.desc())
        .limit(100)
        .all()
    )
    promos = (
        db.query(Promo)
        .order_by(Promo.rental_type, Promo.priority.desc())
        .all()
    )
    settings = ensure_settings(db)
    ctx = _ctx(
        request,
        user,
        court_options=court_options,
        racket_options=racket_options,
        rackets=rackets,
        courts=courts,
        users=users,
        logs=logs,
        promos=promos,
        promos_edit_json=_promos_edit_json(promos),
        promo_kinds=[PROMO_BONUS_MINUTES, PROMO_DISCOUNT_PERCENT],
        settings=settings,
    )
    ctx.pop("request", None)
    return templates.TemplateResponse(request, "admin.html", ctx)


@router.post("/settings/overtime")
def save_overtime_settings(
    request: Request,
    db: Session = Depends(get_db),
    court_overtime_rate: float = Form(...),
    racket_overtime_rate: float = Form(...),
    overtime_grace_minutes: int = Form(...),
    warning_minutes: int = Form(...),
):
    user = require_role(request, db, "admin")
    settings = ensure_settings(db)
    settings.court_overtime_rate = max(0.0, court_overtime_rate)
    settings.racket_overtime_rate = max(0.0, racket_overtime_rate)
    settings.overtime_grace_minutes = max(0, overtime_grace_minutes)
    settings.warning_minutes = max(1, warning_minutes)
    log_event(
        db,
        "SETTINGS_UPDATED",
        (
            f"Overtime: court ₱{settings.court_overtime_rate}/hr, "
            f"racket ₱{settings.racket_overtime_rate}/hr, "
            f"grace {settings.overtime_grace_minutes}m, warning {settings.warning_minutes}m"
        ),
        user.id,
    )
    db.commit()
    return RedirectResponse("/admin?tab=overtime", status_code=302)


@router.post("/settings/booking")
def save_booking_settings(
    request: Request,
    db: Session = Depends(get_db),
    allow_cancel_unpaid_booking: Optional[str] = Form(None),
    allow_cancel_paid_booking: Optional[str] = Form(None),
):
    user = require_role(request, db, "admin")
    settings = ensure_settings(db)
    settings.allow_cancel_unpaid_booking = allow_cancel_unpaid_booking == "on"
    settings.allow_cancel_paid_booking = allow_cancel_paid_booking == "on"
    log_event(
        db,
        "SETTINGS_UPDATED",
        (
            "Booking cancellation: "
            f"unpaid {'allowed' if settings.allow_cancel_unpaid_booking else 'blocked'}, "
            f"paid {'allowed' if settings.allow_cancel_paid_booking else 'blocked'}"
        ),
        user.id,
    )
    db.commit()
    return RedirectResponse("/admin?tab=overtime", status_code=302)


@router.post("/time-option/add")
def add_time_option(
    request: Request,
    db: Session = Depends(get_db),
    type: str = Form(...),
    label: str = Form(...),
    duration_minutes: int = Form(...),
    price: float = Form(...),
):
    user = require_role(request, db, "admin")
    opt = RentalTimeOption(
        type=type,
        label=label,
        duration_minutes=duration_minutes,
        price=price,
        is_active=True,
    )
    db.add(opt)
    log_event(db, "TIME_OPTION_ADDED", f"Added {type} option: {label}", user.id, "time_option")
    db.commit()
    return RedirectResponse("/admin", status_code=302)


@router.post("/time-option/{option_id}/toggle")
def toggle_time_option(option_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_role(request, db, "admin")
    opt = db.query(RentalTimeOption).filter(RentalTimeOption.id == option_id).first()
    if opt:
        opt.is_active = not opt.is_active
        log_event(
            db,
            "TIME_OPTION_TOGGLED",
            f"Toggled {opt.label} to {'active' if opt.is_active else 'inactive'}",
            user.id,
        )
        db.commit()
    return RedirectResponse("/admin", status_code=302)


@router.post("/time-option/{option_id}/delete")
def delete_time_option(option_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_role(request, db, "admin")
    opt = db.query(RentalTimeOption).filter(RentalTimeOption.id == option_id).first()
    if opt:
        db.delete(opt)
        log_event(db, "TIME_OPTION_DELETED", f"Deleted option {opt.label}", user.id)
        db.commit()
    return RedirectResponse("/admin", status_code=302)


@router.post("/court/add")
def add_court(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    description: str = Form(""),
):
    user = require_role(request, db, "admin")
    court = Court(name=name.strip(), description=description.strip())
    db.add(court)
    log_event(db, "COURT_ADDED", f"Added court {name}", user.id, "court")
    db.commit()
    return RedirectResponse("/admin", status_code=302)


@router.post("/court/{court_id}/toggle")
def toggle_court(court_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_role(request, db, "admin")
    court = db.query(Court).filter(Court.id == court_id).first()
    if court:
        court.is_active = not court.is_active
        log_event(db, "COURT_TOGGLED", f"Toggled {court.name}", user.id)
        db.commit()
    return RedirectResponse("/admin", status_code=302)


@router.post("/racket/add")
def add_racket(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    rf_chip_id: str = Form(""),
):
    user = require_role(request, db, "admin")
    racket = Racket(name=name.strip(), rf_chip_id=rf_chip_id.strip() or "RF-PENDING")
    db.add(racket)
    log_event(db, "RACKET_ADDED", f"Added racket {name}", user.id, "racket")
    db.commit()
    return RedirectResponse("/admin", status_code=302)


@router.post("/racket/{racket_id}/status")
def set_racket_status(
    racket_id: int,
    request: Request,
    db: Session = Depends(get_db),
    status: str = Form(...),
):
    user = require_role(request, db, "admin")
    racket = db.query(Racket).filter(Racket.id == racket_id).first()
    if racket:
        racket.status = status
        log_event(db, "RACKET_STATUS", f"Set {racket.name} to {status}", user.id, "racket", racket.id)
        db.commit()
    return RedirectResponse("/admin", status_code=302)


@router.post("/racket/{racket_id}/toggle")
def toggle_racket(racket_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_role(request, db, "admin")
    racket = db.query(Racket).filter(Racket.id == racket_id).first()
    if racket:
        racket.is_active = not racket.is_active
        log_event(db, "RACKET_TOGGLED", f"Toggled {racket.name}", user.id)
        db.commit()
    return RedirectResponse("/admin", status_code=302)


@router.post("/user/add")
def add_user(
    request: Request,
    db: Session = Depends(get_db),
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("cashier"),
):
    user = require_role(request, db, "admin")
    if db.query(User).filter(User.username == username).first():
        return RedirectResponse("/admin?error=user_exists", status_code=302)
    db.add(
        User(
            username=username.strip(),
            password_hash=hash_password(password),
            role=role,
        )
    )
    log_event(db, "USER_ADDED", f"Added user {username}", user.id)
    db.commit()
    return RedirectResponse("/admin", status_code=302)


@router.post("/user/{user_id}/reset-password")
def reset_password(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    password: str = Form(...),
):
    admin = require_role(request, db, "admin")
    target = db.query(User).filter(User.id == user_id).first()
    if target:
        target.password_hash = hash_password(password)
        log_event(db, "PASSWORD_RESET", f"Reset password for {target.username}", admin.id)
        db.commit()
    return RedirectResponse("/admin", status_code=302)


@router.post("/promo/add")
def add_promo(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    description: str = Form(""),
    rental_type: str = Form(...),
    promo_kind: str = Form(...),
    window_start: str = Form(...),
    window_end: str = Form(...),
    time_option_id: str = Form(""),
    bonus_minutes: int = Form(0),
    discount_percent: float = Form(0),
    days_of_week: str = Form(""),
    priority: int = Form(0),
):
    user = require_role(request, db, "admin")
    fields = _promo_form_fields(
        name,
        description,
        rental_type,
        promo_kind,
        window_start,
        window_end,
        time_option_id,
        bonus_minutes,
        discount_percent,
        days_of_week,
        priority,
    )
    db.add(Promo(**fields, is_active=True))
    log_event(db, "PROMO_ADDED", f"Added promo {fields['name']}", user.id, "promo")
    db.commit()
    return RedirectResponse("/admin?tab=promos", status_code=302)


@router.post("/promo/{promo_id}/edit")
def edit_promo(
    promo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    description: str = Form(""),
    rental_type: str = Form(...),
    promo_kind: str = Form(...),
    window_start: str = Form(...),
    window_end: str = Form(...),
    time_option_id: str = Form(""),
    bonus_minutes: int = Form(0),
    discount_percent: float = Form(0),
    days_of_week: str = Form(""),
    priority: int = Form(0),
    is_active: str = Form("true"),
):
    user = require_role(request, db, "admin")
    promo = db.query(Promo).filter(Promo.id == promo_id).first()
    if not promo:
        return RedirectResponse("/admin?tab=promos", status_code=302)

    fields = _promo_form_fields(
        name,
        description,
        rental_type,
        promo_kind,
        window_start,
        window_end,
        time_option_id,
        bonus_minutes,
        discount_percent,
        days_of_week,
        priority,
    )
    for key, value in fields.items():
        setattr(promo, key, value)
    promo.is_active = is_active.lower() in ("true", "1", "on", "yes")
    log_event(db, "PROMO_UPDATED", f"Updated promo {promo.name}", user.id, "promo", promo.id)
    db.commit()
    return RedirectResponse("/admin?tab=promos", status_code=302)


@router.post("/promo/{promo_id}/toggle")
def toggle_promo(promo_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_role(request, db, "admin")
    promo = db.query(Promo).filter(Promo.id == promo_id).first()
    if promo:
        promo.is_active = not promo.is_active
        log_event(
            db,
            "PROMO_TOGGLED",
            f"Toggled {promo.name} to {'active' if promo.is_active else 'inactive'}",
            user.id,
        )
        db.commit()
    return RedirectResponse("/admin?tab=promos", status_code=302)


@router.post("/promo/{promo_id}/delete")
def delete_promo(promo_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_role(request, db, "admin")
    promo = db.query(Promo).filter(Promo.id == promo_id).first()
    if promo:
        db.delete(promo)
        log_event(db, "PROMO_DELETED", f"Deleted promo {promo.name}", user.id)
        db.commit()
    return RedirectResponse("/admin?tab=promos", status_code=302)


@router.post("/racket/{racket_id}/mark-available")
def mark_racket_available(racket_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_role(request, db, "admin")
    racket = db.query(Racket).filter(Racket.id == racket_id).first()
    if racket and racket.status == "damaged":
        racket.status = "available"
        log_event(db, "RACKET_AVAILABLE", f"Marked {racket.name} available", user.id, "racket", racket.id)
        db.commit()
    return RedirectResponse("/dashboard", status_code=302)
