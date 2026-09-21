from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime, date, timezone
from sqlalchemy import func
from backend.database import db_session
from backend.models import (
    Appointment, PatientProfile, DoctorProfile, Ward, Bed, User,
    RoleEnum, GenderEnum, AppointmentStatusEnum, BedStatusEnum
)
from backend.security import get_password_hash
from backend.utils.decorators import login_required, roles_required
from ml.inference.predictors import no_show_predictor

receptionist_bp = Blueprint("receptionist", __name__, url_prefix="/receptionist")

import math

@receptionist_bp.route("/")
@login_required
@roles_required(RoleEnum.RECEPTIONIST, RoleEnum.ADMIN)
def dashboard():
    q = request.args.get("q", "").strip()

    query = db_session.query(Appointment)
    if q:
        query = query.join(Appointment.patient).join(PatientProfile.user).filter(
            (User.first_name.ilike(f"%{q}%")) |
            (User.last_name.ilike(f"%{q}%")) |
            (User.phone.ilike(f"%{q}%")) |
            (Appointment.token_number == (int(q) if q.isdigit() else -1))
        )

    appointments = query.order_by(Appointment.appointment_datetime.asc()).all()
    total_patients = db_session.query(PatientProfile).count()
    available_beds = db_session.query(Bed).filter(Bed.status == BedStatusEnum.AVAILABLE).count()

    return render_template(
        "receptionist/dashboard.html",
        active_page="rec_dashboard",
        appointments=appointments,
        total_patients=total_patients,
        available_beds=available_beds,
        search_query=q
    )

@receptionist_bp.route("/patients")
@login_required
@roles_required(RoleEnum.RECEPTIONIST, RoleEnum.ADMIN)
def patients_directory():
    q = request.args.get("q", "").strip()
    gender = request.args.get("gender", "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 8

    query = db_session.query(PatientProfile).join(PatientProfile.user)

    if q:
        query = query.filter(
            (User.first_name.ilike(f"%{q}%")) |
            (User.last_name.ilike(f"%{q}%")) |
            (User.phone.ilike(f"%{q}%")) |
            (User.email.ilike(f"%{q}%")) |
            (PatientProfile.blood_group.ilike(f"%{q}%"))
        )

    if gender and gender in [g.value for g in GenderEnum]:
        query = query.filter(PatientProfile.gender == GenderEnum(gender))

    total_count = query.count()
    total_pages = max(1, math.ceil(total_count / per_page))
    patients = query.order_by(PatientProfile.user_id.desc()).offset((page - 1) * per_page).limit(per_page).all()

    return render_template(
        "receptionist/patients.html",
        active_page="rec_patients",
        patients=patients,
        search_query=q,
        gender_filter=gender,
        current_page=page,
        total_pages=total_pages,
        total_count=total_count
    )

@receptionist_bp.route("/register", methods=["GET", "POST"])
@login_required
@roles_required(RoleEnum.RECEPTIONIST, RoleEnum.ADMIN)
def register_patient():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        phone = request.form.get("phone", "").strip()
        dob_str = request.form.get("dob")
        gender_str = request.form.get("gender")
        blood_group = request.form.get("blood_group")
        allergies = request.form.get("allergies")
        chronic = request.form.get("chronic_conditions")
        ec_name = request.form.get("emergency_contact_name")
        ec_phone = request.form.get("emergency_contact_phone")

        existing = db_session.query(User).filter(User.email == email).first()
        if existing:
            flash("Patient with this email already exists in system.", "danger")
            return render_template("receptionist/register.html", active_page="rec_register")

        try:
            dob_val = datetime.strptime(dob_str, "%Y-%m-%d").date()
        except Exception:
            flash("Invalid date of birth format.", "danger")
            return render_template("receptionist/register.html", active_page="rec_register")

        user = User(
            email=email,
            password_hash=get_password_hash("Password123!"),
            role=RoleEnum.PATIENT,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            is_active=True
        )
        db_session.add(user)
        db_session.flush()

        profile = PatientProfile(
            user_id=user.id,
            dob=dob_val,
            gender=GenderEnum(gender_str),
            blood_group=blood_group,
            allergies=allergies,
            chronic_conditions=chronic,
            emergency_contact_name=ec_name,
            emergency_contact_phone=ec_phone
        )
        db_session.add(profile)
        db_session.commit()

        flash(f"Patient {user.full_name} registered successfully. Default password is 'Password123!'.", "success")
        return redirect(url_for("receptionist.book_appointment", patient_id=user.id))

    return render_template("receptionist/register.html", active_page="rec_register")

@receptionist_bp.route("/book", methods=["GET", "POST"])
@login_required
@roles_required(RoleEnum.RECEPTIONIST, RoleEnum.ADMIN)
def book_appointment():
    patients = db_session.query(PatientProfile).all()
    doctors = db_session.query(DoctorProfile).all()
    selected_patient_id = request.args.get("patient_id")

    if request.method == "POST":
        patient_id = int(request.form.get("patient_id"))
        doctor_id = int(request.form.get("doctor_id"))
        appt_dt_str = request.form.get("appointment_datetime")
        reason = request.form.get("reason", "").strip()

        try:
            appt_dt = datetime.strptime(appt_dt_str, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
        except Exception:
            flash("Invalid appointment date and time.", "danger")
            return redirect(url_for("receptionist.book_appointment"))

        patient = db_session.query(PatientProfile).filter(PatientProfile.user_id == patient_id).first()
        doctor = db_session.query(DoctorProfile).filter(DoctorProfile.user_id == doctor_id).first()

        # Generate token number
        app_date = appt_dt.date()
        start_day = datetime.combine(app_date, datetime.min.time(), tzinfo=timezone.utc)
        end_day = datetime.combine(app_date, datetime.max.time(), tzinfo=timezone.utc)
        count_today = db_session.query(func.count(Appointment.id)).filter(
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_datetime >= start_day,
            Appointment.appointment_datetime <= end_day
        ).scalar() or 0
        token_num = count_today + 1

        # Run ML Appointment No-Show Prediction
        lead_time = max(0, (appt_dt.date() - date.today()).days)
        patient_age = max(1, (date.today() - patient.dob).days // 365)
        
        ml_features = {
            "age": patient_age,
            "gender": patient.gender.value if hasattr(patient.gender, "value") else str(patient.gender),
            "lead_time_days": lead_time,
            "day_of_week": appt_dt.strftime("%a"),
            "appointment_hour": appt_dt.hour,
            "department": doctor.department.name if doctor.department else "General Medicine",
            "historical_appointments": len(patient.appointments),
            "historical_no_show_ratio": 0.10,
            "sms_reminder_sent": 1
        }
        prediction = no_show_predictor.predict(ml_features)
        prob = prediction.get("no_show_probability", 0.15)
        recommendation = prediction.get("recommendation", "")

        appointment = Appointment(
            patient_id=patient_id,
            doctor_id=doctor_id,
            appointment_datetime=appt_dt,
            status=AppointmentStatusEnum.SCHEDULED,
            reason=reason,
            token_number=token_num,
            no_show_probability=prob
        )
        db_session.add(appointment)
        db_session.commit()

        flash(f"Appointment booked! Token #{token_num}. AI Triage: {recommendation}", "success")
        return redirect(url_for("receptionist.dashboard"))

    return render_template(
        "receptionist/book.html",
        active_page="rec_book",
        patients=patients,
        doctors=doctors,
        selected_patient_id=selected_patient_id
    )

@receptionist_bp.route("/beds")
@login_required
@roles_required(RoleEnum.RECEPTIONIST, RoleEnum.ADMIN, RoleEnum.NURSE)
def bed_lookup():
    wards = db_session.query(Ward).all()
    return render_template("receptionist/beds.html", active_page="rec_beds", wards=wards)
