from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class CourtRentRequest(BaseModel):
    court_id: int
    customer_name: str = Field(min_length=1, max_length=128)
    time_option_id: int
    payment_received: float = Field(ge=0, default=0)


class CourtScheduleRentRequest(BaseModel):
    court_id: int
    customer_name: str = Field(min_length=1, max_length=128)
    start_time: datetime
    duration_hours: int = Field(ge=1, le=24)
    payment_received: float = Field(ge=0, default=0)


class RacketRentRequest(BaseModel):
    racket_id: int
    customer_name: str = Field(min_length=1, max_length=128)
    time_option_id: Optional[int] = None
    duration_hours: Optional[int] = Field(default=None, ge=1, le=24)
    payment_received: float = Field(ge=0, default=0)


class RacketSwapRequest(BaseModel):
    rental_id: int
    new_racket_id: int
    reason: str = Field(min_length=1)


class CompleteRentalRequest(BaseModel):
    payment_received: float = Field(ge=0, default=0)


class RecordPaymentRequest(BaseModel):
    payment_received: float = Field(gt=0)


class TimeOptionCreate(BaseModel):
    type: str
    label: str
    duration_minutes: int
    price: float
    is_active: bool = True


class TimeOptionUpdate(BaseModel):
    label: Optional[str] = None
    duration_minutes: Optional[int] = None
    price: Optional[float] = None
    is_active: Optional[bool] = None


class CourtCreate(BaseModel):
    name: str
    description: str = ""


class CourtUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class RacketCreate(BaseModel):
    name: str
    rf_chip_id: str = ""


class RacketUpdate(BaseModel):
    name: Optional[str] = None
    rf_chip_id: Optional[str] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "cashier"


class PasswordReset(BaseModel):
    password: str = Field(min_length=4)


class LoginForm(BaseModel):
    username: str
    password: str


class RentalInfo(BaseModel):
    rental_id: int
    customer: str
    ends_at: datetime
    time_remaining_seconds: int
    time_option_label: str
    amount_billed: float
    amount_paid: float
    balance_due: float

    class Config:
        from_attributes = True
