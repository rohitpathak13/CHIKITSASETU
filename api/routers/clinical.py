from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from core.database import get_db
from core.models import (
    MedicalRecord, Prescription, PrescriptionItem, LabOrder, LabTestType,
    User, DoctorProfile, PatientProfile, RoleEnum, LabOrderStatusEnum, PrescriptionStatusEnum
)
from api.dependencies import get_current_user, require_roles
from api.schemas.clinical import MedicalRecordCreateRequest, MedicalRecordResponse

router = APIRouter(prefix="/clinical", tags=["Clinical Records & EMR"])

@router.post("/records", response_model=MedicalRecordResponse, status_code=status.HTTP_201_CREATED)
def create_medical_record(
    payload: MedicalRecordCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.DOCTOR, RoleEnum.ADMIN]))
):
    """
    Creates an Electronic Medical Record (EMR) including diagnosis, vitals,
    optional electronic prescriptions, and diagnostic lab test orders.
    """
    patient = db.query(PatientProfile).filter(PatientProfile.user_id == payload.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    record = MedicalRecord(
        patient_id=payload.patient_id,
        doctor_id=current_user.id,
        appointment_id=payload.appointment_id,
        visit_date=date.today(),
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
        follow_up_date=payload.follow_up_date
    )
    if payload.allergies:
        if patient.allergies:
            if payload.allergies.lower() not in patient.allergies.lower():
                patient.allergies = f"{patient.allergies}, {payload.allergies}"
        else:
            patient.allergies = payload.allergies

    db.add(record)
    db.flush()

    # Create associated prescription if items provided
    if payload.prescriptions:
        rx = Prescription(
            medical_record_id=record.id,
            patient_id=payload.patient_id,
            doctor_id=current_user.id,
            status=PrescriptionStatusEnum.PENDING,
            notes="Standard outpatient prescription"
        )
        db.add(rx)
        db.flush()

        for item in payload.prescriptions:
            rx_item = PrescriptionItem(
                prescription_id=rx.id,
                medicine_id=item.medicine_id,
                dosage=item.dosage,
                frequency=item.frequency,
                duration_days=item.duration_days,
                instructions=item.instructions,
                quantity_prescribed=item.quantity_prescribed
            )
            db.add(rx_item)

    # Create associated lab orders if test IDs provided
    if payload.lab_test_ids:
        for test_id in payload.lab_test_ids:
            lab_order = LabOrder(
                patient_id=payload.patient_id,
                doctor_id=current_user.id,
                medical_record_id=record.id,
                test_type_id=test_id,
                status=LabOrderStatusEnum.ORDERED
            )
            db.add(lab_order)

    db.commit()
    db.refresh(record)
    return record

@router.get("/records/patient/{patient_id}", response_model=List[MedicalRecordResponse])
def get_patient_history(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves longitudinal medical records for a given patient."""
    if current_user.role == RoleEnum.PATIENT and current_user.id != patient_id:
        raise HTTPException(status_code=403, detail="Unauthorized access to patient records")
    return db.query(MedicalRecord).filter(MedicalRecord.patient_id == patient_id).order_by(MedicalRecord.visit_date.desc()).all()
