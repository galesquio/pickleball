from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(16), nullable=False)  # admin | cashier
    created_at = Column(DateTime, default=datetime.utcnow)

    court_rentals = relationship("CourtRental", back_populates="cashier")
    racket_rentals = relationship("RacketRental", back_populates="cashier")


class Court(Base):
    __tablename__ = "courts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), nullable=False)
    description = Column(String(255), default="")
    is_active = Column(Boolean, default=True)

    rentals = relationship("CourtRental", back_populates="court")


class Racket(Base):
    __tablename__ = "rackets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), nullable=False)
    rf_chip_id = Column(String(64), default="")
    status = Column(String(16), default="available")  # available | rented | damaged
    is_active = Column(Boolean, default=True)

    rentals = relationship("RacketRental", back_populates="racket")


class SystemSettings(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, default=1)
    court_overtime_rate = Column(Float, default=50.0)
    racket_overtime_rate = Column(Float, default=20.0)
    overtime_grace_minutes = Column(Integer, default=10)
    warning_minutes = Column(Integer, default=15)


class RentalTimeOption(Base):
    __tablename__ = "rental_time_options"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(16), nullable=False)  # court | racket
    label = Column(String(64), nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True)

    promos = relationship("Promo", back_populates="time_option")


class Promo(Base):
    __tablename__ = "promos"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(String(255), default="")
    rental_type = Column(String(16), nullable=False)  # court | racket
    time_option_id = Column(Integer, ForeignKey("rental_time_options.id"), nullable=True)
    promo_kind = Column(String(32), nullable=False)  # bonus_minutes | discount_percent
    bonus_minutes = Column(Integer, default=0)
    discount_percent = Column(Float, default=0)
    window_start = Column(String(5), nullable=False)  # HH:MM local facility time
    window_end = Column(String(5), nullable=False)
    valid_from = Column(Date, nullable=True)
    valid_until = Column(Date, nullable=True)
    days_of_week = Column(String(32), default="")  # empty = every day; 0=Mon … 6=Sun
    priority = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    time_option = relationship("RentalTimeOption", back_populates="promos")


class CourtRental(Base):
    __tablename__ = "court_rentals"

    id = Column(Integer, primary_key=True, index=True)
    court_id = Column(Integer, ForeignKey("courts.id"), nullable=False)
    time_option_id = Column(Integer, ForeignKey("rental_time_options.id"), nullable=False)
    promo_id = Column(Integer, ForeignKey("promos.id"), nullable=True)
    cashier_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    customer_name = Column(String(128), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    ends_at = Column(DateTime, nullable=False)
    status = Column(String(16), default="active")  # active | completed | cancelled
    amount_billed = Column(Float, nullable=False)
    amount_paid = Column(Float, nullable=False, default=0)
    bonus_minutes = Column(Integer, default=0)
    completed_at = Column(DateTime, nullable=True)
    overtime_minutes = Column(Integer, default=0)
    overtime_hours_charged = Column(Integer, default=0)
    overtime_charge = Column(Float, default=0)
    checkout_payment = Column(Float, default=0)
    checkout_change = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    court = relationship("Court", back_populates="rentals")
    time_option = relationship("RentalTimeOption")
    promo = relationship("Promo")
    cashier = relationship("User", back_populates="court_rentals")


class RacketRental(Base):
    __tablename__ = "racket_rentals"

    id = Column(Integer, primary_key=True, index=True)
    racket_id = Column(Integer, ForeignKey("rackets.id"), nullable=False)
    time_option_id = Column(Integer, ForeignKey("rental_time_options.id"), nullable=False)
    promo_id = Column(Integer, ForeignKey("promos.id"), nullable=True)
    cashier_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    customer_name = Column(String(128), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    ends_at = Column(DateTime, nullable=False)
    status = Column(String(16), default="active")  # active | completed | swapped | cancelled
    amount_billed = Column(Float, nullable=False)
    amount_paid = Column(Float, nullable=False, default=0)
    bonus_minutes = Column(Integer, default=0)
    completed_at = Column(DateTime, nullable=True)
    overtime_minutes = Column(Integer, default=0)
    overtime_hours_charged = Column(Integer, default=0)
    overtime_charge = Column(Float, default=0)
    checkout_payment = Column(Float, default=0)
    checkout_change = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    racket = relationship("Racket", back_populates="rentals")
    time_option = relationship("RentalTimeOption")
    promo = relationship("Promo")
    cashier = relationship("User", back_populates="racket_rentals")
    swaps = relationship("RacketSwap", back_populates="original_rental")


class RacketSwap(Base):
    __tablename__ = "racket_swaps"

    id = Column(Integer, primary_key=True, index=True)
    original_rental_id = Column(Integer, ForeignKey("racket_rentals.id"), nullable=False)
    old_racket_id = Column(Integer, ForeignKey("rackets.id"), nullable=False)
    new_racket_id = Column(Integer, ForeignKey("rackets.id"), nullable=False)
    reason = Column(Text, nullable=False)
    swapped_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    swapped_at = Column(DateTime, default=datetime.utcnow)

    original_rental = relationship("RacketRental", back_populates="swaps")


class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(64), nullable=False)
    description = Column(Text, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    entity_type = Column(String(64), default="")
    entity_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
