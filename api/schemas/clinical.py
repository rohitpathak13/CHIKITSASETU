from pydantic import BaseModel
from typing import Optional, List
from datetime import date
from decimal import Decimal

class PrescriptionItemCreate(BaseModel):
    medicine_id: int
    dosage: str
    frequency: str
    duration_days: int
    instructions: Optional[str] = None
    quantity_prescribed: int

class MedicalRecordCreateRequest(BaseModel):
    patient_id: int
    doctor_id: Optional[int] = None
    appointment_id: Optional[int] = None
    symptoms: str
    diagnosis: str
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
    prescriptions: Optional[List[PrescriptionItemCreate]] = None
    lab_test_ids: Optional[List[int]] = None

class MedicalRecordResponse(BaseModel):
    id: int
    patient_id: int
    doctor_id: int
    appointment_id: Optional[int] = None
    visit_date: date
    symptoms: str
    diagnosis: str
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

    class Config:
        from_attributes = True
