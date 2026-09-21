import pytest
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal

from backend.models import (
    User, RoleEnum, Patient, PatientProfile, Doctor, Staff, Department,
    Room, Ward, Bed, Admission, BedTransfer, Invoice,
    RoomTypeEnum, WardTypeEnum, BedStatusEnum, AdmissionStatusEnum, GenderEnum, AuditLog
)
from backend.security import get_password_hash, create_access_token
from backend.services import inpatient_service
from backend.services.inpatient_service import (
    admit_patient, transfer_bed, discharge_patient, update_bed_status,
    get_ipd_dashboard_stats, get_bed_availability, get_admission_detail,
    get_patient_admission_history, list_admissions,
    BedUnavailableError, PatientAlreadyAdmittedError, AdmissionNotFoundError,
    BedNotFoundError, InvalidAdmissionDataError
)


@pytest.fixture
def ipd_fixture(db_session):
    """
    Sets up a complete clinical IPD environment with:
    - 1 Admin, 1 Doctor, 1 Nurse, 2 Patients
    - 1 Department (Cardiology), 1 Ward (ICU / General)
    - 2 Rooms (Room 101: 2 beds, Room 102: 2 beds)
    - 4 Beds total: Bed 101-A, Bed 101-B, Bed 102-A, Bed 102-B (all initially AVAILABLE)
    """
    # 1. Department
    cardio_dept = Department(name="Cardiology", code="CARD-01", description="Cardiology Ward & Inpatient Unit")
    db_session.add(cardio_dept)
    db_session.flush()

    # 2. Users & Profiles
    admin_user = User(
        email="admin_ipd@chikitsasetu.ai",
        password_hash=get_password_hash("AdminPass123!"),
        role=RoleEnum.ADMIN,
        first_name="IPD",
        last_name="Administrator",
        is_active=True
    )
    doc_user = User(
        email="doctor_ipd@chikitsasetu.ai",
        password_hash=get_password_hash("DocPass123!"),
        role=RoleEnum.DOCTOR,
        first_name="Gregory",
        last_name="House",
        is_active=True
    )
    nurse_user = User(
        email="nurse_ipd@chikitsasetu.ai",
        password_hash=get_password_hash("NursePass123!"),
        role=RoleEnum.NURSE,
        first_name="Florence",
        last_name="Nightingale",
        is_active=True
    )
    pat1_user = User(
        email="patient1_ipd@chikitsasetu.ai",
        password_hash=get_password_hash("PatPass123!"),
        role=RoleEnum.PATIENT,
        first_name="John",
        last_name="Watson",
        is_active=True
    )
    pat2_user = User(
        email="patient2_ipd@chikitsasetu.ai",
        password_hash=get_password_hash("PatPass123!"),
        role=RoleEnum.PATIENT,
        first_name="Sherlock",
        last_name="Holmes",
        is_active=True
    )
    db_session.add_all([admin_user, doc_user, nurse_user, pat1_user, pat2_user])
    db_session.flush()

    # Doctor Profile
    doctor = Doctor(
        id=doc_user.id,
        specialization="Cardiology",
        department_id=cardio_dept.id,
        license_number="CARD-IPD-9988",
        qualification="MD, Interventional Cardiology",
        consultation_fee=Decimal("150.00")
    )
    db_session.add(doctor)

    # Nurse Profile
    nurse = Staff(
        id=nurse_user.id,
        department_id=cardio_dept.id,
        employee_id="STF-NURSE-01",
        designation="Charge Nurse"
    )
    db_session.add(nurse)

    # Patients & Profiles (Patient is alias of PatientProfile)
    pat1 = Patient(
        id=pat1_user.id,
        dob=date(1985, 7, 7),
        gender=GenderEnum.MALE,
        blood_group="O+",
        allergies="Penicillin"
    )
    pat2 = Patient(
        id=pat2_user.id,
        dob=date(1982, 1, 6),
        gender=GenderEnum.MALE,
        blood_group="A+"
    )
    db_session.add_all([pat1, pat2])
    db_session.flush()

    # 3. Rooms
    room101 = Room(
        room_number="101",
        room_type=RoomTypeEnum.GENERAL,
        floor=1,
        department_id=cardio_dept.id,
        daily_rate=Decimal("200.00"),
        total_beds=2
    )
    room102 = Room(
        room_number="102",
        room_type=RoomTypeEnum.ICU,
        floor=2,
        department_id=cardio_dept.id,
        daily_rate=Decimal("500.00"),
        total_beds=2
    )
    db_session.add_all([room101, room102])
    db_session.flush()

    # 4. Beds (Bed 101-A, Bed 101-B, Bed 102-A, Bed 102-B)
    bed101a = Bed(room_id=room101.id, bed_number="101-A", status=BedStatusEnum.AVAILABLE, daily_rate=Decimal("200.00"))
    bed101b = Bed(room_id=room101.id, bed_number="101-B", status=BedStatusEnum.AVAILABLE, daily_rate=Decimal("200.00"))
    bed102a = Bed(room_id=room102.id, bed_number="102-A", status=BedStatusEnum.AVAILABLE, daily_rate=Decimal("500.00"))
    bed102b = Bed(room_id=room102.id, bed_number="102-B", status=BedStatusEnum.AVAILABLE, daily_rate=Decimal("500.00"))
    db_session.add_all([bed101a, bed101b, bed102a, bed102b])
    db_session.commit()

    return {
        "admin": admin_user,
        "doctor": doc_user,
        "nurse": nurse_user,
        "patient1": pat1_user,
        "patient2": pat2_user,
        "dept": cardio_dept,
        "room101": room101,
        "room102": room102,
        "bed101a": bed101a,
        "bed101b": bed101b,
        "bed102a": bed102a,
        "bed102b": bed102b
    }


# =====================================================================
# 1. Admission & Bed Allocation Tests
# =====================================================================

def test_patient_admission_success(db_session, ipd_fixture):
    """Verifies admitting a patient changes bed to OCCUPIED and creates an active Admission."""
    pat = ipd_fixture["patient1"]
    bed = ipd_fixture["bed101a"]
    doc = ipd_fixture["doctor"]
    dept = ipd_fixture["dept"]

    assert bed.status == BedStatusEnum.AVAILABLE

    admission = admit_patient(
        db_session=db_session,
        patient_id=pat.id,
        bed_id=bed.id,
        admitting_doctor_id=doc.id,
        admission_reason="Acute Myocardial Infarction observation",
        department_id=dept.id,
        notes="Administer anticoagulant and monitor vitals q2h."
    )
    db_session.commit()

    assert admission.id is not None
    assert admission.status == AdmissionStatusEnum.ADMITTED
    assert admission.patient_id == pat.id
    assert admission.bed_id == bed.id
    assert admission.department_id == dept.id

    # Verify bed status updated to OCCUPIED
    db_session.refresh(bed)
    assert bed.status == BedStatusEnum.OCCUPIED
    assert bed.is_available is False
    assert bed.current_admission.id == admission.id


def test_prevent_assigning_occupied_bed(db_session, ipd_fixture):
    """
    CRITICAL REQUIREMENT: Prevent assigning an occupied bed.
    Verifies BedUnavailableError is raised if attempting to admit to an occupied bed.
    """
    pat1 = ipd_fixture["patient1"]
    pat2 = ipd_fixture["patient2"]
    bed = ipd_fixture["bed101a"]
    doc = ipd_fixture["doctor"]

    # Admit Patient 1 to Bed 101-A
    admit_patient(
        db_session=db_session,
        patient_id=pat1.id,
        bed_id=bed.id,
        admitting_doctor_id=doc.id,
        admission_reason="Patient 1 Initial Admission"
    )
    db_session.commit()
    db_session.refresh(bed)
    assert bed.status == BedStatusEnum.OCCUPIED

    # Attempt to admit Patient 2 to Bed 101-A (MUST BE BLOCKED)
    with pytest.raises(BedUnavailableError) as exc_info:
        admit_patient(
            db_session=db_session,
            patient_id=pat2.id,
            bed_id=bed.id,
            admitting_doctor_id=doc.id,
            admission_reason="Patient 2 Conflicting Admission"
        )

    assert "Cannot assign Bed '101-A'" in str(exc_info.value)
    assert "OCCUPIED" in str(exc_info.value)


def test_prevent_assigning_reserved_or_maintenance_bed(db_session, ipd_fixture):
    """Verifies that RESERVED and MAINTENANCE beds also cannot be assigned for admission."""
    pat = ipd_fixture["patient1"]
    bed_res = ipd_fixture["bed101a"]
    bed_maint = ipd_fixture["bed101b"]
    doc = ipd_fixture["doctor"]

    # Set statuses
    bed_res.status = BedStatusEnum.RESERVED
    bed_maint.status = BedStatusEnum.MAINTENANCE
    db_session.commit()

    # Attempt admission on RESERVED bed
    with pytest.raises(BedUnavailableError) as exc_res:
        admit_patient(
            db_session=db_session,
            patient_id=pat.id,
            bed_id=bed_res.id,
            admitting_doctor_id=doc.id,
            admission_reason="Test Reserved Bed"
        )
    assert "RESERVED" in str(exc_res.value)

    # Attempt admission on MAINTENANCE bed
    with pytest.raises(BedUnavailableError) as exc_maint:
        admit_patient(
            db_session=db_session,
            patient_id=pat.id,
            bed_id=bed_maint.id,
            admitting_doctor_id=doc.id,
            admission_reason="Test Maintenance Bed"
        )
    assert "MAINTENANCE" in str(exc_maint.value)


def test_prevent_duplicate_active_admission(db_session, ipd_fixture):
    """Verifies a patient who is already actively admitted cannot be admitted again."""
    pat = ipd_fixture["patient1"]
    bed1 = ipd_fixture["bed101a"]
    bed2 = ipd_fixture["bed101b"]
    doc = ipd_fixture["doctor"]

    admit_patient(
        db_session=db_session,
        patient_id=pat.id,
        bed_id=bed1.id,
        admitting_doctor_id=doc.id,
        admission_reason="First Admission"
    )
    db_session.commit()

    with pytest.raises(PatientAlreadyAdmittedError) as exc:
        admit_patient(
            db_session=db_session,
            patient_id=pat.id,
            bed_id=bed2.id,
            admitting_doctor_id=doc.id,
            admission_reason="Second Admission Attempt"
        )
    assert f"Patient #{pat.id} is already actively admitted" in str(exc.value)


# =====================================================================
# 2. Bed Transfer Tests
# =====================================================================

def test_bed_transfer_success(db_session, ipd_fixture):
    """
    Verifies transferring an admitted patient from Bed 101-A to Bed 102-A:
    - Origin bed 101-A transitions to MAINTENANCE.
    - Destination bed 102-A transitions to OCCUPIED.
    - BedTransfer audit entry is recorded with reasons and timestamps.
    """
    pat = ipd_fixture["patient1"]
    bed_from = ipd_fixture["bed101a"]
    bed_to = ipd_fixture["bed102a"]
    doc = ipd_fixture["doctor"]

    admission = admit_patient(
        db_session=db_session,
        patient_id=pat.id,
        bed_id=bed_from.id,
        admitting_doctor_id=doc.id,
        admission_reason="Initial Semi-Private"
    )
    db_session.commit()

    transfer = transfer_bed(
        db_session=db_session,
        admission_id=admission.id,
        to_bed_id=bed_to.id,
        reason="Condition deteriorated; transferred to ICU",
        transferred_by_id=doc.id,
        notes="Oxygen saturation dropping, ventilator required",
        release_previous_as=BedStatusEnum.MAINTENANCE
    )
    db_session.commit()

    # Refresh states
    db_session.refresh(bed_from)
    db_session.refresh(bed_to)
    db_session.refresh(admission)

    assert transfer.id is not None
    assert transfer.from_bed_id == bed_from.id
    assert transfer.to_bed_id == bed_to.id
    assert transfer.reason == "Condition deteriorated; transferred to ICU"

    # Bed statuses
    assert bed_from.status == BedStatusEnum.MAINTENANCE
    assert bed_to.status == BedStatusEnum.OCCUPIED

    # Admission pointer updated
    assert admission.bed_id == bed_to.id
    assert len(admission.transfers) == 1


def test_prevent_transfer_to_occupied_bed(db_session, ipd_fixture):
    """Verifies that transferring to an OCCUPIED bed is blocked by BedUnavailableError."""
    pat1 = ipd_fixture["patient1"]
    pat2 = ipd_fixture["patient2"]
    bed1 = ipd_fixture["bed101a"]
    bed2 = ipd_fixture["bed102a"]
    doc = ipd_fixture["doctor"]

    adm1 = admit_patient(db_session, pat1.id, bed1.id, doc.id, "Patient 1")
    adm2 = admit_patient(db_session, pat2.id, bed2.id, doc.id, "Patient 2")
    db_session.commit()

    # Attempt to transfer Patient 1 into Bed 2 which is already occupied by Patient 2
    with pytest.raises(BedUnavailableError) as exc:
        transfer_bed(
            db_session=db_session,
            admission_id=adm1.id,
            to_bed_id=bed2.id,
            reason="Illegal transfer to occupied bed"
        )
    assert "Only AVAILABLE beds can be assigned" in str(exc.value)


# =====================================================================
# 3. Discharge & Billing Tests
# =====================================================================

def test_discharge_patient_and_release_bed(db_session, ipd_fixture):
    """
    Verifies discharging a patient:
    - Admission status changes to DISCHARGED.
    - Bed status changes to MAINTENANCE for sanitization.
    - Itemized invoice is created for stay and services.
    """
    pat = ipd_fixture["patient1"]
    bed = ipd_fixture["bed101a"]
    doc = ipd_fixture["doctor"]

    admission = admit_patient(
        db_session=db_session,
        patient_id=pat.id,
        bed_id=bed.id,
        admitting_doctor_id=doc.id,
        admission_reason="Observation"
    )
    db_session.commit()

    adm, invoice = discharge_patient(
        db_session=db_session,
        admission_id=admission.id,
        discharge_summary="Patient recovered satisfactorily and is discharged home."
    )
    db_session.commit()

    db_session.refresh(bed)
    db_session.refresh(admission)

    assert admission.status == AdmissionStatusEnum.DISCHARGED
    assert admission.discharge_date is not None
    assert "satisfactorily" in admission.discharge_summary
    assert bed.status == BedStatusEnum.MAINTENANCE
    assert invoice is not None
    assert invoice.total_amount > 0


# =====================================================================
# 4. Bed Status Transitions & Maintenance
# =====================================================================

def test_update_bed_status_sanitization_flow(db_session, ipd_fixture):
    """Verifies updating bed status from MAINTENANCE back to AVAILABLE after cleaning."""
    bed = ipd_fixture["bed101a"]
    bed.status = BedStatusEnum.MAINTENANCE
    db_session.commit()

    updated = update_bed_status(
        db_session=db_session,
        bed_id=bed.id,
        new_status=BedStatusEnum.AVAILABLE,
        actor_id=ipd_fixture["nurse"].id,
        notes="Deep sanitization and new linens placed"
    )
    db_session.commit()

    assert updated.status == BedStatusEnum.AVAILABLE
    assert updated.is_available is True


# =====================================================================
# 5. Dashboard Statistics Calculation Tests
# =====================================================================

def test_ipd_dashboard_statistics(db_session, ipd_fixture):
    """
    Verifies IPD Dashboard statistics calculations:
    - Total beds
    - Occupied beds
    - Available beds
    - Reserved beds
    - Maintenance beds
    - Occupancy percentage ((Occupied / Total) * 100)
    """
    bed1 = ipd_fixture["bed101a"]
    bed2 = ipd_fixture["bed101b"]
    bed3 = ipd_fixture["bed102a"]
    bed4 = ipd_fixture["bed102b"]
    pat = ipd_fixture["patient1"]
    doc = ipd_fixture["doctor"]

    # Configure exact statuses across 4 beds:
    # 1. Admit to bed1 -> OCCUPIED
    admit_patient(db_session, pat.id, bed1.id, doc.id, "Cardio Observation")
    # 2. bed2 -> AVAILABLE
    bed2.status = BedStatusEnum.AVAILABLE
    # 3. bed3 -> RESERVED
    bed3.status = BedStatusEnum.RESERVED
    # 4. bed4 -> MAINTENANCE
    bed4.status = BedStatusEnum.MAINTENANCE
    db_session.commit()

    stats = get_ipd_dashboard_stats(db_session)

    assert stats["total_beds"] == 4
    assert stats["occupied_beds"] == 1
    assert stats["available_beds"] == 1
    assert stats["reserved_beds"] == 1
    assert stats["maintenance_beds"] == 1
    # Occupancy percentage: (1 / 4) * 100 = 25.0%
    assert stats["occupancy_percentage"] == 25.0
    assert stats["total_rooms"] == 2
    assert stats["active_admissions_count"] == 1


# =====================================================================
# 6. Admission History Retrieval Tests
# =====================================================================

def test_patient_admission_history(db_session, ipd_fixture):
    """Verifies chronological tracking of multiple admissions for a patient."""
    pat = ipd_fixture["patient1"]
    bed1 = ipd_fixture["bed101a"]
    bed2 = ipd_fixture["bed101b"]
    doc = ipd_fixture["doctor"]

    # 1st Episode: Admitted and Discharged
    adm1 = admit_patient(db_session, pat.id, bed1.id, doc.id, "Episode 1: Chest Pain")
    db_session.commit()
    discharge_patient(db_session, adm1.id, "Discharged after normal ECG")
    # Release bed1 from maintenance to available
    bed1.status = BedStatusEnum.AVAILABLE
    db_session.commit()

    # 2nd Episode: Readmitted
    adm2 = admit_patient(db_session, pat.id, bed2.id, doc.id, "Episode 2: Palpitations")
    db_session.commit()

    history = get_patient_admission_history(db_session, pat.id)

    assert len(history) == 2
    assert history[0].id == adm2.id  # Latest first
    assert history[0].status == AdmissionStatusEnum.ADMITTED
    assert history[1].id == adm1.id
    assert history[1].status == AdmissionStatusEnum.DISCHARGED


# =====================================================================
# 7. Flask Web Blueprint Integration Tests
# =====================================================================

def test_flask_ipd_web_flows(flask_client, db_session, ipd_fixture):
    """
    Verifies Flask Web routes:
    - /ipd/ (dashboard)
    - /ipd/beds (bed roster)
    - /ipd/admissions (admissions listing)
    - POST /ipd/admit
    - POST /ipd/transfer/<id>
    - POST /ipd/discharge/<id>
    """
    admin = ipd_fixture["admin"]
    pat = ipd_fixture["patient1"]
    bed = ipd_fixture["bed101a"]
    bed_dest = ipd_fixture["bed102a"]
    doc = ipd_fixture["doctor"]

    # Simulate logged-in admin
    with flask_client.session_transaction() as sess:
        sess["user_id"] = admin.id
        sess["user_role"] = admin.role.value
        sess["user_name"] = f"{admin.first_name} {admin.last_name}"

    # 1. Access Dashboard
    resp = flask_client.get("/ipd/")
    assert resp.status_code == 200
    assert b"Inpatient Department (IPD)" in resp.data
    assert b"Live Ward &amp; Room Bed Matrix" in resp.data or b"Live Ward" in resp.data

    # 2. Access Beds Roster
    resp_beds = flask_client.get("/ipd/beds")
    assert resp_beds.status_code == 200
    assert b"Hospital Bed Availability Directory" in resp_beds.data

    # 3. Post Admission via Web
    admit_resp = flask_client.post("/ipd/admit", data={
        "patient_id": pat.id,
        "bed_id": bed.id,
        "doctor_id": doc.id,
        "admission_reason": "Web Inpatient Admission",
        "notes": "Admitted via portal"
    }, follow_redirects=True)
    assert admit_resp.status_code == 200
    assert b"successfully admitted" in admit_resp.data

    # Verify admission created
    adm = db_session.query(Admission).filter(Admission.patient_id == pat.id, Admission.status == AdmissionStatusEnum.ADMITTED).first()
    assert adm is not None

    # 4. Post Transfer via Web
    transfer_resp = flask_client.post(f"/ipd/transfer/{adm.id}", data={
        "to_bed_id": bed_dest.id,
        "reason": "Web Portal Bed Transfer",
        "release_previous_as": "maintenance"
    }, follow_redirects=True)
    assert transfer_resp.status_code == 200
    assert b"transferred to Bed" in transfer_resp.data

    # 5. Post Discharge via Web
    discharge_resp = flask_client.post(f"/ipd/discharge/{adm.id}", data={
        "discharge_summary": "Discharged successfully via web portal"
    }, follow_redirects=True)
    assert discharge_resp.status_code == 200
    assert b"successfully discharged" in discharge_resp.data


# =====================================================================
# 8. FastAPI Endpoints Integration Tests
# =====================================================================

def test_fastapi_ipd_endpoints(fastapi_client, db_session, ipd_fixture):
    """
    Verifies FastAPI endpoints:
    - GET /api/v1/inpatient/dashboard-stats
    - GET /api/v1/inpatient/beds
    - POST /api/v1/inpatient/admit
    - POST /api/v1/inpatient/admissions/{id}/transfer
    - POST /api/v1/inpatient/admissions/{id}/discharge
    """
    admin = ipd_fixture["admin"]
    pat = ipd_fixture["patient1"]
    bed1 = ipd_fixture["bed101a"]
    bed2 = ipd_fixture["bed102a"]
    token = create_access_token({"sub": str(admin.id), "role": admin.role.value, "email": admin.email})
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Dashboard Stats
    stats_res = fastapi_client.get("/api/v1/inpatient/dashboard-stats", headers=headers)
    assert stats_res.status_code == 200
    data = stats_res.json()
    assert "total_beds" in data
    assert "occupancy_percentage" in data

    # 2. List Beds
    beds_res = fastapi_client.get("/api/v1/inpatient/beds", headers=headers)
    assert beds_res.status_code == 200
    assert len(beds_res.json()) >= 4

    # 3. Admit Patient
    admit_res = fastapi_client.post("/api/v1/inpatient/admit", headers=headers, json={
        "patient_id": pat.id,
        "bed_id": bed1.id,
        "admission_reason": "FastAPI Triage Admission"
    })
    assert admit_res.status_code == 201
    adm_id = admit_res.json()["id"]

    # 4. Attempt to admit to OCCUPIED bed (MUST FAIL WITH 400)
    conflict_res = fastapi_client.post("/api/v1/inpatient/admit", headers=headers, json={
        "patient_id": ipd_fixture["patient2"].id,
        "bed_id": bed1.id,
        "admission_reason": "Conflicting API Admission"
    })
    assert conflict_res.status_code == 400
    assert "Cannot assign Bed" in conflict_res.json()["detail"]

    # 5. Bed Transfer
    transfer_res = fastapi_client.post(f"/api/v1/inpatient/admissions/{adm_id}/transfer", headers=headers, json={
        "to_bed_id": bed2.id,
        "reason": "FastAPI clinical transfer"
    })
    assert transfer_res.status_code == 200
    assert transfer_res.json()["to_bed_id"] == bed2.id

    # 6. Discharge
    discharge_res = fastapi_client.post(f"/api/v1/inpatient/admissions/{adm_id}/discharge", headers=headers, json={
        "discharge_summary": "Discharged from API test"
    })
    assert discharge_res.status_code == 200
    assert discharge_res.json()["status"] == "unpaid"
