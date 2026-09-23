from typing import List, Optional
from datetime import date
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query

logger = logging.getLogger(__name__)
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import MedicalRecord, User, RoleEnum, Patient, Doctor
from backend.fastapi_service.dependencies import get_current_user, require_roles
from backend.fastapi_service.schemas.medical_record import (
    MedicalRecordCreateRequest,
    MedicalRecordUpdateRequest,
    MedicalRecordResponse
)
from backend.services import medical_record_service

router = APIRouter(prefix="/medical-records", tags=["Medical Records & EMR"])


@router.get("/", response_model=List[MedicalRecordResponse])
def list_medical_records(
    patient_id: Optional[int] = None,
    doctor_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lists electronic medical records with optional patient or doctor filter."""
    if current_user.role not in (RoleEnum.ADMIN, RoleEnum.DOCTOR, RoleEnum.PATIENT):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. Role is not authorized to list medical records.")

    if current_user.role == RoleEnum.PATIENT:
        patient_id = current_user.id

    q = db.query(MedicalRecord)
    if patient_id:
        q = q.filter(MedicalRecord.patient_id == patient_id)
    if doctor_id:
        q = q.filter(MedicalRecord.doctor_id == doctor_id)

    records = q.order_by(MedicalRecord.visit_date.desc()).offset(skip).limit(limit).all()
    return records


@router.post("/", response_model=MedicalRecordResponse, status_code=status.HTTP_201_CREATED)
def create_medical_record(
    payload: MedicalRecordCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.DOCTOR, RoleEnum.ADMIN]))
):
    """Creates a validated Electronic Medical Record (EMR) encounter with vital signs and diagnoses."""
    try:
        # Resolve treating doctor ID
        doc_id = getattr(payload, "doctor_id", None)
        if not doc_id and current_user.role == RoleEnum.DOCTOR:
            doc_record = db.query(Doctor).filter(Doctor.id == current_user.id).first()
            if doc_record:
                doc_id = doc_record.id

        if not doc_id:
            # If current user has doctor profile
            doc_record = db.query(Doctor).filter(Doctor.id == current_user.id).first()
            if doc_record:
                doc_id = doc_record.id
            else:
                # Find any active doctor
                first_doc = db.query(Doctor).first()
                if first_doc:
                    doc_id = first_doc.id
                else:
                    # Dynamically create doctor record for current_user
                    auto_doc = Doctor(
                        id=current_user.id,
                        specialization="General Medicine",
                        license_number=f"DOC-AUTO-{current_user.id}",
                        qualification="MBBS"
                    )
                    db.add(auto_doc)
                    db.flush()
                    doc_id = auto_doc.id

        record = medical_record_service.create_medical_record(
            db=db,
            patient_id=payload.patient_id,
            doctor_id=doc_id,
            symptoms=payload.symptoms,
            diagnosis=payload.diagnosis,
            clinical_notes=payload.clinical_notes,
            vitals_bp=payload.vitals_bp,
            vitals_pulse=payload.vitals_pulse,
            vitals_temp=payload.vitals_temp,
            vitals_spo2=payload.vitals_spo2,
            vitals_weight=payload.vitals_weight,
            vitals_height=payload.vitals_height,
            vitals_respiratory_rate=payload.vitals_respiratory_rate,
            allergies=payload.allergies,
            treatment_plan=payload.treatment_plan,
            follow_up_date=payload.follow_up_date,
            appointment_id=payload.appointment_id,
            actor_id=current_user.id
        )
        db.commit()
        db.refresh(record)
        return record
    except medical_record_service.InvalidMedicalRecordDataError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.exception("Medical record creation failed unexpectedly: %s", e)
        raise HTTPException(status_code=500, detail="Medical record creation failed. Please try again.")


@router.get("/{record_id}", response_model=MedicalRecordResponse)
def get_medical_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves single EMR encounter detail with confidentiality enforcement."""
    try:
        record = medical_record_service.get_medical_record_detail(
            db=db,
            record_id=record_id,
            viewer_id=current_user.id,
            viewer_role=current_user.role.value
        )
        return record
    except medical_record_service.MedicalRecordNotFoundError:
        raise HTTPException(status_code=404, detail="Medical record not found")
    except medical_record_service.MedicalRecordPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.put("/{record_id}", response_model=MedicalRecordResponse)
def update_medical_record(
    record_id: int,
    payload: MedicalRecordUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.DOCTOR, RoleEnum.ADMIN]))
):
    """Updates clinical notes, diagnosis, vitals, or treatment plan for a medical record."""
    update_kwargs = {k: v for k, v in payload.dict().items() if v is not None}
    try:
        record = medical_record_service.update_medical_record(
            db=db,
            record_id=record_id,
            actor_id=current_user.id,
            actor_role=current_user.role.value,
            **update_kwargs
        )
        db.commit()
        db.refresh(record)
        return record
    except medical_record_service.MedicalRecordNotFoundError:
        raise HTTPException(status_code=404, detail="Medical record not found")
    except medical_record_service.InvalidMedicalRecordDataError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except medical_record_service.MedicalRecordPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/patient/{patient_id}", response_model=List[MedicalRecordResponse])
def get_patient_emr_history(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves chronological EMR history for a specific patient."""
    if current_user.role not in (RoleEnum.ADMIN, RoleEnum.DOCTOR) and (current_user.role != RoleEnum.PATIENT or current_user.id != patient_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized to view patient's clinical medical records")
    records = db.query(MedicalRecord).filter(MedicalRecord.patient_id == patient_id).order_by(MedicalRecord.visit_date.desc()).all()
    return records


@router.get("/patient/{patient_id}/timeline")
def get_patient_timeline(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves unified medical history timeline spanning visits, prescriptions, labs, and admissions."""
    try:
        timeline = medical_record_service.get_patient_medical_timeline(
            db=db,
            patient_id=patient_id,
            viewer_id=current_user.id,
            viewer_role=current_user.role.value
        )
        return timeline
    except medical_record_service.MedicalRecordPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
