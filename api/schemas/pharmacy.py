from pydantic import BaseModel, Field
from typing import Optional, List, Any
from decimal import Decimal
from datetime import date, datetime


class DispenseRequest(BaseModel):
    prescription_id: int
    items: Optional[List[dict]] = None  # list of {"prescription_item_id": int, "quantity_dispensed": int}


class MedicineResponse(BaseModel):
    id: int
    name: str
    generic_name: Optional[str] = None
    category: str
    unit: str
    unit_price: Decimal
    purchase_price: Optional[Decimal] = Decimal("0.00")
    reorder_level: int
    supplier: Optional[str] = None
    manufacturer: Optional[str] = None
    description: Optional[str] = None
    total_stock: int
    is_low_stock: bool

    class Config:
        from_attributes = True


class MedicineCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    generic_name: Optional[str] = None
    category: str = Field(..., min_length=1, max_length=100)
    unit: str = Field(..., min_length=1, max_length=30)
    unit_price: Decimal = Field(..., gt=0)
    purchase_price: Optional[Decimal] = Field(default=Decimal("0.00"), ge=0)
    reorder_level: Optional[int] = Field(default=20, ge=0)
    supplier: Optional[str] = None
    manufacturer: Optional[str] = None
    description: Optional[str] = None


class MedicineUpdateRequest(BaseModel):
    name: Optional[str] = None
    generic_name: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = None
    unit_price: Optional[Decimal] = Field(default=None, gt=0)
    purchase_price: Optional[Decimal] = Field(default=None, ge=0)
    reorder_level: Optional[int] = Field(default=None, ge=0)
    supplier: Optional[str] = None
    manufacturer: Optional[str] = None
    description: Optional[str] = None


class StockInRequest(BaseModel):
    medicine_id: int
    batch_number: str = Field(..., min_length=1, max_length=60)
    expiry_date: str = Field(..., description="Format: YYYY-MM-DD")
    quantity: int = Field(..., gt=0)
    purchase_cost: Decimal = Field(..., ge=0)
    selling_price: Optional[Decimal] = Field(default=None, gt=0)
    supplier: Optional[str] = None
    notes: Optional[str] = None


class StockOutRequest(BaseModel):
    batch_id: int
    quantity: int = Field(..., gt=0)
    reason: str = Field(..., min_length=1)
    notes: Optional[str] = None


class BatchResponse(BaseModel):
    id: int
    medicine_id: int
    batch_number: str
    expiry_date: date
    quantity_in_stock: int
    purchase_cost: Decimal
    selling_price: Optional[Decimal] = None
    supplier: Optional[str] = None
    is_expired: bool
    is_expiring_soon: bool
    days_to_expiry: int
    status_label: str

    class Config:
        from_attributes = True


class StockTransactionResponse(BaseModel):
    id: int
    medicine_id: int
    batch_id: Optional[int] = None
    transaction_type: str
    quantity: int
    unit_price: Optional[Decimal] = None
    supplier: Optional[str] = None
    reference_type: Optional[str] = None
    reference_id: Optional[int] = None
    created_at: Optional[datetime] = None
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class PharmacyDashboardStatsResponse(BaseModel):
    total_medicines: int
    total_stock_units: int
    total_batches: int
    low_stock_count: int
    expired_batches_count: int
    expired_units_count: int
    expiring_soon_batches_count: int
    expiring_soon_units_count: int
    valuation_cost: float
    valuation_retail: float
    pending_prescriptions_count: int
    dispensed_prescriptions_count: int
    total_prescriptions_count: int


class PrescriptionItemCreate(BaseModel):
    medicine_id: int
    dosage: str
    frequency: str
    duration_days: int
    quantity_prescribed: int
    instructions: Optional[str] = None


class PrescriptionCreateRequest(BaseModel):
    patient_id: int
    items: List[PrescriptionItemCreate]
    medical_record_id: Optional[int] = None
    notes: Optional[str] = None


class PrescriptionItemResponse(BaseModel):
    id: int
    medicine_id: int
    dosage: str
    frequency: str
    duration_days: int
    quantity_prescribed: int
    quantity_dispensed: int
    instructions: Optional[str] = None

    class Config:
        from_attributes = True


class PrescriptionResponse(BaseModel):
    id: int
    patient_id: int
    doctor_id: int
    medical_record_id: Optional[int] = None
    status: str
    notes: Optional[str] = None
    items: List[PrescriptionItemResponse] = []

    class Config:
        from_attributes = True
