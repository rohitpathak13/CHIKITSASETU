from typing import List, Optional
from datetime import datetime, date, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from backend.database import get_db
from backend.models import Appointment, PatientProfile, DoctorProfile, User, RoleEnum, AppointmentStatusEnum
from backend.fastapi_service.dependencies import get_current_user, require_roles
from backend.fastapi_service.schemas.appointment import AppointmentCreateRequest, AppointmentResponse, AppointmentStatusUpdate
from ml.inference.predictors import no_show_predictor
from backend.services import audit_service

router = APIRouter(prefix="/appointments", tags=["Appointments"])

@router.get("/", response_model=List[AppointmentResponse])
def list_appointments(
    doctor_id: Optional[int] = None,
    patient_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves appointments filtered by doctor or patient."""
    q = db.query(Appointment)
    if doctor_id:
        q = q.filter(Appointment.doctor_id == doctor_id)
    if patient_id:
        q = q.filter(Appointment.patient_id == patient_id)
    elif current_user.role == RoleEnum.PATIENT:
        q = q.filter(Appointment.patient_id == current_user.id)
    return q.order_by(Appointment.appointment_datetime.asc()).all()

@router.post("/", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
def create_appointment(
    payload: AppointmentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Schedules an appointment and computes real-time ML no-show risk score."""
    target_patient_id = payload.patient_id
    if current_user.role == RoleEnum.PATIENT:
        if payload.patient_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Patients may only schedule appointments for themselves."
            )
        target_patient_id = current_user.id

    patient = db.query(PatientProfile).filter(PatientProfile.user_id == target_patient_id).first()
    doctor = db.query(DoctorProfile).filter(DoctorProfile.user_id == payload.doctor_id).first()
    if not patient or not doctor:
        raise HTTPException(status_code=404, detail="Patient or Doctor profile not found")

    # Generate daily token number for this doctor
    app_date = payload.appointment_datetime.date()
    start_of_day = datetime.combine(app_date, datetime.min.time(), tzinfo=timezone.utc)
    end_of_day = datetime.combine(app_date, datetime.max.time(), tzinfo=timezone.utc)
    
    count_today = db.query(func.count(Appointment.id)).filter(
        Appointment.doctor_id == payload.doctor_id,
        Appointment.appointment_datetime >= start_of_day,
        Appointment.appointment_datetime <= end_of_day
    ).scalar() or 0
    token_num = count_today + 1

    # Feature extraction for ML No-Show Prediction
    lead_time = max(0, (payload.appointment_datetime.date() - date.today()).days)
    patient_age = max(1, (date.today() - patient.dob).days // 365)
    
    # Calculate historical adherence
    total_past = db.query(func.count(Appointment.id)).filter(
        Appointment.patient_id == payload.patient_id,
        Appointment.appointment_datetime < payload.appointment_datetime
    ).scalar() or 0
    no_shows_past = db.query(func.count(Appointment.id)).filter(
        Appointment.patient_id == payload.patient_id,
        Appointment.status == AppointmentStatusEnum.NO_SHOW
    ).scalar() or 0
    ratio = (no_shows_past / total_past) if total_past > 0 else 0.12

    ml_features = {
        "age": patient_age,
        "gender": patient.gender.value if hasattr(patient.gender, "value") else str(patient.gender),
        "lead_time_days": lead_time,
        "day_of_week": payload.appointment_datetime.strftime("%a"),
        "appointment_hour": payload.appointment_datetime.hour,
        "department": doctor.department.name if doctor.department else "General Medicine",
        "historical_appointments": total_past,
        "historical_no_show_ratio": round(ratio, 2),
        "sms_reminder_sent": payload.sms_reminder_sent or 1
    }

    prediction = no_show_predictor.predict(ml_features)
    predicted_prob = prediction.get("no_show_probability", 0.15)

    appointment = Appointment(
        patient_id=target_patient_id,
        doctor_id=payload.doctor_id,
        appointment_datetime=payload.appointment_datetime,
        status=AppointmentStatusEnum.SCHEDULED,
        reason=payload.reason,
        token_number=token_num,
        no_show_probability=predicted_prob
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)

    audit_service.log_appointment_change(
        db=db,
        appointment_id=appointment.id,
        action=audit_service.AuditActions.APPOINTMENT_CREATE,
        actor_id=current_user.id,
        metadata={
            "patient_id": appointment.patient_id,
            "doctor_id": appointment.doctor_id,
            "datetime": appointment.appointment_datetime.isoformat() if appointment.appointment_datetime else None,
            "token_number": appointment.token_number,
            "no_show_probability": float(appointment.no_show_probability or 0.0)
        }
    )

    return appointment

@router.get("/{appointment_id}", response_model=AppointmentResponse)
def get_appointment_detail(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves details of a specific appointment."""
    app = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if current_user.role == RoleEnum.PATIENT and app.patient_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return app


@router.patch("/{appointment_id}/status", response_model=AppointmentResponse)
def update_status(
    appointment_id: int,
    payload: AppointmentStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.ADMIN, RoleEnum.DOCTOR, RoleEnum.RECEPTIONIST]))
):
    """Updates appointment progress status."""
    app = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Appointment not found")
    app.status = payload.status
    db.commit()
    db.refresh(app)

    audit_service.log_appointment_change(
        db=db,
        appointment_id=app.id,
        action=audit_service.AuditActions.APPOINTMENT_UPDATE,
        actor_id=current_user.id,
        metadata={
            "new_status": payload.status.value if hasattr(payload.status, "value") else str(payload.status),
            "patient_id": app.patient_id,
            "doctor_id": app.doctor_id
        }
    )

    return app


@router.post("/{appointment_id}/cancel", response_model=AppointmentResponse)
def cancel_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cancels a scheduled appointment."""
    app = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if current_user.role == RoleEnum.PATIENT and app.patient_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    app.status = AppointmentStatusEnum.CANCELLED
    db.commit()
    db.refresh(app)

    audit_service.log_appointment_change(
        db=db,
        appointment_id=app.id,
        action=audit_service.AuditActions.APPOINTMENT_CANCEL,
        actor_id=current_user.id,
        metadata={
            "patient_id": app.patient_id,
            "doctor_id": app.doctor_id,
            "cancelled_by": current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
        }
    )

    return app
