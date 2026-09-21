from pydantic import BaseModel, EmailStr
from typing import Optional
from decimal import Decimal

class DoctorCreateRequest(BaseModel):
    email: EmailStr
    password: str = "Password123!"
    first_name: str
    last_name: str
    phone: Optional[str] = None
    department_id: Optional[int] = None
    specialization: str
    license_number: str
    consultation_fee: Decimal = Decimal("500.00")
    qualification: str = "MBBS, MD"
    room_number: Optional[str] = None
    available_days: str = "Mon,Tue,Wed,Thu,Fri"

class DoctorUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    department_id: Optional[int] = None
    specialization: Optional[str] = None
    consultation_fee: Optional[Decimal] = None
    qualification: Optional[str] = None
    room_number: Optional[str] = None
    available_days: Optional[str] = None

class DoctorResponse(BaseModel):
    id: int
    user_id: int
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    specialization: str
    license_number: str
    consultation_fee: float
    qualification: str
    room_number: Optional[str] = None
    available_days: str

    class Config:
        from_attributes = True
