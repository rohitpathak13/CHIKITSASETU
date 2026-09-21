import math
from datetime import datetime, date, timezone, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort, jsonify
from sqlalchemy import or_, desc, func

from backend.database import db_session
from backend.models import (
    Appointment, Patient, Doctor, User, Department,
    RoleEnum, AppointmentStatusEnum, AuditLog
)
from backend.services.appointment_service import (
    book_appointment, reschedule_appointment, cancel_appointment,
    complete_appointment, update_appointment_status, get_available_slots,
    AppointmentServiceError, DuplicateBookingError, DoctorUnavailableError,
    InvalidAppointmentDataError, AppointmentStateError, CLINIC_SLOTS
)
from backend.utils.decorators import login_required, roles_required, normalize_role

appointment_bp = Blueprint("appointment", __name__, url_prefix="/appointments")

STAFF_ROLES = {
    RoleEnum.ADMIN.value,
    RoleEnum.DOCTOR.value,
    RoleEnum.RECEPTIONIST.value,
    RoleEnum.NURSE.value
}


def paginate_query(query, page: int = 1, per_page: int = 10):
    total = query.count()
    pages = max(1, math.ceil(total / per_page)) if total > 0 else 1
    page = max(1, min(page, pages))
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return items, total, page, pages


# =====================================================================
# 1. Master Appointment Roster (Search, Filter, Pagination)
# =====================================================================

@appointment_bp.route("/")
@login_required
def index():
    user_role = normalize_role(session.get("user_role", ""))
    logged_in_user_id = session.get("user_id")

    q = request.args.get("q", "").strip()
    department_id = request.args.get("department_id", "").strip()
    doctor_id = request.args.get("doctor_id", "").strip()
    status_filter = request.args.get("status", "").strip().lower()
    date_filter = request.args.get("date", "all").strip().lower()
    custom_date = request.args.get("custom_date", "").strip()

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    query = db_session.query(Appointment).join(Appointment.patient).join(Patient.user).join(Appointment.doctor)

    # Role-Based Scoping
    if user_role == RoleEnum.PATIENT.value:
        query = query.filter(Appointment.patient_id == logged_in_user_id)
    elif user_role == RoleEnum.DOCTOR.value:
        # Default to doctor's own appointments unless explicitly choosing all or another filter
        if not doctor_id:
            doctor_id = str(logged_in_user_id)
            query = query.filter(Appointment.doctor_id == logged_in_user_id)
        elif doctor_id != "all":
            query = query.filter(Appointment.doctor_id == int(doctor_id))
    elif doctor_id and doctor_id != "all":
        query = query.filter(Appointment.doctor_id == int(doctor_id))

    # Department filter
    if department_id and department_id != "all":
        try:
            query = query.filter(Doctor.department_id == int(department_id))
        except ValueError:
            pass

    # Status filter
    if status_filter and status_filter != "all":
        try:
            st_enum = AppointmentStatusEnum(status_filter)
            query = query.filter(Appointment.status == st_enum)
        except ValueError:
            pass

    # Date filter
    today = date.today()
    if date_filter == "today":
        start_day = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
        end_day = datetime.combine(today, datetime.max.time(), tzinfo=timezone.utc)
        query = query.filter(Appointment.appointment_datetime >= start_day, Appointment.appointment_datetime <= end_day)
    elif date_filter == "tomorrow":
        tmr = today + timedelta(days=1)
        start_day = datetime.combine(tmr, datetime.min.time(), tzinfo=timezone.utc)
        end_day = datetime.combine(tmr, datetime.max.time(), tzinfo=timezone.utc)
        query = query.filter(Appointment.appointment_datetime >= start_day, Appointment.appointment_datetime <= end_day)
    elif date_filter == "this_week":
        start_week = datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time(), tzinfo=timezone.utc)
        end_week = datetime.combine(today + timedelta(days=6 - today.weekday()), datetime.max.time(), tzinfo=timezone.utc)
        query = query.filter(Appointment.appointment_datetime >= start_week, Appointment.appointment_datetime <= end_week)
    elif custom_date:
        try:
            target = datetime.strptime(custom_date, "%Y-%m-%d").date()
            start_day = datetime.combine(target, datetime.min.time(), tzinfo=timezone.utc)
            end_day = datetime.combine(target, datetime.max.time(), tzinfo=timezone.utc)
            query = query.filter(Appointment.appointment_datetime >= start_day, Appointment.appointment_datetime <= end_day)
        except ValueError:
            pass

    # Search filter (Patient name, MRN, phone, doctor name, token)
    if q:
        clean_q = q.upper().replace("PAT-", "").lstrip("0")
        id_filter = int(clean_q) if clean_q.isdigit() else -1
        search_term = f"%{q}%"
        query = query.filter(
            or_(
                User.first_name.ilike(search_term),
                User.last_name.ilike(search_term),
                User.phone.ilike(search_term),
                Appointment.reason.ilike(search_term),
                Appointment.patient_id == id_filter,
                Appointment.token_number == (int(clean_q) if clean_q.isdigit() else -1)
            )
        )

    # Order by appointment time
    query = query.order_by(Appointment.appointment_datetime.desc())
    appointments, total, page, pages = paginate_query(query, page=page, per_page=10)

    # Summary Statistics
    base_stats_q = db_session.query(Appointment)
    if user_role == RoleEnum.PATIENT.value:
        base_stats_q = base_stats_q.filter(Appointment.patient_id == logged_in_user_id)
    elif user_role == RoleEnum.DOCTOR.value and doctor_id and doctor_id != "all":
        base_stats_q = base_stats_q.filter(Appointment.doctor_id == int(doctor_id))

    all_appts = base_stats_q.all()
    stats = {
        "total": len(all_appts),
        "today": sum(1 for a in all_appts if a.appointment_datetime and a.appointment_datetime.date() == today),
        "scheduled": sum(1 for a in all_appts if a.status == AppointmentStatusEnum.SCHEDULED),
        "confirmed": sum(1 for a in all_appts if a.status == AppointmentStatusEnum.CONFIRMED),
        "completed": sum(1 for a in all_appts if a.status == AppointmentStatusEnum.COMPLETED),
        "cancelled": sum(1 for a in all_appts if a.status == AppointmentStatusEnum.CANCELLED)
    }

    departments = db_session.query(Department).filter(Department.is_active == True).all()
    doctors = db_session.query(Doctor).all()

    return render_template(
        "appointments/index.html",
        active_page="appointments_roster",
        appointments=appointments,
        total=total,
        page=page,
        pages=pages,
        stats=stats,
        departments=departments,
        doctors=doctors,
        q=q,
        department_id=department_id,
        doctor_id=doctor_id,
        status_filter=status_filter,
        date_filter=date_filter,
        custom_date=custom_date,
        user_role=user_role,
        today_date=today.strftime("%Y-%m-%d")
    )


# =====================================================================
# 2. Book New Appointment
# =====================================================================

@appointment_bp.route("/book", methods=["GET", "POST"])
@login_required
def book():
    user_role = normalize_role(session.get("user_role", ""))
    logged_in_user_id = session.get("user_id")

    # Patient can book for self; Staff can book for any patient
    allowed_roles = STAFF_ROLES | {RoleEnum.PATIENT.value}
    if user_role not in allowed_roles:
        abort(403)

    if request.method == "POST":
        if user_role == RoleEnum.PATIENT.value:
            patient_id = logged_in_user_id
        else:
            try:
                patient_id = int(request.form.get("patient_id"))
            except (ValueError, TypeError):
                flash("Please select a valid patient.", "danger")
                return redirect(url_for("appointment.book"))

        try:
            doctor_id = int(request.form.get("doctor_id"))
        except (ValueError, TypeError):
            flash("Please select a valid consulting doctor.", "danger")
            return redirect(url_for("appointment.book"))

        appt_date_str = request.form.get("appointment_date", "").strip()
        time_slot = request.form.get("time_slot", "").strip()
        reason = request.form.get("reason", "").strip()

        if not appt_date_str or not time_slot:
            flash("Appointment date and consultation time slot are required.", "danger")
            return redirect(url_for("appointment.book"))

        combined_dt_str = f"{appt_date_str}T{time_slot}"

        try:
            appointment = book_appointment(
                db=db_session,
                patient_id=patient_id,
                doctor_id=doctor_id,
                appointment_datetime=combined_dt_str,
                reason=reason,
                actor_id=logged_in_user_id,
                ip_address=request.remote_addr
            )
            flash(
                f"Appointment booked successfully! Token #{appointment.token_number} with Dr. {appointment.doctor.user.full_name} "
                f"on {appointment.appointment_datetime.strftime('%Y-%m-%d at %H:%M')}.",
                "success"
            )
            if user_role == RoleEnum.PATIENT.value:
                return redirect(url_for("patient.appointments"))
            return redirect(url_for("appointment.index"))

        except (DuplicateBookingError, DoctorUnavailableError, InvalidAppointmentDataError) as e:
            flash(str(e), "danger")
            return redirect(url_for("appointment.book", patient_id=patient_id, doctor_id=doctor_id))

        except Exception as e:
            db_session.rollback()
            flash(f"Unexpected booking error: {str(e)}", "danger")
            return redirect(url_for("appointment.book"))

    # GET: Prepare form choices
    preselected_patient_id = request.args.get("patient_id")
    preselected_doctor_id = request.args.get("doctor_id")

    departments = db_session.query(Department).filter(Department.is_active == True).all()
    doctors = db_session.query(Doctor).all()
    patients = db_session.query(Patient).all() if user_role in STAFF_ROLES else []

    current_patient = None
    if user_role == RoleEnum.PATIENT.value:
        current_patient = db_session.query(Patient).filter(Patient.id == logged_in_user_id).first()
    elif preselected_patient_id:
        current_patient = db_session.query(Patient).filter(Patient.id == int(preselected_patient_id)).first()

    return render_template(
        "appointments/book.html",
        active_page="appointments_book",
        departments=departments,
        doctors=doctors,
        patients=patients,
        current_patient=current_patient,
        preselected_doctor_id=preselected_doctor_id,
        user_role=user_role,
        today_date=date.today().strftime("%Y-%m-%d"),
        clinic_slots=CLINIC_SLOTS
    )


# =====================================================================
# 3. Reschedule Appointment
# =====================================================================

@appointment_bp.route("/<int:appointment_id>/reschedule", methods=["GET", "POST"])
@login_required
def reschedule(appointment_id: int):
    user_role = normalize_role(session.get("user_role", ""))
    logged_in_user_id = session.get("user_id")

    appointment = db_session.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        flash("Appointment not found.", "danger")
        return redirect(url_for("appointment.index"))

    # RBAC: Patient can only reschedule their own appointment; Staff can reschedule any
    if user_role == RoleEnum.PATIENT.value and appointment.patient_id != logged_in_user_id:
        abort(403)
    elif user_role not in (STAFF_ROLES | {RoleEnum.PATIENT.value}):
        abort(403)

    if request.method == "POST":
        appt_date_str = request.form.get("appointment_date", "").strip()
        time_slot = request.form.get("time_slot", "").strip()
        reason = request.form.get("reason", "").strip()

        if not appt_date_str or not time_slot:
            flash("New appointment date and consultation time slot are required.", "danger")
            return redirect(url_for("appointment.reschedule", appointment_id=appointment_id))

        combined_dt_str = f"{appt_date_str}T{time_slot}"

        try:
            rescheduled_appt = reschedule_appointment(
                db=db_session,
                appointment_id=appointment_id,
                new_datetime=combined_dt_str,
                actor_id=logged_in_user_id,
                ip_address=request.remote_addr,
                reason=reason
            )
            flash(
                f"Appointment #{appointment_id} rescheduled to {rescheduled_appt.appointment_datetime.strftime('%Y-%m-%d at %H:%M')}. New Token #{rescheduled_appt.token_number}.",
                "success"
            )
            if user_role == RoleEnum.PATIENT.value:
                return redirect(url_for("patient.appointments"))
            return redirect(url_for("appointment.index"))

        except (DuplicateBookingError, DoctorUnavailableError, InvalidAppointmentDataError, AppointmentStateError) as e:
            flash(str(e), "danger")
            return redirect(url_for("appointment.reschedule", appointment_id=appointment_id))

    return render_template(
        "appointments/reschedule.html",
        active_page="appointments_roster",
        appointment=appointment,
        today_date=date.today().strftime("%Y-%m-%d"),
        clinic_slots=CLINIC_SLOTS
    )


# =====================================================================
# 4. Cancel Appointment
# =====================================================================

@appointment_bp.route("/<int:appointment_id>/cancel", methods=["POST"])
@login_required
def cancel(appointment_id: int):
    user_role = normalize_role(session.get("user_role", ""))
    logged_in_user_id = session.get("user_id")

    appointment = db_session.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        flash("Appointment not found.", "danger")
        return redirect(url_for("appointment.index"))

    # RBAC: Patient can cancel own appointment; Staff can cancel any
    if user_role == RoleEnum.PATIENT.value and appointment.patient_id != logged_in_user_id:
        abort(403)
    elif user_role not in (STAFF_ROLES | {RoleEnum.PATIENT.value}):
        abort(403)

    reason = request.form.get("cancellation_reason", "").strip()

    try:
        cancel_appointment(
            db=db_session,
            appointment_id=appointment_id,
            actor_id=logged_in_user_id,
            ip_address=request.remote_addr,
            cancellation_reason=reason
        )
        flash(f"Appointment #{appointment_id} has been cancelled.", "success")
    except AppointmentStateError as e:
        flash(str(e), "danger")

    if user_role == RoleEnum.PATIENT.value:
        return redirect(url_for("patient.appointments"))
    return redirect(url_for("appointment.index"))


# =====================================================================
# 5. Complete Appointment
# =====================================================================

@appointment_bp.route("/<int:appointment_id>/complete", methods=["POST"])
@login_required
@roles_required(RoleEnum.DOCTOR, RoleEnum.ADMIN)
def complete(appointment_id: int):
    logged_in_user_id = session.get("user_id")
    try:
        complete_appointment(
            db=db_session,
            appointment_id=appointment_id,
            actor_id=logged_in_user_id,
            ip_address=request.remote_addr
        )
        flash(f"Appointment #{appointment_id} marked as completed.", "success")
    except (AppointmentNotFoundError, AppointmentStateError) as e:
        flash(str(e), "danger")

    return redirect(url_for("appointment.index"))


# =====================================================================
# 6. Status Update Controller
# =====================================================================

@appointment_bp.route("/<int:appointment_id>/status", methods=["POST"])
@login_required
@roles_required(RoleEnum.ADMIN, RoleEnum.DOCTOR, RoleEnum.RECEPTIONIST)
def update_status(appointment_id: int):
    logged_in_user_id = session.get("user_id")
    new_status = request.form.get("status", "").strip().lower()

    try:
        update_appointment_status(
            db=db_session,
            appointment_id=appointment_id,
            new_status=new_status,
            actor_id=logged_in_user_id,
            ip_address=request.remote_addr
        )
        flash(f"Appointment #{appointment_id} status updated to {new_status}.", "success")
    except (AppointmentNotFoundError, InvalidAppointmentDataError, AppointmentStateError) as e:
        flash(str(e), "danger")

    return redirect(url_for("appointment.index"))


# =====================================================================
# 7. Asynchronous Real-Time Doctor Slot Availability API
# =====================================================================

@appointment_bp.route("/api/doctor-slots")
@login_required
def api_doctor_slots():
    try:
        doctor_id = int(request.args.get("doctor_id"))
        target_date = request.args.get("date", "").strip()
    except (TypeError, ValueError):
        return jsonify({"error": "Valid doctor_id and date (YYYY-MM-DD) are required."}), 400

    try:
        slot_data = get_available_slots(db_session, doctor_id, target_date)
        return jsonify(slot_data)
    except DoctorUnavailableError as e:
        return jsonify({"error": str(e), "is_available": False, "free_slots": []}), 200
    except InvalidAppointmentDataError as e:
        return jsonify({"error": str(e)}), 400
