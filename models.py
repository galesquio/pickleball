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
    merchandise_sales = relationship("MerchandiseSale", back_populates="cashier")


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
    allow_cancel_unpaid_booking = Column(Boolean, default=True)
    allow_cancel_paid_booking = Column(Boolean, default=False)


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
    payment_pending = Column(Boolean, default=False)
    payment_pending_amount = Column(Float, default=0)
    auto_completed = Column(Boolean, default=False)
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
    payment_pending = Column(Boolean, default=False)
    payment_pending_amount = Column(Float, default=0)
    auto_completed = Column(Boolean, default=False)
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


class MerchandiseProduct(Base):
    __tablename__ = "merchandise_products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    sku = Column(String(64), default="", index=True)
    category = Column(String(32), default="other")
    unit_price = Column(Float, nullable=False)
    cost_price = Column(Float, nullable=True)
    stock_quantity = Column(Integer, default=0, nullable=False)
    low_stock_threshold = Column(Integer, default=5)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    inventory_transactions = relationship("MerchandiseInventoryTransaction", back_populates="product")
    sale_items = relationship("MerchandiseSaleItem", back_populates="product")


class MerchandiseInventoryTransaction(Base):
    __tablename__ = "merchandise_inventory_transactions"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("merchandise_products.id"), nullable=False)
    transaction_type = Column(String(16), nullable=False)  # stock_in | stock_out | sale | damage
    quantity = Column(Integer, nullable=False)
    stock_before = Column(Integer, nullable=False)
    stock_after = Column(Integer, nullable=False)
    unit_cost = Column(Float, nullable=True)
    notes = Column(Text, default="")
    reference_id = Column(Integer, nullable=True)
    performed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("MerchandiseProduct", back_populates="inventory_transactions")
    user = relationship("User")


class MerchandiseSale(Base):
    __tablename__ = "merchandise_sales"

    id = Column(Integer, primary_key=True, index=True)
    cashier_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    subtotal = Column(Float, nullable=False)
    amount_paid = Column(Float, nullable=False)
    change_given = Column(Float, nullable=False, default=0)
    payment_method = Column(String(16), default="cash")
    customer_name = Column(String(128), default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    cashier = relationship("User", back_populates="merchandise_sales")
    items = relationship("MerchandiseSaleItem", back_populates="sale", cascade="all, delete-orphan")


class MerchandiseSaleItem(Base):
    __tablename__ = "merchandise_sale_items"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("merchandise_sales.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("merchandise_products.id"), nullable=False)
    product_name = Column(String(128), nullable=False)
    unit_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    line_total = Column(Float, nullable=False)

    sale = relationship("MerchandiseSale", back_populates="items")
    product = relationship("MerchandiseProduct", back_populates="sale_items")


class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(64), nullable=False)
    description = Column(Text, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    entity_type = Column(String(64), default="")
    entity_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
