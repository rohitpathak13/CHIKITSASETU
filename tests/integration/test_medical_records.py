import pytest
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session

from core.models import (
    User, Doctor, Patient, Department, Appointment, MedicalRecord, Diagnosis,
    Prescription, PrescriptionItem, LabOrder, LabTestType, Medicine, Admission, Room, Bed,
    AuditLog, RoleEnum, GenderEnum, AppointmentStatusEnum, PrescriptionStatusEnum
)
from core.security import get_password_hash
from core.services.medical_record_service import (
    create_medical_record, update_medical_record, get_patient_medical_timeline,
    get_medical_record_detail, validate_vitals,
    MedicalRecordServiceError, InvalidMedicalRecordDataError,
    MedicalRecordNotFoundError, MedicalRecordPermissionError
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


def setup_emr_fixtures(db: Session):
    """Creates a sample Department, Doctor, Patient 1, Patient 2, and Admin."""
    dept = db.query(Department).filter(Department.name == "Internal Medicine").first()
    if not dept:
        dept = Department(name="Internal Medicine", description="Adult general medicine", code="IMED", is_active=True)
        db.add(dept)
        db.commit()

    # Doctor 1
    doc_user = create_user_helper(db, "dr.sharma@chikitsasetu.ai", RoleEnum.DOCTOR, "Alok", "Sharma")
    doctor = db.query(Doctor).filter(Doctor.id == doc_user.id).first()
    if not doctor:
        doctor = Doctor(
            id=doc_user.id,
            department_id=dept.id,
            specialization="Internal Medicine",
            license_number="MCI-IMED-101",
            qualification="MBBS, MD (General Medicine)",
            consultation_fee=Decimal("600.00"),
            available_days="Mon,Tue,Wed,Thu,Fri",
            room_number="Room 201"
        )
        db.add(doctor)
        db.commit()

    # Doctor 2 (for unauthorized edit tests)
    doc2_user = create_user_helper(db, "dr.nair@chikitsasetu.ai", RoleEnum.DOCTOR, "Ravi", "Nair")
    doctor2 = db.query(Doctor).filter(Doctor.id == doc2_user.id).first()
    if not doctor2:
        doctor2 = Doctor(
            id=doc2_user.id,
            department_id=dept.id,
            specialization="Pulmonology",
            license_number="MCI-PULM-102",
            qualification="MBBS, MD (Pulmonology)",
            consultation_fee=Decimal("700.00"),
            available_days="Mon,Wed,Fri"
        )
        db.add(doctor2)
        db.commit()

    # Patient 1
    pat1_user = create_user_helper(db, "pat.rohit@chikitsasetu.ai", RoleEnum.PATIENT, "Rohit", "Verma")
    patient1 = db.query(Patient).filter(Patient.id == pat1_user.id).first()
    if not patient1:
        patient1 = Patient(
            id=pat1_user.id,
            dob=date(1988, 6, 15),
            gender=GenderEnum.MALE,
            blood_group="O+",
            allergies=None,
            chronic_conditions="Asthma",
            emergency_contact_name="Sunita Verma",
            emergency_contact_phone="9876500001"
        )
        db.add(patient1)
        db.commit()

    # Patient 2 (for cross-patient access boundary tests)
    pat2_user = create_user_helper(db, "pat.meera@chikitsasetu.ai", RoleEnum.PATIENT, "Meera", "Sen")
    patient2 = db.query(Patient).filter(Patient.id == pat2_user.id).first()
    if not patient2:
        patient2 = Patient(
            id=pat2_user.id,
            dob=date(1994, 11, 23),
            gender=GenderEnum.FEMALE,
            blood_group="B+",
            allergies="Aspirin",
            emergency_contact_name="Amit Sen",
            emergency_contact_phone="9876500002"
        )
        db.add(patient2)
        db.commit()

    # Admin
    admin_user = create_user_helper(db, "admin.emr@chikitsasetu.ai", RoleEnum.ADMIN, "Admin", "Chief")

    # Pharmacist (unauthorized role)
    pharm_user = create_user_helper(db, "pharm.emr@chikitsasetu.ai", RoleEnum.PHARMACIST, "Prakash", "Chemist")

    return {
        "dept": dept,
        "doctor": doctor,
        "doctor2": doctor2,
        "patient1": patient1,
        "patient2": patient2,
        "patient1_user": pat1_user,
        "patient2_user": pat2_user,
        "admin": admin_user,
        "pharmacist": pharm_user
    }


def login_client(client, email: str, password: str = "Password123!"):
    client.get("/logout")
    return client.post("/login", data={"email": email, "password": password}, follow_redirects=True)


# =====================================================================
# 1. Service Layer: Comprehensive EMR Creation
# =====================================================================

def test_doctor_create_medical_record_full_fields(db_session):
    fixtures = setup_emr_fixtures(db_session)
    doctor = fixtures["doctor"]
    patient = fixtures["patient1"]

    follow_up = date.today() + timedelta(days=14)

    record = create_medical_record(
        db=db_session,
        patient_id=patient.id,
        doctor_id=doctor.id,
        symptoms="Productive cough with yellow sputum, low-grade fever for 3 days, mild dyspnea",
        diagnosis="Acute Bronchitis with Bronchospasm",
        clinical_notes="Chest bilateral wheezing noted. Advised warm steam inhalation and hydration.",
        vitals_bp="124/82",
        vitals_pulse=78,
        vitals_temp=Decimal("37.8"),
        vitals_spo2=97,
        vitals_weight=Decimal("74.5"),
        vitals_height=Decimal("178.0"),
        vitals_respiratory_rate=18,
        allergies="Amoxicillin (mild pruritus)",
        treatment_plan="Course of Azithromycin, Salbutamol nebulization SOS, avoid cold beverages, bed rest 4 days",
        follow_up_date=follow_up,
        diagnosis_code="J20.9",
        actor_id=doctor.id,
        ip_address="192.168.1.50"
    )

    assert record is not None
    assert record.id is not None
    assert record.patient_id == patient.id
    assert record.doctor_id == doctor.id
    assert record.symptoms == "Productive cough with yellow sputum, low-grade fever for 3 days, mild dyspnea"
    assert record.diagnosis == "Acute Bronchitis with Bronchospasm"
    assert record.vitals_bp == "124/82"
    assert record.vitals_pulse == 78
    assert float(record.vitals_temp) == 37.8
    assert record.vitals_spo2 == 97
    assert float(record.vitals_weight) == 74.5
    assert float(record.vitals_height) == 178.0
    assert record.vitals_respiratory_rate == 18
    assert record.allergies == "Amoxicillin (mild pruritus)"
    assert "Azithromycin" in record.treatment_plan
    assert record.follow_up_date == follow_up

    # Verify Diagnosis entity was automatically registered
    diag = db_session.query(Diagnosis).filter(Diagnosis.medical_record_id == record.id).first()
    assert diag is not None
    assert diag.diagnosis_code == "J20.9"
    assert diag.diagnosis_name == "Acute Bronchitis with Bronchospasm"
    assert diag.status == "Active"

    # Verify Patient global allergy was updated
    db_session.refresh(patient)
    assert "Amoxicillin" in patient.allergies

    # Verify Audit Log entry
    audit = db_session.query(AuditLog).filter(
        AuditLog.resource_type == "MedicalRecord",
        AuditLog.resource_id == record.id,
        AuditLog.action == "MEDICAL_RECORD_CREATED"
    ).first()
    assert audit is not None
    assert audit.user_id == doctor.id


# =====================================================================
# 2. Service Layer: Vitals Physiological Validation
# =====================================================================

def test_medical_record_vitals_validation():
    # Valid blood pressure
    validate_vitals(bp="120/80")
    validate_vitals(bp="140/90")

    # Invalid BP: malformed string
    with pytest.raises(InvalidMedicalRecordDataError) as exc_bp1:
        validate_vitals(bp="invalid_bp")
    assert "Invalid blood pressure format" in str(exc_bp1.value)

    # Invalid BP: systolic <= diastolic
    with pytest.raises(InvalidMedicalRecordDataError) as exc_bp2:
        validate_vitals(bp="80/120")
    assert "strictly higher" in str(exc_bp2.value)

    # Invalid BP: physiological bounds
    with pytest.raises(InvalidMedicalRecordDataError) as exc_bp3:
        validate_vitals(bp="350/80")
    assert "out of physiological range" in str(exc_bp3.value)

    # Pulse out of range
    with pytest.raises(InvalidMedicalRecordDataError) as exc_pulse:
        validate_vitals(pulse=15)
    assert "pulse out of plausible range" in str(exc_pulse.value)

    # Temperature out of range
    with pytest.raises(InvalidMedicalRecordDataError) as exc_temp:
        validate_vitals(temp=52.0)
    assert "temperature out of plausible" in str(exc_temp.value)

    # SpO2 out of range
    with pytest.raises(InvalidMedicalRecordDataError) as exc_spo2:
        validate_vitals(spo2=35)
    assert "SpO2" in str(exc_spo2.value)


# =====================================================================
# 3. Service Layer: Follow-Up Date Validation
# =====================================================================

def test_medical_record_follow_up_validation(db_session):
    fixtures = setup_emr_fixtures(db_session)
    doctor = fixtures["doctor"]
    patient = fixtures["patient1"]

    # Past follow up date rejected
    past_date = date.today() - timedelta(days=2)
    with pytest.raises(InvalidMedicalRecordDataError) as exc_date:
        create_medical_record(
            db=db_session,
            patient_id=patient.id,
            doctor_id=doctor.id,
            symptoms="Mild fever",
            diagnosis="Viral fever",
            follow_up_date=past_date
        )
    assert "past" in str(exc_date.value)


# =====================================================================
# 4. Service Layer: Progressive Allergy Synchronization
# =====================================================================

def test_allergies_sync_to_patient_profile(db_session):
    fixtures = setup_emr_fixtures(db_session)
    doctor = fixtures["doctor"]
    patient = fixtures["patient1"]

    # Initial allergy is None
    assert patient.allergies is None

    # First encounter documents Ciprofloxacin
    create_medical_record(
        db=db_session,
        patient_id=patient.id,
        doctor_id=doctor.id,
        symptoms="UTI symptoms",
        diagnosis="Urinary Tract Infection",
        allergies="Ciprofloxacin"
    )
    db_session.refresh(patient)
    assert patient.allergies == "Ciprofloxacin"

    # Second encounter documents Ibuprofen
    create_medical_record(
        db=db_session,
        patient_id=patient.id,
        doctor_id=doctor.id,
        symptoms="Knee sprain",
        diagnosis="Ligament Strain",
        allergies="Ibuprofen"
    )
    db_session.refresh(patient)
    assert "Ciprofloxacin" in patient.allergies
    assert "Ibuprofen" in patient.allergies


# =====================================================================
# 5. Service Layer: Chronological Medical History Timeline
# =====================================================================

def test_chronological_medical_history_timeline(db_session):
    fixtures = setup_emr_fixtures(db_session)
    doctor = fixtures["doctor"]
    patient = fixtures["patient1"]

    # 1. Past consultation (10 days ago)
    rec1 = create_medical_record(
        db=db_session,
        patient_id=patient.id,
        doctor_id=doctor.id,
        symptoms="Throat pain",
        diagnosis="Pharyngitis",
        treatment_plan="Salt water gargles"
    )
    rec1.visit_date = date.today() - timedelta(days=10)

    # 2. Recent consultation (today)
    rec2 = create_medical_record(
        db=db_session,
        patient_id=patient.id,
        doctor_id=doctor.id,
        symptoms="Hypertension routine check",
        diagnosis="Essential Hypertension",
        vitals_bp="130/85",
        treatment_plan="Low sodium DASH diet, regular aerobic exercise"
    )
    db_session.commit()

    # Fetch timeline as patient
    timeline_res = get_patient_medical_timeline(
        db=db_session,
        patient_id=patient.id,
        viewer_id=patient.id,
        viewer_role="patient"
    )

    assert timeline_res is not None
    events = timeline_res["events"]
    assert len(events) >= 2

    # Verify chronological sorting (descending: most recent first)
    for i in range(len(events) - 1):
        assert events[i]["date"] >= events[i + 1]["date"]

    # Find the recent consultation event
    consult_events = [e for e in events if e["type"] == "consultation"]
    assert len(consult_events) >= 2
    assert consult_events[0]["data"]["diagnosis"] == "Essential Hypertension"
    assert "Low sodium DASH diet" in consult_events[0]["data"]["treatment_plan"]
    assert consult_events[0]["data"]["vitals_bp"] == "130/85"


# =====================================================================
# 6. Service Layer: EMR Update & Security Audit Diff
# =====================================================================

def test_doctor_update_medical_record_and_audit(db_session):
    fixtures = setup_emr_fixtures(db_session)
    doctor = fixtures["doctor"]
    doctor2 = fixtures["doctor2"]
    patient = fixtures["patient1"]

    record = create_medical_record(
        db=db_session,
        patient_id=patient.id,
        doctor_id=doctor.id,
        symptoms="Fever and body ache",
        diagnosis="Viral Syndrome",
        treatment_plan="Paracetamol 650mg SOS"
    )

    # 1. Unauthorized Doctor 2 attempts to edit Doctor 1's record -> Should raise MedicalRecordPermissionError
    with pytest.raises(MedicalRecordPermissionError):
        update_medical_record(
            db=db_session,
            record_id=record.id,
            actor_id=doctor2.id,
            actor_role="doctor",
            treatment_plan="Unauthorized change"
        )

    # 2. Authoring Doctor updates the treatment plan and vitals
    updated = update_medical_record(
        db=db_session,
        record_id=record.id,
        actor_id=doctor.id,
        actor_role="doctor",
        diagnosis="Dengue Fever (NS1 Positive)",
        vitals_bp="110/70",
        vitals_spo2=99,
        treatment_plan="Oral rehydration solution, platelet monitoring every 24h, complete bed rest",
        change_reason="NS1 lab antigen confirmation received"
    )

    assert updated.diagnosis == "Dengue Fever (NS1 Positive)"
    assert updated.vitals_bp == "110/70"
    assert "platelet monitoring" in updated.treatment_plan

    # Verify Audit Log
    audit = db_session.query(AuditLog).filter(
        AuditLog.resource_id == record.id,
        AuditLog.action == "MEDICAL_RECORD_UPDATED"
    ).first()
    assert audit is not None
    assert "NS1 lab antigen confirmation received" in audit.details_json


# =====================================================================
# 7. Web Integration: Patient Timeline View
# =====================================================================

def test_patient_can_view_own_records_timeline_web(flask_client, db_session):
    fixtures = setup_emr_fixtures(db_session)
    doctor = fixtures["doctor"]
    patient = fixtures["patient1"]

    record = create_medical_record(
        db=db_session,
        patient_id=patient.id,
        doctor_id=doctor.id,
        symptoms="Severe migraine with photophobia",
        diagnosis="Acute Migraine with Aura",
        vitals_bp="118/76",
        vitals_pulse=74,
        treatment_plan="Zolmitriptan 2.5mg, dark room rest, avoid caffeine",
        clinical_notes="Prescription dispensed. Review if symptoms worsen."
    )

    login_client(flask_client, patient.user.email)
    res = flask_client.get("/patient/records")
    assert res.status_code == 200
    assert b"Acute Migraine with Aura" in res.data
    assert b"Severe migraine with photophobia" in res.data
    assert b"Zolmitriptan" in res.data
    assert b"118/76" in res.data

    # Test single record detail view
    res_detail = flask_client.get(f"/patient/records/{record.id}")
    assert res_detail.status_code == 200
    assert b"Acute Migraine with Aura" in res_detail.data


# =====================================================================
# 8. Web Integration: Cross-Patient Confidentiality (RBAC)
# =====================================================================

def test_rbac_patient_cannot_view_other_patient_records(flask_client, db_session):
    fixtures = setup_emr_fixtures(db_session)
    doctor = fixtures["doctor"]
    patient1 = fixtures["patient1"]
    patient2 = fixtures["patient2"]

    # Record belongs to Patient 1
    record = create_medical_record(
        db=db_session,
        patient_id=patient1.id,
        doctor_id=doctor.id,
        symptoms="Chest heaviness",
        diagnosis="Stable Angina"
    )

    # Login as Patient 2 and try to access Patient 1's record
    login_client(flask_client, patient2.user.email)
    malicious_res = flask_client.get(f"/patient/records/{record.id}")
    assert malicious_res.status_code == 403


# =====================================================================
# 9. Web Integration: Unauthorized Roles Blocked from EMR Creation
# =====================================================================

def test_rbac_unauthorized_roles_blocked_from_emr_creation(flask_client, db_session):
    fixtures = setup_emr_fixtures(db_session)
    patient = fixtures["patient1"]
    pharmacist = fixtures["pharmacist"]

    # Pharmacist attempts to access new EMR record route
    login_client(flask_client, pharmacist.email)
    res_pharm = flask_client.get(f"/doctor/patient/{patient.id}/record/new")
    assert res_pharm.status_code == 403

    # Patient attempts to access new EMR record route
    login_client(flask_client, fixtures["patient1_user"].email)
    res_pat = flask_client.get(f"/doctor/patient/{patient.id}/record/new")
    assert res_pat.status_code == 403


# =====================================================================
# 10. Web Integration: Doctor Consultation Encounter Flow
# =====================================================================

def test_doctor_web_consultation_creates_emr_and_completes_appointment(flask_client, db_session):
    fixtures = setup_emr_fixtures(db_session)
    doctor = fixtures["doctor"]
    patient = fixtures["patient1"]

    # Create scheduled appointment
    appt = Appointment(
        patient_id=patient.id,
        doctor_id=doctor.id,
        appointment_datetime=datetime.now(timezone.utc) + timedelta(days=1),
        status=AppointmentStatusEnum.SCHEDULED,
        reason="Fever checkup",
        token_number=1
    )
    db_session.add(appt)
    db_session.commit()

    login_client(flask_client, doctor.user.email)

    post_data = {
        "symptoms": "High fever, chills, severe myalgia",
        "diagnosis": "Viral Influenza A",
        "diagnosis_code": "J10.1",
        "clinical_notes": "Prescribed Oseltamivir. Hydration and rest.",
        "vitals_bp": "120/78",
        "vitals_pulse": "84",
        "vitals_temp": "38.5",
        "vitals_spo2": "96",
        "vitals_weight": "72.0",
        "vitals_height": "176.0",
        "vitals_respiratory_rate": "16",
        "allergies": "Paracetamol allergy",
        "treatment_plan": "Antiviral regimen, isolation for 5 days, oral fluids",
        "follow_up_date": (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")
    }

    resp = flask_client.post(f"/doctor/consultation/{appt.id}", data=post_data, follow_redirects=True)
    assert resp.status_code == 200

    # Verify Appointment is completed
    updated_appt = db_session.query(Appointment).filter(Appointment.id == appt.id).first()
    assert updated_appt.status == AppointmentStatusEnum.COMPLETED

    # Verify MedicalRecord created
    rec = db_session.query(MedicalRecord).filter(MedicalRecord.appointment_id == appt.id).first()
    assert rec is not None
    assert rec.diagnosis == "Viral Influenza A"
    assert rec.treatment_plan == "Antiviral regimen, isolation for 5 days, oral fluids"
    assert rec.allergies == "Paracetamol allergy"


# =====================================================================
# 11. Web Integration: Doctor Direct EMR Creation & Edit
# =====================================================================

def test_doctor_direct_emr_create_and_edit_web(flask_client, db_session):
    fixtures = setup_emr_fixtures(db_session)
    doctor = fixtures["doctor"]
    patient = fixtures["patient1"]

    login_client(flask_client, doctor.user.email)

    # 1. Create direct EMR record
    create_data = {
        "symptoms": "Persistent lower back pain radiating to left leg",
        "diagnosis": "Lumbar Radiculopathy (L4-L5)",
        "diagnosis_code": "M54.16",
        "clinical_notes": "Straight leg raise positive at 45 degrees.",
        "vitals_bp": "130/84",
        "vitals_pulse": "72",
        "vitals_temp": "36.8",
        "vitals_spo2": "99",
        "treatment_plan": "Physical therapy 3x/week, core strengthening, avoid heavy lifting",
        "follow_up_date": (date.today() + timedelta(days=21)).strftime("%Y-%m-%d")
    }
    create_resp = flask_client.post(
        f"/doctor/patient/{patient.id}/record/new",
        data=create_data,
        follow_redirects=True
    )
    assert create_resp.status_code == 200

    created_rec = db_session.query(MedicalRecord).filter(
        MedicalRecord.patient_id == patient.id,
        MedicalRecord.diagnosis == "Lumbar Radiculopathy (L4-L5)"
    ).first()
    assert created_rec is not None

    # 2. Edit EMR record
    edit_data = {
        "symptoms": "Persistent lower back pain radiating to left leg, improved with physio",
        "diagnosis": "Lumbar Radiculopathy (L4-L5) - Improving",
        "clinical_notes": "Patient reports 50% symptom reduction.",
        "vitals_bp": "125/80",
        "vitals_pulse": "70",
        "vitals_temp": "36.7",
        "vitals_spo2": "99",
        "treatment_plan": "Continue lumbar physio, resume light walking",
        "follow_up_date": (date.today() + timedelta(days=30)).strftime("%Y-%m-%d"),
        "change_reason": "Follow-up review notes updated after physical therapy assessment"
    }
    edit_resp = flask_client.post(
        f"/doctor/record/{created_rec.id}/edit",
        data=edit_data,
        follow_redirects=True
    )
    assert edit_resp.status_code == 200

    db_session.refresh(created_rec)
    assert created_rec.diagnosis == "Lumbar Radiculopathy (L4-L5) - Improving"
    assert "Continue lumbar physio" in created_rec.treatment_plan
