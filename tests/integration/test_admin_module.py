import pytest
from datetime import datetime, date, timezone
from decimal import Decimal
from core.models import (
    User, Doctor, Patient, Staff, Department, Room, Bed,
    Appointment, Admission, Bill, Medicine, MedicineInventory, AuditLog,
    RoleEnum, GenderEnum, RoomTypeEnum, BedStatusEnum, BillStatusEnum,
    AppointmentStatusEnum, AdmissionStatusEnum
)
from core.security import get_password_hash


def login_as_admin(flask_client, db_session):
    admin = db_session.query(User).filter(User.email == "admin_mod_test@medicare.ai").first()
    if not admin:
        admin = User(
            email="admin_mod_test@medicare.ai",
            password_hash=get_password_hash("Password123!"),
            role=RoleEnum.ADMIN,
            first_name="Admin",
            last_name="Commander",
            is_active=True
        )
        db_session.add(admin)
        db_session.commit()

    flask_client.post("/login", data={
        "email": "admin_mod_test@medicare.ai",
        "password": "Password123!"
    })
    return admin


# =====================================================================
# 1. Executive Dashboard KPIs & Recent Activity
# =====================================================================

def test_admin_dashboard_metrics(flask_client, db_session):
    admin = login_as_admin(flask_client, db_session)

    # Seed Department
    dept = Department(name="Cardiology Division", code="CARD_TEST", is_active=True)
    db_session.add(dept)
    db_session.flush()

    # Seed Doctor
    doc_user = User(
        email="doc_kpi@medicare.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.DOCTOR,
        first_name="Sanjay",
        last_name="Gupta",
        is_active=True
    )
    db_session.add(doc_user)
    db_session.flush()

    doc = Doctor(
        id=doc_user.id,
        department_id=dept.id,
        specialization="Cardiology",
        qualification="MD, DM",
        license_number="LIC-KPI-01",
        consultation_fee=Decimal("800.00")
    )
    db_session.add(doc)

    # Seed Staff
    staff_user = User(
        email="staff_kpi@medicare.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.NURSE,
        first_name="Kavita",
        last_name="Nair",
        is_active=True
    )
    db_session.add(staff_user)
    db_session.flush()

    staff = Staff(
        id=staff_user.id,
        department_id=dept.id,
        employee_id="EMP-KPI-01",
        designation="ICU Nurse",
        shift="Morning"
    )
    db_session.add(staff)

    # Seed Patient
    pat_user = User(
        email="pat_kpi@medicare.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.PATIENT,
        first_name="Rohan",
        last_name="Mehta",
        is_active=True
    )
    db_session.add(pat_user)
    db_session.flush()

    pat = Patient(
        id=pat_user.id,
        dob=date(1992, 5, 10),
        gender=GenderEnum.MALE,
        blood_group="B+"
    )
    db_session.add(pat)

    # Seed Room and Beds
    room = Room(
        room_number="ICU-KPI-1",
        room_type=RoomTypeEnum.ICU,
        floor=3,
        department_id=dept.id,
        total_beds=2,
        daily_rate=Decimal("3000.00")
    )
    db_session.add(room)
    db_session.flush()

    bed1 = Bed(room_id=room.id, bed_number="BED-K1", status=BedStatusEnum.OCCUPIED)
    bed2 = Bed(room_id=room.id, bed_number="BED-K2", status=BedStatusEnum.AVAILABLE)
    db_session.add_all([bed1, bed2])
    db_session.flush()

    # Seed Appointment
    appt = Appointment(
        patient_id=pat.id,
        doctor_id=doc.id,
        appointment_datetime=datetime.now(timezone.utc),
        status=AppointmentStatusEnum.SCHEDULED,
        reason="Heart consultation"
    )
    db_session.add(appt)

    # Seed Admission
    admission = Admission(
        patient_id=pat.id,
        admitting_doctor_id=doc.id,
        bed_id=bed1.id,
        admission_reason="Acute chest pain",
        status=AdmissionStatusEnum.ADMITTED
    )
    db_session.add(admission)

    # Seed Bills (1 Unpaid, 1 Paid)
    bill1 = Bill(
        patient_id=pat.id,
        bill_number="BILL-KPI-01",
        total_amount=Decimal("5000.00"),
        status=BillStatusEnum.UNPAID
    )
    bill2 = Bill(
        patient_id=pat.id,
        bill_number="BILL-KPI-02",
        total_amount=Decimal("2000.00"),
        status=BillStatusEnum.PAID
    )
    db_session.add_all([bill1, bill2])

    # Seed Medicine (Low Stock)
    med = Medicine(
        name="Atorvastatin 20mg",
        category="Cardiovascular",
        unit="Tablet",
        unit_price=Decimal("15.00"),
        reorder_level=50
    )
    db_session.add(med)
    db_session.flush()

    # Low stock batch (10 tablets < 50 reorder level)
    batch = MedicineInventory(
        medicine_id=med.id,
        batch_number="BAT-KPI-01",
        quantity_in_stock=10,
        expiry_date=date(2028, 1, 1),
        purchase_cost=Decimal("8.00")
    )
    db_session.add(batch)

    # Seed Audit Log
    audit = AuditLog(
        user_id=admin.id,
        action="SYSTEM_HEALTH_CHECK",
        resource_type="ExecutiveDashboard",
        resource_id=None,
        ip_address="127.0.0.1",
        details_json='{"status": "Nominal"}'
    )
    db_session.add(audit)
    db_session.commit()

    # Fetch Admin Dashboard
    res = flask_client.get("/admin/")
    assert res.status_code == 200
    assert b"Total Patients" in res.data
    assert b"Active Doctors" in res.data
    assert b"Hospital Staff" in res.data
    assert b"Total Appointments" in res.data
    assert b"Inpatient Admissions" in res.data
    assert b"Bed Occupancy" in res.data
    assert b"Pending Invoices" in res.data
    assert b"Low-Stock Medicines" in res.data
    assert b"SYSTEM_HEALTH_CHECK" in res.data

    flask_client.get("/logout")


# =====================================================================
# 2. Users Management
# =====================================================================

def test_admin_manage_users(flask_client, db_session):
    admin = login_as_admin(flask_client, db_session)

    # 1. Access user list
    res = flask_client.get("/admin/users")
    assert res.status_code == 200
    assert b"Hospital Personnel & Patient Accounts" in res.data

    # 2. Search users
    res_search = flask_client.get("/admin/users?q=Commander")
    assert res_search.status_code == 200
    assert b"Admin Commander" in res_search.data

    # 3. Filter by role
    res_role = flask_client.get("/admin/users?role=admin")
    assert res_role.status_code == 200
    assert b"admin_mod_test@medicare.ai" in res_role.data

    # 4. Provision new Doctor user via POST
    res_create = flask_client.post("/admin/users/create", data={
        "first_name": "Deepak",
        "last_name": "Chopra",
        "email": "dr.deepak@medicare.ai",
        "phone": "+91 98765 43299",
        "role": "doctor",
        "password": "Password123!",
        "specialization": "Integrative Medicine",
        "qualification": "MD",
        "license_number": "LIC-PROV-01",
        "consultation_fee": "750.00"
    }, follow_redirects=True)
    assert res_create.status_code == 200
    assert b"provisioned successfully" in res_create.data

    new_doc_user = db_session.query(User).filter(User.email == "dr.deepak@medicare.ai").first()
    assert new_doc_user is not None
    assert new_doc_user.role == RoleEnum.DOCTOR
    assert new_doc_user.doctor_profile is not None
    assert new_doc_user.doctor_profile.specialization == "Integrative Medicine"

    # 5. Duplicate email validation
    res_dup = flask_client.post("/admin/users/create", data={
        "first_name": "Duplicate",
        "last_name": "Test",
        "email": "dr.deepak@medicare.ai",
        "role": "patient",
        "password": "Password123!"
    }, follow_redirects=True)
    assert b"already exists" in res_dup.data

    # 6. Toggle active status
    res_toggle = flask_client.post(f"/admin/users/{new_doc_user.id}/toggle-status", follow_redirects=True)
    assert res_toggle.status_code == 200
    db_session.expire_all()
    doc_check = db_session.query(User).filter(User.id == new_doc_user.id).first()
    assert doc_check.is_active is False
    assert b"deactivated" in res_toggle.data

    # 7. Prevent self-deactivation
    res_self_toggle = flask_client.post(f"/admin/users/{admin.id}/toggle-status", follow_redirects=True)
    assert b"cannot deactivate your own" in res_self_toggle.data
    admin_check = db_session.query(User).filter(User.id == admin.id).first()
    assert admin_check.is_active is True

    flask_client.get("/logout")


# =====================================================================
# 3. Doctors Management
# =====================================================================

def test_admin_manage_doctors(flask_client, db_session):
    login_as_admin(flask_client, db_session)

    dept = Department(name="Neurology", code="NEURO", is_active=True)
    db_session.add(dept)
    db_session.commit()

    # 1. Create doctor
    res_create = flask_client.post("/admin/doctors/create", data={
        "first_name": "Sunil",
        "last_name": "Gavaskar",
        "email": "dr.sunil@medicare.ai",
        "phone": "+91 98765 12345",
        "specialization": "Neurosurgeon",
        "qualification": "MBBS, MCh",
        "license_number": "MCI-NEURO-99",
        "department_id": str(dept.id),
        "consultation_fee": "1200.00",
        "room_number": "OPD-304",
        "available_days": "Mon,Wed,Fri",
        "password": "Password123!"
    }, follow_redirects=True)
    assert res_create.status_code == 200
    assert b"added to medical staff" in res_create.data

    doc = db_session.query(Doctor).filter(Doctor.license_number == "MCI-NEURO-99").first()
    assert doc is not None
    assert doc.specialization == "Neurosurgeon"
    assert doc.consultation_fee == Decimal("1200.00")

    # 2. View doctor list and filter by department
    res_list = flask_client.get(f"/admin/doctors?dept={dept.id}")
    assert res_list.status_code == 200
    assert b"Sunil Gavaskar" in res_list.data
    assert b"Neurosurgeon" in res_list.data

    # 3. Duplicate license rejection
    res_dup = flask_client.post("/admin/doctors/create", data={
        "first_name": "Clone",
        "last_name": "Doctor",
        "email": "clone.doc@medicare.ai",
        "specialization": "Neurology",
        "license_number": "MCI-NEURO-99",
        "password": "Password123!"
    }, follow_redirects=True)
    assert b"already registered" in res_dup.data

    # 4. Edit doctor
    res_edit = flask_client.post(f"/admin/doctors/{doc.id}/edit", data={
        "specialization": "Chief Neurosurgeon",
        "qualification": "MBBS, MCh, FACS",
        "consultation_fee": "1500.00",
        "room_number": "OPD-305",
        "available_days": "Mon,Tue,Wed,Thu,Fri"
    }, follow_redirects=True)
    assert res_edit.status_code == 200
    db_session.refresh(doc)
    assert doc.specialization == "Chief Neurosurgeon"
    assert doc.consultation_fee == Decimal("1500.00")

    flask_client.get("/logout")


# =====================================================================
# 4. Staff Management
# =====================================================================

def test_admin_manage_staff(flask_client, db_session):
    login_as_admin(flask_client, db_session)

    dept = Department(name="Pharmacy Division", code="PHARM_DEPT", is_active=True)
    db_session.add(dept)
    db_session.commit()

    # 1. Create staff member
    res_create = flask_client.post("/admin/staff/create", data={
        "first_name": "Pooja",
        "last_name": "Hegde",
        "email": "pooja.pharm@medicare.ai",
        "phone": "+91 98765 88888",
        "employee_id": "EMP-PHARM-101",
        "role": "pharmacist",
        "designation": "Clinical Pharmacist",
        "department_id": str(dept.id),
        "shift": "Evening",
        "password": "Password123!"
    }, follow_redirects=True)
    assert res_create.status_code == 200
    assert b"added successfully" in res_create.data

    staff = db_session.query(Staff).filter(Staff.employee_id == "EMP-PHARM-101").first()
    assert staff is not None
    assert staff.designation == "Clinical Pharmacist"
    assert staff.shift == "Evening"

    # 2. View staff list & filter by shift
    res_list = flask_client.get("/admin/staff?shift=Evening")
    assert res_list.status_code == 200
    assert b"Pooja Hegde" in res_list.data
    assert b"EMP-PHARM-101" in res_list.data

    # 3. Duplicate employee ID rejection
    res_dup = flask_client.post("/admin/staff/create", data={
        "first_name": "Duplicate",
        "last_name": "Staff",
        "email": "dup.staff@medicare.ai",
        "employee_id": "EMP-PHARM-101",
        "designation": "Pharmacist",
        "password": "Password123!"
    }, follow_redirects=True)
    assert b"already exists" in res_dup.data

    flask_client.get("/logout")


# =====================================================================
# 5. Patients Management
# =====================================================================

def test_admin_manage_patients(flask_client, db_session):
    login_as_admin(flask_client, db_session)

    # 1. Create Patient
    res_create = flask_client.post("/admin/patients/create", data={
        "first_name": "Ishaan",
        "last_name": "Kishore",
        "email": "ishaan.k@example.com",
        "phone": "+91 97777 66666",
        "dob": "1988-11-20",
        "gender": "male",
        "blood_group": "AB+",
        "emergency_contact_name": "Ananya Kishore",
        "emergency_contact_phone": "+91 97777 55555",
        "address": "123 Indiranagar, Bengaluru",
        "allergies": "Aspirin",
        "chronic_conditions": "Asthma",
        "password": "Password123!"
    }, follow_redirects=True)
    assert res_create.status_code == 200
    assert b"registered successfully" in res_create.data

    pat = db_session.query(Patient).join(Patient.user).filter(User.email == "ishaan.k@example.com").first()
    assert pat is not None
    assert pat.blood_group == "AB+"
    assert pat.emergency_contact_name == "Ananya Kishore"
    assert pat.allergies == "Aspirin"

    # 2. View patient list, search and filter
    res_search = flask_client.get("/admin/patients?q=Ishaan&gender=male&blood_group=AB%2B")
    assert res_search.status_code == 200
    assert b"Ishaan Kishore" in res_search.data
    assert b"Aspirin" in res_search.data

    flask_client.get("/logout")


# =====================================================================
# 6. Departments Management
# =====================================================================

def test_admin_manage_departments(flask_client, db_session):
    login_as_admin(flask_client, db_session)

    # 1. Create Department
    res_create = flask_client.post("/admin/departments/create", data={
        "name": "Orthopedics & Joint Care",
        "code": "ORTHO",
        "description": "Musculoskeletal surgical care and physical rehabilitation."
    }, follow_redirects=True)
    assert res_create.status_code == 200
    assert b"established successfully" in res_create.data

    dept = db_session.query(Department).filter(Department.code == "ORTHO").first()
    assert dept is not None
    assert dept.name == "Orthopedics & Joint Care"

    # 2. Duplicate department code rejection
    res_dup = flask_client.post("/admin/departments/create", data={
        "name": "Orthopedics Branch 2",
        "code": "ORTHO"
    }, follow_redirects=True)
    assert b"already exists" in res_dup.data

    # 3. View department list
    res_list = flask_client.get("/admin/departments")
    assert res_list.status_code == 200
    assert b"Orthopedics" in res_list.data
    assert b"ORTHO" in res_list.data

    flask_client.get("/logout")


# =====================================================================
# 7. Rooms and Beds Management
# =====================================================================

def test_admin_manage_rooms_and_beds(flask_client, db_session):
    login_as_admin(flask_client, db_session)

    dept = Department(name="Pediatrics Unit", code="PEDS_UNIT", is_active=True)
    db_session.add(dept)
    db_session.commit()

    # 1. Create Room
    res_room_create = flask_client.post("/admin/rooms/create", data={
        "room_number": "PEDS-201",
        "room_type": "pediatric",
        "floor": "2",
        "department_id": str(dept.id),
        "daily_rate": "1800.00",
        "total_beds": "4"
    }, follow_redirects=True)
    assert res_room_create.status_code == 200
    assert b"created successfully" in res_room_create.data

    room = db_session.query(Room).filter(Room.room_number == "PEDS-201").first()
    assert room is not None
    assert room.room_type == RoomTypeEnum.PEDIATRIC
    assert room.daily_rate == Decimal("1800.00")

    # 2. View Rooms with filter
    res_rooms = flask_client.get("/admin/rooms?type=pediatric")
    assert res_rooms.status_code == 200
    assert b"PEDS-201" in res_rooms.data

    # 3. Create Bed inside Room
    res_bed_create = flask_client.post("/admin/beds/create", data={
        "room_id": str(room.id),
        "bed_number": "BED-P1",
        "daily_rate": "1800.00"
    }, follow_redirects=True)
    assert res_bed_create.status_code == 200
    assert b"added to Room" in res_bed_create.data

    bed = db_session.query(Bed).filter(Bed.room_id == room.id, Bed.bed_number == "BED-P1").first()
    assert bed is not None
    assert bed.status == BedStatusEnum.AVAILABLE

    # 4. Duplicate bed number in same room rejection
    res_bed_dup = flask_client.post("/admin/beds/create", data={
        "room_id": str(room.id),
        "bed_number": "BED-P1"
    }, follow_redirects=True)
    assert b"already exists in Room" in res_bed_dup.data

    # 5. View Beds & Update Bed Status
    res_beds_list = flask_client.get(f"/admin/beds?room_id={room.id}")
    assert res_beds_list.status_code == 200
    assert b"BED-P1" in res_beds_list.data

    res_status = flask_client.post(f"/admin/beds/{bed.id}/status", data={
        "status": "maintenance"
    }, follow_redirects=True)
    assert res_status.status_code == 200
    db_session.refresh(bed)
    assert bed.status == BedStatusEnum.MAINTENANCE
    assert b"MAINTENANCE" in res_status.data

    flask_client.get("/logout")


# =====================================================================
# 8. Audit Logs
# =====================================================================

def test_admin_audit_logs(flask_client, db_session):
    login_as_admin(flask_client, db_session)

    res = flask_client.get("/admin/audits")
    assert res.status_code == 200
    assert b"HIPAA-Compliant System & Security Logs" in res.data

    flask_client.get("/logout")


# =====================================================================
# 9. Role-Based Access Control (RBAC) Protection
# =====================================================================

@pytest.mark.parametrize("admin_endpoint", [
    "/admin/",
    "/admin/users",
    "/admin/doctors",
    "/admin/staff",
    "/admin/patients",
    "/admin/departments",
    "/admin/rooms",
    "/admin/beds",
    "/admin/audits"
])
def test_non_admin_cannot_access_admin_module(flask_client, db_session, admin_endpoint):
    # Create doctor user
    doctor = db_session.query(User).filter(User.email == "dr.forbidden@medicare.ai").first()
    if not doctor:
        doctor = User(
            email="dr.forbidden@medicare.ai",
            password_hash=get_password_hash("Password123!"),
            role=RoleEnum.DOCTOR,
            first_name="Doctor",
            last_name="Blocked",
            is_active=True
        )
        db_session.add(doctor)
        db_session.commit()

    # Login as doctor
    flask_client.post("/login", data={"email": "dr.forbidden@medicare.ai", "password": "Password123!"})

    # Attempt to access admin endpoint
    res = flask_client.get(admin_endpoint)
    assert res.status_code == 403

    flask_client.get("/logout")
