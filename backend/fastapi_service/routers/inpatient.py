from typing import List, Optional
from datetime import datetime, date, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from backend.database import get_db
from backend.models import (
    Ward, Bed, Admission, PatientProfile, User, Patient, Doctor,
    RoleEnum, BedStatusEnum, AdmissionStatusEnum
)
from backend.fastapi_service.dependencies import get_current_user, require_roles
from backend.fastapi_service.schemas.inpatient import (
    AdmissionCreateRequest, BedResponse, AdmissionResponse,
    BedTransferRequest, BedTransferResponse, BedStatusUpdateRequest,
    DischargeRequest, IPDDashboardStatsResponse
)
from backend.services import inpatient_service
from ml.inference.predictors import readmission_predictor

router = APIRouter(prefix="/inpatient", tags=["Inpatient & Bed Management"])


@router.get("/dashboard-stats", response_model=IPDDashboardStatsResponse)
def get_ipd_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.ADMIN, RoleEnum.DOCTOR, RoleEnum.NURSE, RoleEnum.RECEPTIONIST]))
):
    """
    Returns real-time IPD dashboard statistics:
    Total beds, Occupied beds, Available beds, Reserved beds, Maintenance beds, and Occupancy percentage.
    """
    stats = inpatient_service.get_ipd_dashboard_stats(db)
    return stats


@router.get("/beds", response_model=List[BedResponse])
def list_beds(
    ward_id: Optional[int] = None,
    room_id: Optional[int] = None,
    department_id: Optional[int] = None,
    status_filter: Optional[BedStatusEnum] = Query(None, alias="status"),
    available_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lists hospital beds with real-time occupancy status and filters."""
    target_status = BedStatusEnum.AVAILABLE if available_only else status_filter
    beds = inpatient_service.get_bed_availability(
        db_session=db,
        department_id=department_id,
        room_id=room_id,
        status=target_status
    )
    if ward_id:
        beds = [b for b in beds if b.ward_id == ward_id]
    return beds


@router.patch("/beds/{bed_id}/status", response_model=BedResponse)
def update_bed_status(
    bed_id: int,
    payload: BedStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.ADMIN, RoleEnum.NURSE, RoleEnum.DOCTOR]))
):
    """
    Updates the operational status of a bed (e.g. from MAINTENANCE to AVAILABLE).
    """
    try:
        bed = inpatient_service.update_bed_status(
            db_session=db,
            bed_id=bed_id,
            new_status=payload.status,
            actor_id=current_user.id,
            notes=payload.notes
        )
        db.commit()
        db.refresh(bed)
        return bed
    except (inpatient_service.BedNotFoundError) as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except (inpatient_service.InvalidAdmissionDataError) as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Bed status update failed: {str(e)}")


@router.post("/admit", response_model=AdmissionResponse, status_code=status.HTTP_201_CREATED)
def admit_patient(
    payload: AdmissionCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.DOCTOR, RoleEnum.ADMIN, RoleEnum.RECEPTIONIST, RoleEnum.NURSE]))
):
    """
    Admits a patient to an inpatient bed, strictly preventing occupied bed assignment,
    and runs the ML 30-day Readmission Risk predictor for clinical triage.
    """
    # Identify admitting doctor
    admitting_doctor_id = current_user.id if current_user.role == RoleEnum.DOCTOR else 2
    # Verify doctor profile exists or fallback
    doc_exists = db.query(Doctor).filter(Doctor.id == admitting_doctor_id).first()
    if not doc_exists:
        first_doc = db.query(Doctor).first()
        if first_doc:
            admitting_doctor_id = first_doc.id

    nurse_id = current_user.id if current_user.role == RoleEnum.NURSE else payload.nurse_id

    try:
        admission = inpatient_service.admit_patient(
            db_session=db,
            patient_id=payload.patient_id,
            bed_id=payload.bed_id,
            admitting_doctor_id=admitting_doctor_id,
            admission_reason=payload.admission_reason,
            department_id=payload.department_id,
            nurse_id=nurse_id,
            notes=payload.notes,
            actor_id=current_user.id
        )

        # ML 30-day Readmission Risk calculation
        try:
            patient_prof = db.query(PatientProfile).filter(PatientProfile.user_id == payload.patient_id).first()
            patient_dob = patient_prof.dob if patient_prof and patient_prof.dob else date(1980, 1, 1)
            patient_age = max(1, (date.today() - patient_dob).days // 365)
            ward_type_str = admission.bed.ward.ward_type.value if admission.bed and admission.bed.ward else "general"

            ml_features = {
                "age": patient_age,
                "gender": patient_prof.gender.value if patient_prof and hasattr(patient_prof.gender, "value") else "other",
                "admission_type": "emergency" if ward_type_str in ("emergency", "icu") else "elective",
                "ward_type": ward_type_str,
                "length_of_stay_days": 4.0,
                "previous_admissions_12m": 0,
                "chronic_conditions_count": 1,
                "abnormal_lab_count": 0,
                "vital_instability_index": 0.15,
                "medication_count": 4,
                "high_risk_medication_flag": 0
            }
            pred = readmission_predictor.predict(ml_features)
            admission.readmission_risk_score = pred.get("risk_score", 0.25)
        except Exception:
            admission.readmission_risk_score = 0.20

        db.commit()
        db.refresh(admission)
        return admission

    except inpatient_service.BedUnavailableError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except (inpatient_service.PatientAlreadyAdmittedError, inpatient_service.InvalidAdmissionDataError) as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except inpatient_service.BedNotFoundError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Admission failed: {str(e)}")


@router.post("/admissions/{admission_id}/transfer", response_model=BedTransferResponse)
def transfer_patient(
    admission_id: int,
    payload: BedTransferRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.DOCTOR, RoleEnum.ADMIN, RoleEnum.NURSE]))
):
    """
    Transfers an admitted patient to a new bed. Strictly prevents transferring to occupied/unavailable beds.
    """
    try:
        transfer = inpatient_service.transfer_bed(
            db_session=db,
            admission_id=admission_id,
            to_bed_id=payload.to_bed_id,
            reason=payload.reason,
            transferred_by_id=current_user.id,
            notes=payload.notes,
            release_previous_as=payload.release_previous_as or BedStatusEnum.MAINTENANCE
        )
        db.commit()
        db.refresh(transfer)
        return transfer
    except (inpatient_service.AdmissionNotFoundError, inpatient_service.BedNotFoundError) as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except (inpatient_service.BedUnavailableError, inpatient_service.InvalidAdmissionDataError) as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Bed transfer failed: {str(e)}")


@router.post("/admissions/{admission_id}/discharge")
def discharge_patient(
    admission_id: int,
    payload: Optional[DischargeRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.DOCTOR, RoleEnum.ADMIN, RoleEnum.NURSE]))
):
    """
    Discharges inpatient, calculates bed and clinical charges,
    generates consolidated billing invoice, and marks bed as MAINTENANCE.
    """
    summary = payload.discharge_summary if payload else "Discharged in stable clinical condition"
    try:
        adm, invoice = inpatient_service.discharge_patient(
            db_session=db,
            admission_id=admission_id,
            discharge_summary=summary,
            actor_id=current_user.id
        )
        db.commit()
        return {
            "message": "Patient successfully discharged and cleared",
            "admission_id": adm.id,
            "bed_status": adm.bed.status.value if adm.bed else "maintenance",
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "total_amount": float(invoice.total_amount),
            "status": invoice.status.value
        }
    except (ValueError, inpatient_service.InvalidAdmissionDataError) as ve:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Discharge processing failed: {str(e)}")


@router.get("/admissions", response_model=List[AdmissionResponse])
def list_admissions(
    status_filter: Optional[AdmissionStatusEnum] = Query(None, alias="status"),
    patient_id: Optional[int] = None,
    doctor_id: Optional[int] = None,
    department_id: Optional[int] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.ADMIN, RoleEnum.DOCTOR, RoleEnum.NURSE, RoleEnum.RECEPTIONIST]))
):
    """Lists admissions with filtering by status, doctor, department, or patient text search."""
    admissions = inpatient_service.list_admissions(
        db_session=db,
        status=status_filter,
        patient_id=patient_id,
        doctor_id=doctor_id,
        department_id=department_id,
        search=search
    )
    return admissions


@router.get("/admissions/{admission_id}", response_model=AdmissionResponse)
def get_admission_detail(
    admission_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Gets details for a specific admission record."""
    try:
        adm = inpatient_service.get_admission_detail(db, admission_id)
        return adm
    except inpatient_service.AdmissionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/patients/{patient_id}/history", response_model=List[AdmissionResponse])
def get_patient_history(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Gets chronological IPD admission history for a patient."""
    # Patients can only view their own history unless staff
    if current_user.role == RoleEnum.PATIENT and current_user.id != patient_id:
        raise HTTPException(status_code=403, detail="Access denied to other patient's admission history")

    history = inpatient_service.get_patient_admission_history(db, patient_id)
    return history
