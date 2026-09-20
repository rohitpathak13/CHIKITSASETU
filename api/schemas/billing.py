from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime, date
from core.models.billing import BillStatusEnum, PaymentStatusEnum, ItemTypeEnum, PaymentMethodEnum


class BillItemCreateSchema(BaseModel):
    item_type: str = "consultation"
    description: str
    unit_price: Decimal = Field(..., gt=0)
    quantity: int = Field(default=1, gt=0)


class BillCreateRequest(BaseModel):
    patient_id: int
    items: List[BillItemCreateSchema]
    discount: Decimal = Decimal("0.00")
    discount_value: Optional[Decimal] = None
    discount_type: str = "amount"
    tax_rate: Decimal = Decimal("0.05")
    insurance_covered: Decimal = Decimal("0.00")
    admission_id: Optional[int] = None
    appointment_id: Optional[int] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None


class PaymentCreateRequest(BaseModel):
    invoice_id: Optional[int] = None
    bill_id: Optional[int] = None
    amount: Decimal = Field(..., gt=0)
    payment_method: str = "cash"
    transaction_reference: Optional[str] = None
    notes: Optional[str] = None


class RefundCreateRequest(BaseModel):
    refund_amount: Optional[Decimal] = None
    amount: Optional[Decimal] = None
    reason: str = "Refund request"


class BillItemResponse(BaseModel):
    id: int
    item_type: ItemTypeEnum
    description: str
    unit_price: float
    quantity: int
    subtotal: float

    class Config:
        from_attributes = True


class PaymentResponse(BaseModel):
    id: int
    amount: float
    payment_method: PaymentMethodEnum
    transaction_reference: Optional[str] = None
    is_refund: bool = False
    payment_date: datetime

    class Config:
        from_attributes = True


class InvoiceResponse(BaseModel):
    id: int
    bill_number: str
    invoice_number: str
    patient_id: int
    subtotal: float
    discount: float
    tax: float
    insurance_covered: float
    total_amount: float
    final_amount: Optional[float] = None
    status: BillStatusEnum
    amount_paid: float
    balance_due: float

    class Config:
        from_attributes = True


class BillDetailResponse(InvoiceResponse):
    items: List[BillItemResponse] = []
    payments: List[PaymentResponse] = []
    due_date: Optional[date] = None
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class BillingStatsResponse(BaseModel):
    total_billed: float
    total_invoiced: Optional[float] = None
    total_collected: float
    total_due: float
    total_balance_due: Optional[float] = None
    total_refunds: float
    total_invoices_count: int
    status_counts: Dict[str, int]

