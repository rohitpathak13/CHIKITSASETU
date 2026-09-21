from typing import List, Optional
from datetime import datetime, date, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Bill, Invoice, Payment, User, RoleEnum, BillStatusEnum
from backend.services import billing_service
from backend.fastapi_service.dependencies import get_current_user, require_roles
from backend.fastapi_service.schemas.billing import (
    InvoiceResponse, BillDetailResponse, BillCreateRequest,
    PaymentCreateRequest, RefundCreateRequest, BillingStatsResponse
)

router = APIRouter(prefix="/billing", tags=["Billing & Finance"])


@router.get("/invoices", response_model=List[InvoiceResponse])
def list_invoices(
    patient_id: Optional[int] = None,
    q: Optional[str] = None,
    status: Optional[str] = None,
    item_type: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves and searches patient invoices with filtering."""
    if current_user.role not in (RoleEnum.ADMIN, RoleEnum.RECEPTIONIST, RoleEnum.PATIENT):
        raise HTTPException(
            status_code=403,
            detail=f"Access denied. Role '{current_user.role.value}' is not authorized to access billing records."
        )

    target_patient_id = patient_id
    if current_user.role == RoleEnum.PATIENT:
        target_patient_id = current_user.id

    bills, _ = billing_service.search_and_filter_bills(
        db=db,
        query=q,
        status=status,
        item_type=item_type,
        start_date=start_date,
        end_date=end_date,
        patient_id=target_patient_id,
        limit=limit,
        offset=offset
    )
    return bills


@router.post("/invoices", response_model=BillDetailResponse, status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: BillCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.ADMIN, RoleEnum.RECEPTIONIST]))
):
    """Creates a new hospital invoice across any of the 7 components."""
    try:
        items_data = [item.dict() for item in payload.items]
        disc = payload.discount_value if payload.discount_value is not None else payload.discount
        disc_type = payload.discount_type
        if disc_type == "fixed":
            disc_type = "amount"
        bill = billing_service.create_bill(
            db=db,
            patient_id=payload.patient_id,
            items=items_data,
            discount=disc,
            discount_type=disc_type,
            tax_rate=payload.tax_rate,
            insurance_covered=payload.insurance_covered,
            admission_id=payload.admission_id,
            appointment_id=payload.appointment_id,
            due_date=payload.due_date,
            notes=payload.notes,
            actor_id=current_user.id
        )
        db.commit()
        db.refresh(bill)
        return bill
    except billing_service.BillingServiceError as be:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(be))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Bill creation failed: {str(e)}")


@router.get("/invoices/{invoice_id}", response_model=BillDetailResponse)
def get_invoice_detail(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves detailed invoice with itemized components and payment receipts."""
    bill = db.query(Bill).filter(Bill.id == invoice_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if current_user.role == RoleEnum.PATIENT:
        is_own = (bill.patient_id == current_user.id) or (bill.patient and bill.patient.user_id == current_user.id)
        if not is_own:
            raise HTTPException(status_code=403, detail="Access forbidden to this invoice")

    return bill


@router.post("/payments", status_code=status.HTTP_201_CREATED)
def record_payment(
    payload: PaymentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.ADMIN, RoleEnum.RECEPTIONIST]))
):
    """Records a payment against an outstanding invoice."""
    target_id = payload.invoice_id or payload.bill_id
    if not target_id:
        raise HTTPException(status_code=400, detail="invoice_id or bill_id is required")

    try:
        payment, bill = billing_service.record_payment(
            db=db,
            bill_id=target_id,
            amount=payload.amount,
            payment_method=payload.payment_method,
            transaction_reference=payload.transaction_reference,
            notes=payload.notes,
            actor_id=current_user.id
        )
        db.commit()
        return {
            "message": "Payment recorded successfully",
            "payment_id": payment.id,
            "invoice_status": bill.status.value,
            "bill_status": bill.status.value,
            "balance_due": float(bill.balance_due),
            "new_balance": float(bill.balance_due)
        }
    except billing_service.BillingServiceError as be:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(be))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Payment processing failed: {str(e)}")


@router.post("/invoices/{invoice_id}/refund")
def process_refund(
    invoice_id: int,
    payload: RefundCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.ADMIN]))
):
    """Processes a verified patient refund and transitions status accordingly."""
    refund_amt = payload.refund_amount if payload.refund_amount is not None else payload.amount
    if refund_amt is None or refund_amt <= 0:
        raise HTTPException(status_code=400, detail="Valid refund amount is required")

    try:
        refund_payment, bill = billing_service.process_refund(
            db=db,
            bill_id=invoice_id,
            amount=refund_amt,
            reason=payload.reason,
            actor_id=current_user.id
        )
        db.commit()
        return {
            "message": "Refund processed successfully",
            "refund_id": refund_payment.id,
            "invoice_status": bill.status.value,
            "bill_status": bill.status.value,
            "net_amount_paid": float(bill.amount_paid)
        }
    except billing_service.BillingServiceError as be:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(be))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Refund processing failed: {str(e)}")


@router.get("/dashboard-stats", response_model=BillingStatsResponse)
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.ADMIN, RoleEnum.RECEPTIONIST]))
):
    """Retrieves billing revenue and receivables statistics."""
    stats = billing_service.get_billing_dashboard_stats(db)
    if "total_invoiced" not in stats:
        stats["total_invoiced"] = stats.get("total_billed", 0.0)
    if "total_balance_due" not in stats:
        stats["total_balance_due"] = stats.get("total_due", 0.0)
    return stats

