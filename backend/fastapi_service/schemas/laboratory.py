from pydantic import BaseModel
from typing import Optional, List
from decimal import Decimal
from backend.models.laboratory import LabOrderStatusEnum

class LabOrderCreateRequest(BaseModel):
    patient_id: int
    test_type_id: Optional[int] = None
    test_id: Optional[int] = None
    medical_record_id: Optional[int] = None
    priority: Optional[str] = "routine"
    clinical_notes: Optional[str] = None

class LabResultEntryRequest(BaseModel):
    lab_order_id: Optional[int] = None
    measured_value: float
    unit: Optional[str] = None
    is_abnormal: Optional[bool] = None
    result_text: Optional[str] = None
    technician_notes: Optional[str] = None

class LabOrderReviewRequest(BaseModel):
    review_notes: Optional[str] = None
    doctor_review_notes: Optional[str] = None

class LabOrderCancelRequest(BaseModel):
    reason: str

class LabTestFormularyCreateRequest(BaseModel):
    name: str
    test_code: str
    sample_type: str
    cost: float
    unit: Optional[str] = None
    reference_range_min: Optional[float] = None
    reference_range_max: Optional[float] = None
    description: Optional[str] = None
    department_id: Optional[int] = None

class LabOrderResponse(BaseModel):
    id: int
    patient_id: int
    doctor_id: int
    test_type_id: int
    status: LabOrderStatusEnum
    ordered_at: str

    class Config:
        from_attributes = True

