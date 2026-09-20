"""
Hospital Billing and Invoicing Service.

Provides multi-component clinical bill management, deterministic calculation
engine (Subtotal, Discount, Tax, Final Amount, Amount Paid, Balance),
payment processing (PENDING -> PARTIAL -> PAID), refund workflows (-> REFUNDED),
and multi-facet search and billing history.
"""

from datetime import datetime, date, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Optional, Tuple, Any

from sqlalchemy import or_, and_, func
from sqlalchemy.orm import Session, joinedload

from core.models.user import User, Patient, PatientProfile, RoleEnum
from core.models.billing import (
    Bill, BillItem, Payment, Insurance,
    BillStatusEnum, PaymentStatusEnum, ItemTypeEnum, PaymentMethodEnum
)
from core.models.audit import AuditLog, Notification, NotificationTypeEnum


# =====================================================================
# Custom Exceptions
# =====================================================================

class BillingServiceError(Exception):
    """Base exception for hospital billing domain errors."""
    pass


class BillNotFoundError(BillingServiceError):
    """Raised when an invoice or bill cannot be located."""
    pass


class InvalidBillDataError(BillingServiceError):
    """Raised when bill payload or parameters fail validation."""
    pass


class PaymentExceedsBalanceError(BillingServiceError):
    """Raised when attempting to pay more than the outstanding balance."""
    pass


class InvalidRefundError(BillingServiceError):
    """Raised when refund amount exceeds cumulative settled payments or is invalid."""
    pass


# =====================================================================
# Calculation Engine
# =====================================================================

def to_decimal(val: Any) -> Decimal:
    """Safely coerces value to a 2-decimal-place Decimal using ROUND_HALF_UP."""
    if val is None or val == "":
        return Decimal("0.00")
    if isinstance(val, Decimal):
        return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    try:
        return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


def calculate_bill_totals(
    items: List[Dict[str, Any]],
    discount: Any = Decimal("0.00"),
    discount_type: str = "amount",
    tax_rate: Any = Decimal("0.05"),
    tax_amount: Optional[Any] = None,
    insurance_covered: Any = Decimal("0.00"),
    amount_paid: Any = Decimal("0.00")
) -> Dict[str, Decimal]:
    """
    Deterministic calculation engine for hospital billing.

    Formulas:
        Subtotal = sum(item.quantity * item.unit_price)
        Discount Amount = (Subtotal * discount / 100) if discount_type == 'percent' else discount
        Taxable Base = max(0, Subtotal - Discount)
        Tax Amount = round(Taxable Base * tax_rate, 2) if explicit tax_amount is None else tax_amount
        Final Amount = max(0, Subtotal - Discount + Tax - Insurance Covered)
        Balance Due = max(0, Final Amount - Amount Paid)

    Returns:
        Dict with Decimal values: subtotal, discount, tax, insurance_covered, final_amount, amount_paid, balance.
    """
    subtotal = Decimal("0.00")
    for item in items:
        qty = int(item.get("quantity", 1) or 1)
        uprice = to_decimal(item.get("unit_price", "0.00"))
        subtotal += (Decimal(qty) * uprice).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Discount Calculation
    disc_val = to_decimal(discount)
    if discount_type == "percent":
        discount_amount = (subtotal * (disc_val / Decimal("100.00"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        discount_amount = disc_val
    discount_amount = min(discount_amount, subtotal)
    discount_amount = max(Decimal("0.00"), discount_amount)

    taxable_base = max(Decimal("0.00"), subtotal - discount_amount)

    # Tax Calculation
    if tax_amount is not None:
        final_tax = to_decimal(tax_amount)
    else:
        trate = to_decimal(tax_rate)
        final_tax = (taxable_base * trate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    final_tax = max(Decimal("0.00"), final_tax)

    # Insurance
    ins_cov = to_decimal(insurance_covered)
    ins_cov = max(Decimal("0.00"), ins_cov)

    # Final Amount
    final_amount = max(Decimal("0.00"), subtotal - discount_amount + final_tax - ins_cov)
    final_amount = final_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Paid & Balance
    paid = to_decimal(amount_paid)
    balance = max(Decimal("0.00"), final_amount - paid).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "subtotal": subtotal,
        "discount": discount_amount,
        "tax": final_tax,
        "insurance_covered": ins_cov,
        "final_amount": final_amount,
        "amount_paid": paid,
        "balance": balance
    }


def generate_bill_number(db: Session, prefix: str = "INV") -> str:
    """Generates sequential, collision-resistant hospital bill number."""
    today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    count = db.query(Bill).filter(Bill.bill_number.like(f"{prefix}-{today_str}-%")).count()
    return f"{prefix}-{today_str}-{count + 1:04d}"


# =====================================================================
# Bill Creation & Itemization
# =====================================================================

def create_bill(
    db: Session,
    patient_id: int,
    items: List[Dict[str, Any]],
    discount: Any = Decimal("0.00"),
    discount_type: str = "amount",
    tax_rate: Any = Decimal("0.05"),
    tax_amount: Optional[Any] = None,
    insurance_covered: Any = Decimal("0.00"),
    admission_id: Optional[int] = None,
    appointment_id: Optional[int] = None,
    insurance_id: Optional[int] = None,
    due_date: Optional[date] = None,
    notes: Optional[str] = None,
    actor_id: Optional[int] = None
) -> Bill:
    """
    Creates a new hospital bill across any of the 7 components:
    Consultation, Laboratory, Medicines, Room, Bed, Procedures, Other services.
    """
    # Verify patient
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        patient_user = db.query(User).filter(User.id == patient_id, User.role == RoleEnum.PATIENT).first()
        if patient_user:
            patient = db.query(Patient).filter(Patient.user_id == patient_id).first()
    if not patient:
        raise InvalidBillDataError(f"Patient with ID {patient_id} does not exist.")

    if not items:
        raise InvalidBillDataError("Cannot generate bill: at least one line item is required.")

    # Calculate exact totals
    calc = calculate_bill_totals(
        items=items,
        discount=discount,
        discount_type=discount_type,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        insurance_covered=insurance_covered,
        amount_paid=Decimal("0.00")
    )

    bill_num = generate_bill_number(db, prefix="INV")

    bill = Bill(
        bill_number=bill_num,
        patient_id=patient.id,
        admission_id=admission_id,
        appointment_id=appointment_id,
        insurance_id=insurance_id,
        subtotal=calc["subtotal"],
        discount=calc["discount"],
        tax=calc["tax"],
        insurance_covered=calc["insurance_covered"],
        total_amount=calc["final_amount"],
        status=BillStatusEnum.PENDING,
        due_date=due_date,
        notes=notes
    )
    db.add(bill)
    db.flush()

    # Add line items
    for item_data in items:
        raw_type = item_data.get("item_type", "consultation")
        # Validate or normalize enum
        try:
            item_type = ItemTypeEnum(raw_type)
        except ValueError:
            try:
                item_type = ItemTypeEnum[raw_type.upper()]
            except (KeyError, ValueError):
                item_type = ItemTypeEnum.OTHER_SERVICES

        desc = str(item_data.get("description", "Hospital Service")).strip()
        uprice = to_decimal(item_data.get("unit_price", "0.00"))
        qty = int(item_data.get("quantity", 1) or 1)
        item_subtotal = (Decimal(qty) * uprice).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        bill_item = BillItem(
            bill_id=bill.id,
            item_type=item_type,
            description=desc,
            unit_price=uprice,
            quantity=qty,
            subtotal=item_subtotal
        )
        db.add(bill_item)

    db.flush()
    bill.recalculate()

    # Audit Log
    if actor_id:
        audit = AuditLog(
            user_id=actor_id,
            action="HOSPITAL_BILL_CREATED",
            resource_type="Bill",
            resource_id=bill.id,
            details_json=f'{{"bill_number": "{bill.bill_number}", "patient_id": {patient.id}, "final_amount": {float(bill.total_amount)}}}'
        )
        db.add(audit)

    # Notification to patient user
    if patient.user_id:
        notif = Notification(
            user_id=patient.user_id,
            title=f"New Invoice Generated: {bill.bill_number}",
            message=f"An invoice of ${bill.total_amount:.2f} has been generated for your recent hospital services.",
            type=NotificationTypeEnum.SYSTEM
        )
        db.add(notif)

    return bill


def add_bill_item(
    db: Session,
    bill_id: int,
    item_type: Any,
    description: str,
    unit_price: Any,
    quantity: int = 1
) -> BillItem:
    """Adds a single itemized charge to an existing bill and triggers recalculation."""
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill:
        raise BillNotFoundError(f"Bill #{bill_id} not found.")

    if bill.status == BillStatusEnum.PAID:
        raise InvalidBillDataError("Cannot add items to an already settled (PAID) invoice.")

    try:
        itype = ItemTypeEnum(item_type)
    except ValueError:
        try:
            itype = ItemTypeEnum[str(item_type).upper()]
        except Exception:
            itype = ItemTypeEnum.OTHER_SERVICES

    uprice = to_decimal(unit_price)
    qty = max(1, int(quantity))
    subtot = (Decimal(qty) * uprice).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    item = BillItem(
        bill_id=bill.id,
        item_type=itype,
        description=description,
        unit_price=uprice,
        quantity=qty,
        subtotal=subtot
    )
    db.add(item)
    db.flush()

    bill.recalculate()
    return item


# =====================================================================
# Payment & Refund Lifecycle
# =====================================================================

def record_payment(
    db: Session,
    bill_id: int,
    amount: Any,
    payment_method: Any = PaymentMethodEnum.CASH,
    transaction_reference: Optional[str] = None,
    notes: Optional[str] = None,
    actor_id: Optional[int] = None
) -> Tuple[Payment, Bill]:
    """
    Records a payment against an invoice.
    Updates amount_paid, computes balance, and transitions status to PARTIAL or PAID.
    """
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill:
        raise BillNotFoundError(f"Bill #{bill_id} not found.")

    pay_amount = to_decimal(amount)
    if pay_amount <= Decimal("0.00"):
        raise InvalidBillDataError("Payment amount must be greater than zero.")

    cur_balance = Decimal(str(bill.balance_due))
    # Allow 1 cent leeway for rounding
    if pay_amount > cur_balance + Decimal("0.01"):
        raise PaymentExceedsBalanceError(
            f"Payment amount (${pay_amount:.2f}) exceeds current outstanding balance (${cur_balance:.2f})."
        )

    # Normalize payment method
    try:
        pmethod = PaymentMethodEnum(payment_method)
    except ValueError:
        try:
            pmethod = PaymentMethodEnum[str(payment_method).upper()]
        except Exception:
            pmethod = PaymentMethodEnum.CASH

    txn_ref = transaction_reference or f"PAY-{int(datetime.now(timezone.utc).timestamp())}"

    payment = Payment(
        bill=bill,
        bill_id=bill.id,
        amount=pay_amount,
        payment_method=pmethod,
        transaction_reference=txn_ref,
        is_refund=False,
        notes=notes,
        payment_date=datetime.now(timezone.utc)
    )
    db.add(payment)
    db.flush()

    bill.recalculate()

    # Audit Log
    if actor_id:
        audit = AuditLog(
            user_id=actor_id,
            action="HOSPITAL_BILL_PAYMENT_RECORDED",
            resource_type="Bill",
            resource_id=bill.id,
            details_json=f'{{"bill_number": "{bill.bill_number}", "amount": {float(pay_amount)}, "status": "{bill.status.value}"}}'
        )
        db.add(audit)

    # Dispatched completion notification if fully settled
    if bill.status == BillStatusEnum.PAID and bill.patient and bill.patient.user_id:
        notif = Notification(
            user_id=bill.patient.user_id,
            title=f"Payment Settled: {bill.bill_number}",
            message=f"Thank you. Your invoice {bill.bill_number} has been fully settled ($0.00 balance due).",
            type=NotificationTypeEnum.SYSTEM
        )
        db.add(notif)

    return payment, bill


def process_refund(
    db: Session,
    bill_id: int,
    amount: Any,
    reason: str,
    actor_id: Optional[int] = None
) -> Tuple[Payment, Bill]:
    """
    Processes a refund for a previously paid or partially paid bill.
    Records a refund transaction (is_refund=True), updates net amount_paid and balance,
    and transitions status to REFUNDED if fully refunded or PARTIAL if partially refunded.
    """
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill:
        raise BillNotFoundError(f"Bill #{bill_id} not found.")

    refund_amount = to_decimal(amount)
    if refund_amount <= Decimal("0.00"):
        raise InvalidRefundError("Refund amount must be greater than zero.")

    settled_paid = Decimal(str(bill.amount_paid))
    if refund_amount > settled_paid + Decimal("0.01"):
        raise InvalidRefundError(
            f"Refund amount (${refund_amount:.2f}) cannot exceed settled paid amount (${settled_paid:.2f})."
        )

    if not reason or not reason.strip():
        raise InvalidRefundError("A valid clinical or administrative reason is required for processing refunds.")

    # Determine original payment method
    last_payment = db.query(Payment).filter(
        Payment.bill_id == bill.id,
        Payment.is_refund == False
    ).order_by(Payment.payment_date.desc()).first()

    pmethod = last_payment.payment_method if last_payment else PaymentMethodEnum.CASH
    txn_ref = f"REFUND-{int(datetime.now(timezone.utc).timestamp())}"

    refund_payment = Payment(
        bill=bill,
        bill_id=bill.id,
        amount=refund_amount,
        payment_method=pmethod,
        transaction_reference=txn_ref,
        is_refund=True,
        notes=f"Refund: {reason.strip()}",
        payment_date=datetime.now(timezone.utc)
    )
    db.add(refund_payment)
    db.flush()

    # Determine status after refund
    net_paid = Decimal(str(bill.amount_paid))
    if net_paid <= Decimal("0.00") or refund_amount == settled_paid:
        bill.status = BillStatusEnum.REFUNDED
    else:
        bill.status = BillStatusEnum.PARTIAL

    # Audit Log
    if actor_id:
        audit = AuditLog(
            user_id=actor_id,
            action="HOSPITAL_BILL_REFUND_PROCESSED",
            resource_type="Bill",
            resource_id=bill.id,
            details_json=f'{{"bill_number": "{bill.bill_number}", "refund_amount": {float(refund_amount)}, "reason": "{reason.strip()}", "status": "{bill.status.value}"}}'
        )
        db.add(audit)

    # Patient Notification
    if bill.patient and bill.patient.user_id:
        notif = Notification(
            user_id=bill.patient.user_id,
            title=f"Refund Processed: {bill.bill_number}",
            message=f"A refund of ${refund_amount:.2f} has been processed for invoice {bill.bill_number}. Reason: {reason.strip()}",
            type=NotificationTypeEnum.SYSTEM
        )
        db.add(notif)

    return refund_payment, bill


# =====================================================================
# Search, History, and Filtering
# =====================================================================

def search_and_filter_bills(
    db: Session,
    query: Optional[str] = None,
    status: Optional[str] = None,
    item_type: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    patient_id: Optional[int] = None,
    min_amount: Optional[Decimal] = None,
    max_amount: Optional[Decimal] = None,
    limit: int = 100,
    offset: int = 0
) -> Tuple[List[Bill], int]:
    """
    Search and filter bills with multi-criteria support:
    - Text search across invoice number, patient name, patient email, phone.
    - Payment status filter (all, pending, partial, paid, refunded).
    - Clinical component filter (consultation, laboratory, medicines, etc.).
    - Date range filter.
    """
    q = db.query(Bill).join(Patient, Bill.patient_id == Patient.id).join(User, Patient.user_id == User.id)

    # Patient Filter
    if patient_id:
        q = q.filter(Bill.patient_id == patient_id)

    # Search Query
    if query and query.strip():
        raw_q = query.strip()
        term = f"%{raw_q.lower()}%"
        mrn_id = None
        if raw_q.lower().startswith("mrn-"):
            try:
                mrn_id = int(raw_q.lower().replace("mrn-", "").lstrip("0") or "0")
            except ValueError:
                pass

        filters = [
            func.lower(Bill.bill_number).like(term),
            func.lower(User.first_name).like(term),
            func.lower(User.last_name).like(term),
            func.lower(User.email).like(term),
            func.lower(User.phone).like(term)
        ]
        if mrn_id is not None:
            filters.append(Patient.id == mrn_id)

        q = q.filter(or_(*filters))

    # Status Filter
    if status and status.lower() not in ("all", ""):
        norm_status = status.lower()
        if norm_status in ("pending", "unpaid"):
            q = q.filter(Bill.status.in_([BillStatusEnum.PENDING, BillStatusEnum.UNPAID]))
        elif norm_status in ("partial", "partially_paid"):
            q = q.filter(Bill.status.in_([BillStatusEnum.PARTIAL, BillStatusEnum.PARTIALLY_PAID]))
        elif norm_status == "paid":
            q = q.filter(Bill.status == BillStatusEnum.PAID)
        elif norm_status == "refunded":
            q = q.filter(Bill.status == BillStatusEnum.REFUNDED)
        elif norm_status == "cancelled":
            q = q.filter(Bill.status == BillStatusEnum.CANCELLED)

    # Item Type / Component Filter
    if item_type and item_type.lower() not in ("all", ""):
        try:
            itype = ItemTypeEnum(item_type.lower())
            q = q.join(BillItem, Bill.id == BillItem.bill_id).filter(BillItem.item_type == itype).distinct()
        except ValueError:
            pass

    # Date Range Filter
    if start_date:
        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
        q = q.filter(Bill.created_at >= start_dt)
    if end_date:
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
        q = q.filter(Bill.created_at <= end_dt)

    # Amount Range Filter
    if min_amount is not None:
        q = q.filter(Bill.total_amount >= to_decimal(min_amount))
    if max_amount is not None:
        q = q.filter(Bill.total_amount <= to_decimal(max_amount))

    total_count = q.count()
    bills = q.order_by(Bill.created_at.desc()).offset(offset).limit(limit).all()

    return bills, total_count


def get_patient_billing_history(db: Session, patient_id: int) -> Dict[str, Any]:
    """
    Retrieves longitudinal billing history and financial summary for a patient.
    """
    bills = db.query(Bill).filter(Bill.patient_id == patient_id).order_by(Bill.created_at.desc()).all()

    total_invoiced = sum((Decimal(str(b.total_amount or "0.00")) for b in bills), Decimal("0.00"))
    total_paid = sum((Decimal(str(b.amount_paid or "0.00")) for b in bills), Decimal("0.00"))
    total_balance = sum((Decimal(str(b.balance_due or "0.00")) for b in bills), Decimal("0.00"))

    return {
        "patient_id": patient_id,
        "total_bills_count": len(bills),
        "total_invoiced": float(total_invoiced),
        "total_paid": float(total_paid),
        "total_balance_due": float(total_balance),
        "bills": bills
    }


def get_billing_dashboard_stats(db: Session) -> Dict[str, Any]:
    """Computes executive billing and receivables KPIs."""
    all_bills = db.query(Bill).all()

    total_billed = sum((Decimal(str(b.total_amount or "0.00")) for b in all_bills), Decimal("0.00"))
    total_collected = sum((Decimal(str(b.amount_paid or "0.00")) for b in all_bills), Decimal("0.00"))
    total_due = sum((Decimal(str(b.balance_due or "0.00")) for b in all_bills), Decimal("0.00"))

    # Calculate total refunds from payments table
    all_refunds = db.query(Payment).filter(Payment.is_refund == True).all()
    total_refunds = sum((Decimal(str(p.amount or "0.00")) for p in all_refunds), Decimal("0.00"))

    # Status breakdown
    counts = {
        "pending": 0,
        "partial": 0,
        "paid": 0,
        "refunded": 0,
        "cancelled": 0
    }
    for b in all_bills:
        s = b.status
        if s in (BillStatusEnum.PENDING, BillStatusEnum.UNPAID):
            counts["pending"] += 1
        elif s in (BillStatusEnum.PARTIAL, BillStatusEnum.PARTIALLY_PAID):
            counts["partial"] += 1
        elif s == BillStatusEnum.PAID:
            counts["paid"] += 1
        elif s == BillStatusEnum.REFUNDED:
            counts["refunded"] += 1
        elif s == BillStatusEnum.CANCELLED:
            counts["cancelled"] += 1

    return {
        "total_billed": float(total_billed.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "total_invoiced": float(total_billed.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "total_collected": float(total_collected.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "total_due": float(total_due.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "total_balance_due": float(total_due.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "total_refunds": float(total_refunds.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "total_invoices_count": len(all_bills),
        "status_counts": counts
    }
