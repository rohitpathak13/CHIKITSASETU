from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime, timezone
from decimal import Decimal
from backend.database import db_session
from backend.models import (
    Admission, Bed, Ward, MedicalRecord, PatientProfile,
    RoleEnum, BedStatusEnum, AdmissionStatusEnum
)
from backend.utils.decorators import login_required, roles_required

nurse_bp = Blueprint("nurse", __name__, url_prefix="/nurse")

@nurse_bp.route("/")
@login_required
@roles_required(RoleEnum.NURSE, RoleEnum.ADMIN)
def dashboard():
    admissions = db_session.query(Admission).filter(
        Admission.status == AdmissionStatusEnum.ADMITTED
    ).order_by(Admission.admission_date.desc()).all()

    total_occupied = sum(1 for a in admissions)
    total_beds = db_session.query(Bed).count()
    wards = db_session.query(Ward).all()
    maintenance_beds = db_session.query(Bed).filter(Bed.status == BedStatusEnum.MAINTENANCE).all()

    return render_template(
        "nurse/dashboard.html",
        active_page="nurse_dashboard",
        admissions=admissions,
        total_occupied=total_occupied,
        total_beds=total_beds,
        wards=wards,
        maintenance_beds=maintenance_beds
    )

@nurse_bp.route("/vitals", methods=["GET", "POST"])
@login_required
@roles_required(RoleEnum.NURSE, RoleEnum.ADMIN)
def log_vitals():
    admissions = db_session.query(Admission).filter(
        Admission.status == AdmissionStatusEnum.ADMITTED
    ).all()

    if request.method == "POST":
        admission_id = int(request.form.get("admission_id"))
        bp = request.form.get("vitals_bp", "").strip()
        pulse = request.form.get("vitals_pulse")
        temp = request.form.get("vitals_temp")
        spo2 = request.form.get("vitals_spo2")
        notes = request.form.get("notes", "").strip()

        adm = db_session.query(Admission).filter(Admission.id == admission_id).first()
        if not adm:
            flash("Admission record not found.", "danger")
            return redirect(url_for("nurse.dashboard"))

        # Add vital observation record to medical history
        vitals_entry = MedicalRecord(
            patient_id=adm.patient_id,
            doctor_id=adm.admitting_doctor_id,
            symptoms="Inpatient Routine Vital Signs Charting",
            diagnosis="Inpatient Monitoring Observation",
            clinical_notes=f"Recorded by Nurse {session.get('user_name')}: {notes}",
            vitals_bp=bp or None,
            vitals_pulse=int(pulse) if pulse else None,
            vitals_temp=Decimal(temp) if temp else None,
            vitals_spo2=int(spo2) if spo2 else None
        )
        db_session.add(vitals_entry)
        db_session.commit()

        flash(f"Vitals recorded successfully for {adm.patient.user.full_name} (Bed {adm.bed.bed_number}).", "success")
        return redirect(url_for("nurse.dashboard"))

    return render_template("nurse/vitals.html", active_page="nurse_vitals", admissions=admissions)

@nurse_bp.route("/bed/<int:bed_id>/release", methods=["POST"])
@login_required
@roles_required(RoleEnum.NURSE, RoleEnum.ADMIN)
def release_bed(bed_id: int):
    bed = db_session.query(Bed).filter(Bed.id == bed_id).first()
    if bed:
        bed.status = BedStatusEnum.AVAILABLE
        db_session.commit()
        flash(f"Bed {bed.bed_number} cleaned and released as AVAILABLE.", "success")
    return redirect(url_for("nurse.dashboard"))

@nurse_bp.route("/admission/<int:admission_id>/discharge", methods=["POST"])
@login_required
@roles_required(RoleEnum.NURSE, RoleEnum.ADMIN, RoleEnum.DOCTOR)
def discharge_inpatient(admission_id: int):
    from backend.services.discharge_billing import process_inpatient_discharge_and_billing

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
            f"Patient {adm.patient.user.full_name} successfully discharged. "
            f"Bed {adm.bed.bed_number} transitioned to MAINTENANCE. "
            f"Generated Invoice #{invoice.invoice_number} (Total: ${float(invoice.total_amount):.2f}).",
            "success"
        )
        return redirect(url_for("billing.invoice_detail", invoice_id=invoice.id))
    except Exception as e:
        db_session.rollback()
        flash(f"Discharge clearance failed: {str(e)}", "danger")
        return redirect(url_for("nurse.dashboard"))
