from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import date
from backend.models.user import GenderEnum

class PatientCreateRequest(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    password: str = Field(default="Password123!", min_length=8, description="Minimum 8 characters")
    phone: Optional[str] = None
    dob: date
    gender: GenderEnum
    blood_group: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    address: Optional[str] = None
    allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None

class PatientUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    dob: Optional[date] = None
    gender: Optional[GenderEnum] = None
    blood_group: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    address: Optional[str] = None
    allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None

class PatientResponse(BaseModel):
    user_id: int
    id: Optional[int] = None
    medical_record_number: Optional[str] = None
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    dob: date
    gender: GenderEnum
    blood_group: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    address: Optional[str] = None
    allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None

    class Config:
        from_attributes = True
