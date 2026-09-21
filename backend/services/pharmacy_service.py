import re
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any, Union
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, or_

from backend.models import (
    Medicine, MedicineInventory, MedicineBatch,
    StockTransaction, StockTransactionTypeEnum,
    Prescription, PrescriptionStatusEnum,
    User, AuditLog, Notification, NotificationTypeEnum
)


# =====================================================================
# Service Exceptions
# =====================================================================

class PharmacyServiceError(Exception):
    """Base exception for pharmacy and inventory management."""
    pass


class MedicineNotFoundError(PharmacyServiceError):
    """Raised when a referenced medicine cannot be found."""
    pass


class BatchNotFoundError(PharmacyServiceError):
    """Raised when a referenced medicine batch cannot be found."""
    pass


class InvalidInventoryDataError(PharmacyServiceError):
    """Raised when inventory, pricing, batch, or stock parameters are invalid."""
    pass


class InsufficientInventoryError(PharmacyServiceError):
    """Raised when attempting to deduct more stock than available in a batch."""
    pass


# =====================================================================
# Medicine Formulary Catalog Management
# =====================================================================

def create_medicine(
    db_session: Session,
    name: str,
    category: str,
    unit: str,
    unit_price: Union[Decimal, float, str, int],
    purchase_price: Optional[Union[Decimal, float, str, int]] = None,
    reorder_level: int = 20,
    generic_name: Optional[str] = None,
    supplier: Optional[str] = None,
    manufacturer: Optional[str] = None,
    description: Optional[str] = None,
    actor_id: Optional[int] = None,
    ip_address: Optional[str] = None
) -> Medicine:
    """
    Creates a new formulary medicine entry with pricing, unit, supplier, and minimum stock threshold.
    """
    clean_name = str(name).strip() if name else ""
    if not clean_name:
        raise InvalidInventoryDataError("Medicine name is required.")

    # Check uniqueness
    existing = db_session.query(Medicine).filter(func.lower(Medicine.name) == clean_name.lower()).first()
    if existing:
        raise InvalidInventoryDataError(f"Medicine with name '{clean_name}' already exists in formulary.")

    clean_category = str(category).strip() if category else ""
    if not clean_category:
        raise InvalidInventoryDataError("Medication category is required.")

    clean_unit = str(unit).strip() if unit else ""
    if not clean_unit:
        raise InvalidInventoryDataError("Dispensing unit (e.g. Tablet, Syrup, Capsule) is required.")

    try:
        dec_unit_price = Decimal(str(unit_price))
        if dec_unit_price <= 0:
            raise InvalidInventoryDataError("Selling / unit price must be greater than zero.")
    except Exception as e:
        if isinstance(e, InvalidInventoryDataError):
            raise
        raise InvalidInventoryDataError(f"Invalid unit price: '{unit_price}'. Must be a valid positive number.")

    dec_purchase_price = Decimal("0.00")
    if purchase_price is not None:
        try:
            dec_purchase_price = Decimal(str(purchase_price))
            if dec_purchase_price < 0:
                raise InvalidInventoryDataError("Purchase price cannot be negative.")
        except Exception as e:
            if isinstance(e, InvalidInventoryDataError):
                raise
            raise InvalidInventoryDataError(f"Invalid purchase price: '{purchase_price}'.")

    try:
        int_reorder = int(reorder_level)
        if int_reorder < 0:
            raise InvalidInventoryDataError("Minimum stock / reorder level cannot be negative.")
    except (ValueError, TypeError):
        raise InvalidInventoryDataError("Reorder level must be an integer.")

    medicine = Medicine(
        name=clean_name,
        generic_name=str(generic_name).strip() if generic_name else None,
        category=clean_category,
        unit=clean_unit,
        unit_price=dec_unit_price,
        purchase_price=dec_purchase_price,
        reorder_level=int_reorder,
        supplier=str(supplier).strip() if supplier else None,
        manufacturer=str(manufacturer).strip() if manufacturer else None,
        description=str(description).strip() if description else None
    )
    db_session.add(medicine)
    db_session.flush()

    if actor_id:
        audit = AuditLog(
            user_id=actor_id,
            action="MEDICINE_CATALOG_CREATED",
            resource_type="Medicine",
            resource_id=medicine.id,
            details={
                "name": medicine.name,
                "category": medicine.category,
                "unit": medicine.unit,
                "selling_price": str(medicine.unit_price),
                "purchase_price": str(medicine.purchase_price),
                "reorder_level": medicine.reorder_level,
                "supplier": medicine.supplier
            },
            ip_address=ip_address
        )
        db_session.add(audit)

    db_session.commit()
    return medicine


def update_medicine(
    db_session: Session,
    medicine_id: int,
    name: Optional[str] = None,
    generic_name: Optional[str] = None,
    category: Optional[str] = None,
    unit: Optional[str] = None,
    unit_price: Optional[Union[Decimal, float, str, int]] = None,
    purchase_price: Optional[Union[Decimal, float, str, int]] = None,
    reorder_level: Optional[int] = None,
    supplier: Optional[str] = None,
    manufacturer: Optional[str] = None,
    description: Optional[str] = None,
    actor_id: Optional[int] = None,
    ip_address: Optional[str] = None
) -> Medicine:
    """
    Updates an existing medicine formulary catalog record.
    """
    medicine = db_session.query(Medicine).filter(Medicine.id == medicine_id).first()
    if not medicine:
        raise MedicineNotFoundError(f"Medicine #{medicine_id} not found.")

    if name is not None:
        clean_name = str(name).strip()
        if not clean_name:
            raise InvalidInventoryDataError("Medicine name cannot be empty.")
        # Check duplicate if name changed
        if clean_name.lower() != medicine.name.lower():
            dup = db_session.query(Medicine).filter(
                func.lower(Medicine.name) == clean_name.lower(),
                Medicine.id != medicine.id
            ).first()
            if dup:
                raise InvalidInventoryDataError(f"Medicine with name '{clean_name}' already exists.")
        medicine.name = clean_name

    if generic_name is not None:
        medicine.generic_name = str(generic_name).strip() or None

    if category is not None:
        clean_cat = str(category).strip()
        if not clean_cat:
            raise InvalidInventoryDataError("Category cannot be empty.")
        medicine.category = clean_cat

    if unit is not None:
        clean_unit = str(unit).strip()
        if not clean_unit:
            raise InvalidInventoryDataError("Unit cannot be empty.")
        medicine.unit = clean_unit

    if unit_price is not None:
        try:
            dec_unit_price = Decimal(str(unit_price))
            if dec_unit_price <= 0:
                raise InvalidInventoryDataError("Selling / unit price must be positive.")
            medicine.unit_price = dec_unit_price
        except Exception as e:
            if isinstance(e, InvalidInventoryDataError):
                raise
            raise InvalidInventoryDataError(f"Invalid unit price '{unit_price}'.")

    if purchase_price is not None:
        try:
            dec_purch_price = Decimal(str(purchase_price))
            if dec_purch_price < 0:
                raise InvalidInventoryDataError("Purchase price cannot be negative.")
            medicine.purchase_price = dec_purch_price
        except Exception as e:
            if isinstance(e, InvalidInventoryDataError):
                raise
            raise InvalidInventoryDataError(f"Invalid purchase price '{purchase_price}'.")

    if reorder_level is not None:
        try:
            int_reorder = int(reorder_level)
            if int_reorder < 0:
                raise InvalidInventoryDataError("Reorder level cannot be negative.")
            medicine.reorder_level = int_reorder
        except (ValueError, TypeError):
            raise InvalidInventoryDataError("Reorder level must be an integer.")

    if supplier is not None:
        medicine.supplier = str(supplier).strip() or None

    if manufacturer is not None:
        medicine.manufacturer = str(manufacturer).strip() or None

    if description is not None:
        medicine.description = str(description).strip() or None

    if actor_id:
        audit = AuditLog(
            user_id=actor_id,
            action="MEDICINE_CATALOG_UPDATED",
            resource_type="Medicine",
            resource_id=medicine.id,
            details={"medicine_id": medicine.id, "name": medicine.name},
            ip_address=ip_address
        )
        db_session.add(audit)

    db_session.commit()
    return medicine


def get_medicine(db_session: Session, medicine_id: int) -> Medicine:
    """Retrieves a single medicine by ID."""
    medicine = db_session.query(Medicine).filter(Medicine.id == medicine_id).first()
    if not medicine:
        raise MedicineNotFoundError(f"Medicine #{medicine_id} not found.")
    return medicine


def list_medicines(
    db_session: Session,
    search: Optional[str] = None,
    category: Optional[str] = None,
    stock_status: Optional[str] = None
) -> List[Medicine]:
    """
    Lists medicines with optional search by name/generic/supplier, category, and stock health status.
    """
    query = db_session.query(Medicine)

    if category and category.strip() and category.strip().lower() != "all":
        query = query.filter(Medicine.category.ilike(f"%{category.strip()}%"))

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Medicine.name.ilike(term),
                Medicine.generic_name.ilike(term),
                Medicine.supplier.ilike(term),
                Medicine.manufacturer.ilike(term)
            )
        )

    medicines = query.order_by(Medicine.name.asc()).all()

    if stock_status:
        stat_lower = stock_status.strip().lower()
        if stat_lower == "low_stock":
            medicines = [m for m in medicines if m.is_low_stock]
        elif stat_lower == "out_of_stock":
            medicines = [m for m in medicines if m.total_stock == 0]
        elif stat_lower == "adequate":
            medicines = [m for m in medicines if not m.is_low_stock and m.total_stock > 0]

    return medicines


# =====================================================================
# Stock In & Stock Out Workflows
# =====================================================================

def stock_in(
    db_session: Session,
    medicine_id: int,
    batch_number: str,
    expiry_date: Union[date, str],
    quantity: int,
    purchase_cost: Union[Decimal, float, str, int],
    selling_price: Optional[Union[Decimal, float, str, int]] = None,
    supplier: Optional[str] = None,
    reference_type: Optional[str] = "PURCHASE_ORDER",
    reference_id: Optional[int] = None,
    performed_by_id: Optional[int] = None,
    notes: Optional[str] = None,
    ip_address: Optional[str] = None
) -> Dict[str, Any]:
    """
    Receives inventory stock into a new or existing batch and logs an immutable StockTransaction.
    """
    medicine = db_session.query(Medicine).filter(Medicine.id == medicine_id).first()
    if not medicine:
        raise MedicineNotFoundError(f"Medicine #{medicine_id} not found in catalog.")

    clean_batch_num = str(batch_number).strip() if batch_number else ""
    if not clean_batch_num:
        raise InvalidInventoryDataError("Batch number is required.")

    # Quantity validation
    try:
        qty_int = int(quantity)
        if qty_int <= 0:
            raise InvalidInventoryDataError("Stock-in quantity must be greater than zero.")
    except (ValueError, TypeError):
        raise InvalidInventoryDataError("Stock-in quantity must be a positive integer.")

    # Expiry date validation
    if isinstance(expiry_date, str):
        try:
            exp_date = datetime.strptime(expiry_date.strip(), "%Y-%m-%d").date()
        except ValueError:
            raise InvalidInventoryDataError(f"Invalid expiry date format: '{expiry_date}'. Must be YYYY-MM-DD.")
    elif isinstance(expiry_date, date):
        exp_date = expiry_date
    else:
        raise InvalidInventoryDataError("Expiry date must be a date object or 'YYYY-MM-DD' string.")

    if exp_date < date.today():
        raise InvalidInventoryDataError(f"Cannot receive expired batch stock. Expiry date '{exp_date}' is in the past.")

    # Purchase Cost validation
    try:
        dec_cost = Decimal(str(purchase_cost))
        if dec_cost < 0:
            raise InvalidInventoryDataError("Purchase cost cannot be negative.")
    except Exception as e:
        if isinstance(e, InvalidInventoryDataError):
            raise
        raise InvalidInventoryDataError(f"Invalid purchase cost: '{purchase_cost}'.")

    # Selling Price validation (optional, falls back to medicine unit_price)
    dec_selling_price = None
    if selling_price is not None:
        try:
            dec_selling_price = Decimal(str(selling_price))
            if dec_selling_price <= 0:
                raise InvalidInventoryDataError("Selling price must be greater than zero.")
        except Exception as e:
            if isinstance(e, InvalidInventoryDataError):
                raise
            raise InvalidInventoryDataError(f"Invalid selling price: '{selling_price}'.")
    else:
        dec_selling_price = medicine.unit_price

    clean_supplier = str(supplier).strip() if supplier else (medicine.supplier or None)
    clean_notes = str(notes).strip() if notes else None

    # Check for existing batch
    batch = db_session.query(MedicineInventory).filter(
        MedicineInventory.medicine_id == medicine.id,
        MedicineInventory.batch_number == clean_batch_num
    ).first()

    if batch:
        batch.quantity_in_stock += qty_int
        batch.expiry_date = exp_date
        batch.purchase_cost = dec_cost
        if dec_selling_price:
            batch.selling_price = dec_selling_price
        if clean_supplier:
            batch.supplier = clean_supplier
    else:
        batch = MedicineInventory(
            medicine_id=medicine.id,
            batch_number=clean_batch_num,
            expiry_date=exp_date,
            quantity_in_stock=qty_int,
            initial_quantity=qty_int,
            purchase_cost=dec_cost,
            selling_price=dec_selling_price,
            supplier=clean_supplier,
            received_date=date.today()
        )
        db_session.add(batch)
        db_session.flush()

    # Record Immutable Stock Movement
    transaction = StockTransaction(
        medicine_id=medicine.id,
        batch_id=batch.id,
        transaction_type=StockTransactionTypeEnum.STOCK_IN,
        quantity=qty_int,
        unit_price=dec_cost,
        supplier=clean_supplier,
        reference_type=reference_type,
        reference_id=reference_id,
        performed_by_id=performed_by_id,
        notes=clean_notes
    )
    db_session.add(transaction)

    # Log Audit Record
    if performed_by_id:
        audit = AuditLog(
            user_id=performed_by_id,
            action="STOCK_IN_RECEIVED",
            resource_type="MedicineInventory",
            resource_id=batch.id,
            details={
                "medicine_id": medicine.id,
                "medicine_name": medicine.name,
                "batch_number": clean_batch_num,
                "quantity_added": qty_int,
                "new_batch_stock": batch.quantity_in_stock,
                "total_medicine_stock": medicine.total_stock,
                "supplier": clean_supplier,
                "expiry_date": exp_date.isoformat()
            },
            ip_address=ip_address
        )
        db_session.add(audit)

    db_session.commit()
    return {
        "medicine_id": medicine.id,
        "batch_id": batch.id,
        "batch_number": batch.batch_number,
        "quantity_added": qty_int,
        "quantity_in_stock": batch.quantity_in_stock,
        "total_medicine_stock": medicine.total_stock,
        "transaction_id": transaction.id
    }


def stock_out(
    db_session: Session,
    batch_id: int,
    quantity: int,
    reason: str,
    reference_type: Optional[str] = "MANUAL_STOCK_OUT",
    reference_id: Optional[int] = None,
    performed_by_id: Optional[int] = None,
    notes: Optional[str] = None,
    ip_address: Optional[str] = None
) -> Dict[str, Any]:
    """
    Deducts stock from a specific batch for reasons such as expired discard, damaged goods,
    supplier return, or inventory adjustments.
    """
    batch = db_session.query(MedicineInventory).filter(MedicineInventory.id == batch_id).first()
    if not batch:
        raise BatchNotFoundError(f"Medicine batch #{batch_id} not found.")

    clean_reason = str(reason).strip() if reason else ""
    if not clean_reason:
        raise InvalidInventoryDataError("A reason is required for stock deduction / write-off.")

    try:
        qty_int = int(quantity)
        if qty_int <= 0:
            raise InvalidInventoryDataError("Stock-out quantity must be greater than zero.")
    except (ValueError, TypeError):
        raise InvalidInventoryDataError("Stock-out quantity must be a positive integer.")

    if qty_int > batch.quantity_in_stock:
        raise InsufficientInventoryError(
            f"Cannot deduct {qty_int} unit(s). Batch #{batch.batch_number} only has {batch.quantity_in_stock} unit(s) in stock."
        )

    # Determine specific stock transaction type
    reason_lower = clean_reason.lower()
    if "expire" in reason_lower:
        txn_type = StockTransactionTypeEnum.EXPIRED_DISCARD
    elif "return" in reason_lower:
        txn_type = StockTransactionTypeEnum.RETURNED
    elif "adjust" in reason_lower:
        txn_type = StockTransactionTypeEnum.ADJUSTMENT
    else:
        txn_type = StockTransactionTypeEnum.STOCK_OUT

    # Deduct stock
    batch.quantity_in_stock -= qty_int

    clean_notes = str(notes).strip() if notes else clean_reason

    # Record Stock Transaction
    transaction = StockTransaction(
        medicine_id=batch.medicine_id,
        batch_id=batch.id,
        transaction_type=txn_type,
        quantity=qty_int,
        unit_price=batch.purchase_cost,
        supplier=batch.supplier,
        reference_type=reference_type,
        reference_id=reference_id,
        performed_by_id=performed_by_id,
        notes=clean_notes
    )
    db_session.add(transaction)

    # Log Audit Record
    if performed_by_id:
        audit = AuditLog(
            user_id=performed_by_id,
            action=f"STOCK_OUT_{txn_type.value.upper()}",
            resource_type="MedicineInventory",
            resource_id=batch.id,
            details={
                "medicine_id": batch.medicine_id,
                "medicine_name": batch.medicine.name if batch.medicine else None,
                "batch_number": batch.batch_number,
                "quantity_deducted": qty_int,
                "remaining_batch_stock": batch.quantity_in_stock,
                "reason": clean_reason,
                "transaction_type": txn_type.value
            },
            ip_address=ip_address
        )
        db_session.add(audit)

    db_session.commit()
    return {
        "batch_id": batch.id,
        "batch_number": batch.batch_number,
        "quantity_deducted": qty_int,
        "remaining_batch_stock": batch.quantity_in_stock,
        "transaction_id": transaction.id,
        "transaction_type": txn_type.value
    }


# =====================================================================
# Automated Risk Detections: Low Stock, Expired, Expiring Soon
# =====================================================================

def get_low_stock_medicines(db_session: Session) -> List[Medicine]:
    """
    Returns all medicines where current unexpired total stock is at or below the reorder level.
    """
    medicines = db_session.query(Medicine).all()
    return [m for m in medicines if m.is_low_stock]


def get_expired_batches(db_session: Session) -> List[MedicineInventory]:
    """
    Returns all inventory batches that have passed their expiration date and still contain stock > 0.
    """
    today = date.today()
    return db_session.query(MedicineInventory).filter(
        MedicineInventory.expiry_date < today,
        MedicineInventory.quantity_in_stock > 0
    ).order_by(MedicineInventory.expiry_date.asc()).all()


def get_expiring_soon_batches(db_session: Session, days: int = 30) -> List[MedicineInventory]:
    """
    Returns active inventory batches that will expire within the specified timeframe (default 30 days) and have stock > 0.
    """
    today = date.today()
    cutoff = today + timedelta(days=days)
    return db_session.query(MedicineInventory).filter(
        MedicineInventory.expiry_date >= today,
        MedicineInventory.expiry_date <= cutoff,
        MedicineInventory.quantity_in_stock > 0
    ).order_by(MedicineInventory.expiry_date.asc()).all()


# =====================================================================
# Dashboard Analytics & Statistics
# =====================================================================

def get_pharmacy_dashboard_stats(db_session: Session) -> Dict[str, Any]:
    """
    Aggregates comprehensive operational and inventory metrics for the pharmacy dashboard.
    """
    today = date.today()
    all_medicines = db_session.query(Medicine).all()
    all_batches = db_session.query(MedicineInventory).all()

    # Low Stock Medicines
    low_stock = [m for m in all_medicines if m.is_low_stock]

    # Expired Batches
    expired_batches = [b for b in all_batches if b.expiry_date < today and b.quantity_in_stock > 0]
    expired_units_count = sum(b.quantity_in_stock for b in expired_batches)

    # Expiring Soon Batches (within 30 days)
    cutoff_30 = today + timedelta(days=30)
    expiring_soon_batches = [
        b for b in all_batches
        if today <= b.expiry_date <= cutoff_30 and b.quantity_in_stock > 0
    ]
    expiring_soon_units_count = sum(b.quantity_in_stock for b in expiring_soon_batches)

    # Total active stock units
    total_active_stock_units = sum(
        b.quantity_in_stock for b in all_batches
        if b.expiry_date >= today and b.quantity_in_stock > 0
    )

    # Inventory Valuation
    valuation_cost = sum(
        (b.purchase_cost or Decimal("0.00")) * b.quantity_in_stock
        for b in all_batches
        if b.expiry_date >= today and b.quantity_in_stock > 0
    )
    valuation_retail = sum(
        (b.selling_price or b.medicine.unit_price or Decimal("0.00")) * b.quantity_in_stock
        for b in all_batches
        if b.expiry_date >= today and b.quantity_in_stock > 0 and b.medicine
    )

    # Prescriptions
    pending_prescriptions_count = db_session.query(Prescription).filter(
        Prescription.status.in_([PrescriptionStatusEnum.PENDING, PrescriptionStatusEnum.PARTIALLY_DISPENSED])
    ).count()

    dispensed_prescriptions_count = db_session.query(Prescription).filter(
        Prescription.status == PrescriptionStatusEnum.DISPENSED
    ).count()

    total_prescriptions_count = db_session.query(Prescription).count()

    # Recent Stock Transactions
    recent_transactions = db_session.query(StockTransaction).order_by(
        desc(StockTransaction.created_at)
    ).limit(10).all()

    return {
        "total_medicines": len(all_medicines),
        "total_stock_units": total_active_stock_units,
        "total_batches": len(all_batches),
        "low_stock_count": len(low_stock),
        "low_stock_medicines": low_stock,
        "expired_batches_count": len(expired_batches),
        "expired_units_count": expired_units_count,
        "expired_batches": expired_batches,
        "expiring_soon_batches_count": len(expiring_soon_batches),
        "expiring_soon_units_count": expiring_soon_units_count,
        "expiring_soon_batches": expiring_soon_batches,
        "valuation_cost": round(float(valuation_cost), 2),
        "valuation_retail": round(float(valuation_retail), 2),
        "pending_prescriptions_count": pending_prescriptions_count,
        "dispensed_prescriptions_count": dispensed_prescriptions_count,
        "total_prescriptions_count": total_prescriptions_count,
        "recent_transactions": recent_transactions
    }


def list_stock_transactions(
    db_session: Session,
    medicine_id: Optional[int] = None,
    batch_id: Optional[int] = None,
    transaction_type: Optional[str] = None,
    limit: int = 100
) -> List[StockTransaction]:
    """
    Returns a filtered, chronological history of stock movement transactions.
    """
    query = db_session.query(StockTransaction)

    if medicine_id is not None:
        query = query.filter(StockTransaction.medicine_id == medicine_id)

    if batch_id is not None:
        query = query.filter(StockTransaction.batch_id == batch_id)

    if transaction_type and transaction_type.strip() and transaction_type.strip().lower() != "all":
        query = query.filter(StockTransaction.transaction_type == transaction_type.strip().lower())

    return query.order_by(desc(StockTransaction.created_at)).limit(limit).all()
