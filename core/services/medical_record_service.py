import re
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any, Union
from sqlalchemy.orm import Session
from sqlalchemy import desc

from core.models import (
    MedicalRecord, Diagnosis, Patient, Doctor, Appointment,
    Prescription, LabOrder, Admission, User, AuditLog,
    RoleEnum, AppointmentStatusEnum
)


# =====================================================================
# Custom Service Exceptions
# =====================================================================

class MedicalRecordServiceError(Exception):
    """Base exception for medical record / EMR errors."""
    pass


class InvalidMedicalRecordDataError(MedicalRecordServiceError):
    """Raised when clinical data or vital signs fail validation."""
    pass


class MedicalRecordNotFoundError(MedicalRecordServiceError):
    """Raised when the requested medical record cannot be located."""
    pass


class MedicalRecordPermissionError(MedicalRecordServiceError):
    """Raised when a user attempts unauthorized access or tampering with an EMR record."""
    pass


# =====================================================================
# Physiological Validation Helpers
# =====================================================================

BP_PATTERN = re.compile(r"^(\d{2,3})/(\d{2,3})$")


def validate_vitals(
    bp: Optional[str] = None,
    pulse: Optional[int] = None,
    temp: Optional[Union[float, Decimal]] = None,
    spo2: Optional[int] = None,
    weight: Optional[Union[float, Decimal]] = None,
    height: Optional[Union[float, Decimal]] = None,
    respiratory_rate: Optional[int] = None
):
    """Validates that recorded physiological vital signs fall within plausible biological bounds."""
    if bp:
        match = BP_PATTERN.match(bp.strip())
        if not match:
            raise InvalidMedicalRecordDataError(f"Invalid blood pressure format: '{bp}'. Expected 'systolic/diastolic' (e.g. '120/80').")
        systolic, diastolic = int(match.group(1)), int(match.group(2))
        if not (50 <= systolic <= 300) or not (30 <= diastolic <= 200):
            raise InvalidMedicalRecordDataError(f"Blood pressure values out of physiological range: {systolic}/{diastolic} mmHg.")
        if systolic <= diastolic:
            raise InvalidMedicalRecordDataError(f"Systolic blood pressure ({systolic}) must be strictly higher than diastolic ({diastolic}).")

    if pulse is not None:
        if not (30 <= pulse <= 260):
            raise InvalidMedicalRecordDataError(f"Heart rate / pulse out of plausible range (30-260 bpm): {pulse}.")

    if temp is not None:
        val = float(temp)
        if not (30.0 <= val <= 45.0):
            raise InvalidMedicalRecordDataError(f"Body temperature out of plausible physiological range (30.0-45.0°C): {val}°C.")

    if spo2 is not None:
        if not (50 <= spo2 <= 100):
            raise InvalidMedicalRecordDataError(f"Blood oxygen saturation (SpO2) out of range (50-100%): {spo2}%.")

    if weight is not None:
        w_val = float(weight)
        if not (0.5 <= w_val <= 600.0):
            raise InvalidMedicalRecordDataError(f"Patient weight out of plausible range (0.5-600 kg): {w_val} kg.")

    if height is not None:
        h_val = float(height)
        if not (20.0 <= h_val <= 280.0):
            raise InvalidMedicalRecordDataError(f"Patient height out of plausible range (20-280 cm): {h_val} cm.")

    if respiratory_rate is not None:
        if not (4 <= respiratory_rate <= 80):
            raise InvalidMedicalRecordDataError(f"Respiratory rate out of plausible range (4-80 breaths/min): {respiratory_rate}.")


def parse_date(date_val: Union[str, date, None]) -> Optional[date]:
    """Safely converts string or date object to standard date."""
    if not date_val:
        return None
    if isinstance(date_val, date):
        return date_val
    if isinstance(date_val, str):
        clean = date_val.strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(clean, fmt).date()
            except ValueError:
                continue
    raise InvalidMedicalRecordDataError(f"Invalid date format: '{date_val}'. Expected YYYY-MM-DD.")


# =====================================================================
# Clinical EMR Lifecycle Operations
# =====================================================================

def create_medical_record(
    db: Session,
    patient_id: int,
    doctor_id: int,
    symptoms: str,
    diagnosis: str,
    clinical_notes: Optional[str] = None,
    vitals_bp: Optional[str] = None,
    vitals_pulse: Optional[int] = None,
    vitals_temp: Optional[Union[float, Decimal]] = None,
    vitals_spo2: Optional[int] = None,
    vitals_weight: Optional[Union[float, Decimal]] = None,
    vitals_height: Optional[Union[float, Decimal]] = None,
    vitals_respiratory_rate: Optional[int] = None,
    allergies: Optional[str] = None,
    treatment_plan: Optional[str] = None,
    follow_up_date: Optional[Union[str, date]] = None,
    appointment_id: Optional[int] = None,
    diagnosis_code: Optional[str] = None,
    diagnosis_type: str = "Primary",
    actor_id: Optional[int] = None,
    ip_address: Optional[str] = None
) -> MedicalRecord:
    """
    Creates an Electronic Medical Record (EMR) encounter with clinical validations,
    vital sign checks, diagnosis registration, allergy profile sync, and audit logging.
    """
    if not symptoms or not symptoms.strip():
        raise InvalidMedicalRecordDataError("Patient symptoms / chief complaints are required.")
    if not diagnosis or not diagnosis.strip():
        raise InvalidMedicalRecordDataError("Clinical diagnosis is required.")

    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise InvalidMedicalRecordDataError(f"Patient ID {patient_id} does not exist.")

    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise InvalidMedicalRecordDataError(f"Doctor ID {doctor_id} does not exist.")

    # Validate vitals
    validate_vitals(
        bp=vitals_bp,
        pulse=vitals_pulse,
        temp=vitals_temp,
        spo2=vitals_spo2,
        weight=vitals_weight,
        height=vitals_height,
        respiratory_rate=vitals_respiratory_rate
    )

    # Validate follow-up date
    parsed_follow_up = parse_date(follow_up_date)
    today = date.today()
    if parsed_follow_up and parsed_follow_up < today:
        raise InvalidMedicalRecordDataError("Follow-up date cannot be set in the past.")

    # 1. Instantiate MedicalRecord
    record = MedicalRecord(
        patient_id=patient_id,
        doctor_id=doctor_id,
        appointment_id=appointment_id,
        visit_date=today,
        symptoms=symptoms.strip(),
        diagnosis=diagnosis.strip(),
        clinical_notes=clinical_notes.strip() if clinical_notes else None,
        vitals_bp=vitals_bp.strip() if vitals_bp else None,
        vitals_pulse=int(vitals_pulse) if vitals_pulse is not None else None,
        vitals_temp=Decimal(str(vitals_temp)) if vitals_temp is not None else None,
        vitals_spo2=int(vitals_spo2) if vitals_spo2 is not None else None,
        vitals_weight=Decimal(str(vitals_weight)) if vitals_weight is not None else None,
        vitals_height=Decimal(str(vitals_height)) if vitals_height is not None else None,
        vitals_respiratory_rate=int(vitals_respiratory_rate) if vitals_respiratory_rate is not None else None,
        allergies=allergies.strip() if allergies else None,
        treatment_plan=treatment_plan.strip() if treatment_plan else None,
        follow_up_date=parsed_follow_up
    )
    db.add(record)
    db.flush()

    # 2. Sync allergies to Patient global profile if new allergens documented
    if allergies and allergies.strip():
        new_allergy = allergies.strip()
        if patient.allergies:
            existing_allergies = [a.strip().lower() for a in patient.allergies.split(",") if a.strip()]
            if new_allergy.lower() not in existing_allergies:
                patient.allergies = f"{patient.allergies}, {new_allergy}"
        else:
            patient.allergies = new_allergy

    # 3. Register Diagnosis entity for ICD-10 registry tracking
    diag_obj = Diagnosis(
        patient_id=patient_id,
        doctor_id=doctor_id,
        medical_record_id=record.id,
        diagnosis_code=diagnosis_code.strip() if diagnosis_code else "R69",
        diagnosis_name=diagnosis.strip(),
        diagnosis_type=diagnosis_type,
        status="Active",
        diagnosed_date=today
    )
    db.add(diag_obj)

    # 4. If linked to an appointment, complete the appointment
    if appointment_id:
        appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
        if appt and appt.status != AppointmentStatusEnum.CANCELLED:
            appt.status = AppointmentStatusEnum.COMPLETED

    # 5. Audit Logging
    audit = AuditLog(
        user_id=actor_id or doctor_id,
        action="MEDICAL_RECORD_CREATED",
        resource_type="MedicalRecord",
        resource_id=record.id,
        ip_address=ip_address,
        details_json=f'{{"patient_id": {patient_id}, "doctor_id": {doctor_id}, "diagnosis": "{record.diagnosis[:50]}", "follow_up": "{parsed_follow_up}"}}'
    )
    db.add(audit)
    db.commit()

    return record


def update_medical_record(
    db: Session,
    record_id: int,
    actor_id: int,
    actor_role: str,
    symptoms: Optional[str] = None,
    diagnosis: Optional[str] = None,
    clinical_notes: Optional[str] = None,
    vitals_bp: Optional[str] = None,
    vitals_pulse: Optional[int] = None,
    vitals_temp: Optional[Union[float, Decimal]] = None,
    vitals_spo2: Optional[int] = None,
    vitals_weight: Optional[Union[float, Decimal]] = None,
    vitals_height: Optional[Union[float, Decimal]] = None,
    vitals_respiratory_rate: Optional[int] = None,
    allergies: Optional[str] = None,
    treatment_plan: Optional[str] = None,
    follow_up_date: Optional[Union[str, date]] = None,
    change_reason: Optional[str] = None,
    ip_address: Optional[str] = None
) -> MedicalRecord:
    """
    Updates an existing Medical Record. Strictly enforces that only the treating doctor
    or an administrator can modify clinical notes and diagnoses, recording an audit log diff.
    """
    record = db.query(MedicalRecord).filter(MedicalRecord.id == record_id).first()
    if not record:
        raise MedicalRecordNotFoundError(f"Medical Record ID {record_id} not found.")

    norm_role = actor_role.lower().strip() if actor_role else ""
    # Strict RBAC: Only authoring doctor or admin can edit
    if norm_role != "admin" and record.doctor_id != actor_id:
        raise MedicalRecordPermissionError("Only the authoring doctor or a medical administrator may amend this clinical record.")

    # Validate updated vitals if provided
    validate_vitals(
        bp=vitals_bp if vitals_bp is not None else record.vitals_bp,
        pulse=vitals_pulse if vitals_pulse is not None else record.vitals_pulse,
        temp=vitals_temp if vitals_temp is not None else record.vitals_temp,
        spo2=vitals_spo2 if vitals_spo2 is not None else record.vitals_spo2,
        weight=vitals_weight if vitals_weight is not None else record.vitals_weight,
        height=vitals_height if vitals_height is not None else record.vitals_height,
        respiratory_rate=vitals_respiratory_rate if vitals_respiratory_rate is not None else record.vitals_respiratory_rate
    )

    changes = []

    if symptoms is not None and symptoms.strip():
        if record.symptoms != symptoms.strip():
            changes.append("symptoms")
            record.symptoms = symptoms.strip()

    if diagnosis is not None and diagnosis.strip():
        if record.diagnosis != diagnosis.strip():
            changes.append("diagnosis")
            record.diagnosis = diagnosis.strip()
            # Update diagnosis model
            diag = db.query(Diagnosis).filter(Diagnosis.medical_record_id == record.id).first()
            if diag:
                diag.diagnosis_name = diagnosis.strip()

    if clinical_notes is not None:
        if record.clinical_notes != clinical_notes.strip():
            changes.append("clinical_notes")
            record.clinical_notes = clinical_notes.strip() if clinical_notes.strip() else None

    if vitals_bp is not None:
        record.vitals_bp = vitals_bp.strip() if vitals_bp.strip() else None
        changes.append("vitals_bp")

    if vitals_pulse is not None:
        record.vitals_pulse = int(vitals_pulse) if vitals_pulse else None
        changes.append("vitals_pulse")

    if vitals_temp is not None:
        record.vitals_temp = Decimal(str(vitals_temp)) if vitals_temp else None
        changes.append("vitals_temp")

    if vitals_spo2 is not None:
        record.vitals_spo2 = int(vitals_spo2) if vitals_spo2 else None
        changes.append("vitals_spo2")

    if vitals_weight is not None:
        record.vitals_weight = Decimal(str(vitals_weight)) if vitals_weight else None
        changes.append("vitals_weight")

    if vitals_height is not None:
        record.vitals_height = Decimal(str(vitals_height)) if vitals_height else None
        changes.append("vitals_height")

    if vitals_respiratory_rate is not None:
        record.vitals_respiratory_rate = int(vitals_respiratory_rate) if vitals_respiratory_rate else None
        changes.append("vitals_respiratory_rate")

    if allergies is not None:
        record.allergies = allergies.strip() if allergies.strip() else None
        changes.append("allergies")
        if record.allergies and record.patient:
            if record.patient.allergies:
                if record.allergies.lower() not in record.patient.allergies.lower():
                    record.patient.allergies = f"{record.patient.allergies}, {record.allergies}"
            else:
                record.patient.allergies = record.allergies

    if treatment_plan is not None:
        record.treatment_plan = treatment_plan.strip() if treatment_plan.strip() else None
        changes.append("treatment_plan")

    if follow_up_date is not None:
        parsed_fup = parse_date(follow_up_date)
        if parsed_fup and parsed_fup < date.today():
            raise InvalidMedicalRecordDataError("Follow-up date cannot be set in the past.")
        record.follow_up_date = parsed_fup
        changes.append("follow_up_date")

    # Record audit log
    audit = AuditLog(
        user_id=actor_id,
        action="MEDICAL_RECORD_UPDATED",
        resource_type="MedicalRecord",
        resource_id=record.id,
        ip_address=ip_address,
        details_json=f'{{"record_id": {record.id}, "changed_fields": {changes}, "reason": "{change_reason or "Clinical amendment"}"}}'
    )
    db.add(audit)
    db.commit()

    return record


# =====================================================================
# Chronological Medical History Timeline Engine
# =====================================================================

def get_patient_medical_timeline(
    db: Session,
    patient_id: int,
    viewer_id: int,
    viewer_role: str
) -> Dict[str, Any]:
    """
    Assembles a unified, chronological timeline of all clinical encounters,
    diagnoses, prescriptions, diagnostic lab orders, and inpatient admissions.
    Enforces strict patient confidentiality and role-based access.
    """
    norm_role = viewer_role.lower().strip() if viewer_role else ""

    # Strict RBAC Check
    if norm_role == "patient" and viewer_id != patient_id:
        raise MedicalRecordPermissionError("Unauthorized: Patients may only access their own clinical records.")

    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise InvalidMedicalRecordDataError(f"Patient ID {patient_id} not found.")

    timeline_events = []

    # 1. Clinical Consultations & Medical Records
    records = db.query(MedicalRecord).filter(MedicalRecord.patient_id == patient_id).all()
    for r in records:
        vitals_list = []
        if r.vitals_bp: vitals_list.append(f"BP: {r.vitals_bp}")
        if r.vitals_pulse: vitals_list.append(f"Pulse: {r.vitals_pulse} bpm")
        if r.vitals_temp: vitals_list.append(f"Temp: {r.vitals_temp}°C")
        if r.vitals_spo2: vitals_list.append(f"SpO2: {r.vitals_spo2}%")
        if r.vitals_weight: vitals_list.append(f"Wt: {r.vitals_weight} kg")
        if r.vitals_height: vitals_list.append(f"Ht: {r.vitals_height} cm")
        if r.vitals_respiratory_rate: vitals_list.append(f"RR: {r.vitals_respiratory_rate}/min")

        doc_name = r.doctor.user.full_name if (r.doctor and r.doctor.user) else "Attending Doctor"
        dept_name = r.doctor.department.name if (r.doctor and r.doctor.department) else "General Medicine"

        timeline_events.append({
            "id": f"consultation-{r.id}",
            "entity_id": r.id,
            "type": "consultation",
            "date": r.visit_date,
            "date_str": r.visit_date.strftime("%Y-%m-%d"),
            "title": f"Consultation: {r.diagnosis}",
            "subtitle": f"Attending: Dr. {doc_name} ({dept_name})",
            "doctor_name": doc_name,
            "department": dept_name,
            "doctor_id": r.doctor_id,
            "badge_class": "badge-info",
            "icon": "🩺",
            "data": {
                "symptoms": r.symptoms,
                "diagnosis": r.diagnosis,
                "clinical_notes": r.clinical_notes,
                "vitals_summary": " | ".join(vitals_list) if vitals_list else None,
                "allergies": r.allergies,
                "treatment_plan": r.treatment_plan,
                "follow_up_date": r.follow_up_date.strftime("%Y-%m-%d") if r.follow_up_date else None,
                "vitals_bp": r.vitals_bp,
                "vitals_pulse": r.vitals_pulse,
                "vitals_temp": str(r.vitals_temp) if r.vitals_temp else None,
                "vitals_spo2": r.vitals_spo2,
                "vitals_weight": str(r.vitals_weight) if r.vitals_weight else None,
                "vitals_height": str(r.vitals_height) if r.vitals_height else None,
                "appointment_id": r.appointment_id
            }
        })

    # 2. Diagnoses & ICD-10 Registry
    diagnoses = db.query(Diagnosis).filter(Diagnosis.patient_id == patient_id).all()
    for d in diagnoses:
        # Avoid duplicating consultation diagnosis if it has the exact same date and name
        timeline_events.append({
            "id": f"diagnosis-{d.id}",
            "entity_id": d.id,
            "type": "diagnosis",
            "date": d.diagnosed_date,
            "date_str": d.diagnosed_date.strftime("%Y-%m-%d"),
            "title": f"ICD-10 Diagnosis: {d.diagnosis_name}",
            "subtitle": f"Code: {d.diagnosis_code or 'N/A'} | Classification: {d.diagnosis_type}",
            "doctor_name": d.doctor.user.full_name if (d.doctor and d.doctor.user) else "Doctor",
            "badge_class": "badge-primary" if d.status == "Active" else "badge-neutral",
            "icon": "📋",
            "data": {
                "code": d.diagnosis_code,
                "name": d.diagnosis_name,
                "type": d.diagnosis_type,
                "status": d.status,
                "description": d.description
            }
        })

    # 3. Prescriptions (Rx)
    prescriptions = db.query(Prescription).filter(Prescription.patient_id == patient_id).all()
    for rx in prescriptions:
        rx_date = rx.created_at.date() if rx.created_at else date.today()
        items_summary = [f"{it.medicine.name} ({it.dosage}, {it.frequency} for {it.duration_days}d)" for it in rx.items if it.medicine]
        timeline_events.append({
            "id": f"prescription-{rx.id}",
            "entity_id": rx.id,
            "type": "prescription",
            "date": rx_date,
            "date_str": rx_date.strftime("%Y-%m-%d"),
            "title": f"Prescription: RX-#{rx.id}",
            "subtitle": f"Status: {rx.status.value.capitalize() if hasattr(rx.status, 'value') else rx.status}",
            "doctor_name": rx.doctor.user.full_name if (rx.doctor and rx.doctor.user) else "Doctor",
            "badge_class": "badge-success" if rx.status == "dispensed" else "badge-warning",
            "icon": "💊",
            "data": {
                "status": rx.status.value if hasattr(rx.status, "value") else str(rx.status),
                "notes": rx.notes,
                "items": items_summary,
                "rx_items": items_summary,
                "item_count": len(rx.items)
            }
        })

    # 4. Diagnostic Laboratory Orders
    lab_orders = db.query(LabOrder).filter(LabOrder.patient_id == patient_id).all()
    for lo in lab_orders:
        lo_date = lo.ordered_at.date() if lo.ordered_at else date.today()
        test_name = lo.test_type.name if lo.test_type else "Laboratory Test"
        timeline_events.append({
            "id": f"lab-{lo.id}",
            "entity_id": lo.id,
            "type": "lab_order",
            "date": lo_date,
            "date_str": lo_date.strftime("%Y-%m-%d"),
            "title": f"Lab Investigation: {test_name}",
            "subtitle": f"Order #{lo.id} | Status: {lo.status.value.capitalize() if hasattr(lo.status, 'value') else lo.status}",
            "doctor_name": lo.doctor.user.full_name if (lo.doctor and lo.doctor.user) else "Doctor",
            "badge_class": "badge-info",
            "icon": "🔬",
            "data": {
                "test_name": test_name,
                "test_code": lo.test_type.test_code if lo.test_type else "N/A",
                "status": lo.status.value if hasattr(lo.status, "value") else str(lo.status)
            }
        })

    # 5. Inpatient Admissions & Discharges
    admissions = db.query(Admission).filter(Admission.patient_id == patient_id).all()
    for adm in admissions:
        adm_date = adm.admission_date.date() if adm.admission_date else date.today()
        ward_name = adm.room.department.name if (adm.room and adm.room.department) else "General Ward"
        timeline_events.append({
            "id": f"admission-{adm.id}",
            "entity_id": adm.id,
            "type": "admission",
            "date": adm_date,
            "date_str": adm_date.strftime("%Y-%m-%d"),
            "title": f"Hospital Admission: {ward_name}",
            "subtitle": f"Bed: {adm.bed.bed_number if adm.bed else 'Bed Assigned'} | Status: {adm.status.capitalize()}",
            "doctor_name": adm.admitting_doctor.user.full_name if (adm.admitting_doctor and adm.admitting_doctor.user) else "Attending",
            "badge_class": "badge-danger" if adm.status == "admitted" else "badge-neutral",
            "icon": "🏥",
            "data": {
                "reason": adm.reason,
                "status": adm.status,
                "discharge_date": adm.discharge_date.strftime("%Y-%m-%d") if adm.discharge_date else "Active Inpatient",
                "ward": ward_name
            }
        })

    # Sort strictly chronological (most recent encounter first)
    timeline_events.sort(key=lambda x: x["date"], reverse=True)

    return {
        "patient": patient,
        "total_events": len(timeline_events),
        "events": timeline_events,
        "records_count": len(records),
        "diagnoses_count": len(diagnoses),
        "prescriptions_count": len(prescriptions),
        "lab_orders_count": len(lab_orders),
        "admissions_count": len(admissions)
    }


def get_medical_record_detail(
    db: Session,
    record_id: int,
    viewer_id: int,
    viewer_role: str
) -> MedicalRecord:
    """Fetches a single medical record with strict RBAC authorization."""
    record = db.query(MedicalRecord).filter(MedicalRecord.id == record_id).first()
    if not record:
        raise MedicalRecordNotFoundError(f"Medical Record ID {record_id} not found.")

    norm_role = viewer_role.lower().strip() if viewer_role else ""
    if norm_role == "patient" and viewer_id != record.patient_id:
        raise MedicalRecordPermissionError("Unauthorized: Patients may only view their own medical records.")

    return record
