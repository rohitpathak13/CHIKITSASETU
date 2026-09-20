import pytest
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
from core.models import (
    User, Doctor, Patient, Department, Room, Bed, Appointment,
    MedicalRecord, Diagnosis, Prescription, PrescriptionItem, Medicine,
    LabTest, LabOrder, LabResult, Admission, AuditLog,
    RoleEnum, GenderEnum, AppointmentStatusEnum, PrescriptionStatusEnum,
    LabOrderStatusEnum, RoomTypeEnum, BedStatusEnum, AdmissionStatusEnum
)
from core.security import get_password_hash


def create_user(db_session, email, role, first_name="Test", last_name="User", phone=None):
    user = db_session.query(User).filter(User.email == email).first()
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
        db_session.add(user)
        db_session.commit()
    return user


def login_user(flask_client, email, password="Password123!"):
    flask_client.get("/logout")
    return flask_client.post("/login", data={"email": email, "password": password}, follow_redirects=True)


# =====================================================================
# 1. Doctor Dashboard & Today's / Pending / Completed Queues
# =====================================================================

def test_doctor_dashboard_kpis_and_queues(flask_client, db_session):
    # Setup Dept & Doctor
    dept = Department(name="Neurology Clinic", code="NEURO", is_active=True)
    db_session.add(dept)
    db_session.flush()

    doc_user = create_user(db_session, "doc_dash@medicare.ai", RoleEnum.DOCTOR, "Vikram", "Sarabhai")
    doc = Doctor(
        id=doc_user.id,
        department_id=dept.id,
        specialization="Neurology",
        qualification="MBBS, DM (Neurology)",
        license_number="LIC-NEURO-001",
        consultation_fee=Decimal("900.00"),
        room_number="Room 305",
        available_days="Mon,Tue,Wed,Thu,Fri"
    )
    db_session.add(doc)
    db_session.flush()

    # Create Patients
    p1_user = create_user(db_session, "p1_dash@test.ai", RoleEnum.PATIENT, "Patient", "One")
    p1 = Patient(id=p1_user.id, dob=date(1985, 1, 1), gender=GenderEnum.MALE)
    db_session.add(p1)

    p2_user = create_user(db_session, "p2_dash@test.ai", RoleEnum.PATIENT, "Patient", "Two")
    p2 = Patient(id=p2_user.id, dob=date(1990, 2, 2), gender=GenderEnum.FEMALE)
    db_session.add(p2)

    p3_user = create_user(db_session, "p3_dash@test.ai", RoleEnum.PATIENT, "Patient", "Three")
    p3 = Patient(id=p3_user.id, dob=date(1995, 3, 3), gender=GenderEnum.MALE)
    db_session.add(p3)

    db_session.flush()

    today = date.today()
    # 1. Today's Appointment (Pending / Scheduled)
    app1 = Appointment(
        patient_id=p1.id,
        doctor_id=doc.id,
        appointment_datetime=datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(hours=10),
        status=AppointmentStatusEnum.SCHEDULED,
        reason="Migraine aura evaluation",
        token_number=1,
        no_show_probability=0.15
    )
    db_session.add(app1)

    # 2. Today's Appointment (Completed)
    app2 = Appointment(
        patient_id=p2.id,
        doctor_id=doc.id,
        appointment_datetime=datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(hours=11),
        status=AppointmentStatusEnum.COMPLETED,
        reason="Follow-up after EEG",
        token_number=2
    )
    db_session.add(app2)

    # 3. Future Appointment (Pending)
    future_date = today + timedelta(days=5)
    app3 = Appointment(
        patient_id=p3.id,
        doctor_id=doc.id,
        appointment_datetime=datetime.combine(future_date, datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(hours=14),
        status=AppointmentStatusEnum.CONFIRMED,
        reason="Nerve conduction study",
        token_number=1
    )
    db_session.add(app3)

    # 4. Inpatient Admission under this doctor
    room = Room(room_number="Ward-B-101", room_type=RoomTypeEnum.GENERAL, floor=3, total_beds=4, daily_rate=Decimal("1200.00"), department_id=dept.id)
    db_session.add(room)
    db_session.flush()

    bed = Bed(bed_number="B-101-A", room_id=room.id, status=BedStatusEnum.OCCUPIED)
    db_session.add(bed)
    db_session.flush()

    adm = Admission(
        patient_id=p1.id,
        admitting_doctor_id=doc.id,
        bed_id=bed.id,
        admission_date=datetime.now(timezone.utc),
        admission_reason="Acute Neurological Observation",
        status=AdmissionStatusEnum.ADMITTED
    )
    db_session.add(adm)
    db_session.commit()

    # Login as Doctor
    login_user(flask_client, "doc_dash@medicare.ai")
    resp = flask_client.get("/doctor/")
    assert resp.status_code == 200

    html = resp.data.decode("utf-8")
    assert "Dr. Vikram Sarabhai" in html
    assert "Neurology" in html
    assert "Neurology Clinic" in html
    assert "LIC-NEURO-001" in html

    # KPIs check
    assert "Migraine aura evaluation" in html
    assert "Follow-up after EEG" in html
    assert "Acute Neurological Observation" in html


# =====================================================================
# 2. Doctor Profile View & Update Validation
# =====================================================================

def test_doctor_profile_view_and_update(flask_client, db_session):
    dept = Department(name="Pediatrics Ward", code="PEDIATRICS", is_active=True)
    db_session.add(dept)
    db_session.flush()

    doc_user = create_user(db_session, "doc_prof@medicare.ai", RoleEnum.DOCTOR, "Ananya", "Sen", phone="+91 9123456789")
    doc = Doctor(
        id=doc_user.id,
        department_id=dept.id,
        specialization="Pediatrics",
        qualification="MBBS, DCH",
        license_number="LIC-PED-099",
        consultation_fee=Decimal("600.00"),
        room_number="Room 102",
        available_days="Mon,Wed,Fri"
    )
    db_session.add(doc)
    db_session.commit()

    login_user(flask_client, "doc_prof@medicare.ai")

    # 1. GET Profile View
    resp = flask_client.get("/doctor/profile")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "Dr. Ananya Sen" in html
    assert "Pediatrics" in html
    assert "LIC-PED-099" in html
    assert "MBBS, DCH" in html

    # 2. POST Valid Profile Update
    update_data = {
        "phone": "+91 9998887777",
        "room_number": "Room 204 OPD",
        "qualification": "MBBS, MD (Pediatrics), FAAP",
        "consultation_fee": "750.00",
        "available_days": ["Mon", "Tue", "Thu", "Sat"]
    }
    resp_post = flask_client.post("/doctor/profile", data=update_data)
    assert resp_post.status_code == 302

    db_session.expire_all()
    updated_doc = db_session.query(Doctor).filter(Doctor.id == doc.id).first()
    assert updated_doc.user.phone == "+91 9998887777"
    assert updated_doc.room_number == "Room 204 OPD"
    assert updated_doc.qualification == "MBBS, MD (Pediatrics), FAAP"
    assert updated_doc.consultation_fee == Decimal("750.00")
    assert "Mon" in updated_doc.available_days and "Sat" in updated_doc.available_days

    # Verify Audit Log
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "DOCTOR_PROFILE_UPDATED",
        AuditLog.resource_id == doc.id
    ).first()
    assert audit is not None

    # 3. Validation: Missing Qualification
    bad_qual = {
        "qualification": "",
        "available_days": ["Mon"]
    }
    resp_bad = flask_client.post("/doctor/profile", data=bad_qual)
    assert resp_bad.status_code == 400
    assert b"qualification is required" in resp_bad.data

    # 4. Validation: No available days selected
    bad_days = {
        "qualification": "MBBS",
        "available_days": []
    }
    resp_no_days = flask_client.post("/doctor/profile", data=bad_days)
    assert resp_no_days.status_code == 400
    assert b"available day must be selected" in resp_no_days.data

    # 5. Validation: Negative consultation fee
    neg_fee = {
        "qualification": "MBBS",
        "available_days": ["Mon"],
        "consultation_fee": "-100"
    }
    resp_neg = flask_client.post("/doctor/profile", data=neg_fee)
    assert resp_neg.status_code == 400
    assert b"cannot be negative" in resp_neg.data


# =====================================================================
# 3. Appointment Schedule & Status Management
# =====================================================================

def test_doctor_schedule_date_and_status_filtering(flask_client, db_session):
    dept = Department(name="Dermatology Dept", code="DERM_TEST", is_active=True)
    db_session.add(dept)
    db_session.flush()

    doc_user = create_user(db_session, "doc_sched@medicare.ai", RoleEnum.DOCTOR, "Deepa", "Iyer")
    doc = Doctor(
        id=doc_user.id,
        department_id=dept.id,
        specialization="Dermatology",
        qualification="MBBS, MD Dermatology",
        license_number="LIC-DERM-404",
        consultation_fee=Decimal("700.00")
    )
    db_session.add(doc)
    db_session.flush()

    pt_user = create_user(db_session, "pt_sched@test.ai", RoleEnum.PATIENT, "Ravi", "Verma")
    pt = Patient(id=pt_user.id, dob=date(1992, 5, 5), gender=GenderEnum.MALE)
    db_session.add(pt)
    db_session.flush()

    today = date.today()
    appt_today = Appointment(
        patient_id=pt.id,
        doctor_id=doc.id,
        appointment_datetime=datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(hours=10),
        status=AppointmentStatusEnum.SCHEDULED,
        reason="Skin allergy patch test",
        token_number=1
    )
    db_session.add(appt_today)

    appt_past = Appointment(
        patient_id=pt.id,
        doctor_id=doc.id,
        appointment_datetime=datetime.combine(today - timedelta(days=3), datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(hours=15),
        status=AppointmentStatusEnum.COMPLETED,
        reason="Psoriasis review",
        token_number=3
    )
    db_session.add(appt_past)
    db_session.commit()

    login_user(flask_client, "doc_sched@medicare.ai")

    # 1. Default schedule (defaults to today)
    resp = flask_client.get("/doctor/schedule")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "Skin allergy patch test" in html

    # 2. Show all schedule
    resp_all = flask_client.get("/doctor/schedule?date=all")
    assert resp_all.status_code == 200
    html_all = resp_all.data.decode("utf-8")
    assert "Skin allergy patch test" in html_all
    assert "Psoriasis review" in html_all

    # 3. Filter by status=completed
    resp_comp = flask_client.get("/doctor/schedule?date=all&status=completed")
    assert resp_comp.status_code == 200
    html_comp = resp_comp.data.decode("utf-8")
    assert "Psoriasis review" in html_comp
    assert "Skin allergy patch test" not in html_comp

    # 4. POST Status Transition: Update appt_today to confirmed
    resp_update = flask_client.post("/doctor/schedule", data={
        "appointment_id": appt_today.id,
        "status": "confirmed"
    })
    assert resp_update.status_code == 302

    db_session.expire_all()
    updated_appt = db_session.query(Appointment).filter(Appointment.id == appt_today.id).first()
    assert updated_appt.status == AppointmentStatusEnum.CONFIRMED

    # Verify Audit Log
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "APPOINTMENT_STATUS_UPDATED",
        AuditLog.resource_id == appt_today.id
    ).first()
    assert audit is not None


# =====================================================================
# 4. Doctor Patients List (Outpatients & Inpatients)
# =====================================================================

def test_doctor_patient_list_outpatients_and_inpatients(flask_client, db_session):
    dept = Department(name="Orthopedics Dept", code="ORTHO_TEST", is_active=True)
    db_session.add(dept)
    db_session.flush()

    doc_user = create_user(db_session, "doc_pts@medicare.ai", RoleEnum.DOCTOR, "Harish", "Patel")
    doc = Doctor(
        id=doc_user.id,
        department_id=dept.id,
        specialization="Orthopedics",
        qualification="MS Ortho",
        license_number="LIC-ORTHO-111",
        consultation_fee=Decimal("800.00")
    )
    db_session.add(doc)
    db_session.flush()

    # Outpatient
    op_user = create_user(db_session, "op_pat@test.ai", RoleEnum.PATIENT, "Tarun", "Shah", phone="+91 9811111111")
    op_pt = Patient(id=op_user.id, dob=date(1988, 8, 8), gender=GenderEnum.MALE, blood_group="O+")
    db_session.add(op_pt)
    db_session.flush()

    op_appt = Appointment(
        patient_id=op_pt.id,
        doctor_id=doc.id,
        appointment_datetime=datetime.now(timezone.utc),
        status=AppointmentStatusEnum.SCHEDULED,
        reason="Knee ligament sprain"
    )
    db_session.add(op_appt)

    # Inpatient
    ip_user = create_user(db_session, "ip_pat@test.ai", RoleEnum.PATIENT, "Geeta", "Shah", phone="+91 9822222222")
    ip_pt = Patient(id=ip_user.id, dob=date(1975, 4, 4), gender=GenderEnum.FEMALE, blood_group="A+")
    db_session.add(ip_pt)
    db_session.flush()

    room = Room(room_number="Room-401", room_type=RoomTypeEnum.GENERAL, floor=4, total_beds=1, daily_rate=Decimal("3000.00"), department_id=dept.id)
    db_session.add(room)
    db_session.flush()

    bed = Bed(bed_number="401-1", room_id=room.id, status=BedStatusEnum.OCCUPIED)
    db_session.add(bed)
    db_session.flush()

    ip_adm = Admission(
        patient_id=ip_pt.id,
        admitting_doctor_id=doc.id,
        bed_id=bed.id,
        admission_date=datetime.now(timezone.utc),
        admission_reason="Femur fracture surgery post-op",
        status=AdmissionStatusEnum.ADMITTED
    )
    db_session.add(ip_adm)
    db_session.commit()

    login_user(flask_client, "doc_pts@medicare.ai")

    # 1. All Patients
    resp = flask_client.get("/doctor/patients")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "Tarun Shah" in html
    assert "Geeta Shah" in html

    # 2. Filter by Outpatient
    resp_op = flask_client.get("/doctor/patients?type=outpatient")
    assert resp_op.status_code == 200
    html_op = resp_op.data.decode("utf-8")
    assert "Tarun Shah" in html_op
    assert "Geeta Shah" not in html_op

    # 3. Filter by Inpatient
    resp_ip = flask_client.get("/doctor/patients?type=inpatient")
    assert resp_ip.status_code == 200
    html_ip = resp_ip.data.decode("utf-8")
    assert "Geeta Shah" in html_ip
    assert "Tarun Shah" not in html_ip

    # 4. Search by Name
    resp_search = flask_client.get("/doctor/patients?q=Tarun")
    assert resp_search.status_code == 200
    assert b"Tarun Shah" in resp_search.data
    assert b"Geeta Shah" not in resp_search.data


# =====================================================================
# 5. Patient Longitudinal Medical History Access (Clinical RBAC)
# =====================================================================

def test_doctor_patient_medical_history_access(flask_client, db_session):
    dept = Department(name="General Medicine", code="GEN_MED", is_active=True)
    db_session.add(dept)
    db_session.flush()

    doc_user = create_user(db_session, "doc_hist@medicare.ai", RoleEnum.DOCTOR, "Dr. Sunita", "Williams")
    doc = Doctor(
        id=doc_user.id,
        department_id=dept.id,
        specialization="Internal Medicine",
        qualification="MBBS, MD",
        license_number="LIC-MED-777",
        consultation_fee=Decimal("650.00")
    )
    db_session.add(doc)
    db_session.flush()

    # Patient A (Doctor HAS a relationship with)
    pa_user = create_user(db_session, "pa_hist@test.ai", RoleEnum.PATIENT, "Ramesh", "Kumar")
    pa = Patient(
        id=pa_user.id,
        dob=date(1980, 10, 10),
        gender=GenderEnum.MALE,
        blood_group="B+",
        allergies="Aspirin",
        chronic_conditions="Hypertension"
    )
    db_session.add(pa)
    db_session.flush()

    appt_a = Appointment(
        patient_id=pa.id,
        doctor_id=doc.id,
        appointment_datetime=datetime.now(timezone.utc),
        status=AppointmentStatusEnum.COMPLETED,
        reason="Routine clinical check"
    )
    db_session.add(appt_a)
    db_session.flush()

    rec = MedicalRecord(
        patient_id=pa.id,
        doctor_id=doc.id,
        visit_date=date.today(),
        symptoms="Chronic headache and elevated BP",
        diagnosis="Stage 2 Hypertension",
        vitals_bp="142/92",
        vitals_pulse=80,
        clinical_notes="Prescribed Telmisartan."
    )
    db_session.add(rec)
    db_session.flush()

    diag = Diagnosis(
        patient_id=pa.id,
        doctor_id=doc.id,
        diagnosis_code="I10",
        diagnosis_name="Essential Hypertension",
        status="Active",
        diagnosed_date=date.today()
    )
    db_session.add(diag)
    db_session.flush()

    # Patient B (Doctor has NO relationship with)
    pb_user = create_user(db_session, "pb_hist@test.ai", RoleEnum.PATIENT, "Unrelated", "Person")
    pb = Patient(id=pb_user.id, dob=date(1995, 1, 1), gender=GenderEnum.FEMALE)
    db_session.add(pb)
    db_session.commit()

    login_user(flask_client, "doc_hist@medicare.ai")

    # 1. Doctor can view Patient A's medical history
    resp_pa = flask_client.get(f"/doctor/patient/{pa.id}/history")
    assert resp_pa.status_code == 200
    html = resp_pa.data.decode("utf-8")
    assert "Ramesh Kumar" in html
    assert f"PAT-{pa.id:05d}" in html
    assert "Aspirin" in html
    assert "Stage 2 Hypertension" in html
    assert "I10" in html
    assert "142/92" in html

    # 2. Doctor CANNOT view Patient B's history (403 Forbidden - Clinical RBAC Boundary)
    resp_pb = flask_client.get(f"/doctor/patient/{pb.id}/history")
    assert resp_pb.status_code == 403

    # 3. Admin CAN view Patient B's history
    create_user(db_session, "admin_hist@medicare.ai", RoleEnum.ADMIN, "Admin", "Overwatch")
    login_user(flask_client, "admin_hist@medicare.ai")
    resp_admin = flask_client.get(f"/doctor/patient/{pb.id}/history")
    assert resp_admin.status_code == 200


# =====================================================================
# 6. Role-Based Access Control (RBAC) Security Boundaries
# =====================================================================

def test_doctor_management_rbac_permissions(flask_client, db_session):
    doc_user = create_user(db_session, "rbac_doc@medicare.ai", RoleEnum.DOCTOR, "Doctor", "Who")
    doc = Doctor(
        id=doc_user.id,
        specialization="General",
        qualification="MBBS",
        license_number="LIC-WHO-1",
        consultation_fee=Decimal("500.00")
    )
    db_session.add(doc)

    pat_user = create_user(db_session, "rbac_patient@medicare.ai", RoleEnum.PATIENT, "Patient", "User")
    pat = Patient(id=pat_user.id, dob=date(1990, 1, 1), gender=GenderEnum.MALE)
    db_session.add(pat)

    pharm_user = create_user(db_session, "rbac_pharm_doc@medicare.ai", RoleEnum.PHARMACIST, "Pharm", "User")
    lab_user = create_user(db_session, "rbac_lab_doc@medicare.ai", RoleEnum.LAB_TECHNICIAN, "Lab", "User")
    db_session.commit()

    # 1. Patient role attempting to access doctor workbench routes -> 403 Forbidden
    login_user(flask_client, "rbac_patient@medicare.ai")
    assert flask_client.get("/doctor/").status_code == 403
    assert flask_client.get("/doctor/schedule").status_code == 403
    assert flask_client.get("/doctor/profile").status_code == 403
    assert flask_client.get("/doctor/patients").status_code == 403

    # 2. Pharmacist role attempting to access doctor workbench -> 403 Forbidden
    login_user(flask_client, "rbac_pharm_doc@medicare.ai")
    assert flask_client.get("/doctor/").status_code == 403
    assert flask_client.get("/doctor/schedule").status_code == 403
    assert flask_client.get("/doctor/profile").status_code == 403

    # 3. Lab Tech role attempting to access doctor workbench -> 403 Forbidden
    login_user(flask_client, "rbac_lab_doc@medicare.ai")
    assert flask_client.get("/doctor/").status_code == 403
    assert flask_client.get("/doctor/schedule").status_code == 403

    # 4. Unauthenticated access -> 302 Redirect to Login
    flask_client.get("/logout")
    assert flask_client.get("/doctor/").status_code == 302
    assert flask_client.get("/doctor/schedule").status_code == 302
    assert flask_client.get("/doctor/profile").status_code == 302
