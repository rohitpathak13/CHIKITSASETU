from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from datetime import datetime, date, timezone
from decimal import Decimal
from sqlalchemy import or_, desc

from core.database import db_session
from core.models import (
    Doctor, User, Department, Patient, PatientProfile,
    Appointment, MedicalRecord, Diagnosis, Prescription, PrescriptionItem,
    LabOrder, LabTestType, Medicine, Admission,
    RoleEnum, AppointmentStatusEnum, PrescriptionStatusEnum, LabOrderStatusEnum,
    AuditLog
)
from core.services.medical_record_service import (
    create_medical_record, update_medical_record, get_patient_medical_timeline,
    get_medical_record_detail, MedicalRecordServiceError, InvalidMedicalRecordDataError,
    MedicalRecordNotFoundError, MedicalRecordPermissionError
)
from core.services.prescription_service import (
    create_prescription, get_prescription_detail, list_prescriptions,
    PrescriptionServiceError, InvalidPrescriptionDataError,
    PrescriptionNotFoundError, PrescriptionPermissionError
)
from core.services.laboratory_service import (
    order_lab_tests, doctor_review_lab_result, list_lab_orders,
    get_lab_order_detail, LaboratoryServiceError, InvalidLabDataError,
    LabOrderNotFoundError, LabPermissionError, LabInvalidStateTransitionError
)
from web.decorators import login_required, roles_required, normalize_role
from ml.inference.predictors import readmission_predictor

doctor_bp = Blueprint("doctor", __name__, url_prefix="/doctor")


# =====================================================================
# 1. Doctor Dashboard (Today's, Pending, Completed Consultations)
# =====================================================================

@doctor_bp.route("/")
@login_required
@roles_required(RoleEnum.DOCTOR)
def dashboard():
    doctor_id = session.get("user_id")
    doctor = db_session.query(Doctor).filter(Doctor.id == doctor_id).first()

    # All appointments for this doctor
    all_appointments = db_session.query(Appointment).filter(
        Appointment.doctor_id == doctor_id
    ).order_by(Appointment.appointment_datetime.asc()).all()

    today = date.today()

    # Segment appointments
    today_appointments = [
        a for a in all_appointments
        if a.appointment_datetime and a.appointment_datetime.date() == today
    ]

    pending_appointments = [
        a for a in all_appointments
        if a.status in [AppointmentStatusEnum.SCHEDULED, AppointmentStatusEnum.CONFIRMED]
    ]

    completed_appointments = [
        a for a in all_appointments
        if a.status == AppointmentStatusEnum.COMPLETED
    ]

    today_completed = [a for a in today_appointments if a.status == AppointmentStatusEnum.COMPLETED]
    today_pending = [a for a in today_appointments if a.status in [AppointmentStatusEnum.SCHEDULED, AppointmentStatusEnum.CONFIRMED]]

    # Active inpatients admitted under this doctor
    admissions = db_session.query(Admission).filter(
        Admission.admitting_doctor_id == doctor_id,
        Admission.status == "admitted"
    ).order_by(Admission.admission_date.desc()).all()

    return render_template(
        "doctor/dashboard.html",
        active_page="doctor_dashboard",
        doctor=doctor,
        today_appointments=today_appointments,
        pending_appointments=pending_appointments,
        completed_appointments=completed_appointments,
        admissions=admissions,
        stats={
            "today_total": len(today_appointments),
            "today_completed": len(today_completed),
            "today_pending": len(today_pending),
            "total_pending": len(pending_appointments),
            "total_completed": len(completed_appointments),
            "inpatient_census": len(admissions)
        }
    )


# =====================================================================
# 2. Doctor Profile & Availability Management
# =====================================================================

@doctor_bp.route("/profile", methods=["GET", "POST"])
@login_required
@roles_required(RoleEnum.DOCTOR, RoleEnum.ADMIN)
def profile():
    doctor_id = session.get("user_id")
    doctor = db_session.query(Doctor).filter(Doctor.id == doctor_id).first()

    if not doctor:
        flash("Doctor profile not found.", "danger")
        return redirect(url_for("doctor.dashboard"))

    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        room_number = request.form.get("room_number", "").strip()
        qualification = request.form.get("qualification", "").strip()

        # Handle available days
        available_days_list = request.form.getlist("available_days")
        if not available_days_list:
            available_days_raw = request.form.get("available_days", "").strip()
            if available_days_raw:
                available_days_list = [d.strip() for d in available_days_raw.split(",") if d.strip()]

        # Validation
        if not qualification:
            flash("Medical qualification is required.", "danger")
            return render_template("doctor/profile.html", active_page="doctor_profile", doctor=doctor), 400

        valid_days = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
        cleaned_days = [d for d in available_days_list if d in valid_days]
        if not cleaned_days:
            flash("At least one valid available day must be selected (Mon-Sun).", "danger")
            return render_template("doctor/profile.html", active_page="doctor_profile", doctor=doctor), 400

        doctor.user.phone = phone or None
        doctor.room_number = room_number or None
        doctor.qualification = qualification
        doctor.available_days = ",".join(cleaned_days)

        # Consultation fee
        fee_str = request.form.get("consultation_fee")
        if fee_str:
            try:
                fee = Decimal(fee_str)
                if fee < 0:
                    flash("Consultation fee cannot be negative.", "danger")
                    return render_template("doctor/profile.html", active_page="doctor_profile", doctor=doctor), 400
                doctor.consultation_fee = fee
            except (ValueError, ArithmeticError):
                flash("Invalid consultation fee format.", "danger")
                return render_template("doctor/profile.html", active_page="doctor_profile", doctor=doctor), 400

        audit = AuditLog(
            user_id=doctor_id,
            action="DOCTOR_PROFILE_UPDATED",
            resource_type="Doctor",
            resource_id=doctor.id,
            ip_address=request.remote_addr,
            details_json=f'{{"doctor_id": {doctor.id}, "room": "{room_number}", "days": "{doctor.available_days}"}}'
        )
        db_session.add(audit)
        db_session.commit()

        flash("Doctor profile and availability schedule updated successfully.", "success")
        return redirect(url_for("doctor.profile"))

    # Convert available_days to list for template checkboxes
    current_days = set(doctor.available_days.split(",")) if doctor.available_days else set()

    return render_template(
        "doctor/profile.html",
        active_page="doctor_profile",
        doctor=doctor,
        current_days=current_days
    )


# =====================================================================
# 3. Appointment Schedule & Status Controls
# =====================================================================

@doctor_bp.route("/schedule", methods=["GET", "POST"])
@login_required
@roles_required(RoleEnum.DOCTOR, RoleEnum.ADMIN)
def schedule():
    doctor_id = session.get("user_id")
    doctor = db_session.query(Doctor).filter(Doctor.id == doctor_id).first()

    if request.method == "POST":
        appointment_id = request.form.get("appointment_id")
        new_status = request.form.get("status", "").strip().lower()

        appointment = db_session.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.doctor_id == doctor_id
        ).first()

        if not appointment:
            flash("Appointment not found or not assigned to you.", "danger")
            return redirect(url_for("doctor.schedule"))

        try:
            st_enum = AppointmentStatusEnum(new_status)
            appointment.status = st_enum

            audit = AuditLog(
                user_id=doctor_id,
                action="APPOINTMENT_STATUS_UPDATED",
                resource_type="Appointment",
                resource_id=appointment.id,
                ip_address=request.remote_addr,
                details_json=f'{{"appointment_id": {appointment.id}, "status": "{new_status}"}}'
            )
            db_session.add(audit)
            db_session.commit()
            flash(f"Appointment #{appointment.id} marked as {new_status}.", "success")
        except ValueError:
            flash("Invalid appointment status.", "danger")

        return redirect(url_for("doctor.schedule"))

    # Filters
    date_filter = request.args.get("date", "").strip()
    status_filter = request.args.get("status", "").strip().lower()

    query = db_session.query(Appointment).filter(Appointment.doctor_id == doctor_id)
    appointments = query.order_by(Appointment.appointment_datetime.asc()).all()

    filtered = appointments
    if date_filter and date_filter != "all":
        try:
            target_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
            filtered = [a for a in filtered if a.appointment_datetime and a.appointment_datetime.date() == target_date]
        except ValueError:
            pass
    elif not date_filter:
        # Default to today
        target_date = date.today()
        date_filter = target_date.strftime("%Y-%m-%d")
        filtered = [a for a in filtered if a.appointment_datetime and a.appointment_datetime.date() == target_date]

    if status_filter and status_filter != "all":
        filtered = [a for a in filtered if a.status.value == status_filter]

    return render_template(
        "doctor/schedule.html",
        active_page="doctor_schedule",
        doctor=doctor,
        appointments=filtered,
        date_filter=date_filter,
        status_filter=status_filter,
        today_date=date.today().strftime("%Y-%m-%d")
    )


# =====================================================================
# 4. Doctor Patients Roster (Outpatients & Inpatients)
# =====================================================================

@doctor_bp.route("/patients")
@login_required
@roles_required(RoleEnum.DOCTOR)
def my_patients():
    doctor_id = session.get("user_id")
    q = request.args.get("q", "").strip()
    patient_type = request.args.get("type", "all").strip().lower()

    # 1. Fetch distinct patient IDs associated with this doctor
    appt_pts = db_session.query(Appointment.patient_id).filter(Appointment.doctor_id == doctor_id).distinct().all()
    adm_pts = db_session.query(Admission.patient_id).filter(Admission.admitting_doctor_id == doctor_id).distinct().all()
    rec_pts = db_session.query(MedicalRecord.patient_id).filter(MedicalRecord.doctor_id == doctor_id).distinct().all()

    outpatient_ids = {r[0] for r in appt_pts} | {r[0] for r in rec_pts}
    inpatient_ids = {r[0] for r in adm_pts}
    all_ids = outpatient_ids | inpatient_ids

    if not all_ids:
        patients_data = []
    else:
        query = db_session.query(Patient).join(Patient.user).filter(Patient.id.in_(all_ids))

        if q:
            clean_q = q.upper().replace("PAT-", "").lstrip("0")
            id_filter = int(clean_q) if clean_q.isdigit() else -1
            query = query.filter(
                or_(
                    User.first_name.ilike(f"%{q}%"),
                    User.last_name.ilike(f"%{q}%"),
                    User.email.ilike(f"%{q}%"),
                    User.phone.ilike(f"%{q}%"),
                    Patient.blood_group.ilike(f"%{q}%"),
                    Patient.id == id_filter
                )
            )

        patients = query.order_by(Patient.id.desc()).all()

        patients_data = []
        for p in patients:
            is_inpatient = p.id in inpatient_ids
            is_outpatient = p.id in outpatient_ids

            if patient_type == "inpatient" and not is_inpatient:
                continue
            if patient_type == "outpatient" and not is_outpatient:
                continue

            # Latest appointment with this doctor
            latest_appt = db_session.query(Appointment).filter(
                Appointment.doctor_id == doctor_id,
                Appointment.patient_id == p.id
            ).order_by(Appointment.appointment_datetime.desc()).first()

            # Active admission if any
            active_adm = db_session.query(Admission).filter(
                Admission.admitting_doctor_id == doctor_id,
                Admission.patient_id == p.id,
                Admission.status == "admitted"
            ).first()

            patients_data.append({
                "patient": p,
                "is_inpatient": is_inpatient,
                "is_outpatient": is_outpatient,
                "active_admission": active_adm,
                "latest_appointment": latest_appt
            })

    # Active admissions for discharge modal actions
    admissions = db_session.query(Admission).filter(
        Admission.admitting_doctor_id == doctor_id
    ).order_by(Admission.admission_date.desc()).all()

    return render_template(
        "doctor/patients.html",
        active_page="doctor_patients",
        patients_data=patients_data,
        admissions=admissions,
        search_query=q,
        patient_type=patient_type
    )


# =====================================================================
# 5. Patient Longitudinal Medical History Access (Clinical RBAC)
# =====================================================================

@doctor_bp.route("/patient/<int:patient_id>/history")
@login_required
@roles_required(RoleEnum.DOCTOR, RoleEnum.ADMIN)
def patient_history(patient_id: int):
    doctor_id = session.get("user_id")
    user_role = normalize_role(session.get("user_role", ""))

    patient = db_session.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        flash("Patient chart not found.", "danger")
        return redirect(url_for("doctor.my_patients"))

    # Role permission check: Doctor must only access appropriate patient information
    # Doctor has access if doctor has treated or is scheduled to treat the patient
    if user_role != RoleEnum.ADMIN.value:
        has_appt = db_session.query(Appointment).filter(
            Appointment.doctor_id == doctor_id, Appointment.patient_id == patient_id
        ).first()
        has_adm = db_session.query(Admission).filter(
            Admission.admitting_doctor_id == doctor_id, Admission.patient_id == patient_id
        ).first()
        has_rec = db_session.query(MedicalRecord).filter(
            MedicalRecord.doctor_id == doctor_id, MedicalRecord.patient_id == patient_id
        ).first()
        has_rx = db_session.query(Prescription).filter(
            Prescription.doctor_id == doctor_id, Prescription.patient_id == patient_id
        ).first()

        if not (has_appt or has_adm or has_rec or has_rx):
            abort(403)

    today = date.today()
    age = today.year - patient.dob.year - ((today.month, today.day) < (patient.dob.month, patient.dob.day))

    # Longitudinal clinical history
    medical_records = db_session.query(MedicalRecord).filter(
        MedicalRecord.patient_id == patient_id
    ).order_by(MedicalRecord.visit_date.desc()).all()

    diagnoses = db_session.query(Diagnosis).filter(
        Diagnosis.patient_id == patient_id
    ).order_by(Diagnosis.diagnosed_date.desc()).all()

    prescriptions = db_session.query(Prescription).filter(
        Prescription.patient_id == patient_id
    ).order_by(Prescription.created_at.desc()).all()

    lab_orders = db_session.query(LabOrder).filter(
        LabOrder.patient_id == patient_id
    ).order_by(LabOrder.ordered_at.desc()).all()

    doctor_appointments = db_session.query(Appointment).filter(
        Appointment.patient_id == patient_id,
        Appointment.doctor_id == doctor_id
    ).order_by(Appointment.appointment_datetime.desc()).all()

    timeline_data = get_patient_medical_timeline(db_session, patient_id, doctor_id, user_role)

    return render_template(
        "doctor/patient_history.html",
        active_page="doctor_patients",
        patient=patient,
        age=age,
        medical_records=medical_records,
        diagnoses=diagnoses,
        prescriptions=prescriptions,
        lab_orders=lab_orders,
        doctor_appointments=doctor_appointments,
        timeline=timeline_data["events"],
        counts=timeline_data
    )


# =====================================================================
# 6. Consultation Encounter & Direct EMR Operations
# =====================================================================

@doctor_bp.route("/consultation/<int:appointment_id>", methods=["GET", "POST"])
@login_required
@roles_required(RoleEnum.DOCTOR)
def consultation(appointment_id: int):
    doctor_id = session.get("user_id")
    appointment = db_session.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.doctor_id == doctor_id
    ).first()

    if not appointment:
        flash("Appointment not found or not assigned to you.", "danger")
        return redirect(url_for("doctor.dashboard"))

    patient = appointment.patient
    medicines = db_session.query(Medicine).all()
    lab_tests = db_session.query(LabTestType).all()

    # Patient prior history
    prior_records = db_session.query(MedicalRecord).filter(
        MedicalRecord.patient_id == patient.user_id
    ).order_by(MedicalRecord.visit_date.desc()).all()

    # Calculate real-time ML Readmission Risk score for clinical decision support
    patient_age = max(1, (date.today() - patient.dob).days // 365)
    ml_eval = readmission_predictor.predict({
        "age": patient_age,
        "gender": patient.gender.value if hasattr(patient.gender, "value") else str(patient.gender),
        "previous_admissions_12m": len(patient.admissions),
        "chronic_conditions_count": 2 if patient.chronic_conditions else 0,
        "vital_instability_index": 0.20,
        "medication_count": 4
    })

    if request.method == "POST":
        symptoms = request.form.get("symptoms", "").strip()
        diagnosis = request.form.get("diagnosis", "").strip()
        clinical_notes = request.form.get("clinical_notes", "").strip()
        vitals_bp = request.form.get("vitals_bp", "").strip()
        vitals_pulse = request.form.get("vitals_pulse")
        vitals_temp = request.form.get("vitals_temp")
        vitals_spo2 = request.form.get("vitals_spo2")
        vitals_weight = request.form.get("vitals_weight")
        vitals_height = request.form.get("vitals_height")
        vitals_respiratory_rate = request.form.get("vitals_respiratory_rate")
        allergies = request.form.get("allergies", "").strip()
        treatment_plan = request.form.get("treatment_plan", "").strip()
        follow_up_date = request.form.get("follow_up_date")
        diag_code = request.form.get("diagnosis_code", "R69").strip()

        try:
            record = create_medical_record(
                db=db_session,
                patient_id=patient.user_id,
                doctor_id=doctor_id,
                symptoms=symptoms,
                diagnosis=diagnosis,
                clinical_notes=clinical_notes,
                vitals_bp=vitals_bp or None,
                vitals_pulse=int(vitals_pulse) if vitals_pulse else None,
                vitals_temp=Decimal(vitals_temp) if vitals_temp else None,
                vitals_spo2=int(vitals_spo2) if vitals_spo2 else None,
                vitals_weight=Decimal(vitals_weight) if vitals_weight else None,
                vitals_height=Decimal(vitals_height) if vitals_height else None,
                vitals_respiratory_rate=int(vitals_respiratory_rate) if vitals_respiratory_rate else None,
                allergies=allergies or None,
                treatment_plan=treatment_plan or None,
                follow_up_date=follow_up_date,
                appointment_id=appointment.id,
                diagnosis_code=diag_code,
                actor_id=doctor_id,
                ip_address=request.remote_addr
            )
        except (InvalidMedicalRecordDataError, MedicalRecordServiceError) as e:
            flash(str(e), "danger")
            return redirect(url_for("doctor.consultation", appointment_id=appointment.id))

        # Prescriptions: multi-medicine or single medicine parsing
        med_ids = request.form.getlist("medicine_id") or request.form.getlist("medicine_ids[]")
        dosages = request.form.getlist("dosage") or request.form.getlist("dosages[]")
        frequencies = request.form.getlist("frequency") or request.form.getlist("frequencies[]")
        durations = request.form.getlist("duration_days") or request.form.getlist("durations[]")
        quantities = request.form.getlist("qty_prescribed") or request.form.getlist("quantities[]")
        instructions_list = request.form.getlist("instructions") or request.form.getlist("instructions[]")

        rx_items = []
        for i in range(len(med_ids)):
            m_id = med_ids[i].strip() if i < len(med_ids) and med_ids[i] else None
            d_val = dosages[i].strip() if i < len(dosages) and dosages[i] else None
            if m_id and d_val:
                f_val = frequencies[i].strip() if i < len(frequencies) and frequencies[i] else "1-0-1"
                dur_val = durations[i].strip() if i < len(durations) and durations[i] else 5
                qty_val = quantities[i].strip() if i < len(quantities) and quantities[i] else 10
                inst_val = instructions_list[i].strip() if i < len(instructions_list) and instructions_list[i] else None
                rx_items.append({
                    "medicine_id": m_id,
                    "dosage": d_val,
                    "frequency": f_val,
                    "duration_days": dur_val,
                    "quantity_prescribed": qty_val,
                    "instructions": inst_val
                })

        if rx_items:
            try:
                create_prescription(
                    db_session=db_session,
                    doctor_id=doctor_id,
                    patient_id=patient.user_id,
                    items=rx_items,
                    medical_record_id=record.id,
                    notes=request.form.get("rx_notes", ""),
                    actor_id=doctor_id,
                    ip_address=request.remote_addr
                )
            except (InvalidPrescriptionDataError, PrescriptionServiceError) as e:
                flash(f"Prescription validation warning: {str(e)}", "warning")

        # Lab Orders if selected
        lab_test_id = request.form.get("lab_test_id")
        if lab_test_id:
            lab_order = LabOrder(
                patient_id=patient.user_id,
                doctor_id=doctor_id,
                medical_record_id=record.id,
                test_type_id=int(lab_test_id),
                status=LabOrderStatusEnum.ORDERED
            )
            db_session.add(lab_order)

        db_session.commit()
        flash(f"Clinical encounter finalized for {patient.user.full_name}. Medical Record #{record.id} generated.", "success")
        return redirect(url_for("doctor.dashboard"))

    return render_template(
        "doctor/consultation.html",
        active_page="doctor_dashboard",
        appointment=appointment,
        patient=patient,
        medicines=medicines,
        lab_tests=lab_tests,
        prior_records=prior_records,
        ml_eval=ml_eval,
        today_date=date.today().strftime("%Y-%m-%d")
    )


@doctor_bp.route("/patient/<int:patient_id>/record/new", methods=["GET", "POST"])
@login_required
@roles_required(RoleEnum.DOCTOR, RoleEnum.ADMIN)
def new_medical_record(patient_id: int):
    doctor_id = session.get("user_id")
    patient = db_session.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        flash("Patient chart not found.", "danger")
        return redirect(url_for("doctor.my_patients"))

    if request.method == "POST":
        symptoms = request.form.get("symptoms", "").strip()
        diagnosis = request.form.get("diagnosis", "").strip()
        clinical_notes = request.form.get("clinical_notes", "").strip()
        vitals_bp = request.form.get("vitals_bp", "").strip()
        vitals_pulse = request.form.get("vitals_pulse")
        vitals_temp = request.form.get("vitals_temp")
        vitals_spo2 = request.form.get("vitals_spo2")
        vitals_weight = request.form.get("vitals_weight")
        vitals_height = request.form.get("vitals_height")
        vitals_respiratory_rate = request.form.get("vitals_respiratory_rate")
        allergies = request.form.get("allergies", "").strip()
        treatment_plan = request.form.get("treatment_plan", "").strip()
        follow_up_date = request.form.get("follow_up_date")
        diagnosis_code = request.form.get("diagnosis_code", "R69").strip()

        try:
            record = create_medical_record(
                db=db_session,
                patient_id=patient_id,
                doctor_id=doctor_id,
                symptoms=symptoms,
                diagnosis=diagnosis,
                clinical_notes=clinical_notes,
                vitals_bp=vitals_bp or None,
                vitals_pulse=int(vitals_pulse) if vitals_pulse else None,
                vitals_temp=Decimal(vitals_temp) if vitals_temp else None,
                vitals_spo2=int(vitals_spo2) if vitals_spo2 else None,
                vitals_weight=Decimal(vitals_weight) if vitals_weight else None,
                vitals_height=Decimal(vitals_height) if vitals_height else None,
                vitals_respiratory_rate=int(vitals_respiratory_rate) if vitals_respiratory_rate else None,
                allergies=allergies or None,
                treatment_plan=treatment_plan or None,
                follow_up_date=follow_up_date,
                diagnosis_code=diagnosis_code,
                actor_id=doctor_id,
                ip_address=request.remote_addr
            )
            flash(f"Electronic Medical Record #{record.id} created successfully for {patient.user.full_name}.", "success")
            return redirect(url_for("doctor.patient_history", patient_id=patient.id))
        except (InvalidMedicalRecordDataError, MedicalRecordServiceError) as e:
            flash(str(e), "danger")

    return render_template(
        "doctor/record_create.html",
        active_page="doctor_patients",
        patient=patient,
        today_date=date.today().strftime("%Y-%m-%d")
    )


@doctor_bp.route("/record/<int:record_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required(RoleEnum.DOCTOR, RoleEnum.ADMIN)
def edit_medical_record(record_id: int):
    doctor_id = session.get("user_id")
    user_role = normalize_role(session.get("user_role", ""))
    record = db_session.query(MedicalRecord).filter(MedicalRecord.id == record_id).first()
    if not record:
        flash("Medical Record not found.", "danger")
        return redirect(url_for("doctor.dashboard"))

    if user_role != RoleEnum.ADMIN.value and record.doctor_id != doctor_id:
        abort(403)

    if request.method == "POST":
        symptoms = request.form.get("symptoms", "").strip()
        diagnosis = request.form.get("diagnosis", "").strip()
        clinical_notes = request.form.get("clinical_notes", "").strip()
        vitals_bp = request.form.get("vitals_bp", "").strip()
        vitals_pulse = request.form.get("vitals_pulse")
        vitals_temp = request.form.get("vitals_temp")
        vitals_spo2 = request.form.get("vitals_spo2")
        vitals_weight = request.form.get("vitals_weight")
        vitals_height = request.form.get("vitals_height")
        vitals_respiratory_rate = request.form.get("vitals_respiratory_rate")
        allergies = request.form.get("allergies", "").strip()
        treatment_plan = request.form.get("treatment_plan", "").strip()
        follow_up_date = request.form.get("follow_up_date")
        change_reason = request.form.get("change_reason", "").strip()

        try:
            update_medical_record(
                db=db_session,
                record_id=record_id,
                actor_id=doctor_id,
                actor_role=user_role,
                symptoms=symptoms,
                diagnosis=diagnosis,
                clinical_notes=clinical_notes,
                vitals_bp=vitals_bp,
                vitals_pulse=int(vitals_pulse) if vitals_pulse else None,
                vitals_temp=Decimal(vitals_temp) if vitals_temp else None,
                vitals_spo2=int(vitals_spo2) if vitals_spo2 else None,
                vitals_weight=Decimal(vitals_weight) if vitals_weight else None,
                vitals_height=Decimal(vitals_height) if vitals_height else None,
                vitals_respiratory_rate=int(vitals_respiratory_rate) if vitals_respiratory_rate else None,
                allergies=allergies,
                treatment_plan=treatment_plan,
                follow_up_date=follow_up_date,
                change_reason=change_reason,
                ip_address=request.remote_addr
            )
            flash(f"Medical Record #{record.id} updated successfully.", "success")
            return redirect(url_for("doctor.patient_history", patient_id=record.patient_id))
        except (InvalidMedicalRecordDataError, MedicalRecordServiceError) as e:
            flash(str(e), "danger")

    return render_template(
        "doctor/record_edit.html",
        active_page="doctor_patients",
        record=record,
        patient=record.patient,
        today_date=date.today().strftime("%Y-%m-%d")
    )


@doctor_bp.route("/admission/<int:admission_id>/discharge", methods=["POST"])
@login_required
@roles_required(RoleEnum.DOCTOR, RoleEnum.ADMIN)
def discharge_patient(admission_id: int):
    from core.services.discharge_billing import process_inpatient_discharge_and_billing

    summary = request.form.get("discharge_summary", "").strip()
    try:
        adm, invoice = process_inpatient_discharge_and_billing(
            admission_id=admission_id,
            discharge_summary=summary,
            db=db_session,
            actor_id=session.get("user_id"),
            ip_address=request.remote_addr
        )
        db_session.commit()
        flash(
            f"Patient {adm.patient.user.full_name} discharged successfully. "
            f"Consolidated Invoice #{invoice.invoice_number} created (Total: ${float(invoice.total_amount):.2f}).",
            "success"
        )
    except Exception as e:
        db_session.rollback()
        flash(f"Discharge error: {str(e)}", "danger")

    return redirect(url_for("doctor.my_patients"))


# =====================================================================
# 7. Prescription Management Routes for Doctors
# =====================================================================

@doctor_bp.route("/patient/<int:patient_id>/prescription/new", methods=["GET", "POST"])
@login_required
@roles_required(RoleEnum.DOCTOR, RoleEnum.ADMIN)
def new_prescription(patient_id: int):
    """
    Allows a doctor to create an electronic prescription with one or multiple medications.
    Enforces strict physiological limits (1-365 days duration, 1-1000 units quantity).
    """
    patient = db_session.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        # Check if patient_id refers to user_id
        patient = db_session.query(Patient).filter(Patient.user_id == patient_id).first()
    if not patient:
        flash("Patient not found.", "danger")
        return redirect(url_for("doctor.my_patients"))

    medicines = db_session.query(Medicine).order_by(Medicine.name.asc()).all()
    doctor_id = session.get("user_id")

    if request.method == "POST":
        med_ids = request.form.getlist("medicine_id") or request.form.getlist("medicine_ids[]")
        dosages = request.form.getlist("dosage") or request.form.getlist("dosages[]")
        frequencies = request.form.getlist("frequency") or request.form.getlist("frequencies[]")
        durations = request.form.getlist("duration_days") or request.form.getlist("durations[]")
        quantities = request.form.getlist("qty_prescribed") or request.form.getlist("quantities[]")
        instructions_list = request.form.getlist("instructions") or request.form.getlist("instructions[]")
        notes = request.form.get("rx_notes", "").strip()

        items = []
        for i in range(len(med_ids)):
            m_id = med_ids[i].strip() if i < len(med_ids) and med_ids[i] else None
            d_val = dosages[i].strip() if i < len(dosages) and dosages[i] else None
            if m_id and d_val:
                f_val = frequencies[i].strip() if i < len(frequencies) and frequencies[i] else "1-0-1"
                dur_val = durations[i].strip() if i < len(durations) and durations[i] else 5
                qty_val = quantities[i].strip() if i < len(quantities) and quantities[i] else 10
                inst_val = instructions_list[i].strip() if i < len(instructions_list) and instructions_list[i] else None
                items.append({
                    "medicine_id": m_id,
                    "dosage": d_val,
                    "frequency": f_val,
                    "duration_days": dur_val,
                    "quantity_prescribed": qty_val,
                    "instructions": inst_val
                })

        # Fetch latest medical record for patient if exists
        latest_rec = db_session.query(MedicalRecord).filter(
            MedicalRecord.patient_id == patient.user_id
        ).order_by(desc(MedicalRecord.created_at)).first()
        med_rec_id = latest_rec.id if latest_rec else None

        try:
            rx = create_prescription(
                db_session=db_session,
                doctor_id=doctor_id,
                patient_id=patient.user_id,
                items=items,
                medical_record_id=med_rec_id,
                notes=notes,
                actor_id=doctor_id,
                ip_address=request.remote_addr
            )
            flash(f"Prescription #{rx.id} successfully created with {len(rx.items)} medication(s).", "success")
            return redirect(url_for("doctor.patient_history", patient_id=patient.id))
        except (InvalidPrescriptionDataError, PrescriptionServiceError) as e:
            flash(str(e), "danger")

    return render_template(
        "doctor/prescription_create.html",
        active_page="doctor_patients",
        patient=patient,
        medicines=medicines
    )


@doctor_bp.route("/prescription/<int:rx_id>")
@login_required
@roles_required(RoleEnum.DOCTOR, RoleEnum.ADMIN)
def prescription_detail(rx_id: int):
    """
    Renders detailed clinical view of an electronic prescription order.
    """
    try:
        rx = get_prescription_detail(
            db_session=db_session,
            prescription_id=rx_id,
            requester_user_id=session.get("user_id"),
            requester_role=session.get("user_role")
        )
    except PrescriptionNotFoundError:
        flash("Prescription not found.", "danger")
        return redirect(url_for("doctor.dashboard"))
    except PrescriptionPermissionError as e:
        flash(str(e), "danger")
        return redirect(url_for("doctor.dashboard"))

    return render_template(
        "patient/prescription_detail.html",
        active_page="doctor_patients",
        rx=rx,
        is_doctor_view=True
    )


@doctor_bp.route("/prescriptions")
@login_required
@roles_required(RoleEnum.DOCTOR, RoleEnum.ADMIN)
def prescriptions_list():
    """
    Lists electronic prescriptions authored by the doctor with status filtering.
    """
    status_filter = request.args.get("status", "all")
    search = request.args.get("q", "").strip()
    doctor_id = session.get("user_id")

    # If admin, show all, else filter by current doctor
    doc_filter_id = None if session.get("user_role") == "admin" else doctor_id
    rxs = list_prescriptions(
        db_session=db_session,
        doctor_id=doc_filter_id,
        status=status_filter if status_filter != "all" else None,
        search=search if search else None
    )

    return render_template(
        "doctor/prescriptions_list.html",
        active_page="doctor_prescriptions",
        prescriptions=rxs,
        current_status=status_filter,
        search_query=search
    )


# =====================================================================
# 11. Clinical Laboratory Orders & Diagnostic Review
# =====================================================================

@doctor_bp.route("/patient/<int:patient_id>/lab-order", methods=["GET", "POST"])
@login_required
@roles_required(RoleEnum.DOCTOR, RoleEnum.ADMIN)
def order_lab_test(patient_id: int):
    """
    Physician orders diagnostic laboratory investigations for an outpatient or inpatient.
    """
    doctor_id = session.get("user_id")
    user_role = session.get("user_role")

    patient = db_session.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        flash("Patient not found.", "danger")
        return redirect(url_for("doctor.my_patients"))

    available_tests = db_session.query(LabTestType).order_by(LabTestType.name.asc()).all()

    if request.method == "POST":
        test_ids_raw = request.form.getlist("test_ids")
        priority = request.form.get("priority", "routine").strip().lower()
        clinical_notes = request.form.get("clinical_notes", "").strip()
        med_rec_id = request.form.get("medical_record_id")

        if not test_ids_raw:
            flash("Please select at least one diagnostic test to order.", "warning")
            return render_template(
                "doctor/lab_order_create.html",
                active_page="doctor_patients",
                patient=patient,
                tests=available_tests
            )

        try:
            test_ids = [int(tid) for tid in test_ids_raw]
            created_orders = order_lab_tests(
                db_session=db_session,
                patient_id=patient.id,
                doctor_id=doctor_id,
                test_ids=test_ids,
                medical_record_id=int(med_rec_id) if med_rec_id and med_rec_id.isdigit() else None,
                priority=priority,
                clinical_notes=clinical_notes if clinical_notes else None,
                ordering_user_id=doctor_id,
                user_role=user_role
            )
            flash(f"Successfully ordered {len(created_orders)} diagnostic test(s) for {patient.user.full_name}.", "success")
            return redirect(url_for("doctor.lab_orders"))
        except (InvalidLabDataError, LabPermissionError) as e:
            flash(str(e), "danger")

    return render_template(
        "doctor/lab_order_create.html",
        active_page="doctor_patients",
        patient=patient,
        tests=available_tests
    )


@doctor_bp.route("/lab-orders")
@login_required
@roles_required(RoleEnum.DOCTOR, RoleEnum.ADMIN)
def lab_orders():
    """
    Doctor's diagnostic workbench: review ordered investigations,
    track turnaround, inspect abnormal/critical values, and sign off findings.
    """
    doctor_id = session.get("user_id")
    user_role = session.get("user_role")

    status_filter = request.args.get("status", "all").strip().lower()
    search_q = request.args.get("q", "").strip()
    unreviewed_only = (status_filter == "unreviewed")

    # If admin, show all; if doctor, filter to their ordered tests
    doc_filter_id = None if user_role == "admin" else doctor_id

    # Retrieve all doctor's orders for metric counts
    all_doc_orders = db_session.query(LabOrder)
    if doc_filter_id:
        all_doc_orders = all_doc_orders.filter(LabOrder.doctor_id == doc_filter_id)
    all_doc_orders = all_doc_orders.all()

    counts = {
        "all": len(all_doc_orders),
        "unreviewed": sum(1 for o in all_doc_orders if o.status == LabOrderStatusEnum.COMPLETED and not o.doctor_reviewed),
        "ordered": sum(1 for o in all_doc_orders if o.status == LabOrderStatusEnum.ORDERED),
        "in_progress": sum(1 for o in all_doc_orders if o.status in [LabOrderStatusEnum.SAMPLE_COLLECTED, LabOrderStatusEnum.PROCESSING]),
        "completed": sum(1 for o in all_doc_orders if o.status == LabOrderStatusEnum.COMPLETED),
        "cancelled": sum(1 for o in all_doc_orders if o.status == LabOrderStatusEnum.CANCELLED)
    }

    orders = list_lab_orders(
        db_session=db_session,
        status_filter=None if unreviewed_only or status_filter == "all" else status_filter,
        doctor_id=doc_filter_id,
        search_query=search_q if search_q else None,
        unreviewed_only=unreviewed_only
    )

    return render_template(
        "doctor/lab_orders.html",
        active_page="doctor_lab_orders",
        orders=orders,
        status_filter=status_filter,
        search_q=search_q,
        counts=counts
    )


@doctor_bp.route("/lab-orders/<int:order_id>/review", methods=["POST"])
@login_required
@roles_required(RoleEnum.DOCTOR, RoleEnum.ADMIN)
def review_lab_result(order_id: int):
    """
    Physician reviews pathology findings, enters clinical assessment remarks,
    and signs off on completed report.
    """
    doctor_id = session.get("user_id")
    user_role = session.get("user_role")
    review_notes = request.form.get("review_notes", "").strip()

    try:
        order = doctor_review_lab_result(
            db_session=db_session,
            order_id=order_id,
            doctor_id=doctor_id,
            review_notes=review_notes if review_notes else None,
            user_role=user_role
        )
        flash(f"Clinical review signed off for Order #{order.id} ({order.test.name}). Patient notified.", "success")
    except (LabOrderNotFoundError, LabInvalidStateTransitionError, LabPermissionError) as e:
        flash(str(e), "danger")

    return redirect(url_for("doctor.lab_orders"))

