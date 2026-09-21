from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Prescription, PrescriptionItem, User, RoleEnum, PrescriptionStatusEnum
from backend.fastapi_service.dependencies import get_current_user, require_roles
from backend.fastapi_service.schemas.prescription import (
    PrescriptionCreateRequest,
    PrescriptionResponse,
    DispenseRequest,
    PrescriptionStatusUpdateRequest
)
from backend.services import prescription_service, audit_service

router = APIRouter(prefix="/prescriptions", tags=["Prescriptions"])


@router.get("/", response_model=List[PrescriptionResponse])
def list_prescriptions(
    patient_id: Optional[int] = None,
    doctor_id: Optional[int] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lists electronic prescriptions with patient, doctor, and fulfillment status filters."""
    if current_user.role == RoleEnum.PATIENT:
        patient_id = current_user.id

    q = db.query(Prescription)
    if patient_id:
        q = q.filter(Prescription.patient_id == patient_id)
    if doctor_id:
        q = q.filter(Prescription.doctor_id == doctor_id)
    if status_filter:
        q = q.filter(Prescription.status == status_filter)

    prescriptions = q.order_by(Prescription.created_at.desc()).offset(skip).limit(limit).all()
    return prescriptions


@router.post("/", response_model=PrescriptionResponse, status_code=status.HTTP_201_CREATED)
def create_prescription(
    payload: PrescriptionCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.DOCTOR, RoleEnum.ADMIN]))
):
    """Creates an electronic prescription containing one or more validated medicines."""
    items_data = [item.dict() for item in payload.items]
    try:
        rx = prescription_service.create_prescription(
            db_session=db,
            doctor_id=current_user.id,
            patient_id=payload.patient_id,
            items=items_data,
            medical_record_id=payload.medical_record_id,
            notes=payload.notes,
            actor_id=current_user.id
        )
        return rx
    except prescription_service.InvalidPrescriptionDataError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except prescription_service.PrescriptionServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{prescription_id}", response_model=PrescriptionResponse)
def get_prescription(
    prescription_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves prescription details with role-based confidentiality enforcement."""
    try:
        rx = prescription_service.get_prescription_detail(
            db_session=db,
            prescription_id=prescription_id,
            requester_user_id=current_user.id,
            requester_role=current_user.role.value
        )
        return rx
    except prescription_service.PrescriptionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prescription not found")
    except prescription_service.PrescriptionPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post("/{prescription_id}/dispense")
def dispense_prescription(
    prescription_id: int,
    payload: Optional[DispenseRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.PHARMACIST, RoleEnum.ADMIN]))
):
    """
    Dispenses prescribed medications using First-Expiring, First-Out (FEFO)
    batch deduction logic and updates prescription fulfillment status.
    """
    items = payload.items if payload else None
    try:
        result = prescription_service.dispense_prescription(
            db_session=db,
            prescription_id=prescription_id,
            actor_id=current_user.id,
            item_dispensations=items
        )
        return {
            "message": "Prescription successfully dispensed and inventory updated",
            "prescription_id": prescription_id,
            "status": result["status"],
            "units_dispensed": result["units_dispensed"],
            "deducted_batches": result["deducted_batches"]
        }
    except prescription_service.PrescriptionNotFoundError:
        raise HTTPException(status_code=404, detail="Prescription not found")
    except prescription_service.PrescriptionServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{prescription_id}/status", response_model=PrescriptionResponse)
def update_prescription_status(
    prescription_id: int,
    payload: PrescriptionStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.PHARMACIST, RoleEnum.DOCTOR, RoleEnum.ADMIN]))
):
    """Updates prescription progress status."""
    rx = db.query(Prescription).filter(Prescription.id == prescription_id).first()
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found")
    rx.status = payload.status
    db.commit()
    db.refresh(rx)

    audit_service.log_prescription_change(
        db=db,
        prescription_id=rx.id,
        action=audit_service.AuditActions.PRESCRIPTION_UPDATE,
        actor_id=current_user.id,
        metadata={
            "new_status": payload.status.value if hasattr(payload.status, "value") else str(payload.status),
            "patient_id": rx.patient_id,
            "doctor_id": rx.doctor_id
        }
    )

    return rx
