from datetime import datetime, date, timezone, timedelta
from typing import Optional, List, Dict, Any, Union
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from backend.models import (
    Appointment, Patient, Doctor, User, Department,
    AppointmentStatusEnum, AuditLog
)
from ml.inference.predictors import no_show_predictor


# =====================================================================
# Custom Service Exceptions
# =====================================================================

class AppointmentServiceError(Exception):
    """Base exception for appointment service errors."""
    pass


class DuplicateBookingError(AppointmentServiceError):
    """Raised when an appointment slot is already booked."""
    pass


class DoctorUnavailableError(AppointmentServiceError):
    """Raised when a doctor is not on duty or unavailable on the requested day."""
    pass


class InvalidAppointmentDataError(AppointmentServiceError):
    """Raised when appointment input parameters are invalid."""
    pass


class AppointmentNotFoundError(AppointmentServiceError):
    """Raised when the requested appointment does not exist."""
    pass


class AppointmentStateError(AppointmentServiceError):
    """Raised when an operation violates the appointment lifecycle state."""
    pass


# Standard clinic consultation time slots (30-minute intervals)
CLINIC_SLOTS = [
    "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
    "12:00", "14:00", "14:30", "15:00", "15:30", "16:00", "16:30"
]


# =====================================================================
# Helper Utilities
# =====================================================================

def parse_datetime(dt_input: Union[str, datetime]) -> datetime:
    """Safely normalizes string or datetime input to a timezone-aware UTC datetime."""
    if isinstance(dt_input, datetime):
        if dt_input.tzinfo is None:
            return dt_input.replace(tzinfo=timezone.utc)
        return dt_input

    if not dt_input or not isinstance(dt_input, str):
        raise InvalidAppointmentDataError("Appointment date and time is required.")

    clean_str = dt_input.strip()
    formats = [
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d"
    ]
    for fmt in formats:
        try:
            parsed = datetime.strptime(clean_str, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    raise InvalidAppointmentDataError(f"Invalid date/time format: '{dt_input}'. Expected YYYY-MM-DDTHH:MM.")


def get_available_slots(db: Session, doctor_id: int, target_date: Union[str, date]) -> Dict[str, Any]:
    """Inspects doctor duty schedule and returns booked vs. free consultation slots for a given date."""
    if isinstance(target_date, str):
        try:
            target_date = datetime.strptime(target_date.strip(), "%Y-%m-%d").date()
        except ValueError:
            raise InvalidAppointmentDataError(f"Invalid date format: '{target_date}'. Expected YYYY-MM-DD.")

    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise DoctorUnavailableError(f"Doctor ID {doctor_id} not found.")

    available_days_str = doctor.available_days or "Mon,Tue,Wed,Thu,Fri"
    available_days = {d.strip() for d in available_days_str.split(",") if d.strip()}
    weekday_abbr = target_date.strftime("%a")  # e.g. 'Mon'

    is_on_duty = weekday_abbr in available_days

    # Query active appointments on target_date for this doctor
    start_day = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)
    end_day = datetime.combine(target_date, datetime.max.time(), tzinfo=timezone.utc)

    active_appts = db.query(Appointment).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_datetime >= start_day,
        Appointment.appointment_datetime <= end_day,
        Appointment.status != AppointmentStatusEnum.CANCELLED
    ).all()

    booked_slots = set()
    for app in active_appts:
        if app.appointment_datetime:
            booked_slots.add(app.appointment_datetime.strftime("%H:%M"))

    free_slots = [slot for slot in CLINIC_SLOTS if slot not in booked_slots] if is_on_duty else []

    return {
        "doctor_id": doctor.id,
        "doctor_name": doctor.user.full_name if doctor.user else "Doctor",
        "date": target_date.strftime("%Y-%m-%d"),
        "weekday": target_date.strftime("%A"),
        "is_available": is_on_duty,
        "available_days": available_days_str,
        "all_slots": CLINIC_SLOTS,
        "booked_slots": sorted(list(booked_slots)),
        "free_slots": free_slots
    }


# =====================================================================
# Core Appointment Lifecycle Service Operations
# =====================================================================

def book_appointment(
    db: Session,
    patient_id: int,
    doctor_id: int,
    appointment_datetime: Union[str, datetime],
    reason: Optional[str] = None,
    actor_id: Optional[int] = None,
    ip_address: Optional[str] = None
) -> Appointment:
    """
    Schedules an outpatient appointment with double-booking prevention,
    doctor availability validation, token generation, and ML no-show scoring.
    """
    appt_dt = parse_datetime(appointment_datetime)

    # 1. Validation: Date cannot be in past
    today = date.today()
    if appt_dt.date() < today:
        raise InvalidAppointmentDataError("Cannot book an appointment for a past date.")

    # 2. Validation: Entities must exist
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise InvalidAppointmentDataError(f"Patient with ID {patient_id} does not exist.")

    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise InvalidAppointmentDataError(f"Doctor with ID {doctor_id} does not exist.")

    # 3. Doctor Availability Schedule Check
    available_days_str = doctor.available_days or "Mon,Tue,Wed,Thu,Fri"
    available_days = {d.strip() for d in available_days_str.split(",") if d.strip()}
    weekday_abbr = appt_dt.strftime("%a")

    if weekday_abbr not in available_days:
        day_full = appt_dt.strftime("%A")
        raise DoctorUnavailableError(
            f"Dr. {doctor.user.full_name} is not available on {day_full}s. "
            f"Active clinic schedule: {available_days_str}."
        )

    # 4. Prevent Double Booking: Doctor level
    # Check if doctor already has an active (non-cancelled) appointment at this exact slot
    existing_booking = db.query(Appointment).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_datetime == appt_dt,
        Appointment.status != AppointmentStatusEnum.CANCELLED
    ).first()

    if existing_booking:
        raise DuplicateBookingError(
            f"Dr. {doctor.user.full_name} is already booked at {appt_dt.strftime('%Y-%m-%d %H:%M')}. "
            "Please select a different consultation time slot."
        )

    # 5. Prevent Double Booking: Patient level
    # A patient cannot have two active appointments at the exact same time
    existing_patient_booking = db.query(Appointment).filter(
        Appointment.patient_id == patient_id,
        Appointment.appointment_datetime == appt_dt,
        Appointment.status != AppointmentStatusEnum.CANCELLED
    ).first()

    if existing_patient_booking:
        raise DuplicateBookingError(
            f"Patient {patient.user.full_name} already has an appointment scheduled at {appt_dt.strftime('%Y-%m-%d %H:%M')}."
        )

    # 6. Sequential Daily Token Generation
    app_date = appt_dt.date()
    start_day = datetime.combine(app_date, datetime.min.time(), tzinfo=timezone.utc)
    end_day = datetime.combine(app_date, datetime.max.time(), tzinfo=timezone.utc)

    daily_count = db.query(func.count(Appointment.id)).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_datetime >= start_day,
        Appointment.appointment_datetime <= end_day
    ).scalar() or 0
    token_num = daily_count + 1

    # 7. AI No-Show Risk Scoring
    lead_time = max(0, (app_date - today).days)
    patient_age = max(1, (today - patient.dob).days // 365)

    total_past = db.query(func.count(Appointment.id)).filter(
        Appointment.patient_id == patient_id,
        Appointment.appointment_datetime < appt_dt
    ).scalar() or 0

    no_shows_past = db.query(func.count(Appointment.id)).filter(
        Appointment.patient_id == patient_id,
        Appointment.status == AppointmentStatusEnum.NO_SHOW
    ).scalar() or 0

    ratio = (no_shows_past / total_past) if total_past > 0 else 0.10

    ml_features = {
        "age": patient_age,
        "gender": patient.gender.value if hasattr(patient.gender, "value") else str(patient.gender),
        "lead_time_days": lead_time,
        "day_of_week": weekday_abbr,
        "appointment_hour": appt_dt.hour,
        "department": doctor.department.name if doctor.department else "General Medicine",
        "historical_appointments": total_past,
        "historical_no_show_ratio": round(ratio, 2),
        "sms_reminder_sent": 1
    }

    try:
        prediction = no_show_predictor.predict(ml_features)
        predicted_prob = prediction.get("no_show_probability", 0.15)
    except Exception:
        predicted_prob = 0.15

    # 8. Create and Persist Appointment
    appointment = Appointment(
        patient_id=patient_id,
        doctor_id=doctor_id,
        appointment_datetime=appt_dt,
        status=AppointmentStatusEnum.SCHEDULED,
        reason=reason or "General OPD Consultation",
        token_number=token_num,
        no_show_probability=predicted_prob
    )
    db.add(appointment)
    db.flush()

    # 9. Audit Logging
    audit = AuditLog(
        user_id=actor_id or patient_id,
        action="APPOINTMENT_BOOKED",
        resource_type="Appointment",
        resource_id=appointment.id,
        ip_address=ip_address,
        details_json=f'{{"patient_id": {patient_id}, "doctor_id": {doctor_id}, "token": {token_num}, "datetime": "{appt_dt.isoformat()}"}}'
    )
    db.add(audit)
    db.commit()

    return appointment


def reschedule_appointment(
    db: Session,
    appointment_id: int,
    new_datetime: Union[str, datetime],
    actor_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    reason: Optional[str] = None
) -> Appointment:
    """
    Reschedules an active appointment to a new date/time with availability
    and duplicate booking validation.
    """
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise AppointmentNotFoundError(f"Appointment ID {appointment_id} not found.")

    if appointment.status == AppointmentStatusEnum.COMPLETED:
        raise AppointmentStateError("Cannot reschedule a completed appointment.")

    if appointment.status == AppointmentStatusEnum.CANCELLED:
        raise AppointmentStateError("Cannot reschedule a cancelled appointment.")

    new_dt = parse_datetime(new_datetime)
    today = date.today()
    if new_dt.date() < today:
        raise InvalidAppointmentDataError("Cannot reschedule an appointment to a past date.")

    doctor = appointment.doctor
    available_days_str = doctor.available_days or "Mon,Tue,Wed,Thu,Fri"
    available_days = {d.strip() for d in available_days_str.split(",") if d.strip()}
    weekday_abbr = new_dt.strftime("%a")

    if weekday_abbr not in available_days:
        day_full = new_dt.strftime("%A")
        raise DoctorUnavailableError(
            f"Dr. {doctor.user.full_name} is not available on {day_full}s. "
            f"Active schedule: {available_days_str}."
        )

    # Double booking collision check on target slot
    collision = db.query(Appointment).filter(
        Appointment.doctor_id == doctor.id,
        Appointment.appointment_datetime == new_dt,
        Appointment.id != appointment_id,
        Appointment.status != AppointmentStatusEnum.CANCELLED
    ).first()

    if collision:
        raise DuplicateBookingError(
            f"Dr. {doctor.user.full_name} is already booked at {new_dt.strftime('%Y-%m-%d %H:%M')}."
        )

    # Calculate token for new date
    new_date = new_dt.date()
    start_day = datetime.combine(new_date, datetime.min.time(), tzinfo=timezone.utc)
    end_day = datetime.combine(new_date, datetime.max.time(), tzinfo=timezone.utc)

    daily_count = db.query(func.count(Appointment.id)).filter(
        Appointment.doctor_id == doctor.id,
        Appointment.appointment_datetime >= start_day,
        Appointment.appointment_datetime <= end_day,
        Appointment.id != appointment_id
    ).scalar() or 0

    old_time = appointment.appointment_datetime.strftime('%Y-%m-%d %H:%M') if appointment.appointment_datetime else 'N/A'
    appointment.appointment_datetime = new_dt
    appointment.token_number = daily_count + 1
    appointment.status = AppointmentStatusEnum.SCHEDULED
    if reason:
        appointment.reason = f"{appointment.reason or ''} (Rescheduled: {reason})".strip()

    audit = AuditLog(
        user_id=actor_id or appointment.patient_id,
        action="APPOINTMENT_RESCHEDULED",
        resource_type="Appointment",
        resource_id=appointment.id,
        ip_address=ip_address,
        details_json=f'{{"from": "{old_time}", "to": "{new_dt.isoformat()}", "token": {appointment.token_number}}}'
    )
    db.add(audit)
    db.commit()

    return appointment


def cancel_appointment(
    db: Session,
    appointment_id: int,
    actor_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    cancellation_reason: Optional[str] = None
) -> Appointment:
    """Cancels an appointment, freeing the slot for future bookings."""
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise AppointmentNotFoundError(f"Appointment ID {appointment_id} not found.")

    if appointment.status == AppointmentStatusEnum.COMPLETED:
        raise AppointmentStateError("Cannot cancel an already completed appointment.")

    if appointment.status == AppointmentStatusEnum.CANCELLED:
        return appointment

    appointment.status = AppointmentStatusEnum.CANCELLED
    if cancellation_reason:
        appointment.reason = f"{appointment.reason or ''} [Cancelled: {cancellation_reason}]".strip()

    audit = AuditLog(
        user_id=actor_id or appointment.patient_id,
        action="APPOINTMENT_CANCELLED",
        resource_type="Appointment",
        resource_id=appointment.id,
        ip_address=ip_address,
        details_json=f'{{"appointment_id": {appointment.id}, "reason": "{cancellation_reason or "Patient request"}"}}'
    )
    db.add(audit)
    db.commit()

    return appointment


def complete_appointment(
    db: Session,
    appointment_id: int,
    actor_id: Optional[int] = None,
    ip_address: Optional[str] = None
) -> Appointment:
    """Marks an appointment as completed following a clinical consultation."""
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise AppointmentNotFoundError(f"Appointment ID {appointment_id} not found.")

    if appointment.status == AppointmentStatusEnum.CANCELLED:
        raise AppointmentStateError("Cannot complete a cancelled appointment.")

    appointment.status = AppointmentStatusEnum.COMPLETED

    audit = AuditLog(
        user_id=actor_id or appointment.doctor_id,
        action="APPOINTMENT_COMPLETED",
        resource_type="Appointment",
        resource_id=appointment.id,
        ip_address=ip_address,
        details_json=f'{{"appointment_id": {appointment.id}, "status": "completed"}}'
    )
    db.add(audit)
    db.commit()

    return appointment


def update_appointment_status(
    db: Session,
    appointment_id: int,
    new_status: Union[str, AppointmentStatusEnum],
    actor_id: Optional[int] = None,
    ip_address: Optional[str] = None
) -> Appointment:
    """Transitions an appointment to any designated status."""
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise AppointmentNotFoundError(f"Appointment ID {appointment_id} not found.")

    if isinstance(new_status, str):
        try:
            status_enum = AppointmentStatusEnum(new_status.strip().lower())
        except ValueError:
            raise InvalidAppointmentDataError(f"Invalid status value '{new_status}'.")
    else:
        status_enum = new_status

    if status_enum == AppointmentStatusEnum.CANCELLED:
        return cancel_appointment(db, appointment_id, actor_id, ip_address)
    if status_enum == AppointmentStatusEnum.COMPLETED:
        return complete_appointment(db, appointment_id, actor_id, ip_address)

    appointment.status = status_enum

    audit = AuditLog(
        user_id=actor_id or appointment.doctor_id,
        action="APPOINTMENT_STATUS_UPDATED",
        resource_type="Appointment",
        resource_id=appointment.id,
        ip_address=ip_address,
        details_json=f'{{"appointment_id": {appointment.id}, "new_status": "{status_enum.value}"}}'
    )
    db.add(audit)
    db.commit()

    return appointment
