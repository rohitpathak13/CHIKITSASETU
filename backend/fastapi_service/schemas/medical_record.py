from pydantic import BaseModel
from typing import Optional, List
from datetime import date
from decimal import Decimal
from backend.fastapi_service.schemas.clinical import PrescriptionItemCreate, MedicalRecordCreateRequest, MedicalRecordResponse

class MedicalRecordUpdateRequest(BaseModel):
    symptoms: Optional[str] = None
    diagnosis: Optional[str] = None
    clinical_notes: Optional[str] = None
    vitals_bp: Optional[str] = None
    vitals_pulse: Optional[int] = None
    vitals_temp: Optional[Decimal] = None
    vitals_spo2: Optional[int] = None
    vitals_weight: Optional[Decimal] = None
    vitals_height: Optional[Decimal] = None
    vitals_respiratory_rate: Optional[int] = None
    allergies: Optional[str] = None
    treatment_plan: Optional[str] = None
    follow_up_date: Optional[date] = None

__all__ = [
    "PrescriptionItemCreate",
    "MedicalRecordCreateRequest",
    "MedicalRecordUpdateRequest",
    "MedicalRecordResponse"
]
