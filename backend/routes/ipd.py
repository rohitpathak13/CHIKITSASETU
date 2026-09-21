from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime, timezone
from typing import Optional

from backend.database import db_session
from backend.models import (
    Admission, Bed, Room, Ward, BedTransfer, Department,
    User, Patient, Doctor, Staff, RoleEnum,
    BedStatusEnum, AdmissionStatusEnum, RoomTypeEnum
)
from backend.utils.decorators import login_required, roles_required
from backend.services import inpatient_service

ipd_bp = Blueprint("ipd", __name__, url_prefix="/ipd")


# =====================================================================
# IPD Dashboard
# =====================================================================

@ipd_bp.route("/")
@ipd_bp.route("/dashboard")
@login_required
@roles_required(RoleEnum.ADMIN, RoleEnum.DOCTOR, RoleEnum.NURSE, RoleEnum.RECEPTIONIST)
def dashboard():
    stats = inpatient_service.get_ipd_dashboard_stats(db_session)
    rooms = inpatient_service.get_all_rooms_with_beds(db_session)
    active_admissions = inpatient_service.list_admissions(
        db_session=db_session,
        status=AdmissionStatusEnum.ADMITTED
    )
    available_beds = inpatient_service.get_bed_availability(
        db_session=db_session,
        status=BedStatusEnum.AVAILABLE
    )
    doctors = db_session.query(Doctor).join(Doctor.user).all()
    departments = db_session.query(Department).all()
    patients = db_session.query(Patient).join(Patient.user).all()

    return render_template(
        "ipd/dashboard.html",
        active_page="ipd_dashboard",
        stats=stats,
        rooms=rooms,
        active_admissions=active_admissions,
        available_beds=available_beds,
        doctors=doctors,
        departments=departments,
        patients=patients,
        BedStatusEnum=BedStatusEnum
    )


# =====================================================================
# Bed Roster & Availability
# =====================================================================

@ipd_bp.route("/beds")
@login_required
@roles_required(RoleEnum.ADMIN, RoleEnum.DOCTOR, RoleEnum.NURSE, RoleEnum.RECEPTIONIST)
def beds():
    status_filter = request.args.get("status")
    department_id = request.args.get("department_id", type=int)
    room_id = request.args.get("room_id", type=int)
    room_type_str = request.args.get("room_type")

    status_enum = None
    if status_filter and status_filter.upper() in BedStatusEnum.__members__:
        status_enum = BedStatusEnum[status_filter.upper()]

    room_type_enum = None
    if room_type_str and room_type_str.upper() in RoomTypeEnum.__members__:
        room_type_enum = RoomTypeEnum[room_type_str.upper()]

    beds_list = inpatient_service.get_bed_availability(
        db_session=db_session,
        department_id=department_id,
        room_id=room_id,
        room_type=room_type_enum,
        status=status_enum
    )

    stats = inpatient_service.get_ipd_dashboard_stats(db_session)
    departments = db_session.query(Department).all()
    rooms = db_session.query(Room).all()

    return render_template(
        "ipd/beds.html",
        active_page="ipd_beds",
        beds=beds_list,
        stats=stats,
        departments=departments,
        rooms=rooms,
        current_status=status_filter,
        current_dept=department_id,
        current_room=room_id,
        current_room_type=room_type_str,
        BedStatusEnum=BedStatusEnum,
        RoomTypeEnum=RoomTypeEnum
    )


# =====================================================================
# Bed Status Update (e.g. Sanitize Maintenance -> Available)
# =====================================================================

@ipd_bp.route("/bed/<int:bed_id>/status", methods=["POST"])
@login_required
@roles_required(RoleEnum.ADMIN, RoleEnum.NURSE, RoleEnum.DOCTOR)
def update_bed_status(bed_id: int):
    new_status = request.form.get("status")
    notes = request.form.get("notes")

    if not new_status:
        flash("Target bed status is required.", "danger")
        return redirect(request.referrer or url_for("ipd.beds"))

    try:
        actor_id = session.get("user_id")
        ip_addr = request.remote_addr
        bed = inpatient_service.update_bed_status(
            db_session=db_session,
            bed_id=bed_id,
            new_status=new_status,
            actor_id=actor_id,
            notes=notes,
            ip_address=ip_addr
        )
        db_session.commit()
        flash(f"Bed '{bed.bed_number}' status updated to {bed.status.value.upper()}.", "success")
    except inpatient_service.InpatientServiceError as e:
        db_session.rollback()
        flash(str(e), "danger")
    except Exception as e:
        db_session.rollback()
        flash(f"Failed to update bed status: {str(e)}", "danger")

    return redirect(request.referrer or url_for("ipd.beds"))


# =====================================================================
# Patient Admission
# =====================================================================

@ipd_bp.route("/admit", methods=["POST"])
@login_required
@roles_required(RoleEnum.ADMIN, RoleEnum.DOCTOR, RoleEnum.RECEPTIONIST, RoleEnum.NURSE)
def admit_patient():
    patient_id = request.form.get("patient_id", type=int)
    bed_id = request.form.get("bed_id", type=int)
    doctor_id = request.form.get("doctor_id", type=int)
    department_id = request.form.get("department_id", type=int)
    admission_reason = request.form.get("admission_reason")
    notes = request.form.get("notes")

    # If current user is a doctor and didn't select doctor_id, default to themselves
    current_role = session.get("user_role")
    current_user_id = session.get("user_id")
    if not doctor_id and current_role == "doctor":
        doc_profile = db_session.query(Doctor).filter(Doctor.id == current_user_id).first()
        if doc_profile:
            doctor_id = doc_profile.id

    if not patient_id or not bed_id or not admission_reason:
        flash("Patient, bed, and admission reason are required fields.", "danger")
        return redirect(url_for("ipd.dashboard"))

    if not doctor_id:
        first_doc = db_session.query(Doctor).first()
        if first_doc:
            doctor_id = first_doc.id
        else:
            flash("No valid admitting doctor selected.", "danger")
            return redirect(url_for("ipd.dashboard"))

    try:
        admission = inpatient_service.admit_patient(
            db_session=db_session,
            patient_id=patient_id,
            bed_id=bed_id,
            admitting_doctor_id=doctor_id,
            admission_reason=admission_reason,
            department_id=department_id,
            notes=notes,
            actor_id=current_user_id,
            ip_address=request.remote_addr
        )
        db_session.commit()
        flash(f"Patient successfully admitted to Bed '{admission.bed.bed_number}'.", "success")
        return redirect(url_for("ipd.admission_detail", admission_id=admission.id))
    except (inpatient_service.BedUnavailableError, inpatient_service.PatientAlreadyAdmittedError) as e:
        db_session.rollback()
        flash(f"Admission Denied: {str(e)}", "danger")
    except inpatient_service.InpatientServiceError as e:
        db_session.rollback()
        flash(f"Admission Error: {str(e)}", "danger")
    except Exception as e:
        db_session.rollback()
        flash(f"System error during admission: {str(e)}", "danger")

    return redirect(url_for("ipd.dashboard"))


# =====================================================================
# Bed Transfer
# =====================================================================

@ipd_bp.route("/transfer/<int:admission_id>", methods=["POST"])
@login_required
@roles_required(RoleEnum.ADMIN, RoleEnum.DOCTOR, RoleEnum.NURSE)
def transfer_patient(admission_id: int):
    to_bed_id = request.form.get("to_bed_id", type=int)
    reason = request.form.get("reason")
    notes = request.form.get("notes")
    release_status_str = request.form.get("release_previous_as", "maintenance")

    if not to_bed_id or not reason:
        flash("Destination bed and reason for transfer are required.", "danger")
        return redirect(url_for("ipd.admission_detail", admission_id=admission_id))

    release_as = BedStatusEnum.MAINTENANCE
    if release_status_str.lower() == "available":
        release_as = BedStatusEnum.AVAILABLE

    try:
        current_user_id = session.get("user_id")
        transfer = inpatient_service.transfer_bed(
            db_session=db_session,
            admission_id=admission_id,
            to_bed_id=to_bed_id,
            reason=reason,
            transferred_by_id=current_user_id,
            notes=notes,
            release_previous_as=release_as,
            ip_address=request.remote_addr
        )
        db_session.commit()
        flash(
            f"Patient successfully transferred to Bed '{transfer.to_bed.bed_number}'.",
            "success"
        )
    except inpatient_service.BedUnavailableError as e:
        db_session.rollback()
        flash(f"Transfer Blocked: {str(e)}", "danger")
    except inpatient_service.InpatientServiceError as e:
        db_session.rollback()
        flash(f"Transfer Failed: {str(e)}", "danger")
    except Exception as e:
        db_session.rollback()
        flash(f"System error during bed transfer: {str(e)}", "danger")

    return redirect(url_for("ipd.admission_detail", admission_id=admission_id))


# =====================================================================
# Discharge Patient
# =====================================================================

@ipd_bp.route("/discharge/<int:admission_id>", methods=["POST"])
@login_required
@roles_required(RoleEnum.ADMIN, RoleEnum.DOCTOR, RoleEnum.NURSE)
def discharge_patient(admission_id: int):
    discharge_summary = request.form.get("discharge_summary")

    if not discharge_summary:
        flash("Discharge clinical summary is required.", "danger")
        return redirect(url_for("ipd.admission_detail", admission_id=admission_id))

    try:
        current_user_id = session.get("user_id")
        adm, invoice = inpatient_service.discharge_patient(
            db_session=db_session,
            admission_id=admission_id,
            discharge_summary=discharge_summary,
            actor_id=current_user_id,
            ip_address=request.remote_addr
        )
        db_session.commit()
        flash(
            f"Patient successfully discharged. Invoice #{invoice.invoice_number} generated (${invoice.total_amount:.2f}). Bed marked for MAINTENANCE.",
            "success"
        )
    except (ValueError, inpatient_service.InpatientServiceError) as e:
        db_session.rollback()
        flash(f"Discharge failed: {str(e)}", "danger")
    except Exception as e:
        db_session.rollback()
        flash(f"System error during discharge: {str(e)}", "danger")

    return redirect(url_for("ipd.admission_detail", admission_id=admission_id))


# =====================================================================
# Admissions List & History
# =====================================================================

@ipd_bp.route("/admissions")
@login_required
@roles_required(RoleEnum.ADMIN, RoleEnum.DOCTOR, RoleEnum.NURSE, RoleEnum.RECEPTIONIST)
def admissions():
    status_filter = request.args.get("status")
    department_id = request.args.get("department_id", type=int)
    patient_id = request.args.get("patient_id", type=int)
    search_query = request.args.get("q", "").strip()

    status_enum = None
    if status_filter and status_filter.upper() in AdmissionStatusEnum.__members__:
        status_enum = AdmissionStatusEnum[status_filter.upper()]

    admissions_list = inpatient_service.list_admissions(
        db_session=db_session,
        status=status_enum,
        patient_id=patient_id,
        department_id=department_id,
        search=search_query if search_query else None
    )

    departments = db_session.query(Department).all()
    stats = inpatient_service.get_ipd_dashboard_stats(db_session)

    return render_template(
        "ipd/admissions.html",
        active_page="ipd_admissions",
        admissions=admissions_list,
        departments=departments,
        stats=stats,
        current_status=status_filter,
        current_dept=department_id,
        search_query=search_query,
        AdmissionStatusEnum=AdmissionStatusEnum
    )


# =====================================================================
# Admission Detail & Clinical Chart
# =====================================================================

@ipd_bp.route("/admissions/<int:admission_id>")
@login_required
def admission_detail(admission_id: int):
    try:
        admission = inpatient_service.get_admission_detail(db_session, admission_id)
    except inpatient_service.AdmissionNotFoundError:
        flash("Admission record not found.", "danger")
        return redirect(url_for("ipd.admissions"))

    # If patient, verify they are viewing their own admission
    current_role = session.get("user_role")
    current_user_id = session.get("user_id")
    if current_role == "patient" and admission.patient_id != current_user_id:
        flash("Unauthorized access to admission record.", "danger")
        return redirect(url_for("patient.dashboard"))

    # Fetch available beds for transfer modal
    available_beds = inpatient_service.get_bed_availability(
        db_session=db_session,
        status=BedStatusEnum.AVAILABLE
    )

    # Patient's entire admission history
    patient_history = inpatient_service.get_patient_admission_history(
        db_session=db_session,
        patient_id=admission.patient_id
    )

    return render_template(
        "ipd/admission_detail.html",
        active_page="ipd_admissions",
        admission=admission,
        available_beds=available_beds,
        patient_history=patient_history,
        BedStatusEnum=BedStatusEnum,
        AdmissionStatusEnum=AdmissionStatusEnum
    )
