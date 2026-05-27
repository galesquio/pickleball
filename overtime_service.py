import math
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

from sqlalchemy.orm import Session

from config import facility_now
from models import SystemSettings

RentalType = Literal["court", "racket"]


@dataclass
class OvertimeResult:
    excess_minutes: int
    overtime_hours_charged: int
    overtime_charge: float
    rate_per_hour: float
    grace_minutes: int

    @property
    def has_charge(self) -> bool:
        return self.overtime_charge > 0


def get_settings(db: Session) -> SystemSettings:
    settings = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
    if not settings:
        settings = SystemSettings(id=1)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def ensure_settings(db: Session) -> SystemSettings:
    return get_settings(db)


def rate_for_type(settings: SystemSettings, rental_type: RentalType) -> float:
    if rental_type == "court":
        return float(settings.court_overtime_rate)
    return float(settings.racket_overtime_rate)


def compute_overtime(
    ends_at: datetime,
    rental_type: RentalType,
    settings: SystemSettings,
    completed_at: Optional[datetime] = None,
) -> OvertimeResult:
    """Bill excess time in whole hours after a grace period."""
    now = completed_at or facility_now()
    grace = int(settings.overtime_grace_minutes or 0)
    rate = rate_for_type(settings, rental_type)

    if now <= ends_at:
        return OvertimeResult(0, 0, 0.0, rate, grace)

    excess_seconds = (now - ends_at).total_seconds()
    excess_minutes = int(math.ceil(excess_seconds / 60))

    if excess_minutes <= grace:
        return OvertimeResult(excess_minutes, 0, 0.0, rate, grace)

    hours = int(math.ceil(excess_minutes / 60))
    charge = round(hours * rate, 2)
    return OvertimeResult(excess_minutes, hours, charge, rate, grace)


def rental_timing_payload(ends_at: datetime, settings: SystemSettings) -> dict:
    remaining = max(0, int((ends_at - facility_now()).total_seconds()))
    warning_seconds = int(settings.warning_minutes or 15) * 60

    if remaining > 0:
        if remaining <= warning_seconds:
            state = "warning"
        else:
            state = "ok"
        excess_seconds = 0
        excess_minutes = 0
    else:
        state = "overdue"
        excess_seconds = int((facility_now() - ends_at).total_seconds())
        excess_minutes = int(math.ceil(excess_seconds / 60)) if excess_seconds > 0 else 0

    return {
        "timing_state": state,
        "time_remaining_seconds": remaining,
        "excess_seconds": excess_seconds,
        "excess_minutes": excess_minutes,
        "warning_minutes": int(settings.warning_minutes or 15),
    }


def format_duration_minutes(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes}m"
    h, m = divmod(minutes, 60)
    if m:
        return f"{h}h {m}m"
    return f"{h}h"
