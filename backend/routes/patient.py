import math
from datetime import datetime, date, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from sqlalchemy import or_, desc

from backend.database import db_session
from backend.models import (
    User, Patient, PatientProfile, RoleEnum, GenderEnum,
    Appointment, MedicalRecord, Diagnosis, Prescription,
    LabOrder, Bill, Invoice, AuditLog
)
from backend.services.medical_record_service import (
    get_patient_medical_timeline, get_medical_record_detail,
    MedicalRecordPermissionError, MedicalRecordNotFoundError
)
from backend.services.prescription_service import (
    get_prescription_detail, PrescriptionPermissionError, PrescriptionNotFoundError
)
from backend.services.laboratory_service import (
    get_lab_order_detail, list_lab_orders, get_patient_lab_history,
    LabPermissionError, LabOrderNotFoundError
)
from backend.security import get_password_hash
from backend.utils.decorators import login_required, roles_required, normalize_role

patient_bp = Blueprint("patient", __name__, url_prefix="/patient")

STAFF_PATIENT_MANAGERS = {
    RoleEnum.ADMIN.value,
    RoleEnum.DOCTOR.value,
    RoleEnum.RECEPTIONIST.value,
    RoleEnum.NURSE.value
}

STAFF_PATIENT_EDITORS = {
    RoleEnum.ADMIN.value,
    RoleEnum.RECEPTIONIST.value,
    RoleEnum.DOCTOR.value
}


def paginate(query, page: int = 1, per_page: int = 10):
    """Simple query pagination helper."""
    total = query.count()
    pages = max(1, math.ceil(total / per_page)) if total > 0 else 1
    page = max(1, min(page, pages))
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return items, total, page, pages


# =====================================================================
# 1. Staff Patient Management: Directory (Search, Filter, Pagination)
# =====================================================================

@patient_bp.route("/directory")
@login_required
@roles_required(RoleEnum.ADMIN, RoleEnum.DOCTOR, RoleEnum.RECEPTIONIST, RoleEnum.NURSE)
def directory():
    q = request.args.get("q", "").strip()
    gender_filter = request.args.get("gender", "").strip().lower()
    blood_filter = request.args.get("blood_group", "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    query = db_session.query(Patient).join(Patient.user)

    if q:
        # Support MRN search e.g. "PAT-00005" or numeric "5"
        clean_q = q.upper().replace("PAT-", "").lstrip("0")
        id_filter = int(clean_q) if clean_q.isdigit() else -1

        search_fmt = f"%{q}%"
        query = query.filter(
            or_(
                User.first_name.ilike(search_fmt),
                User.last_name.ilike(search_fmt),
                User.email.ilike(search_fmt),
                User.phone.ilike(search_fmt),
                Patient.blood_group.ilike(search_fmt),
                Patient.id == id_filter
            )
        )

    if gender_filter:
        try:
            g_enum = GenderEnum(gender_filter)
            query = query.filter(Patient.gender == g_enum)
        except ValueError:
            pass

    if blood_filter:
        query = query.filter(Patient.blood_group == blood_filter)

    query = query.order_by(Patient.id.desc())
    patients, total, page, pages = paginate(query, page=page, per_page=10)

    return render_template(
        "patient/directory.html",
        active_page="patient_directory",
        patients=patients,
        total=total,
        page=page,
        pages=pages,
        q=q,
        gender_filter=gender_filter,
        blood_filter=blood_filter
    )


# =====================================================================
# 2. Staff Patient Registration
# =====================================================================

@patient_bp.route("/register", methods=["GET", "POST"])
@login_required
@roles_required(RoleEnum.ADMIN, RoleEnum.RECEPTIONIST, RoleEnum.DOCTOR)
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "").strip()
        if not password:
            import secrets
            password = secrets.token_urlsafe(12) + "A1!"
        elif len(password) < 8:
            flash("Password must be at least 8 characters long.", "danger")
            return render_template("patient/register.html", active_page="patient_directory"), 400
        dob_str = request.form.get("dob", "").strip()
        gender_str = request.form.get("gender", "other").strip().lower()
        blood_group = request.form.get("blood_group", "").strip()
        emergency_name = request.form.get("emergency_contact_name", "").strip()
        emergency_phone = request.form.get("emergency_contact_phone", "").strip()
        address = request.form.get("address", "").strip()
        allergies = request.form.get("allergies", "").strip()
        chronic = request.form.get("chronic_conditions", "").strip()

        # Validations
        if not email or "@" not in email:
            flash("A valid email address is required.", "danger")
            return render_template("patient/register.html", active_page="patient_directory"), 400

        if not first_name or not last_name:
            flash("First and last names are required.", "danger")
            return render_template("patient/register.html", active_page="patient_directory"), 400

        if not dob_str:
            flash("Date of birth is required.", "danger")
            return render_template("patient/register.html", active_page="patient_directory"), 400

        try:
            dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
            if dob > date.today():
                flash("Date of birth cannot be in the future.", "danger")
                return render_template("patient/register.html", active_page="patient_directory"), 400
        except ValueError:
            flash("Invalid date format for date of birth.", "danger")
            return render_template("patient/register.html", active_page="patient_directory"), 400

        existing_user = db_session.query(User).filter(User.email == email).first()
        if existing_user:
            flash(f"An account with email '{email}' already exists.", "danger")
            return render_template("patient/register.html", active_page="patient_directory"), 400

        try:
            gender_enum = GenderEnum(gender_str)
        except ValueError:
            gender_enum = GenderEnum.OTHER

        # Create user
        new_user = User(
            email=email,
            password_hash=get_password_hash(password),
            role=RoleEnum.PATIENT,
            first_name=first_name,
            last_name=last_name,
            phone=phone or None,
            is_active=True
        )
        db_session.add(new_user)
        db_session.flush()

        # Create patient record
        patient = Patient(
            id=new_user.id,
            dob=dob,
            gender=gender_enum,
            blood_group=blood_group or None,
            emergency_contact_name=emergency_name or None,
            emergency_contact_phone=emergency_phone or None,
            address=address or None,
            allergies=allergies or None,
            chronic_conditions=chronic or None
        )
        db_session.add(patient)

        # Audit log
        audit = AuditLog(
            user_id=session.get("user_id"),
            action="PATIENT_REGISTERED",
            resource_type="Patient",
            resource_id=patient.id,
            ip_address=request.remote_addr,
            details_json=f'{{"patient_id": {patient.id}, "name": "{new_user.full_name}", "email": "{email}"}}'
        )
        db_session.add(audit)
        db_session.commit()

        flash(f"Patient {new_user.full_name} (MRN: PAT-{patient.id:05d}) registered successfully.", "success")
        return redirect(url_for("patient.patient_detail", patient_id=patient.id))

    return render_template("patient/register.html", active_page="patient_directory")


# =====================================================================
# 3. 360-Degree Comprehensive Patient Detail View
# =====================================================================

@patient_bp.route("/<int:patient_id>")
@login_required
def patient_detail(patient_id: int):
    user_role = normalize_role(session.get("user_role", ""))
    logged_in_user_id = session.get("user_id")

    # Role permission check:
    # 1. Staff (Admin, Doctor, Receptionist, Nurse) can view any patient
    # 2. Patient can view only their own record (patient_id == logged_in_user_id)
    # 3. All others blocked with 403
    if user_role == RoleEnum.PATIENT.value:
        if logged_in_user_id != patient_id:
            abort(403)
    elif user_role not in STAFF_PATIENT_MANAGERS:
        abort(403)

    patient = db_session.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        flash("Patient record not found.", "danger")
        if user_role == RoleEnum.PATIENT.value:
            return redirect(url_for("patient.dashboard"))
        return redirect(url_for("patient.directory"))

    # Compute patient age
    today = date.today()
    age = today.year - patient.dob.year - ((today.month, today.day) < (patient.dob.month, patient.dob.day))

    # 1. Medical History (Medical Records + Diagnoses)
    medical_records = db_session.query(MedicalRecord).filter(
        MedicalRecord.patient_id == patient_id
    ).order_by(MedicalRecord.visit_date.desc()).all()

    diagnoses = db_session.query(Diagnosis).filter(
        Diagnosis.patient_id == patient_id
    ).order_by(Diagnosis.diagnosed_date.desc()).all()

    # 2. Appointment History
    appointments = db_session.query(Appointment).filter(
        Appointment.patient_id == patient_id
    ).order_by(Appointment.appointment_datetime.desc()).all()

    # 3. Prescription History
    prescriptions = db_session.query(Prescription).filter(
        Prescription.patient_id == patient_id
    ).order_by(Prescription.created_at.desc()).all()

    # 4. Lab Report History
    lab_orders = db_session.query(LabOrder).filter(
        LabOrder.patient_id == patient_id
    ).order_by(LabOrder.ordered_at.desc()).all()

    # 5. Billing History
    bills = db_session.query(Bill).filter(
        Bill.patient_id == patient_id
    ).order_by(Bill.created_at.desc()).all()

    total_billed = sum(float(b.total_amount) for b in bills)
    total_paid = sum(b.amount_paid for b in bills)
    outstanding_balance = max(0.0, total_billed - total_paid)

    return render_template(
        "patient/detail.html",
        active_page="patient_dashboard" if user_role == RoleEnum.PATIENT.value else "patient_directory",
        patient=patient,
        age=age,
        medical_records=medical_records,
        diagnoses=diagnoses,
        appointments=appointments,
        prescriptions=prescriptions,
        lab_orders=lab_orders,
        bills=bills,
        total_billed=round(total_billed, 2),
        total_paid=round(total_paid, 2),
        outstanding_balance=round(outstanding_balance, 2),
        user_role=user_role
    )


# =====================================================================
# 4. Edit Patient Details
# =====================================================================

@patient_bp.route("/<int:patient_id>/edit", methods=["GET", "POST"])
@login_required
def edit_patient(patient_id: int):
    user_role = normalize_role(session.get("user_role", ""))
    logged_in_user_id = session.get("user_id")

    # Authorization:
    # 1. Staff with edit permissions (Admin, Receptionist, Doctor)
    # 2. Patient editing their own profile
    if user_role == RoleEnum.PATIENT.value:
        if logged_in_user_id != patient_id:
            abort(403)
    elif user_role not in STAFF_PATIENT_EDITORS:
        abort(403)

    patient = db_session.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        flash("Patient not found.", "danger")
        return redirect(url_for("patient.directory"))

    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        phone = request.form.get("phone", "").strip()
        blood_group = request.form.get("blood_group", "").strip()
        emergency_name = request.form.get("emergency_contact_name", "").strip()
        emergency_phone = request.form.get("emergency_contact_phone", "").strip()
        address = request.form.get("address", "").strip()
        allergies = request.form.get("allergies", "").strip()
        chronic = request.form.get("chronic_conditions", "").strip()

        if first_name and last_name:
            patient.user.first_name = first_name
            patient.user.last_name = last_name

        patient.user.phone = phone or None
        patient.blood_group = blood_group or None
        patient.emergency_contact_name = emergency_name or None
        patient.emergency_contact_phone = emergency_phone or None
        patient.address = address or None
        patient.allergies = allergies or None
        patient.chronic_conditions = chronic or None

        # Allow staff to update DOB / gender if provided
        if user_role in STAFF_PATIENT_EDITORS:
            dob_str = request.form.get("dob", "").strip()
            if dob_str:
                try:
                    patient.dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
                except ValueError:
                    pass
            gender_str = request.form.get("gender", "").strip().lower()
            if gender_str:
                try:
                    patient.gender = GenderEnum(gender_str)
                except ValueError:
                    pass

        # Audit log
        audit = AuditLog(
            user_id=logged_in_user_id,
            action="PATIENT_EDITED",
            resource_type="Patient",
            resource_id=patient.id,
            ip_address=request.remote_addr,
            details_json=f'{{"patient_id": {patient.id}, "updated_by_role": "{user_role}"}}'
        )
        db_session.add(audit)
        db_session.commit()

        flash(f"Patient profile for {patient.user.full_name} updated successfully.", "success")
        return redirect(url_for("patient.patient_detail", patient_id=patient.id))

    return render_template(
        "patient/edit.html",
        active_page="patient_dashboard" if user_role == RoleEnum.PATIENT.value else "patient_directory",
        patient=patient,
        user_role=user_role
    )


# =====================================================================
# 5. Patient Self-Service Profile Shortcuts
# =====================================================================

@patient_bp.route("/profile")
@login_required
@roles_required(RoleEnum.PATIENT)
def profile():
    patient_id = session.get("user_id")
    return redirect(url_for("patient.patient_detail", patient_id=patient_id))


# =====================================================================
# 6. Patient Portal Personal History Endpoints
# =====================================================================

@patient_bp.route("/")
@login_required
@roles_required(RoleEnum.PATIENT)
def dashboard():
    patient_id = session.get("user_id")
    profile_record = db_session.query(PatientProfile).filter(PatientProfile.user_id == patient_id).first()
    appointments = db_session.query(Appointment).filter(
        Appointment.patient_id == patient_id
    ).order_by(Appointment.appointment_datetime.asc()).limit(5).all()
    records = db_session.query(MedicalRecord).filter(
        MedicalRecord.patient_id == patient_id
    ).order_by(MedicalRecord.visit_date.desc()).limit(3).all()
    invoices = db_session.query(Invoice).filter(
        Invoice.patient_id == patient_id
    ).order_by(Invoice.created_at.desc()).limit(3).all()

    return render_template(
        "patient/dashboard.html",
        active_page="patient_dashboard",
        profile=profile_record,
        appointments=appointments,
        records=records,
        invoices=invoices
    )


@patient_bp.route("/appointments")
@login_required
@roles_required(RoleEnum.PATIENT)
def appointments():
    patient_id = session.get("user_id")
    appts = db_session.query(Appointment).filter(
        Appointment.patient_id == patient_id
    ).order_by(Appointment.appointment_datetime.desc()).all()
    return render_template("patient/appointments.html", active_page="patient_appointments", appointments=appts)


@patient_bp.route("/records")
@login_required
@roles_required(RoleEnum.PATIENT)
def records():
    patient_id = session.get("user_id")
    timeline_data = get_patient_medical_timeline(
        db=db_session,
        patient_id=patient_id,
        viewer_id=patient_id,
        viewer_role=RoleEnum.PATIENT.value
    )
    return render_template(
        "patient/records.html",
        active_page="patient_records",
        patient=timeline_data["patient"],
        timeline=timeline_data["events"],
        total_events=timeline_data["total_events"],
        counts=timeline_data
    )


@patient_bp.route("/records/<int:record_id>")
@login_required
@roles_required(RoleEnum.PATIENT)
def record_detail(record_id: int):
    patient_id = session.get("user_id")
    try:
        record = get_medical_record_detail(
            db=db_session,
            record_id=record_id,
            viewer_id=patient_id,
            viewer_role=RoleEnum.PATIENT.value
        )
        return render_template("patient/record_detail.html", active_page="patient_records", record=record)
    except MedicalRecordPermissionError:
        abort(403)
    except MedicalRecordNotFoundError:
        flash("Medical Record not found.", "danger")
        return redirect(url_for("patient.records"))


@patient_bp.route("/prescriptions")
@login_required
@roles_required(RoleEnum.PATIENT)
def prescriptions():
    patient_id = session.get("user_id")
    status_filter = request.args.get("status", "all")

    query = db_session.query(Prescription).filter(Prescription.patient_id == patient_id)
    if status_filter and status_filter.lower() != "all":
        query = query.filter(Prescription.status == status_filter.lower())

    all_rxs = db_session.query(Prescription).filter(Prescription.patient_id == patient_id).all()
    filtered_rxs = query.order_by(Prescription.created_at.desc()).all()

    total_count = len(all_rxs)
    dispensed_count = sum(1 for r in all_rxs if r.status.value == "dispensed")
    pending_count = sum(1 for r in all_rxs if r.status.value in ["pending", "partially_dispensed"])

    return render_template(
        "patient/prescriptions.html",
        active_page="patient_prescriptions",
        prescriptions=filtered_rxs,
        current_status=status_filter,
        total_count=total_count,
        dispensed_count=dispensed_count,
        pending_count=pending_count
    )


@patient_bp.route("/prescriptions/<int:rx_id>")
@login_required
@roles_required(RoleEnum.PATIENT)
def prescription_detail(rx_id: int):
    """
    Renders printable patient prescription slip.
    Enforces strict role-based confidentiality (403 Forbidden for another patient).
    """
    patient_id = session.get("user_id")
    try:
        rx = get_prescription_detail(
            db_session=db_session,
            prescription_id=rx_id,
            requester_user_id=patient_id,
            requester_role="patient"
        )
    except PrescriptionNotFoundError:
        flash("Prescription not found.", "danger")
        return redirect(url_for("patient.prescriptions"))
    except PrescriptionPermissionError:
        abort(403)

    return render_template(
        "patient/prescription_detail.html",
        active_page="patient_prescriptions",
        rx=rx,
        is_doctor_view=False
    )


@patient_bp.route("/billing")
@login_required
@roles_required(RoleEnum.PATIENT)
def billing():
    patient_id = session.get("user_id")
    invs = db_session.query(Invoice).filter(
        Invoice.patient_id == patient_id
    ).order_by(Invoice.created_at.desc()).all()
    return render_template("patient/billing.html", active_page="patient_billing", invoices=invs)


# =====================================================================
# 7. Patient Portal Diagnostic Laboratory Reports
# =====================================================================

@patient_bp.route("/labs")
@login_required
@roles_required(RoleEnum.PATIENT)
def lab_reports():
    """
    Patient Portal: lists all laboratory investigations ordered for the authenticated patient.
    Provides status filtering and abnormal indicator visibility.
    """
    patient_id = session.get("user_id")
    status_filter = request.args.get("status", "all").strip().lower()

    all_orders = get_patient_lab_history(db_session=db_session, patient_id=patient_id)

    total_count = len(all_orders)
    completed_count = sum(1 for o in all_orders if o.status.value == "completed")
    in_progress_count = sum(1 for o in all_orders if o.status.value in ["ordered", "sample_collected", "processing"])

    if status_filter == "completed":
        filtered_orders = [o for o in all_orders if o.status.value == "completed"]
    elif status_filter == "pending":
        filtered_orders = [o for o in all_orders if o.status.value in ["ordered", "sample_collected", "processing"]]
    elif status_filter == "cancelled":
        filtered_orders = [o for o in all_orders if o.status.value == "cancelled"]
    else:
        filtered_orders = all_orders

    return render_template(
        "patient/lab_reports.html",
        active_page="patient_labs",
        orders=filtered_orders,
        current_status=status_filter,
        total_count=total_count,
        completed_count=completed_count,
        in_progress_count=in_progress_count
    )


@patient_bp.route("/labs/<int:order_id>")
@login_required
@roles_required(RoleEnum.PATIENT, RoleEnum.DOCTOR, RoleEnum.ADMIN, RoleEnum.LAB_TECH)
def lab_report_detail(order_id: int):
    """
    Renders standardized, printable pathology report.
    Strictly verifies patient ownership (returns 403 if patient attempts to view another's report).
    """
    viewer_id = session.get("user_id")
    viewer_role = session.get("user_role")

    try:
        order = get_lab_order_detail(
            db_session=db_session,
            order_id=order_id,
            requester_user_id=viewer_id,
            requester_role=viewer_role
        )
    except LabOrderNotFoundError:
        flash("Laboratory report not found.", "danger")
        return redirect(url_for("patient.lab_reports"))
    except LabPermissionError:
        abort(403)

    return render_template(
        "patient/lab_report_detail.html",
        active_page="patient_labs",
        order=order
    )

