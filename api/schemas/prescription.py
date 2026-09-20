from pydantic import BaseModel
from typing import Optional, List
from core.models.pharmacy import PrescriptionStatusEnum
from api.schemas.pharmacy import (
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
