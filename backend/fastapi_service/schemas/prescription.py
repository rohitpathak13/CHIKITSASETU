from pydantic import BaseModel
from typing import Optional, List
from backend.models.pharmacy import PrescriptionStatusEnum
from backend.fastapi_service.schemas.pharmacy import (
    PrescriptionItemCreate,
    PrescriptionCreateRequest,
    PrescriptionItemResponse,
    PrescriptionResponse,
    DispenseRequest
)

class PrescriptionStatusUpdateRequest(BaseModel):
    status: PrescriptionStatusEnum

__all__ = [
    "PrescriptionItemCreate",
    "PrescriptionCreateRequest",
    "PrescriptionItemResponse",
    "PrescriptionResponse",
    "DispenseRequest",
    "PrescriptionStatusUpdateRequest"
]
