from pydantic import BaseModel
from typing import Optional, List, Any
from decimal import Decimal
from datetime import datetime
from core.models.inpatient import WardTypeEnum, BedStatusEnum, AdmissionStatusEnum, RoomTypeEnum


class AdmissionCreateRequest(BaseModel):
    patient_id: int
    bed_id: int
    admission_reason: str
    department_id: Optional[int] = None
    nurse_id: Optional[int] = None
    notes: Optional[str] = None


class BedTransferRequest(BaseModel):
    to_bed_id: int
    reason: str
    notes: Optional[str] = None
    release_previous_as: Optional[BedStatusEnum] = BedStatusEnum.MAINTENANCE


class BedStatusUpdateRequest(BaseModel):
    status: BedStatusEnum
    notes: Optional[str] = None


class DischargeRequest(BaseModel):
    discharge_summary: str = "Discharged in stable clinical condition"


class BedResponse(BaseModel):
    id: int
    room_id: Optional[int] = None
    ward_id: Optional[int] = None
    bed_number: str
    status: BedStatusEnum
    daily_rate: Decimal

    class Config:
        from_attributes = True


class BedTransferResponse(BaseModel):
    id: int
    admission_id: int
    from_bed_id: Optional[int] = None
    to_bed_id: int
    transferred_at: datetime
    transferred_by_id: Optional[int] = None
    reason: str
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class AdmissionResponse(BaseModel):
    id: int
    patient_id: int
    admitting_doctor_id: Optional[int] = None
    doctor_id: Optional[int] = None
    bed_id: Optional[int] = None
    department_id: Optional[int] = None
    nurse_id: Optional[int] = None
    admission_date: datetime
    discharge_date: Optional[datetime] = None
    discharge_summary: Optional[str] = None
    admission_reason: Optional[str] = None
    status: AdmissionStatusEnum
    readmission_risk_score: Optional[float] = None

    class Config:
        from_attributes = True


class RoomTypeStats(BaseModel):
    room_type: str
    total_beds: int
    occupied_beds: int
    available_beds: int
    occupancy_rate: float


class IPDDashboardStatsResponse(BaseModel):
    total_beds: int
    occupied_beds: int
    available_beds: int
    reserved_beds: int
    maintenance_beds: int
    occupancy_percentage: float
    total_rooms: int
    active_admissions_count: int
    total_admissions_historical: int
    room_types_breakdown: List[RoomTypeStats] = []
