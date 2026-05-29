from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from models import (
    MerchandiseInventoryTransaction,
    MerchandiseProduct,
    MerchandiseSale,
    MerchandiseSaleItem,
    User,
)
from services import log_event

STOCK_IN = "stock_in"
STOCK_OUT = "stock_out"
SALE = "sale"
DAMAGE = "damage"

MERCH_CATEGORIES = ("drink", "towel", "ball", "racket", "other")


def product_to_dict(product: MerchandiseProduct) -> dict:
    return {
        "id": product.id,
        "name": product.name,
        "sku": product.sku or "",
        "category": product.category or "other",
        "unit_price": float(product.unit_price),
        "cost_price": float(product.cost_price) if product.cost_price is not None else None,
        "stock_quantity": product.stock_quantity,
        "low_stock_threshold": product.low_stock_threshold or 5,
        "is_active": product.is_active,
        "is_low_stock": product.stock_quantity <= (product.low_stock_threshold or 5),
    }


def _apply_stock_change(
    db: Session,
    product: MerchandiseProduct,
    quantity: int,
    transaction_type: str,
    user_id: int,
    notes: str = "",
    unit_cost: Optional[float] = None,
    reference_id: Optional[int] = None,
) -> MerchandiseInventoryTransaction:
    quantity = int(quantity)
    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero")

    stock_before = int(product.stock_quantity or 0)
    if transaction_type == STOCK_IN:
        stock_after = stock_before + quantity
    elif transaction_type in (SALE, STOCK_OUT, DAMAGE):
        if stock_before < quantity:
            raise ValueError(
                f"Insufficient stock for {product.name}. Available: {stock_before}"
            )
        stock_after = stock_before - quantity
    else:
        raise ValueError(f"Unknown transaction type: {transaction_type}")

    product.stock_quantity = stock_after
    product.updated_at = datetime.utcnow()

    tx = MerchandiseInventoryTransaction(
        product_id=product.id,
        transaction_type=transaction_type,
        quantity=quantity,
        stock_before=stock_before,
        stock_after=stock_after,
        unit_cost=unit_cost,
        notes=notes or "",
        reference_id=reference_id,
        performed_by=user_id,
    )
    db.add(tx)
    return tx


def create_product(
    db: Session,
    user_id: int,
    name: str,
    unit_price: float,
    category: str = "other",
    sku: str = "",
    initial_stock: int = 0,
    low_stock_threshold: int = 5,
    cost_price: Optional[float] = None,
) -> MerchandiseProduct:
    name = name.strip()
    if not name:
        raise ValueError("Product name is required")
    if unit_price < 0:
        raise ValueError("Unit price cannot be negative")

    sku = sku.strip()
    if sku:
        existing = db.query(MerchandiseProduct).filter(MerchandiseProduct.sku == sku).first()
        if existing:
            raise ValueError(f"SKU already in use: {sku}")

    category = category.strip() or "other"
    if category not in MERCH_CATEGORIES:
        category = "other"

    product = MerchandiseProduct(
        name=name,
        sku=sku,
        category=category,
        unit_price=round(float(unit_price), 2),
        cost_price=round(float(cost_price), 2) if cost_price is not None else None,
        stock_quantity=0,
        low_stock_threshold=max(0, int(low_stock_threshold)),
        is_active=True,
    )
    db.add(product)
    db.flush()

    if initial_stock > 0:
        _apply_stock_change(
            db,
            product,
            initial_stock,
            STOCK_IN,
            user_id,
            notes="Initial stock",
            unit_cost=cost_price,
        )

    log_event(
        db,
        "MERCH_PRODUCT_ADDED",
        f"Added product: {name} @ ₱{product.unit_price:.2f}",
        user_id,
        "merchandise_product",
        product.id,
    )
    return product


def update_product(
    db: Session,
    product_id: int,
    user_id: int,
    name: Optional[str] = None,
    unit_price: Optional[float] = None,
    category: Optional[str] = None,
    sku: Optional[str] = None,
    low_stock_threshold: Optional[int] = None,
    cost_price: Optional[float] = None,
) -> MerchandiseProduct:
    product = db.query(MerchandiseProduct).filter(MerchandiseProduct.id == product_id).first()
    if not product:
        raise ValueError("Product not found")

    if name is not None:
        name = name.strip()
        if not name:
            raise ValueError("Product name is required")
        product.name = name

    if unit_price is not None:
        if unit_price < 0:
            raise ValueError("Unit price cannot be negative")
        product.unit_price = round(float(unit_price), 2)

    if category is not None:
        category = category.strip() or "other"
        product.category = category if category in MERCH_CATEGORIES else "other"

    if sku is not None:
        sku = sku.strip()
        if sku:
            existing = (
                db.query(MerchandiseProduct)
                .filter(MerchandiseProduct.sku == sku, MerchandiseProduct.id != product_id)
                .first()
            )
            if existing:
                raise ValueError(f"SKU already in use: {sku}")
        product.sku = sku

    if low_stock_threshold is not None:
        product.low_stock_threshold = max(0, int(low_stock_threshold))

    if cost_price is not None:
        product.cost_price = round(float(cost_price), 2) if cost_price >= 0 else None

    product.updated_at = datetime.utcnow()
    log_event(
        db,
        "MERCH_PRODUCT_UPDATED",
        f"Updated product: {product.name}",
        user_id,
        "merchandise_product",
        product.id,
    )
    return product


def toggle_product_active(db: Session, product_id: int, user_id: int) -> MerchandiseProduct:
    product = db.query(MerchandiseProduct).filter(MerchandiseProduct.id == product_id).first()
    if not product:
        raise ValueError("Product not found")
    product.is_active = not product.is_active
    product.updated_at = datetime.utcnow()
    log_event(
        db,
        "MERCH_PRODUCT_TOGGLED",
        f"{product.name} set to {'active' if product.is_active else 'inactive'}",
        user_id,
        "merchandise_product",
        product.id,
    )
    return product


def record_stock_in(
    db: Session,
    product_id: int,
    quantity: int,
    user_id: int,
    notes: str = "",
    unit_cost: Optional[float] = None,
) -> MerchandiseInventoryTransaction:
    product = db.query(MerchandiseProduct).filter(MerchandiseProduct.id == product_id).first()
    if not product:
        raise ValueError("Product not found")
    tx = _apply_stock_change(
        db, product, quantity, STOCK_IN, user_id, notes=notes, unit_cost=unit_cost
    )
    log_event(
        db,
        "MERCH_STOCK_IN",
        f"Stock in: {product.name} +{quantity} (now {product.stock_quantity})",
        user_id,
        "merchandise_product",
        product.id,
    )
    return tx


def record_stock_out(
    db: Session,
    product_id: int,
    quantity: int,
    user_id: int,
    transaction_type: str,
    notes: str = "",
) -> MerchandiseInventoryTransaction:
    if transaction_type not in (STOCK_OUT, DAMAGE):
        raise ValueError("Invalid stock-out type")
    product = db.query(MerchandiseProduct).filter(MerchandiseProduct.id == product_id).first()
    if not product:
        raise ValueError("Product not found")
    tx = _apply_stock_change(db, product, quantity, transaction_type, user_id, notes=notes)
    event = "MERCH_DAMAGE" if transaction_type == DAMAGE else "MERCH_STOCK_OUT"
    log_event(
        db,
        event,
        f"{transaction_type}: {product.name} -{quantity} (now {product.stock_quantity})",
        user_id,
        "merchandise_product",
        product.id,
    )
    return tx


def create_merchandise_sale(
    db: Session,
    items: list[dict],
    amount_paid: float,
    cashier_id: int,
    customer_name: Optional[str] = None,
    notes: Optional[str] = None,
) -> MerchandiseSale:
    if not items:
        raise ValueError("Cart is empty")

    amount_paid = round(float(amount_paid), 2)
    line_items: list[tuple[MerchandiseProduct, int, float]] = []
    subtotal = 0.0

    for item in items:
        product_id = int(item["product_id"])
        qty = int(item["quantity"])
        if qty <= 0:
            continue

        product = (
            db.query(MerchandiseProduct)
            .filter(MerchandiseProduct.id == product_id, MerchandiseProduct.is_active.is_(True))
            .first()
        )
        if not product:
            raise ValueError(f"Product #{product_id} is not available")
        if product.stock_quantity < qty:
            raise ValueError(
                f"Insufficient stock for {product.name}. Available: {product.stock_quantity}"
            )

        line_total = round(float(product.unit_price) * qty, 2)
        subtotal += line_total
        line_items.append((product, qty, line_total))

    if not line_items:
        raise ValueError("Cart is empty")

    subtotal = round(subtotal, 2)
    if amount_paid < subtotal - 0.009:
        raise ValueError(
            f"Payment insufficient. Total: ₱{subtotal:.2f}, paid: ₱{amount_paid:.2f}"
        )

    change_given = round(amount_paid - subtotal, 2)
    sale = MerchandiseSale(
        cashier_id=cashier_id,
        subtotal=subtotal,
        amount_paid=amount_paid,
        change_given=change_given,
        customer_name=(customer_name or "").strip(),
        notes=(notes or "").strip(),
    )
    db.add(sale)
    db.flush()

    for product, qty, line_total in line_items:
        db.add(
            MerchandiseSaleItem(
                sale_id=sale.id,
                product_id=product.id,
                product_name=product.name,
                unit_price=product.unit_price,
                quantity=qty,
                line_total=line_total,
            )
        )
        _apply_stock_change(
            db,
            product,
            qty,
            SALE,
            cashier_id,
            notes=f"Sale #{sale.id}",
            reference_id=sale.id,
        )

    item_summary = ", ".join(f"{p.name}×{q}" for p, q, _ in line_items)
    log_event(
        db,
        "MERCH_SALE",
        f"Sale #{sale.id}: ₱{subtotal:.2f} — {item_summary}",
        cashier_id,
        "merchandise_sale",
        sale.id,
    )
    return sale


def merchandise_sales_in_period(db: Session, start: datetime, end: datetime) -> list[MerchandiseSale]:
    return (
        db.query(MerchandiseSale)
        .options(joinedload(MerchandiseSale.cashier), joinedload(MerchandiseSale.items))
        .filter(MerchandiseSale.created_at >= start, MerchandiseSale.created_at < end)
        .order_by(MerchandiseSale.created_at.desc())
        .all()
    )


def merchandise_sales_revenue(sales: list[MerchandiseSale]) -> float:
    return round(sum(float(s.subtotal or 0) for s in sales), 2)


def get_inventory_transactions(
    db: Session,
    product_id: Optional[int] = None,
    transaction_type: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    page: int = 1,
    per_page: int = 25,
    sort_by: str = "datetime",
    sort_dir: str = "desc",
) -> tuple[list[MerchandiseInventoryTransaction], int]:
    from sqlalchemy import asc, desc

    per_page = max(1, min(int(per_page), 100))
    query = db.query(MerchandiseInventoryTransaction).options(
        joinedload(MerchandiseInventoryTransaction.product),
        joinedload(MerchandiseInventoryTransaction.user),
    )

    if product_id:
        query = query.filter(MerchandiseInventoryTransaction.product_id == product_id)
    if transaction_type:
        query = query.filter(MerchandiseInventoryTransaction.transaction_type == transaction_type)
    if start:
        query = query.filter(MerchandiseInventoryTransaction.created_at >= start)
    if end:
        query = query.filter(MerchandiseInventoryTransaction.created_at < end)

    direction = asc if sort_dir.lower() == "asc" else desc
    if sort_by == "product":
        query = query.join(
            MerchandiseProduct,
            MerchandiseInventoryTransaction.product_id == MerchandiseProduct.id,
        )
        query = query.order_by(direction(MerchandiseProduct.name))
    elif sort_by == "by":
        query = query.join(User, MerchandiseInventoryTransaction.performed_by == User.id)
        query = query.order_by(direction(User.username))
    else:
        sort_columns = {
            "datetime": MerchandiseInventoryTransaction.created_at,
            "type": MerchandiseInventoryTransaction.transaction_type,
            "quantity": MerchandiseInventoryTransaction.quantity,
            "stock": MerchandiseInventoryTransaction.stock_after,
            "notes": MerchandiseInventoryTransaction.notes,
        }
        column = sort_columns.get(sort_by, MerchandiseInventoryTransaction.created_at)
        query = query.order_by(direction(column))

    total = query.count()
    offset = (page - 1) * per_page
    rows = query.offset(offset).limit(per_page).all()
    return rows, total


def inventory_summary(db: Session) -> dict:
    products = db.query(MerchandiseProduct).all()
    low_stock = [p for p in products if p.is_active and p.stock_quantity <= (p.low_stock_threshold or 5)]
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    stock_in_today = (
        db.query(MerchandiseInventoryTransaction)
        .filter(
            MerchandiseInventoryTransaction.transaction_type == STOCK_IN,
            MerchandiseInventoryTransaction.created_at >= today_start,
        )
        .count()
    )
    return {
        "total_skus": len(products),
        "active_skus": sum(1 for p in products if p.is_active),
        "low_stock_count": len(low_stock),
        "stock_in_today": stock_in_today,
    }
