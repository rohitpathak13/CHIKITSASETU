import pytest
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session

from core.models import (
    User, Doctor, Patient, Department, Appointment, AuditLog,
    RoleEnum, GenderEnum, AppointmentStatusEnum
)
from core.security import get_password_hash
from core.services.appointment_service import (
    book_appointment, reschedule_appointment, cancel_appointment,
    complete_appointment, update_appointment_status, get_available_slots,
    AppointmentServiceError, DuplicateBookingError, DoctorUnavailableError,
    InvalidAppointmentDataError, AppointmentNotFoundError, AppointmentStateError,
    CLINIC_SLOTS
)


# =====================================================================
# Fixtures and Helpers
# =====================================================================

def create_user_helper(db: Session, email: str, role: RoleEnum, first_name: str, last_name: str, phone: str = "9876543210"):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email,
            password_hash=get_password_hash("Password123!"),
            role=role,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            is_active=True
        )
        db.add(user)
        db.commit()
    return user


def setup_clinical_fixtures(db: Session):
    """Creates a sample Department, Doctor, Patient, Admin, and Receptionist."""
    # 1. Department
    dept = db.query(Department).filter(Department.name == "Cardiology").first()
    if not dept:
        dept = Department(name="Cardiology", description="Heart and cardiovascular care", code="CARD", is_active=True)
        db.add(dept)
        db.commit()

    # 2. Doctor (Available Mon, Tue, Wed, Thu, Fri)
    doc_user = create_user_helper(db, "dr.verma@chikitsasetu.ai", RoleEnum.DOCTOR, "Sunil", "Verma", "9111111111")
    doctor = db.query(Doctor).filter(Doctor.id == doc_user.id).first()
    if not doctor:
        doctor = Doctor(
            id=doc_user.id,
            department_id=dept.id,
            specialization="Interventional Cardiology",
            license_number="MCI-CARD-991",
            qualification="MBBS, MD (Cardiology)",
            consultation_fee=Decimal("750.00"),
            available_days="Mon,Tue,Wed,Thu,Fri",
            room_number="Room 101"
        )
        db.add(doctor)
        db.commit()

    # 3. Patient
    pat_user = create_user_helper(db, "patient.vikram@chikitsasetu.ai", RoleEnum.PATIENT, "Vikram", "Seth", "9222222222")
    patient = db.query(Patient).filter(Patient.id == pat_user.id).first()
    if not patient:
        patient = Patient(
            id=pat_user.id,
            dob=date(1985, 4, 12),
            gender=GenderEnum.MALE,
            blood_group="B+",
            allergies="None",
            chronic_conditions="Hypertension",
            emergency_contact_name="Ananya Seth",
            emergency_contact_phone="9333333333",
            address="15 Park Street, Kolkata"
        )
        db.add(patient)
        db.commit()

    # 4. Second Patient (for isolation & collision tests)
    pat2_user = create_user_helper(db, "patient.priya@chikitsasetu.ai", RoleEnum.PATIENT, "Priya", "Sharma", "9444444444")
    patient2 = db.query(Patient).filter(Patient.id == pat2_user.id).first()
    if not patient2:
        patient2 = Patient(
            id=pat2_user.id,
            dob=date(1992, 8, 20),
            gender=GenderEnum.FEMALE,
            blood_group="A+",
            allergies="Sulfa",
            emergency_contact_name="Rahul Sharma",
            emergency_contact_phone="9555555555"
        )
        db.add(patient2)
        db.commit()

    # 5. Admin & Receptionist
    admin_user = create_user_helper(db, "admin.appt@chikitsasetu.ai", RoleEnum.ADMIN, "Super", "Admin")
    rec_user = create_user_helper(db, "rec.appt@chikitsasetu.ai", RoleEnum.RECEPTIONIST, "Rekha", "Desk")

    return {
        "dept": dept,
        "doctor": doctor,
        "patient": patient,
        "patient2": patient2,
        "admin": admin_user,
        "receptionist": rec_user
    }


def get_next_weekday(target_weekday_abbr: str, start_date: date = None) -> date:
    """Returns the date of the next occurrence of a weekday ('Mon', 'Tue', etc.)."""
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    target_idx = weekdays.index(target_weekday_abbr)
    curr = start_date or (date.today() + timedelta(days=1))
    while curr.weekday() != target_idx:
        curr += timedelta(days=1)
    return curr


def login_client(client, email: str, password: str = "Password123!"):
    client.get("/logout")
    return client.post("/login", data={"email": email, "password": password}, follow_redirects=True)


# =====================================================================
# 1. Service Layer Tests: Successful Booking & Token Generation
# =====================================================================

def test_service_successful_booking(db_session):
    fixtures = setup_clinical_fixtures(db_session)
    doctor = fixtures["doctor"]
    patient = fixtures["patient"]

    # Pick next Monday (doctor is available Mon-Fri)
    booking_date = get_next_weekday("Mon")
    slot_dt = f"{booking_date.strftime('%Y-%m-%d')}T10:00"

    appointment = book_appointment(
        db=db_session,
        patient_id=patient.id,
        doctor_id=doctor.id,
        appointment_datetime=slot_dt,
        reason="Routine Cardiac Follow-up",
        actor_id=patient.id
    )

    assert appointment is not None
    assert appointment.id is not None
    assert appointment.patient_id == patient.id
    assert appointment.doctor_id == doctor.id
    assert appointment.status == AppointmentStatusEnum.SCHEDULED
    assert appointment.token_number == 1
    assert appointment.no_show_probability is not None
    assert 0.0 <= appointment.no_show_probability <= 1.0

    # Verify audit log was recorded
    audit = db_session.query(AuditLog).filter(
        AuditLog.resource_type == "Appointment",
        AuditLog.resource_id == appointment.id,
        AuditLog.action == "APPOINTMENT_BOOKED"
    ).first()
    assert audit is not None
    assert audit.user_id == patient.id

    # Book second appointment on same date for different slot -> Token should be 2
    slot_dt2 = f"{booking_date.strftime('%Y-%m-%d')}T11:00"
    appointment2 = book_appointment(
        db=db_session,
        patient_id=fixtures["patient2"].id,
        doctor_id=doctor.id,
        appointment_datetime=slot_dt2,
        reason="Second patient review"
    )
    assert appointment2.token_number == 2


# =====================================================================
# 2. Service Layer Tests: Prevent Duplicate Booking
# =====================================================================

def test_service_prevent_duplicate_booking_for_doctor(db_session):
    fixtures = setup_clinical_fixtures(db_session)
    doctor = fixtures["doctor"]
    patient = fixtures["patient"]
    patient2 = fixtures["patient2"]

    booking_date = get_next_weekday("Tue")
    slot_dt = f"{booking_date.strftime('%Y-%m-%d')}T14:00"

    # Patient 1 books 14:00
    book_appointment(
        db=db_session,
        patient_id=patient.id,
        doctor_id=doctor.id,
        appointment_datetime=slot_dt,
        reason="Chest discomfort"
    )

    # Patient 2 attempts to book the SAME doctor at the exact same slot -> Must fail
    with pytest.raises(DuplicateBookingError) as exc_info:
        book_appointment(
            db=db_session,
            patient_id=patient2.id,
            doctor_id=doctor.id,
            appointment_datetime=slot_dt,
            reason="Palpitations"
        )
    assert "already booked" in str(exc_info.value)


def test_service_prevent_duplicate_booking_for_patient(db_session):
    fixtures = setup_clinical_fixtures(db_session)
    doctor1 = fixtures["doctor"]
    patient = fixtures["patient"]

    # Create a second doctor in the same or another department
    doc2_user = create_user_helper(db_session, "dr.kapoor@chikitsasetu.ai", RoleEnum.DOCTOR, "Anita", "Kapoor")
    doctor2 = Doctor(
        id=doc2_user.id,
        department_id=fixtures["dept"].id,
        specialization="Pediatric Cardiology",
        license_number="MCI-CARD-992",
        qualification="MBBS, DNB (Cardiology)",
        available_days="Mon,Tue,Wed,Thu,Fri"
    )
    db_session.add(doctor2)
    db_session.commit()

    booking_date = get_next_weekday("Wed")
    slot_dt = f"{booking_date.strftime('%Y-%m-%d')}T15:00"

    # Patient books doctor 1
    book_appointment(
        db=db_session,
        patient_id=patient.id,
        doctor_id=doctor1.id,
        appointment_datetime=slot_dt,
        reason="Consultation 1"
    )

    # Same patient attempts to book doctor 2 at the SAME datetime -> Must fail
    with pytest.raises(DuplicateBookingError) as exc_info:
        book_appointment(
            db=db_session,
            patient_id=patient.id,
            doctor_id=doctor2.id,
            appointment_datetime=slot_dt,
            reason="Consultation 2"
        )
    assert "already has an appointment scheduled" in str(exc_info.value)


# =====================================================================
# 3. Service Layer Tests: Unavailable Doctor
# =====================================================================

def test_service_doctor_unavailable_day(db_session):
    fixtures = setup_clinical_fixtures(db_session)
    doctor = fixtures["doctor"]  # Available Mon,Tue,Wed,Thu,Fri
    patient = fixtures["patient"]

    # Doctor is NOT available on Sunday
    sunday_date = get_next_weekday("Sun")
    sunday_slot = f"{sunday_date.strftime('%Y-%m-%d')}T10:00"

    with pytest.raises(DoctorUnavailableError) as exc_info:
        book_appointment(
            db=db_session,
            patient_id=patient.id,
            doctor_id=doctor.id,
            appointment_datetime=sunday_slot,
            reason="Sunday consultation"
        )
    assert "not available on Sundays" in str(exc_info.value)


def test_service_doctor_not_found(db_session):
    fixtures = setup_clinical_fixtures(db_session)
    patient = fixtures["patient"]
    booking_date = get_next_weekday("Mon")

    with pytest.raises(InvalidAppointmentDataError) as exc_info:
        book_appointment(
            db=db_session,
            patient_id=patient.id,
            doctor_id=999999,  # Non-existent doctor
            appointment_datetime=f"{booking_date.strftime('%Y-%m-%d')}T10:00"
        )
    assert "does not exist" in str(exc_info.value)


# =====================================================================
# 4. Service Layer Tests: Cancellation & Slot Re-booking
# =====================================================================

def test_service_cancellation_and_slot_freed(db_session):
    fixtures = setup_clinical_fixtures(db_session)
    doctor = fixtures["doctor"]
    patient = fixtures["patient"]
    patient2 = fixtures["patient2"]

    booking_date = get_next_weekday("Thu")
    slot_dt = f"{booking_date.strftime('%Y-%m-%d')}T11:30"

    # Patient 1 books slot
    appt = book_appointment(
        db=db_session,
        patient_id=patient.id,
        doctor_id=doctor.id,
        appointment_datetime=slot_dt,
        reason="Initial Consultation"
    )
    assert appt.status == AppointmentStatusEnum.SCHEDULED

    # Patient 1 cancels
    cancelled_appt = cancel_appointment(
        db=db_session,
        appointment_id=appt.id,
        actor_id=patient.id,
        cancellation_reason="Personal Emergency"
    )
    assert cancelled_appt.status == AppointmentStatusEnum.CANCELLED
    assert "Cancelled: Personal Emergency" in cancelled_appt.reason

    # Audit log check
    audit = db_session.query(AuditLog).filter(
        AuditLog.resource_id == appt.id,
        AuditLog.action == "APPOINTMENT_CANCELLED"
    ).first()
    assert audit is not None

    # Verify Patient 2 can now book this exact freed slot!
    appt2 = book_appointment(
        db=db_session,
        patient_id=patient2.id,
        doctor_id=doctor.id,
        appointment_datetime=slot_dt,
        reason="Urgent cardiac check"
    )
    assert appt2 is not None
    assert appt2.status == AppointmentStatusEnum.SCHEDULED


# =====================================================================
# 5. Service Layer Tests: Rescheduling
# =====================================================================

def test_service_reschedule_success(db_session):
    fixtures = setup_clinical_fixtures(db_session)
    doctor = fixtures["doctor"]
    patient = fixtures["patient"]

    mon_date = get_next_weekday("Mon")
    tue_date = get_next_weekday("Tue", start_date=mon_date + timedelta(days=1))

    slot_old = f"{mon_date.strftime('%Y-%m-%d')}T09:30"
    slot_new = f"{tue_date.strftime('%Y-%m-%d')}T14:30"

    appt = book_appointment(
        db=db_session,
        patient_id=patient.id,
        doctor_id=doctor.id,
        appointment_datetime=slot_old,
        reason="Routine visit"
    )

    rescheduled = reschedule_appointment(
        db=db_session,
        appointment_id=appt.id,
        new_datetime=slot_new,
        actor_id=patient.id,
        reason="Office clash on Monday"
    )

    assert rescheduled.id == appt.id
    assert rescheduled.appointment_datetime.strftime("%Y-%m-%d %H:%M") == f"{tue_date.strftime('%Y-%m-%d')} 14:30"
    assert rescheduled.status == AppointmentStatusEnum.SCHEDULED
    assert "Rescheduled: Office clash on Monday" in rescheduled.reason

    # Old slot should now be freed for another booking
    appt_other = book_appointment(
        db=db_session,
        patient_id=fixtures["patient2"].id,
        doctor_id=doctor.id,
        appointment_datetime=slot_old,
        reason="Other patient booked freed Monday slot"
    )
    assert appt_other is not None


def test_service_reschedule_collision_failure(db_session):
    fixtures = setup_clinical_fixtures(db_session)
    doctor = fixtures["doctor"]
    patient1 = fixtures["patient"]
    patient2 = fixtures["patient2"]

    mon_date = get_next_weekday("Mon")
    slot1 = f"{mon_date.strftime('%Y-%m-%d')}T10:00"
    slot2 = f"{mon_date.strftime('%Y-%m-%d')}T10:30"

    appt1 = book_appointment(db=db_session, patient_id=patient1.id, doctor_id=doctor.id, appointment_datetime=slot1)
    appt2 = book_appointment(db=db_session, patient_id=patient2.id, doctor_id=doctor.id, appointment_datetime=slot2)

    # Attempt to reschedule appt1 to appt2's slot (10:30) -> DuplicateBookingError
    with pytest.raises(DuplicateBookingError) as exc_info:
        reschedule_appointment(
            db=db_session,
            appointment_id=appt1.id,
            new_datetime=slot2
        )
    assert "already booked" in str(exc_info.value)


# =====================================================================
# 6. Service Layer Tests: Completion & State Immutability
# =====================================================================

def test_service_complete_appointment_lifecycle(db_session):
    fixtures = setup_clinical_fixtures(db_session)
    doctor = fixtures["doctor"]
    patient = fixtures["patient"]

    fri_date = get_next_weekday("Fri")
    slot = f"{fri_date.strftime('%Y-%m-%d')}T16:00"

    appt = book_appointment(
        db=db_session,
        patient_id=patient.id,
        doctor_id=doctor.id,
        appointment_datetime=slot,
        reason="Hypertension check"
    )

    # Mark completed by doctor
    completed_appt = complete_appointment(
        db=db_session,
        appointment_id=appt.id,
        actor_id=doctor.id
    )
    assert completed_appt.status == AppointmentStatusEnum.COMPLETED

    # Verify state immutability: Cannot cancel completed appointment
    with pytest.raises(AppointmentStateError) as exc_cancel:
        cancel_appointment(db=db_session, appointment_id=appt.id)
    assert "Cannot cancel an already completed appointment" in str(exc_cancel.value)

    # Verify state immutability: Cannot reschedule completed appointment
    next_mon = get_next_weekday("Mon", start_date=fri_date + timedelta(days=1))
    with pytest.raises(AppointmentStateError) as exc_resched:
        reschedule_appointment(
            db=db_session,
            appointment_id=appt.id,
            new_datetime=f"{next_mon.strftime('%Y-%m-%d')}T10:00"
        )
    assert "Cannot reschedule a completed appointment" in str(exc_resched.value)


# =====================================================================
# 7. Service Layer Tests: Invalid Data Validation
# =====================================================================

def test_service_past_date_booking_rejected(db_session):
    fixtures = setup_clinical_fixtures(db_session)
    doctor = fixtures["doctor"]
    patient = fixtures["patient"]

    past_date = date.today() - timedelta(days=3)
    past_slot = f"{past_date.strftime('%Y-%m-%d')}T10:00"

    with pytest.raises(InvalidAppointmentDataError) as exc_info:
        book_appointment(
            db=db_session,
            patient_id=patient.id,
            doctor_id=doctor.id,
            appointment_datetime=past_slot
        )
    assert "past date" in str(exc_info.value)


def test_service_invalid_datetime_format(db_session):
    fixtures = setup_clinical_fixtures(db_session)
    with pytest.raises(InvalidAppointmentDataError) as exc_info:
        book_appointment(
            db=db_session,
            patient_id=fixtures["patient"].id,
            doctor_id=fixtures["doctor"].id,
            appointment_datetime="invalid-date-format"
        )
    assert "Invalid date/time format" in str(exc_info.value)


def test_service_status_transition_invalid_value(db_session):
    fixtures = setup_clinical_fixtures(db_session)
    fri_date = get_next_weekday("Fri")
    appt = book_appointment(
        db=db_session,
        patient_id=fixtures["patient"].id,
        doctor_id=fixtures["doctor"].id,
        appointment_datetime=f"{fri_date.strftime('%Y-%m-%d')}T11:00"
    )

    with pytest.raises(InvalidAppointmentDataError) as exc_info:
        update_appointment_status(
            db=db_session,
            appointment_id=appt.id,
            new_status="unknown_status"
        )
    assert "Invalid status value" in str(exc_info.value)


# =====================================================================
# 8. Service Layer Tests: Doctor Available Slots Calculation
# =====================================================================

def test_service_get_available_slots(db_session):
    fixtures = setup_clinical_fixtures(db_session)
    doctor = fixtures["doctor"]
    mon_date = get_next_weekday("Mon")

    # Initial query: all slots free
    slots_data = get_available_slots(db_session, doctor.id, mon_date)
    assert slots_data["is_available"] is True
    assert len(slots_data["booked_slots"]) == 0
    assert len(slots_data["free_slots"]) == len(CLINIC_SLOTS)

    # Book 10:00 and 11:30
    book_appointment(db=db_session, patient_id=fixtures["patient"].id, doctor_id=doctor.id,
                     appointment_datetime=f"{mon_date.strftime('%Y-%m-%d')}T10:00")
    book_appointment(db=db_session, patient_id=fixtures["patient2"].id, doctor_id=doctor.id,
                     appointment_datetime=f"{mon_date.strftime('%Y-%m-%d')}T11:30")

    updated_slots = get_available_slots(db_session, doctor.id, mon_date)
    assert "10:00" in updated_slots["booked_slots"]
    assert "11:30" in updated_slots["booked_slots"]
    assert "10:00" not in updated_slots["free_slots"]
    assert "11:30" not in updated_slots["free_slots"]
    assert len(updated_slots["free_slots"]) == len(CLINIC_SLOTS) - 2


# =====================================================================
# 9. Web Integration: Patient Booking & Cancellation Flow
# =====================================================================

def test_web_patient_book_and_cancel_appointment(flask_client, db_session):
    fixtures = setup_clinical_fixtures(db_session)
    patient = fixtures["patient"]
    doctor = fixtures["doctor"]

    login_client(flask_client, patient.user.email)

    mon_date = get_next_weekday("Mon")
    post_data = {
        "doctor_id": str(doctor.id),
        "appointment_date": mon_date.strftime("%Y-%m-%d"),
        "time_slot": "10:30",
        "reason": "Chest discomfort check"
    }

    # Book appointment
    response = flask_client.post("/appointments/book", data=post_data, follow_redirects=True)
    assert response.status_code == 200
    assert b"Appointment booked successfully" in response.data or b"Token #" in response.data

    # Check database
    created = db_session.query(Appointment).filter(
        Appointment.patient_id == patient.id,
        Appointment.doctor_id == doctor.id,
        Appointment.status == AppointmentStatusEnum.SCHEDULED
    ).first()
    assert created is not None
    assert created.appointment_datetime.strftime("%H:%M") == "10:30"

    # Patient cancels appointment
    cancel_resp = flask_client.post(
        f"/appointments/{created.id}/cancel",
        data={"cancellation_reason": "Feeling much better"},
        follow_redirects=True
    )
    assert cancel_resp.status_code == 200

    db_session.refresh(created)
    assert created.status == AppointmentStatusEnum.CANCELLED


# =====================================================================
# 10. Web Integration: Staff Booking, Status Updates & Rescheduling
# =====================================================================

def test_web_staff_booking_and_rescheduling(flask_client, db_session):
    fixtures = setup_clinical_fixtures(db_session)
    receptionist = fixtures["receptionist"]
    patient = fixtures["patient"]
    doctor = fixtures["doctor"]

    login_client(flask_client, receptionist.email)

    wed_date = get_next_weekday("Wed")
    post_data = {
        "patient_id": str(patient.id),
        "doctor_id": str(doctor.id),
        "appointment_date": wed_date.strftime("%Y-%m-%d"),
        "time_slot": "14:00",
        "reason": "Routine Consultation via Reception"
    }

    # Staff books
    res = flask_client.post("/appointments/book", data=post_data, follow_redirects=True)
    assert res.status_code == 200
    assert b"Appointment booked successfully" in res.data or b"Token #" in res.data

    created = db_session.query(Appointment).filter(
        Appointment.patient_id == patient.id,
        Appointment.doctor_id == doctor.id,
        Appointment.status == AppointmentStatusEnum.SCHEDULED
    ).first()
    assert created is not None

    # Reschedule via Web
    thu_date = get_next_weekday("Thu")
    resched_data = {
        "appointment_date": thu_date.strftime("%Y-%m-%d"),
        "time_slot": "15:30",
        "reason": "Rescheduled by receptionist per patient call"
    }
    resched_resp = flask_client.post(
        f"/appointments/{created.id}/reschedule",
        data=resched_data,
        follow_redirects=True
    )
    assert resched_resp.status_code == 200
    assert b"rescheduled" in resched_resp.data

    db_session.refresh(created)
    assert created.appointment_datetime.strftime("%H:%M") == "15:30"
    assert created.appointment_datetime.date() == thu_date


# =====================================================================
# 11. Web Integration: Doctor Appointment Completion
# =====================================================================

def test_web_doctor_complete_appointment(flask_client, db_session):
    fixtures = setup_clinical_fixtures(db_session)
    doctor = fixtures["doctor"]
    patient = fixtures["patient"]

    fri_date = get_next_weekday("Fri")
    appt = book_appointment(
        db=db_session,
        patient_id=patient.id,
        doctor_id=doctor.id,
        appointment_datetime=f"{fri_date.strftime('%Y-%m-%d')}T11:00",
        reason="Annual checkup"
    )

    login_client(flask_client, doctor.user.email)
    comp_resp = flask_client.post(f"/appointments/{appt.id}/complete", follow_redirects=True)
    assert comp_resp.status_code == 200

    updated_appt = db_session.query(Appointment).filter(Appointment.id == appt.id).first()
    assert updated_appt.status == AppointmentStatusEnum.COMPLETED


# =====================================================================
# 12. Web Integration: Search and Filtering Roster
# =====================================================================

def test_web_appointments_search_and_filters(flask_client, db_session):
    fixtures = setup_clinical_fixtures(db_session)
    admin = fixtures["admin"]
    doctor = fixtures["doctor"]
    patient1 = fixtures["patient"]
    patient2 = fixtures["patient2"]

    mon_date = get_next_weekday("Mon")
    book_appointment(db=db_session, patient_id=patient1.id, doctor_id=doctor.id,
                     appointment_datetime=f"{mon_date.strftime('%Y-%m-%d')}T09:00", reason="Cardio Followup")
    book_appointment(db=db_session, patient_id=patient2.id, doctor_id=doctor.id,
                     appointment_datetime=f"{mon_date.strftime('%Y-%m-%d')}T09:30", reason="ECG evaluation")

    login_client(flask_client, admin.email)

    # 1. Search by patient first name
    res_search = flask_client.get("/appointments/?q=Vikram")
    assert res_search.status_code == 200
    assert b"Seth" in res_search.data

    # 2. Filter by Status
    res_status = flask_client.get("/appointments/?status=scheduled")
    assert res_status.status_code == 200

    # 3. Filter by Doctor
    res_doc = flask_client.get(f"/appointments/?doctor_id={doctor.id}")
    assert res_doc.status_code == 200

    # 4. Filter by Department
    res_dept = flask_client.get(f"/appointments/?department_id={fixtures['dept'].id}")
    assert res_dept.status_code == 200


# =====================================================================
# 13. Web Integration: Doctor Slots Availability API
# =====================================================================

def test_web_api_doctor_slots(flask_client, db_session):
    fixtures = setup_clinical_fixtures(db_session)
    login_client(flask_client, fixtures["admin"].email)
    doctor = fixtures["doctor"]
    mon_date = get_next_weekday("Mon")

    # Call API for Monday
    resp = flask_client.get(f"/appointments/api/doctor-slots?doctor_id={doctor.id}&date={mon_date.strftime('%Y-%m-%d')}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["is_available"] is True
    assert "free_slots" in data
    assert "09:00" in data["free_slots"]

    # Call API for Sunday (unavailable)
    sun_date = get_next_weekday("Sun")
    resp_sun = flask_client.get(f"/appointments/api/doctor-slots?doctor_id={doctor.id}&date={sun_date.strftime('%Y-%m-%d')}")
    assert resp_sun.status_code == 200
    data_sun = resp_sun.get_json()
    assert data_sun["is_available"] is False
    assert len(data_sun["free_slots"]) == 0


# =====================================================================
# 14. RBAC Boundary & Access Isolation Tests
# =====================================================================

def test_web_rbac_patient_cannot_tamper_other_patient_appointment(flask_client, db_session):
    fixtures = setup_clinical_fixtures(db_session)
    patient1 = fixtures["patient"]
    patient2 = fixtures["patient2"]
    doctor = fixtures["doctor"]

    mon_date = get_next_weekday("Mon")
    appt1 = book_appointment(
        db=db_session,
        patient_id=patient1.id,
        doctor_id=doctor.id,
        appointment_datetime=f"{mon_date.strftime('%Y-%m-%d')}T12:00"
    )

    # Login as Patient 2 and attempt to cancel Patient 1's appointment
    login_client(flask_client, patient2.user.email)
    malicious_cancel = flask_client.post(f"/appointments/{appt1.id}/cancel")
    assert malicious_cancel.status_code == 403

    # Attempt to reschedule Patient 1's appointment
    malicious_resched = flask_client.post(
        f"/appointments/{appt1.id}/reschedule",
        data={"appointment_date": mon_date.strftime("%Y-%m-%d"), "time_slot": "14:00"}
    )
    assert malicious_resched.status_code == 403

    # Attempt to complete Patient 1's appointment
    malicious_comp = flask_client.post(f"/appointments/{appt1.id}/complete")
    assert malicious_comp.status_code == 403
