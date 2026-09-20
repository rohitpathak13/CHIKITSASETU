import pytest
from datetime import datetime, date, timezone
from decimal import Decimal
from core.models import (
    User, Doctor, Patient, Department, Appointment,
    MedicalRecord, Diagnosis, Prescription, PrescriptionItem, Medicine,
    LabTest, LabOrder, LabResult, Bill, Payment, Insurance, AuditLog,
    RoleEnum, GenderEnum, AppointmentStatusEnum, PrescriptionStatusEnum,
    LabOrderStatusEnum, BillStatusEnum, PaymentMethodEnum
)
from core.security import get_password_hash


# =====================================================================
# Helper Fixtures & Setup Functions
# =====================================================================

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
# 1. Patient Registration & Form Validation Tests
# =====================================================================

def test_patient_registration_success(flask_client, db_session):
    staff = create_user(db_session, "receptionist_reg@chikitsasetu.ai", RoleEnum.RECEPTIONIST, "Rita", "Desk")
    login_user(flask_client, "receptionist_reg@chikitsasetu.ai")

    reg_data = {
        "email": "new_patient_reg@test.ai",
        "first_name": "Aarav",
        "last_name": "Mehta",
        "phone": "+91 9988776655",
        "password": "Password123!",
        "dob": "1990-05-15",
        "gender": "male",
        "blood_group": "O+",
        "emergency_contact_name": "Priya Mehta",
        "emergency_contact_phone": "+91 9988776600",
        "address": "42 Marine Drive, Mumbai",
        "allergies": "Penicillin",
        "chronic_conditions": "Asthma"
    }

    resp = flask_client.post("/patient/register", data=reg_data)
    assert resp.status_code == 302, f"Expected redirect, got {resp.status_code}"

    # Verify Patient and User in DB
    db_session.expire_all()
    created_user = db_session.query(User).filter(User.email == "new_patient_reg@test.ai").first()
    assert created_user is not None
    assert created_user.first_name == "Aarav"
    assert created_user.last_name == "Mehta"
    assert created_user.role == RoleEnum.PATIENT

    patient = db_session.query(Patient).filter(Patient.id == created_user.id).first()
    assert patient is not None
    assert patient.dob == date(1990, 5, 15)
    assert patient.gender == GenderEnum.MALE
    assert patient.blood_group == "O+"
    assert patient.emergency_contact_name == "Priya Mehta"
    assert patient.emergency_contact_phone == "+91 9988776600"
    assert patient.allergies == "Penicillin"
    assert patient.chronic_conditions == "Asthma"
    assert patient.address == "42 Marine Drive, Mumbai"

    # Verify Audit Log
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "PATIENT_REGISTERED",
        AuditLog.resource_id == patient.id
    ).first()
    assert audit is not None
    assert audit.resource_type == "Patient"


def test_patient_registration_validations(flask_client, db_session):
    create_user(db_session, "admin_val@chikitsasetu.ai", RoleEnum.ADMIN, "Super", "Admin")
    login_user(flask_client, "admin_val@chikitsasetu.ai")

    # 1. Invalid Email
    bad_email = {
        "email": "not-an-email",
        "first_name": "John",
        "last_name": "Doe",
        "dob": "1995-01-01",
        "gender": "male"
    }
    resp = flask_client.post("/patient/register", data=bad_email)
    assert resp.status_code == 400
    assert b"valid email" in resp.data

    # 2. Missing First/Last Name
    missing_name = {
        "email": "valid_email@test.ai",
        "first_name": "",
        "last_name": "Doe",
        "dob": "1995-01-01",
        "gender": "male"
    }
    resp = flask_client.post("/patient/register", data=missing_name)
    assert resp.status_code == 400
    assert b"names are required" in resp.data

    # 3. Missing DOB
    missing_dob = {
        "email": "valid_email2@test.ai",
        "first_name": "John",
        "last_name": "Doe",
        "dob": "",
        "gender": "male"
    }
    resp = flask_client.post("/patient/register", data=missing_dob)
    assert resp.status_code == 400
    assert b"Date of birth is required" in resp.data

    # 4. Future DOB
    future_dob = {
        "email": "valid_email3@test.ai",
        "first_name": "John",
        "last_name": "Doe",
        "dob": "2099-01-01",
        "gender": "male"
    }
    resp = flask_client.post("/patient/register", data=future_dob)
    assert resp.status_code == 400
    assert b"future" in resp.data

    # 5. Duplicate Email
    existing = create_user(db_session, "existing_patient@test.ai", RoleEnum.PATIENT, "Existing", "One")
    dup_email = {
        "email": "existing_patient@test.ai",
        "first_name": "Duplicate",
        "last_name": "Attempt",
        "dob": "1995-01-01",
        "gender": "male"
    }
    resp = flask_client.post("/patient/register", data=dup_email)
    assert resp.status_code == 400
    assert b"already exists" in resp.data


# =====================================================================
# 2. Directory Search, Filter & Pagination Tests
# =====================================================================

def test_patient_directory_search_and_filtering(flask_client, db_session):
    create_user(db_session, "doc_dir@chikitsasetu.ai", RoleEnum.DOCTOR, "Dr. Sanjay", "Gupta")
    login_user(flask_client, "doc_dir@chikitsasetu.ai")

    # Seed 3 distinct patients
    u1 = create_user(db_session, "search_p1@test.ai", RoleEnum.PATIENT, "Vikram", "Patel", phone="+91 9111111111")
    p1 = Patient(id=u1.id, dob=date(1985, 3, 20), gender=GenderEnum.MALE, blood_group="A+")
    db_session.add(p1)

    u2 = create_user(db_session, "search_p2@test.ai", RoleEnum.PATIENT, "Pooja", "Sharma", phone="+91 9222222222")
    p2 = Patient(id=u2.id, dob=date(1992, 7, 11), gender=GenderEnum.FEMALE, blood_group="B+")
    db_session.add(p2)

    u3 = create_user(db_session, "search_p3@test.ai", RoleEnum.PATIENT, "Anita", "Deshmukh", phone="+91 9333333333")
    p3 = Patient(id=u3.id, dob=date(1978, 11, 5), gender=GenderEnum.FEMALE, blood_group="O-")
    db_session.add(p3)
    db_session.commit()

    # Search by Name
    resp = flask_client.get("/patient/directory?q=Vikram")
    assert resp.status_code == 200
    assert b"Vikram Patel" in resp.data
    assert b"Pooja Sharma" not in resp.data

    # Search by MRN
    mrn_str = f"PAT-{p2.id:05d}"
    resp = flask_client.get(f"/patient/directory?q={mrn_str}")
    assert resp.status_code == 200
    assert b"Pooja Sharma" in resp.data
    assert b"Vikram Patel" not in resp.data

    # Search by Phone
    resp = flask_client.get("/patient/directory?q=9333333333")
    assert resp.status_code == 200
    assert b"Anita Deshmukh" in resp.data

    # Filter by Gender
    resp = flask_client.get("/patient/directory?gender=female")
    assert resp.status_code == 200
    assert b"Pooja Sharma" in resp.data
    assert b"Anita Deshmukh" in resp.data
    assert b"Vikram Patel" not in resp.data

    # Filter by Blood Group
    resp = flask_client.get("/patient/directory?blood_group=A%2B")
    assert resp.status_code == 200
    assert b"Vikram Patel" in resp.data
    assert b"Pooja Sharma" not in resp.data


def test_patient_directory_pagination(flask_client, db_session):
    create_user(db_session, "nurse_page@chikitsasetu.ai", RoleEnum.NURSE, "Sister", "Mary")
    login_user(flask_client, "nurse_page@chikitsasetu.ai")

    # Seed 12 patients
    for i in range(1, 13):
        u = create_user(db_session, f"page_pt_{i}@test.ai", RoleEnum.PATIENT, f"PagingPatient{i:02d}", "Test")
        p = Patient(id=u.id, dob=date(1990, 1, 1), gender=GenderEnum.OTHER)
        db_session.add(p)
    db_session.commit()

    # Page 1 (per_page = 10)
    resp1 = flask_client.get("/patient/directory?page=1")
    assert resp1.status_code == 200
    assert b"Showing page 1 of" in resp1.data

    # Page 2
    resp2 = flask_client.get("/patient/directory?page=2")
    assert resp2.status_code == 200
    assert b"Showing page 2 of" in resp2.data


# =====================================================================
# 3. 360-Degree Comprehensive Patient Detail View Tests
# =====================================================================

def test_patient_360_detail_view_full_history(flask_client, db_session):
    # Setup Doctor & Dept
    dept = Department(name="Internal Medicine Dept", code="IM_TEST", is_active=True)
    db_session.add(dept)
    db_session.flush()

    doc_user = create_user(db_session, "doc_360@chikitsasetu.ai", RoleEnum.DOCTOR, "Arun", "Kumar")
    doc = Doctor(
        id=doc_user.id,
        department_id=dept.id,
        specialization="Internal Medicine",
        qualification="MBBS, MD",
        license_number="DOC-360-LIC",
        consultation_fee=Decimal("750.00")
    )
    db_session.add(doc)
    db_session.flush()

    # Setup Patient with Demographics & Emergency Contact
    pt_user = create_user(db_session, "patient_360@chikitsasetu.ai", RoleEnum.PATIENT, "Sunita", "Rao", phone="+91 9876543210")
    
    insurance = Insurance(
        policy_number="POL-MED-9988",
        provider_name="Star Health Allied",
        coverage_amount=Decimal("500000.00"),
        valid_until=date(2030, 12, 31),
        patient_id=pt_user.id,
        status="Active"
    )
    db_session.add(insurance)
    db_session.flush()

    pt = Patient(
        id=pt_user.id,
        dob=date(1982, 6, 25),
        gender=GenderEnum.FEMALE,
        blood_group="AB+",
        emergency_contact_name="Ramesh Rao",
        emergency_contact_phone="+91 9876500000",
        address="104 Lotus Heights, Pune",
        allergies="Sulfa drugs, Pollen",
        chronic_conditions="Hypertension Stage 1",
        insurance_id=insurance.id
    )
    db_session.add(pt)
    db_session.flush()

    # 1. Appointment
    app = Appointment(
        patient_id=pt.id,
        doctor_id=doc.id,
        appointment_datetime=datetime(2026, 9, 20, 10, 30, tzinfo=timezone.utc),
        status=AppointmentStatusEnum.CONFIRMED,
        reason="Annual cardiac checkup",
        token_number=7
    )
    db_session.add(app)
    db_session.flush()

    # 2. Medical Record & Diagnosis
    rec = MedicalRecord(
        patient_id=pt.id,
        doctor_id=doc.id,
        appointment_id=app.id,
        visit_date=date(2026, 9, 20),
        symptoms="Mild dizziness and palpitations",
        diagnosis="Essential Hypertension",
        vitals_bp="138/88",
        vitals_pulse=76,
        vitals_temp=Decimal("98.6"),
        vitals_spo2=99,
        clinical_notes="Maintain low sodium diet and ambulatory BP monitoring."
    )
    db_session.add(rec)
    db_session.flush()

    diag = Diagnosis(
        patient_id=pt.id,
        doctor_id=doc.id,
        medical_record_id=rec.id,
        diagnosis_code="I10",
        diagnosis_name="Essential (Primary) Hypertension",
        diagnosis_type="Primary",
        status="Active",
        diagnosed_date=date(2026, 9, 20)
    )
    db_session.add(diag)
    db_session.flush()

    # 3. Prescription & Prescription Item
    med = Medicine(
        name="Amlodipine 5mg",
        generic_name="Amlodipine Besylate",
        category="Cardiovascular",
        unit="Tablet",
        unit_price=Decimal("4.50"),
        reorder_level=50
    )
    db_session.add(med)
    db_session.flush()

    rx = Prescription(
        medical_record_id=rec.id,
        patient_id=pt.id,
        doctor_id=doc.id,
        status=PrescriptionStatusEnum.DISPENSED,
        notes="Take once daily in morning"
    )
    db_session.add(rx)
    db_session.flush()

    rx_item = PrescriptionItem(
        prescription_id=rx.id,
        medicine_id=med.id,
        dosage="5 mg",
        frequency="1-0-0 morning",
        duration_days=30,
        quantity_prescribed=30,
        quantity_dispensed=30
    )
    db_session.add(rx_item)
    db_session.flush()

    # 4. Lab Order & Lab Result
    test = LabTest(
        name="Lipid Profile Comprehensive",
        test_code="LIPID-01",
        sample_type="Serum",
        unit="mg/dL",
        reference_range_min=120.0,
        reference_range_max=200.0,
        cost=Decimal("650.00")
    )
    db_session.add(test)
    db_session.flush()

    order = LabOrder(
        patient_id=pt.id,
        doctor_id=doc.id,
        medical_record_id=rec.id,
        test_id=test.id,
        status=LabOrderStatusEnum.COMPLETED,
        ordered_at=datetime(2026, 9, 20, 11, 0, tzinfo=timezone.utc)
    )
    db_session.add(order)
    db_session.flush()

    result = LabResult(
        lab_order_id=order.id,
        measured_value=218.0,
        unit="mg/dL",
        is_abnormal=True,
        critical_alert=False,
        technician_notes="Slight hypercholesterolemia noted."
    )
    db_session.add(result)
    db_session.flush()

    # 5. Bill & Payment
    bill = Bill(
        bill_number="BILL-360-TEST",
        patient_id=pt.id,
        appointment_id=app.id,
        insurance_id=insurance.id,
        subtotal=Decimal("1400.00"),
        discount=Decimal("100.00"),
        total_amount=Decimal("1300.00"),
        status=BillStatusEnum.PARTIALLY_PAID
    )
    db_session.add(bill)
    db_session.flush()

    pay = Payment(
        bill_id=bill.id,
        amount=Decimal("500.00"),
        payment_method=PaymentMethodEnum.UPI,
        transaction_reference="UPI-REF-9988",
        payment_date=datetime.now(timezone.utc)
    )
    db_session.add(pay)
    db_session.commit()

    # Login as Staff (Doctor) and view 360-degree patient chart
    login_user(flask_client, "doc_360@chikitsasetu.ai")
    resp = flask_client.get(f"/patient/{pt.id}")
    assert resp.status_code == 200

    html = resp.data.decode("utf-8")

    # 1. Demographics & Emergency Contact
    assert "Sunita Rao" in html
    assert f"PAT-{pt.id:05d}" in html
    assert "AB+" in html
    assert "104 Lotus Heights, Pune" in html
    assert "Ramesh Rao" in html
    assert "+91 9876500000" in html
    assert "Star Health Allied" in html
    assert "POL-MED-9988" in html

    # 2. Alerts (Allergies & Chronic)
    assert "Sulfa drugs, Pollen" in html
    assert "Hypertension Stage 1" in html

    # 3. Clinical Consultations & Diagnoses
    assert "Essential (Primary) Hypertension" in html
    assert "I10" in html
    assert "Mild dizziness and palpitations" in html
    assert "138/88" in html

    # 4. Appointment
    assert "Annual cardiac checkup" in html
    assert "#7" in html  # Token

    # 5. Prescription
    assert "Amlodipine 5mg" in html
    assert "1-0-0 morning" in html

    # 6. Lab Report & Abnormal Flag
    assert "Lipid Profile Comprehensive" in html
    assert "LIPID-01" in html
    assert "218.0 mg/dL" in html
    assert "ABNORMAL" in html

    # 7. Billing & Balances
    assert "BILL-360-TEST" in html
    assert "1300.00" in html
    assert "500.00" in html
    assert "800.00" in html  # Outstanding balance


# =====================================================================
# 4. Edit Patient Details Tests
# =====================================================================

def test_edit_patient_by_staff(flask_client, db_session):
    create_user(db_session, "admin_editor@chikitsasetu.ai", RoleEnum.ADMIN, "Boss", "Admin")
    login_user(flask_client, "admin_editor@chikitsasetu.ai")

    u = create_user(db_session, "patient_edit_staff@test.ai", RoleEnum.PATIENT, "Rohan", "Kapoor", phone="+91 1111111111")
    p = Patient(id=u.id, dob=date(1993, 4, 12), gender=GenderEnum.MALE, blood_group="O+")
    db_session.add(p)
    db_session.commit()

    edit_data = {
        "first_name": "Rohan",
        "last_name": "Kapoor-Verma",
        "phone": "+91 9999988888",
        "dob": "1993-04-15",
        "gender": "male",
        "blood_group": "A+",
        "emergency_contact_name": "Sneha Kapoor",
        "emergency_contact_phone": "+91 7777766666",
        "address": "Bungalow 7, Bandra West",
        "allergies": "Seafood",
        "chronic_conditions": "Migraine"
    }

    resp = flask_client.post(f"/patient/{p.id}/edit", data=edit_data)
    assert resp.status_code == 302

    db_session.expire_all()
    updated_p = db_session.query(Patient).filter(Patient.id == p.id).first()
    assert updated_p.user.last_name == "Kapoor-Verma"
    assert updated_p.user.phone == "+91 9999988888"
    assert updated_p.blood_group == "A+"
    assert updated_p.dob == date(1993, 4, 15)
    assert updated_p.emergency_contact_name == "Sneha Kapoor"
    assert updated_p.emergency_contact_phone == "+91 7777766666"
    assert updated_p.allergies == "Seafood"
    assert updated_p.chronic_conditions == "Migraine"

    # Verify Audit Log
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "PATIENT_EDITED",
        AuditLog.resource_id == p.id
    ).first()
    assert audit is not None


def test_edit_patient_by_self(flask_client, db_session):
    u = create_user(db_session, "patient_self_edit@test.ai", RoleEnum.PATIENT, "Kavita", "Nair", phone="+91 2222222222")
    p = Patient(id=u.id, dob=date(1995, 8, 20), gender=GenderEnum.FEMALE, blood_group="B+")
    db_session.add(p)
    db_session.commit()

    # Log in as the patient herself
    login_user(flask_client, "patient_self_edit@test.ai")

    edit_data = {
        "first_name": "Kavita",
        "last_name": "Nair",
        "phone": "+91 8888877777",
        "blood_group": "B+",
        "emergency_contact_name": "Anil Nair (Brother)",
        "emergency_contact_phone": "+91 6666655555",
        "address": "Apt 2B, Green Woods",
        "allergies": "Dust Mites",
        "chronic_conditions": "None"
    }

    resp = flask_client.post(f"/patient/{p.id}/edit", data=edit_data)
    assert resp.status_code == 302

    db_session.expire_all()
    updated_p = db_session.query(Patient).filter(Patient.id == p.id).first()
    assert updated_p.user.phone == "+91 8888877777"
    assert updated_p.emergency_contact_name == "Anil Nair (Brother)"
    assert updated_p.address == "Apt 2B, Green Woods"
    assert updated_p.allergies == "Dust Mites"


# =====================================================================
# 5. Role-Based Access Control (RBAC) Permission Tests
# =====================================================================

def test_patient_management_rbac_permissions(flask_client, db_session):
    # Setup Patient A & Patient B
    ua = create_user(db_session, "patient_a@test.ai", RoleEnum.PATIENT, "Alice", "A")
    pa = Patient(id=ua.id, dob=date(1996, 1, 1), gender=GenderEnum.FEMALE)
    db_session.add(pa)

    ub = create_user(db_session, "patient_b@test.ai", RoleEnum.PATIENT, "Bob", "B")
    pb = Patient(id=ub.id, dob=date(1997, 2, 2), gender=GenderEnum.MALE)
    db_session.add(pb)

    # Setup Staff roles
    admin = create_user(db_session, "rbac_admin@test.ai", RoleEnum.ADMIN, "Admin", "User")
    nurse = create_user(db_session, "rbac_nurse@test.ai", RoleEnum.NURSE, "Nurse", "User")
    pharm = create_user(db_session, "rbac_pharm@test.ai", RoleEnum.PHARMACIST, "Pharm", "User")
    db_session.commit()

    # 1. Staff (Admin, Nurse) can access directory & detail
    login_user(flask_client, "rbac_admin@test.ai")
    assert flask_client.get("/patient/directory").status_code == 200
    assert flask_client.get(f"/patient/{pa.id}").status_code == 200

    login_user(flask_client, "rbac_nurse@test.ai")
    assert flask_client.get("/patient/directory").status_code == 200
    assert flask_client.get(f"/patient/{pa.id}").status_code == 200

    # 2. Patient A can view own profile/chart
    login_user(flask_client, "patient_a@test.ai")
    assert flask_client.get(f"/patient/{pa.id}").status_code == 200

    # 3. Patient A cannot access patient directory (403 Forbidden)
    assert flask_client.get("/patient/directory").status_code == 403

    # 4. Patient A CANNOT view Patient B's chart (403 Forbidden)
    assert flask_client.get(f"/patient/{pb.id}").status_code == 403

    # 5. Patient A CANNOT edit Patient B's chart (403 Forbidden)
    resp_cross_edit = flask_client.post(f"/patient/{pb.id}/edit", data={"first_name": "Hacked", "last_name": "User"})
    assert resp_cross_edit.status_code == 403

    # 6. Unauthorized role (Pharmacist) CANNOT access directory or patient detail
    login_user(flask_client, "rbac_pharm@test.ai")
    assert flask_client.get("/patient/directory").status_code == 403
    assert flask_client.get(f"/patient/{pa.id}").status_code == 403
