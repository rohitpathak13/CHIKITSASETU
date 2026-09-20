from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from core.models.clinical import AppointmentStatusEnum

class AppointmentCreateRequest(BaseModel):
    patient_id: int
    doctor_id: int
    appointment_datetime: datetime
    reason: Optional[str] = None
    sms_reminder_sent: Optional[int] = 1

class AppointmentResponse(BaseModel):
    id: int
    patient_id: int
    doctor_id: int
    appointment_datetime: datetime
    status: AppointmentStatusEnum
    reason: Optional[str] = None
    token_number: int
    no_show_probability: Optional[float] = None

    class Config:
        from_attributes = True

class AppointmentStatusUpdate(BaseModel):
    status: AppointmentStatusEnum
