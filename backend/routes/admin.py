import math
from datetime import datetime, date, timezone
from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from sqlalchemy import or_, desc, func

from backend.database import db_session
from backend.models import (
    User, Doctor, Patient, Staff, Department, Room, Bed,
    Appointment, Admission, Bill, Medicine, AuditLog,
    RoleEnum, GenderEnum, RoomTypeEnum, BedStatusEnum,
    BillStatusEnum, AdmissionStatusEnum
)
from backend.security import get_password_hash
from backend.utils.decorators import login_required, roles_required
from backend.services import audit_service

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def paginate(query, page: int = 1, per_page: int = 10):
    """Simple, robust query pagination helper."""
    total = query.count()
    pages = max(1, math.ceil(total / per_page)) if total > 0 else 1
    page = max(1, min(page, pages))
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return items, total, page, pages


# =====================================================================
# 1. Executive Dashboard
# =====================================================================

@admin_bp.route("/")
@login_required
@roles_required(RoleEnum.ADMIN)
def dashboard():
    total_patients = db_session.query(Patient).count()
    total_doctors = db_session.query(Doctor).count()
    total_staff = db_session.query(Staff).count()
    total_appointments = db_session.query(Appointment).count()
    total_admissions = db_session.query(Admission).count()
    
    total_beds = db_session.query(Bed).count()
    occupied_beds = db_session.query(Bed).filter(Bed.status == BedStatusEnum.OCCUPIED).count()
    occupancy_rate = round((occupied_beds / total_beds * 100), 1) if total_beds > 0 else 0.0

    # Pending bills: UNPAID or PARTIALLY_PAID
    pending_bills = db_session.query(Bill).filter(
        Bill.status.in_([BillStatusEnum.UNPAID, BillStatusEnum.PARTIALLY_PAID])
    ).count()

    # Low-stock medicines
    all_medicines = db_session.query(Medicine).all()
    low_stock_medicines = sum(1 for m in all_medicines if m.is_low_stock)

    # Recent system activity (last 10 audit logs)
    recent_audits = db_session.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(10).all()

    return render_template(
        "admin/dashboard.html",
        active_page="admin_dashboard",
        total_patients=total_patients,
        total_doctors=total_doctors,
        total_staff=total_staff,
        total_appointments=total_appointments,
        total_admissions=total_admissions,
        total_beds=total_beds,
        occupied_beds=occupied_beds,
        occupancy_rate=occupancy_rate,
        pending_bills=pending_bills,
        low_stock_medicines=low_stock_medicines,
        recent_audits=recent_audits
    )


# =====================================================================
# 2. Users Management
# =====================================================================

@admin_bp.route("/users")
@login_required
@roles_required(RoleEnum.ADMIN)
def manage_users():
    q = request.args.get("q", "").strip()
    role_filter = request.args.get("role", "").strip()
    status_filter = request.args.get("status", "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    query = db_session.query(User)

    if q:
        search_fmt = f"%{q}%"
        query = query.filter(
            or_(
                User.first_name.ilike(search_fmt),
                User.last_name.ilike(search_fmt),
                User.email.ilike(search_fmt),
                User.phone.ilike(search_fmt)
            )
        )

    if role_filter:
        try:
            r_enum = RoleEnum(role_filter)
            query = query.filter(User.role == r_enum)
        except ValueError:
            pass

    if status_filter == "active":
        query = query.filter(User.is_active == True)
    elif status_filter == "inactive":
        query = query.filter(User.is_active == False)

    query = query.order_by(User.id.asc())
    users, total, page, pages = paginate(query, page=page, per_page=10)

    roles = [r.value for r in RoleEnum]
    departments = db_session.query(Department).filter(Department.is_active == True).all()

    return render_template(
        "admin/users.html",
        active_page="manage_users",
        users=users,
        total=total,
        page=page,
        pages=pages,
        q=q,
        role_filter=role_filter,
        status_filter=status_filter,
        roles=roles,
        departments=departments
    )


@admin_bp.route("/users/create", methods=["POST"])
@login_required
@roles_required(RoleEnum.ADMIN)
def create_user():
    email = request.form.get("email", "").strip().lower()
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    phone = request.form.get("phone", "").strip()
    role_str = request.form.get("role", "").strip()
    password = request.form.get("password", "Password123!")

    # Validations
    if not email or "@" not in email:
        flash("A valid email address is required.", "danger")
        return redirect(url_for("admin.manage_users"))

    if not first_name or not last_name:
        flash("First and last names are required.", "danger")
        return redirect(url_for("admin.manage_users"))

    if len(password) < 8:
        flash("Password must be at least 8 characters long.", "danger")
        return redirect(url_for("admin.manage_users"))

    existing = db_session.query(User).filter(User.email == email).first()
    if existing:
        flash(f"A user with email '{email}' already exists.", "danger")
        return redirect(url_for("admin.manage_users"))

    try:
        role_enum = RoleEnum(role_str)
    except ValueError:
        flash("Invalid role selected.", "danger")
        return redirect(url_for("admin.manage_users"))

    new_user = User(
        email=email,
        password_hash=get_password_hash(password),
        role=role_enum,
        first_name=first_name,
        last_name=last_name,
        phone=phone or None,
        is_active=True
    )
    db_session.add(new_user)
    db_session.flush()

    # Create associated profile if Doctor, Staff, or Patient
    if role_enum == RoleEnum.DOCTOR:
        dept_id = request.form.get("department_id")
        doc_prof = Doctor(
            id=new_user.id,
            department_id=int(dept_id) if dept_id else None,
            specialization=request.form.get("specialization", "General Medicine").strip(),
            qualification=request.form.get("qualification", "MBBS").strip(),
            license_number=request.form.get("license_number", f"LIC-{new_user.id}992").strip(),
            consultation_fee=Decimal(request.form.get("consultation_fee", "600.00")),
            room_number=request.form.get("room_number", "OPD-1").strip(),
            available_days=request.form.get("available_days", "Mon,Tue,Wed,Thu,Fri")
        )
        db_session.add(doc_prof)

    elif role_enum in [RoleEnum.NURSE, RoleEnum.PHARMACIST, RoleEnum.LAB_TECH, RoleEnum.RECEPTIONIST]:
        dept_id = request.form.get("department_id")
        emp_id = request.form.get("employee_id", f"EMP-{new_user.id:04d}").strip()
        staff_prof = Staff(
            id=new_user.id,
            department_id=int(dept_id) if dept_id else None,
            employee_id=emp_id,
            designation=request.form.get("designation", role_enum.value.capitalize()).strip(),
            shift=request.form.get("shift", "Morning")
        )
        db_session.add(staff_prof)

    elif role_enum == RoleEnum.PATIENT:
        patient_prof = Patient(
            id=new_user.id,
            dob=date(1990, 1, 1),
            gender=GenderEnum.OTHER
        )
        db_session.add(patient_prof)

    # Audit log
    audit = AuditLog(
        user_id=session.get("user_id"),
        action="ADMIN_USER_CREATE",
        resource_type="User",
        resource_id=new_user.id,
        ip_address=request.remote_addr,
        details_json=f'{{"created_user_id": {new_user.id}, "email": "{email}", "role": "{role_enum.value}"}}'
    )
    db_session.add(audit)
    db_session.commit()

    flash(f"User {new_user.full_name} ({role_enum.value}) provisioned successfully.", "success")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/users/<int:user_id>/toggle-status", methods=["POST"])
@login_required
@roles_required(RoleEnum.ADMIN)
def toggle_user_status(user_id: int):
    current_admin_id = session.get("user_id")
    if user_id == current_admin_id:
        flash("You cannot deactivate your own administrative account.", "danger")
        return redirect(url_for("admin.manage_users"))

    user = db_session.query(User).filter(User.id == user_id).first()
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("admin.manage_users"))

    user.is_active = not user.is_active
    action_desc = "activated" if user.is_active else "deactivated"

    audit = AuditLog(
        user_id=current_admin_id,
        action="ADMIN_USER_STATUS_CHANGE",
        resource_type="User",
        resource_id=user.id,
        ip_address=request.remote_addr,
        details_json=f'{{"target_user_id": {user.id}, "new_active_status": {user.is_active}}}'
    )
    db_session.add(audit)
    db_session.commit()

    flash(f"User {user.full_name} has been {action_desc}.", "info")
    return redirect(url_for("admin.manage_users"))


# =====================================================================
# 3. Doctors Management
# =====================================================================

@admin_bp.route("/doctors")
@login_required
@roles_required(RoleEnum.ADMIN)
def manage_doctors():
    q = request.args.get("q", "").strip()
    dept_id = request.args.get("dept", "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    query = db_session.query(Doctor).join(Doctor.user)

    if q:
        search_fmt = f"%{q}%"
        query = query.filter(
            or_(
                User.first_name.ilike(search_fmt),
                User.last_name.ilike(search_fmt),
                Doctor.specialization.ilike(search_fmt),
                Doctor.license_number.ilike(search_fmt)
            )
        )

    if dept_id and dept_id.isdigit():
        query = query.filter(Doctor.department_id == int(dept_id))

    query = query.order_by(Doctor.id.asc())
    doctors, total, page, pages = paginate(query, page=page, per_page=10)

    departments = db_session.query(Department).filter(Department.is_active == True).all()

    return render_template(
        "admin/doctors.html",
        active_page="manage_doctors",
        doctors=doctors,
        total=total,
        page=page,
        pages=pages,
        q=q,
        dept_id=dept_id,
        departments=departments
    )


@admin_bp.route("/doctors/create", methods=["POST"])
@login_required
@roles_required(RoleEnum.ADMIN)
def create_doctor():
    email = request.form.get("email", "").strip().lower()
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    phone = request.form.get("phone", "").strip()
    password = request.form.get("password", "Password123!")
    specialization = request.form.get("specialization", "").strip()
    qualification = request.form.get("qualification", "").strip()
    license_number = request.form.get("license_number", "").strip()
    dept_id = request.form.get("department_id")
    consultation_fee = request.form.get("consultation_fee", "600.00")
    room_number = request.form.get("room_number", "OPD-1").strip()
    available_days = request.form.get("available_days", "Mon,Tue,Wed,Thu,Fri").strip()

    if not email or "@" not in email:
        flash("Valid email address is required.", "danger")
        return redirect(url_for("admin.manage_doctors"))

    if not first_name or not last_name or not specialization or not license_number:
        flash("First name, last name, specialization, and license number are required.", "danger")
        return redirect(url_for("admin.manage_doctors"))

    existing_user = db_session.query(User).filter(User.email == email).first()
    if existing_user:
        flash(f"User with email '{email}' already exists.", "danger")
        return redirect(url_for("admin.manage_doctors"))

    existing_lic = db_session.query(Doctor).filter(Doctor.license_number == license_number).first()
    if existing_lic:
        flash(f"Medical license '{license_number}' is already registered.", "danger")
        return redirect(url_for("admin.manage_doctors"))

    try:
        fee_decimal = Decimal(consultation_fee)
    except Exception:
        fee_decimal = Decimal("600.00")

    new_user = User(
        email=email,
        password_hash=get_password_hash(password),
        role=RoleEnum.DOCTOR,
        first_name=first_name,
        last_name=last_name,
        phone=phone or None,
        is_active=True
    )
    db_session.add(new_user)
    db_session.flush()

    doctor = Doctor(
        id=new_user.id,
        department_id=int(dept_id) if dept_id else None,
        specialization=specialization,
        qualification=qualification or "MBBS",
        license_number=license_number,
        consultation_fee=fee_decimal,
        room_number=room_number,
        available_days=available_days
    )
    db_session.add(doctor)

    audit = AuditLog(
        user_id=session.get("user_id"),
        action="ADMIN_DOCTOR_CREATE",
        resource_type="Doctor",
        resource_id=doctor.id,
        ip_address=request.remote_addr,
        details_json=f'{{"doctor_id": {doctor.id}, "license": "{license_number}", "specialization": "{specialization}"}}'
    )
    db_session.add(audit)
    db_session.commit()

    flash(f"Dr. {new_user.full_name} added to medical staff.", "success")
    return redirect(url_for("admin.manage_doctors"))


@admin_bp.route("/doctors/<int:doctor_id>/edit", methods=["POST"])
@login_required
@roles_required(RoleEnum.ADMIN)
def edit_doctor(doctor_id: int):
    doc = db_session.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doc:
        flash("Doctor record not found.", "danger")
        return redirect(url_for("admin.manage_doctors"))

    doc.specialization = request.form.get("specialization", doc.specialization).strip()
    doc.qualification = request.form.get("qualification", doc.qualification).strip()
    doc.room_number = request.form.get("room_number", doc.room_number).strip()
    doc.available_days = request.form.get("available_days", doc.available_days).strip()
    dept_id = request.form.get("department_id")
    if dept_id:
        doc.department_id = int(dept_id)

    fee_str = request.form.get("consultation_fee")
    if fee_str:
        try:
            doc.consultation_fee = Decimal(fee_str)
        except Exception:
            pass

    db_session.commit()
    flash(f"Dr. {doc.user.full_name} details updated.", "success")
    return redirect(url_for("admin.manage_doctors"))


# =====================================================================
# 4. Staff Management
# =====================================================================

@admin_bp.route("/staff")
@login_required
@roles_required(RoleEnum.ADMIN)
def manage_staff():
    q = request.args.get("q", "").strip()
    dept_id = request.args.get("dept", "").strip()
    shift_filter = request.args.get("shift", "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    query = db_session.query(Staff).join(Staff.user)

    if q:
        search_fmt = f"%{q}%"
        query = query.filter(
            or_(
                User.first_name.ilike(search_fmt),
                User.last_name.ilike(search_fmt),
                Staff.employee_id.ilike(search_fmt),
                Staff.designation.ilike(search_fmt)
            )
        )

    if dept_id and dept_id.isdigit():
        query = query.filter(Staff.department_id == int(dept_id))

    if shift_filter:
        query = query.filter(Staff.shift.ilike(shift_filter))

    query = query.order_by(Staff.id.asc())
    staff_members, total, page, pages = paginate(query, page=page, per_page=10)

    departments = db_session.query(Department).filter(Department.is_active == True).all()

    return render_template(
        "admin/staff.html",
        active_page="manage_staff",
        staff_members=staff_members,
        total=total,
        page=page,
        pages=pages,
        q=q,
        dept_id=dept_id,
        shift_filter=shift_filter,
        departments=departments
    )


@admin_bp.route("/staff/create", methods=["POST"])
@login_required
@roles_required(RoleEnum.ADMIN)
def create_staff():
    email = request.form.get("email", "").strip().lower()
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    phone = request.form.get("phone", "").strip()
    password = request.form.get("password", "Password123!")
    role_str = request.form.get("role", "nurse").strip()
    employee_id = request.form.get("employee_id", "").strip()
    designation = request.form.get("designation", "").strip()
    dept_id = request.form.get("department_id")
    shift = request.form.get("shift", "Morning").strip()

    if not email or "@" not in email:
        flash("Valid email address is required.", "danger")
        return redirect(url_for("admin.manage_staff"))

    if not first_name or not last_name or not employee_id or not designation:
        flash("First name, last name, employee ID, and designation are required.", "danger")
        return redirect(url_for("admin.manage_staff"))

    existing_user = db_session.query(User).filter(User.email == email).first()
    if existing_user:
        flash(f"User with email '{email}' already exists.", "danger")
        return redirect(url_for("admin.manage_staff"))

    existing_emp = db_session.query(Staff).filter(Staff.employee_id == employee_id).first()
    if existing_emp:
        flash(f"Staff member with Employee ID '{employee_id}' already exists.", "danger")
        return redirect(url_for("admin.manage_staff"))

    try:
        role_enum = RoleEnum(role_str)
    except ValueError:
        role_enum = RoleEnum.NURSE

    new_user = User(
        email=email,
        password_hash=get_password_hash(password),
        role=role_enum,
        first_name=first_name,
        last_name=last_name,
        phone=phone or None,
        is_active=True
    )
    db_session.add(new_user)
    db_session.flush()

    staff_entry = Staff(
        id=new_user.id,
        department_id=int(dept_id) if dept_id else None,
        employee_id=employee_id,
        designation=designation,
        shift=shift
    )
    db_session.add(staff_entry)

    audit = AuditLog(
        user_id=session.get("user_id"),
        action="ADMIN_STAFF_CREATE",
        resource_type="Staff",
        resource_id=staff_entry.id,
        ip_address=request.remote_addr,
        details_json=f'{{"staff_id": {staff_entry.id}, "employee_id": "{employee_id}", "designation": "{designation}"}}'
    )
    db_session.add(audit)
    db_session.commit()

    flash(f"Staff member {new_user.full_name} ({employee_id}) added successfully.", "success")
    return redirect(url_for("admin.manage_staff"))


# =====================================================================
# 5. Patients Management
# =====================================================================

@admin_bp.route("/patients")
@login_required
@roles_required(RoleEnum.ADMIN)
def manage_patients():
    q = request.args.get("q", "").strip()
    gender_filter = request.args.get("gender", "").strip()
    blood_filter = request.args.get("blood_group", "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    query = db_session.query(Patient).join(Patient.user)

    if q:
        search_fmt = f"%{q}%"
        query = query.filter(
            or_(
                User.first_name.ilike(search_fmt),
                User.last_name.ilike(search_fmt),
                User.email.ilike(search_fmt),
                User.phone.ilike(search_fmt)
            )
        )

    if gender_filter:
        try:
            g_enum = GenderEnum(gender_filter.lower())
            query = query.filter(Patient.gender == g_enum)
        except ValueError:
            pass

    if blood_filter:
        query = query.filter(Patient.blood_group == blood_filter)

    query = query.order_by(Patient.id.asc())
    patients, total, page, pages = paginate(query, page=page, per_page=10)

    return render_template(
        "admin/patients.html",
        active_page="manage_patients",
        patients=patients,
        total=total,
        page=page,
        pages=pages,
        q=q,
        gender_filter=gender_filter,
        blood_filter=blood_filter
    )


@admin_bp.route("/patients/create", methods=["POST"])
@login_required
@roles_required(RoleEnum.ADMIN)
def create_patient():
    email = request.form.get("email", "").strip().lower()
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    phone = request.form.get("phone", "").strip()
    password = request.form.get("password", "Password123!")
    dob_str = request.form.get("dob", "").strip()
    gender_str = request.form.get("gender", "other").strip().lower()
    blood_group = request.form.get("blood_group", "").strip()
    emergency_name = request.form.get("emergency_contact_name", "").strip()
    emergency_phone = request.form.get("emergency_contact_phone", "").strip()
    address = request.form.get("address", "").strip()
    allergies = request.form.get("allergies", "").strip()
    chronic = request.form.get("chronic_conditions", "").strip()

    if not email or "@" not in email:
        flash("Valid email address is required.", "danger")
        return redirect(url_for("admin.manage_patients"))

    if not first_name or not last_name:
        flash("First and last names are required.", "danger")
        return redirect(url_for("admin.manage_patients"))

    existing_user = db_session.query(User).filter(User.email == email).first()
    if existing_user:
        flash(f"User with email '{email}' already exists.", "danger")
        return redirect(url_for("admin.manage_patients"))

    try:
        dob = datetime.strptime(dob_str, "%Y-%m-%d").date() if dob_str else date(1995, 1, 1)
    except ValueError:
        dob = date(1995, 1, 1)

    try:
        gender_enum = GenderEnum(gender_str)
    except ValueError:
        gender_enum = GenderEnum.OTHER

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

    patient_entry = Patient(
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
    db_session.add(patient_entry)

    audit = AuditLog(
        user_id=session.get("user_id"),
        action="ADMIN_PATIENT_CREATE",
        resource_type="Patient",
        resource_id=patient_entry.id,
        ip_address=request.remote_addr,
        details_json=f'{{"patient_id": {patient_entry.id}, "name": "{new_user.full_name}"}}'
    )
    db_session.add(audit)
    db_session.commit()

    flash(f"Patient {new_user.full_name} registered successfully.", "success")
    return redirect(url_for("admin.manage_patients"))


# =====================================================================
# 6. Departments Management
# =====================================================================

@admin_bp.route("/departments")
@login_required
@roles_required(RoleEnum.ADMIN)
def manage_departments():
    departments = db_session.query(Department).all()
    doctors = db_session.query(Doctor).join(Doctor.user).all()

    return render_template(
        "admin/departments.html",
        active_page="manage_departments",
        departments=departments,
        doctors=doctors
    )


@admin_bp.route("/departments/create", methods=["POST"])
@login_required
@roles_required(RoleEnum.ADMIN)
def create_department():
    name = request.form.get("name", "").strip()
    code = request.form.get("code", "").strip().upper()
    description = request.form.get("description", "").strip()
    head_doctor_id = request.form.get("head_doctor_id")

    if not name or not code:
        flash("Department name and unique code are required.", "danger")
        return redirect(url_for("admin.manage_departments"))

    existing_code = db_session.query(Department).filter(
        or_(Department.code == code, Department.name == name)
    ).first()
    if existing_code:
        flash("A department with this code or name already exists.", "danger")
        return redirect(url_for("admin.manage_departments"))

    dept = Department(
        name=name,
        code=code,
        description=description or None,
        head_doctor_id=int(head_doctor_id) if head_doctor_id else None,
        is_active=True
    )
    db_session.add(dept)

    audit = AuditLog(
        user_id=session.get("user_id"),
        action="ADMIN_DEPARTMENT_CREATE",
        resource_type="Department",
        resource_id=None,
        ip_address=request.remote_addr,
        details_json=f'{{"code": "{code}", "name": "{name}"}}'
    )
    db_session.add(audit)
    db_session.commit()

    flash(f"Department '{name}' ({code}) established successfully.", "success")
    return redirect(url_for("admin.manage_departments"))


# =====================================================================
# 7. Rooms Management
# =====================================================================

@admin_bp.route("/rooms")
@login_required
@roles_required(RoleEnum.ADMIN)
def manage_rooms():
    q = request.args.get("q", "").strip()
    room_type_filter = request.args.get("type", "").strip()
    dept_id = request.args.get("dept", "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    query = db_session.query(Room)

    if q:
        query = query.filter(Room.room_number.ilike(f"%{q}%"))

    if room_type_filter:
        try:
            r_enum = RoomTypeEnum(room_type_filter.lower())
            query = query.filter(Room.room_type == r_enum)
        except ValueError:
            pass

    if dept_id and dept_id.isdigit():
        query = query.filter(Room.department_id == int(dept_id))

    query = query.order_by(Room.id.asc())
    rooms, total, page, pages = paginate(query, page=page, per_page=10)

    departments = db_session.query(Department).filter(Department.is_active == True).all()
    room_types = [t.value for t in RoomTypeEnum]

    return render_template(
        "admin/rooms.html",
        active_page="manage_rooms",
        rooms=rooms,
        total=total,
        page=page,
        pages=pages,
        q=q,
        room_type_filter=room_type_filter,
        dept_id=dept_id,
        departments=departments,
        room_types=room_types
    )


@admin_bp.route("/rooms/create", methods=["POST"])
@login_required
@roles_required(RoleEnum.ADMIN)
def create_room():
    room_number = request.form.get("room_number", "").strip().upper()
    room_type_str = request.form.get("room_type", "general").strip().lower()
    floor_str = request.form.get("floor", "1").strip()
    dept_id = request.form.get("department_id")
    daily_rate_str = request.form.get("daily_rate", "1500.00").strip()
    total_beds_str = request.form.get("total_beds", "10").strip()

    if not room_number:
        flash("Room number is required.", "danger")
        return redirect(url_for("admin.manage_rooms"))

    existing = db_session.query(Room).filter(Room.room_number == room_number).first()
    if existing:
        flash(f"Room '{room_number}' already exists.", "danger")
        return redirect(url_for("admin.manage_rooms"))

    try:
        room_type_enum = RoomTypeEnum(room_type_str)
    except ValueError:
        room_type_enum = RoomTypeEnum.GENERAL

    try:
        floor = int(floor_str)
        daily_rate = Decimal(daily_rate_str)
        total_beds = int(total_beds_str)
    except Exception:
        floor, daily_rate, total_beds = 1, Decimal("1500.00"), 10

    room = Room(
        room_number=room_number,
        room_type=room_type_enum,
        floor=floor,
        department_id=int(dept_id) if dept_id else None,
        daily_rate=daily_rate,
        total_beds=total_beds
    )
    db_session.add(room)

    audit = AuditLog(
        user_id=session.get("user_id"),
        action="ADMIN_ROOM_CREATE",
        resource_type="Room",
        resource_id=None,
        ip_address=request.remote_addr,
        details_json=f'{{"room_number": "{room_number}", "type": "{room_type_enum.value}"}}'
    )
    db_session.add(audit)
    db_session.commit()

    flash(f"Room '{room_number}' created successfully.", "success")
    return redirect(url_for("admin.manage_rooms"))


# =====================================================================
# 8. Beds Management
# =====================================================================

@admin_bp.route("/beds")
@login_required
@roles_required(RoleEnum.ADMIN)
def manage_beds():
    q = request.args.get("q", "").strip()
    room_id = request.args.get("room_id", "").strip()
    status_filter = request.args.get("status", "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    query = db_session.query(Bed).join(Bed.room)

    if q:
        query = query.filter(Bed.bed_number.ilike(f"%{q}%"))

    if room_id and room_id.isdigit():
        query = query.filter(Bed.room_id == int(room_id))

    if status_filter:
        try:
            b_enum = BedStatusEnum(status_filter.lower())
            query = query.filter(Bed.status == b_enum)
        except ValueError:
            pass

    query = query.order_by(Bed.id.asc())
    beds, total, page, pages = paginate(query, page=page, per_page=12)

    rooms = db_session.query(Room).all()
    statuses = [s.value for s in BedStatusEnum]

    return render_template(
        "admin/beds.html",
        active_page="manage_beds",
        beds=beds,
        total=total,
        page=page,
        pages=pages,
        q=q,
        room_id=room_id,
        status_filter=status_filter,
        rooms=rooms,
        statuses=statuses
    )


@admin_bp.route("/beds/create", methods=["POST"])
@login_required
@roles_required(RoleEnum.ADMIN)
def create_bed():
    room_id_str = request.form.get("room_id", "").strip()
    bed_number = request.form.get("bed_number", "").strip().upper()
    daily_rate_str = request.form.get("daily_rate", "").strip()

    if not room_id_str or not bed_number:
        flash("Room selection and bed number are required.", "danger")
        return redirect(url_for("admin.manage_beds"))

    room = db_session.query(Room).filter(Room.id == int(room_id_str)).first()
    if not room:
        flash("Target room does not exist.", "danger")
        return redirect(url_for("admin.manage_beds"))

    existing_bed = db_session.query(Bed).filter(
        Bed.room_id == room.id,
        Bed.bed_number == bed_number
    ).first()
    if existing_bed:
        flash(f"Bed '{bed_number}' already exists in Room '{room.room_number}'.", "danger")
        return redirect(url_for("admin.manage_beds"))

    daily_rate = Decimal(daily_rate_str) if daily_rate_str else room.daily_rate

    bed = Bed(
        room_id=room.id,
        bed_number=bed_number,
        status=BedStatusEnum.AVAILABLE,
        daily_rate=daily_rate
    )
    db_session.add(bed)

    audit = AuditLog(
        user_id=session.get("user_id"),
        action="ADMIN_BED_CREATE",
        resource_type="Bed",
        resource_id=None,
        ip_address=request.remote_addr,
        details_json=f'{{"room_id": {room.id}, "bed_number": "{bed_number}"}}'
    )
    db_session.add(audit)
    db_session.commit()

    flash(f"Bed '{bed_number}' added to Room '{room.room_number}'.", "success")
    return redirect(url_for("admin.manage_beds"))


@admin_bp.route("/beds/<int:bed_id>/status", methods=["POST"])
@login_required
@roles_required(RoleEnum.ADMIN)
def update_bed_status(bed_id: int):
    bed = db_session.query(Bed).filter(Bed.id == bed_id).first()
    if not bed:
        flash("Bed not found.", "danger")
        return redirect(url_for("admin.manage_beds"))

    new_status_str = request.form.get("status", "").strip().lower()
    try:
        new_status = BedStatusEnum(new_status_str)
        bed.status = new_status
        db_session.commit()
        flash(f"Bed {bed.bed_number} status changed to {new_status.value.upper()}.", "success")
    except ValueError:
        flash("Invalid bed status.", "danger")

    return redirect(url_for("admin.manage_beds"))


# =====================================================================
# 9. Security & Audit Logs
# =====================================================================

@admin_bp.route("/audits")
@login_required
@roles_required(RoleEnum.ADMIN)
def audit_logs():
    q = request.args.get("q", "").strip()
    action_filter = request.args.get("action", "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    per_page = 15
    offset = (page - 1) * per_page

    logs, total = audit_service.search_audit_logs(
        db=db_session,
        action=action_filter or None,
        search_query=q or None,
        limit=per_page,
        offset=offset
    )

    pages = max(1, math.ceil(total / per_page)) if total > 0 else 1
    actions = audit_service.get_distinct_actions(db_session)

    return render_template(
        "admin/audits.html",
        active_page="audit_logs",
        logs=logs,
        total=total,
        page=page,
        pages=pages,
        q=q,
        action_filter=action_filter,
        actions=actions
    )
