import pytest
from datetime import date, timedelta
from decimal import Decimal

from core.models import (
    User, RoleEnum, Patient, PatientProfile, Doctor, Department,
    Medicine, MedicineBatch, Prescription, PrescriptionItem,
    PrescriptionStatusEnum, AuditLog, Notification, GenderEnum
)
from core.security import get_password_hash
from core.services.prescription_service import (
    create_prescription, dispense_prescription, cancel_prescription,
    get_prescription_detail, list_prescriptions,
    InvalidPrescriptionDataError, PrescriptionServiceError,
    PrescriptionNotFoundError, PrescriptionPermissionError
)


@pytest.fixture
def prescription_fixture(db_session):
    """
    Sets up a complete clinical environment with:
    - 1 Doctor
    - 2 Patients
    - 1 Pharmacist
    - 1 Receptionist
    - 3 Medicines with FEFO batches
    """
    # Department
    dept = Department(name="Internal Medicine", code="INT-MED", description="Internal Medicine")
    db_session.add(dept)
    db_session.flush()

    # Doctor
    doc_user = User(
        email="doc_rx@chikitsasetu.ai",
        password_hash=get_password_hash("DocPass123!"),
        role=RoleEnum.DOCTOR,
        first_name="Gregory",
        last_name="House"
    )
    db_session.add(doc_user)
    db_session.flush()

    doctor = Doctor(
        user_id=doc_user.id,
        department_id=dept.id,
        specialization="Nephrology",
        license_number="DOC-RX-9901",
        qualification="MD, MBBS"
    )
    db_session.add(doctor)

    # Doctor 2
    doc2_user = User(
        email="doc2_rx@chikitsasetu.ai",
        password_hash=get_password_hash("DocPass123!"),
        role=RoleEnum.DOCTOR,
        first_name="James",
        last_name="Wilson"
    )
    db_session.add(doc2_user)
    db_session.flush()
    doctor2 = Doctor(
        user_id=doc2_user.id,
        department_id=dept.id,
        specialization="Oncology",
        license_number="DOC-RX-9902",
        qualification="MD, Oncology"
    )
    db_session.add(doctor2)

    # Patient 1
    pat1_user = User(
        email="patient1_rx@chikitsasetu.ai",
        password_hash=get_password_hash("PatPass123!"),
        role=RoleEnum.PATIENT,
        first_name="Alice",
        last_name="Smith",
        phone="555-0101"
    )
    db_session.add(pat1_user)
    db_session.flush()

    pat1_prof = PatientProfile(id=pat1_user.id, dob=date(1990, 5, 15), gender=GenderEnum.FEMALE, blood_group="A+")
    db_session.add(pat1_prof)

    # Patient 2
    pat2_user = User(
        email="patient2_rx@chikitsasetu.ai",
        password_hash=get_password_hash("PatPass123!"),
        role=RoleEnum.PATIENT,
        first_name="Bob",
        last_name="Jones",
        phone="555-0102"
    )
    db_session.add(pat2_user)
    db_session.flush()

    pat2_prof = PatientProfile(id=pat2_user.id, dob=date(1985, 10, 20), gender=GenderEnum.MALE, blood_group="O-")
    db_session.add(pat2_prof)

    # Pharmacist
    pharm_user = User(
        email="pharmacist_rx@chikitsasetu.ai",
        password_hash=get_password_hash("PharmPass123!"),
        role=RoleEnum.PHARMACIST,
        first_name="Walter",
        last_name="White"
    )
    db_session.add(pharm_user)

    # Receptionist
    rec_user = User(
        email="rec_rx@chikitsasetu.ai",
        password_hash=get_password_hash("RecPass123!"),
        role=RoleEnum.RECEPTIONIST,
        first_name="Pam",
        last_name="Beesly"
    )
    db_session.add(rec_user)
    db_session.flush()

    # Medicines
    med1 = Medicine(
        name="Amoxicillin 500mg",
        generic_name="Amoxicillin",
        category="Antibiotic",
        unit="Capsule",
        unit_price=Decimal("15.00"),
        reorder_level=20
    )
    med2 = Medicine(
        name="Paracetamol 650mg",
        generic_name="Acetaminophen",
        category="Analgesic",
        unit="Tablet",
        unit_price=Decimal("5.00"),
        reorder_level=30
    )
    med3 = Medicine(
        name="Metformin 500mg",
        generic_name="Metformin Hydrochloride",
        category="Antidiabetic",
        unit="Tablet",
        unit_price=Decimal("8.00"),
        reorder_level=25
    )
    db_session.add_all([med1, med2, med3])
    db_session.flush()

    # Batches for med1 (FEFO: Batch A expires in 30 days, Batch B in 180 days)
    batch1_a = MedicineBatch(
        medicine_id=med1.id,
        batch_number="AMX-B1",
        expiry_date=date.today() + timedelta(days=30),
        quantity_in_stock=15,
        purchase_cost=Decimal("7.50")
    )
    batch1_b = MedicineBatch(
        medicine_id=med1.id,
        batch_number="AMX-B2",
        expiry_date=date.today() + timedelta(days=180),
        quantity_in_stock=50,
        purchase_cost=Decimal("7.50")
    )

    # Batch for med2
    batch2 = MedicineBatch(
        medicine_id=med2.id,
        batch_number="PCM-B1",
        expiry_date=date.today() + timedelta(days=365),
        quantity_in_stock=100,
        purchase_cost=Decimal("2.00")
    )

    # Batch for med3 with low stock
    batch3 = MedicineBatch(
        medicine_id=med3.id,
        batch_number="MET-B1",
        expiry_date=date.today() + timedelta(days=200),
        quantity_in_stock=10,
        purchase_cost=Decimal("3.50")
    )

    db_session.add_all([batch1_a, batch1_b, batch2, batch3])
    db_session.commit()

    return {
        "doctor_user": doc_user,
        "doctor": doctor,
        "doctor2_user": doc2_user,
        "patient1_user": pat1_user,
        "patient1_profile": pat1_prof,
        "patient2_user": pat2_user,
        "patient2_profile": pat2_prof,
        "pharm_user": pharm_user,
        "rec_user": rec_user,
        "med1": med1,
        "med2": med2,
        "med3": med3,
        "batch1_a": batch1_a,
        "batch1_b": batch1_b,
        "batch2": batch2,
        "batch3": batch3
    }


def test_doctor_create_single_medicine_prescription(prescription_fixture, db_session):
    """Verifies successful electronic prescription creation for a single drug."""
    data = prescription_fixture
    items = [{
        "medicine_id": data["med1"].id,
        "dosage": "500 mg",
        "frequency": "1-0-1 after meals",
        "duration_days": 7,
        "quantity_prescribed": 14,
        "instructions": "Complete full course with water"
    }]

    rx = create_prescription(
        db_session=db_session,
        doctor_id=data["doctor_user"].id,
        patient_id=data["patient1_user"].id,
        items=items,
        notes="First encounter prescription",
        actor_id=data["doctor_user"].id
    )

    assert rx.id is not None
    assert rx.status == PrescriptionStatusEnum.PENDING
    assert rx.patient_id == data["patient1_user"].id
    assert rx.doctor_id == data["doctor_user"].id
    assert len(rx.items) == 1
    assert rx.items[0].medicine_id == data["med1"].id
    assert rx.items[0].dosage == "500 mg"
    assert rx.items[0].duration_days == 7
    assert rx.items[0].quantity_prescribed == 14
    assert rx.items[0].quantity_dispensed == 0

    # Verify audit log
    audit = db_session.query(AuditLog).filter(
        AuditLog.resource_id == rx.id,
        AuditLog.action == "PRESCRIPTION_CREATED"
    ).first()
    assert audit is not None
    assert audit.user_id == data["doctor_user"].id

    # Verify notification to patient
    notif = db_session.query(Notification).filter(
        Notification.user_id == data["patient1_user"].id,
        Notification.title == "New Prescription Issued"
    ).first()
    assert notif is not None


def test_doctor_create_multi_medicine_prescription(prescription_fixture, db_session):
    """Verifies creating an electronic prescription with multiple distinct medications."""
    data = prescription_fixture
    items = [
        {
            "medicine_id": data["med1"].id,
            "dosage": "500 mg",
            "frequency": "1-0-1",
            "duration_days": 5,
            "quantity_prescribed": 10,
            "instructions": "Take after meals"
        },
        {
            "medicine_id": data["med2"].id,
            "dosage": "650 mg",
            "frequency": "1-1-1 SOS",
            "duration_days": 3,
            "quantity_prescribed": 9,
            "instructions": "For fever only"
        },
        {
            "medicine_id": data["med3"].id,
            "dosage": "500 mg",
            "frequency": "0-0-1",
            "duration_days": 30,
            "quantity_prescribed": 30,
            "instructions": "At bedtime"
        }
    ]

    rx = create_prescription(
        db_session=db_session,
        doctor_id=data["doctor_user"].id,
        patient_id=data["patient1_user"].id,
        items=items,
        notes="Multi-drug therapy",
        actor_id=data["doctor_user"].id
    )

    assert rx.id is not None
    assert len(rx.items) == 3
    med_ids = [item.medicine_id for item in rx.items]
    assert data["med1"].id in med_ids
    assert data["med2"].id in med_ids
    assert data["med3"].id in med_ids


def test_validation_rejects_negative_or_zero_duration(prescription_fixture, db_session):
    """Verifies that duration <= 0 is strictly rejected."""
    data = prescription_fixture

    # duration_days = 0
    with pytest.raises(InvalidPrescriptionDataError) as exc_info:
        create_prescription(
            db_session=db_session,
            doctor_id=data["doctor_user"].id,
            patient_id=data["patient1_user"].id,
            items=[{
                "medicine_id": data["med1"].id,
                "dosage": "500 mg",
                "frequency": "1-0-1",
                "duration_days": 0,
                "quantity_prescribed": 10
            }]
        )
    assert "must be at least 1 day" in str(exc_info.value)

    # duration_days = -5
    with pytest.raises(InvalidPrescriptionDataError) as exc_info2:
        create_prescription(
            db_session=db_session,
            doctor_id=data["doctor_user"].id,
            patient_id=data["patient1_user"].id,
            items=[{
                "medicine_id": data["med1"].id,
                "dosage": "500 mg",
                "frequency": "1-0-1",
                "duration_days": -5,
                "quantity_prescribed": 10
            }]
        )
    assert "must be at least 1 day" in str(exc_info2.value)


def test_validation_rejects_excessive_duration(prescription_fixture, db_session):
    """Verifies that duration > 365 days is rejected."""
    data = prescription_fixture
    with pytest.raises(InvalidPrescriptionDataError) as exc_info:
        create_prescription(
            db_session=db_session,
            doctor_id=data["doctor_user"].id,
            patient_id=data["patient1_user"].id,
            items=[{
                "medicine_id": data["med1"].id,
                "dosage": "500 mg",
                "frequency": "1-0-1",
                "duration_days": 366,
                "quantity_prescribed": 10
            }]
        )
    assert "cannot exceed 365 days" in str(exc_info.value)


def test_validation_rejects_negative_or_zero_quantity(prescription_fixture, db_session):
    """Verifies that prescribed quantity <= 0 is strictly rejected."""
    data = prescription_fixture
    with pytest.raises(InvalidPrescriptionDataError) as exc_info:
        create_prescription(
            db_session=db_session,
            doctor_id=data["doctor_user"].id,
            patient_id=data["patient1_user"].id,
            items=[{
                "medicine_id": data["med1"].id,
                "dosage": "500 mg",
                "frequency": "1-0-1",
                "duration_days": 5,
                "quantity_prescribed": 0
            }]
        )
    assert "must be at least 1 unit" in str(exc_info.value)


def test_validation_rejects_excessive_quantity(prescription_fixture, db_session):
    """Verifies that prescribed quantity > 1000 is rejected."""
    data = prescription_fixture
    with pytest.raises(InvalidPrescriptionDataError) as exc_info:
        create_prescription(
            db_session=db_session,
            doctor_id=data["doctor_user"].id,
            patient_id=data["patient1_user"].id,
            items=[{
                "medicine_id": data["med1"].id,
                "dosage": "500 mg",
                "frequency": "1-0-1",
                "duration_days": 5,
                "quantity_prescribed": 1001
            }]
        )
    assert "cannot exceed 1,000 units" in str(exc_info.value)


def test_validation_rejects_empty_items(prescription_fixture, db_session):
    """Verifies that creating a prescription without medication items raises an error."""
    data = prescription_fixture
    with pytest.raises(InvalidPrescriptionDataError) as exc_info:
        create_prescription(
            db_session=db_session,
            doctor_id=data["doctor_user"].id,
            patient_id=data["patient1_user"].id,
            items=[]
        )
    assert "must contain at least one" in str(exc_info.value)


def test_validation_rejects_duplicate_medicines(prescription_fixture, db_session):
    """Verifies that specifying the same drug multiple times in one order is prevented."""
    data = prescription_fixture
    items = [
        {
            "medicine_id": data["med1"].id,
            "dosage": "250 mg",
            "frequency": "1-0-0",
            "duration_days": 5,
            "quantity_prescribed": 5
        },
        {
            "medicine_id": data["med1"].id,  # Duplicate!
            "dosage": "500 mg",
            "frequency": "0-0-1",
            "duration_days": 5,
            "quantity_prescribed": 5
        }
    ]

    with pytest.raises(InvalidPrescriptionDataError) as exc_info:
        create_prescription(
            db_session=db_session,
            doctor_id=data["doctor_user"].id,
            patient_id=data["patient1_user"].id,
            items=items
        )
    assert "Duplicate medication" in str(exc_info.value)


def test_patient_can_view_own_prescriptions(flask_client, prescription_fixture, db_session):
    """Verifies that a logged-in patient can view their own prescription list and printable slip."""
    data = prescription_fixture
    pat_id = data["patient1_user"].id
    pat_email = data["patient1_user"].email
    pat_name = data["patient1_user"].full_name

    # Create prescription for patient 1
    rx = create_prescription(
        db_session=db_session,
        doctor_id=data["doctor_user"].id,
        patient_id=pat_id,
        items=[{
            "medicine_id": data["med1"].id,
            "dosage": "500 mg",
            "frequency": "1-0-1",
            "duration_days": 7,
            "quantity_prescribed": 14,
            "instructions": "Take with meal"
        }],
        notes="Hydrate adequately."
    )

    with flask_client.session_transaction() as sess:
        sess["user_id"] = pat_id
        sess["user_email"] = pat_email
        sess["user_role"] = "patient"
        sess["user_name"] = pat_name

    # 1. View listing
    resp = flask_client.get("/patient/prescriptions")
    assert resp.status_code == 200
    assert "Amoxicillin 500mg" in resp.data.decode("utf-8")
    assert "Prescription #" in resp.data.decode("utf-8")

    # 2. View detail slip
    detail_resp = flask_client.get(f"/patient/prescriptions/{rx.id}")
    assert detail_resp.status_code == 200
    assert "Amoxicillin 500mg" in detail_resp.data.decode("utf-8")
    assert "Take with meal" in detail_resp.data.decode("utf-8")
    assert "Hydrate adequately" in detail_resp.data.decode("utf-8")


def test_patient_cannot_view_other_patient_prescription(flask_client, prescription_fixture, db_session):
    """Verifies strict cross-patient confidentiality: Patient 2 receives 403 when requesting Patient 1's prescription."""
    data = prescription_fixture
    pat1_id = data["patient1_user"].id
    pat2_id = data["patient2_user"].id
    pat2_email = data["patient2_user"].email
    pat2_name = data["patient2_user"].full_name

    # Create prescription for Patient 1
    rx_pat1 = create_prescription(
        db_session=db_session,
        doctor_id=data["doctor_user"].id,
        patient_id=pat1_id,
        items=[{
            "medicine_id": data["med1"].id,
            "dosage": "500 mg",
            "frequency": "1-0-1",
            "duration_days": 5,
            "quantity_prescribed": 10
        }]
    )

    # Log in as Patient 2
    with flask_client.session_transaction() as sess:
        sess["user_id"] = pat2_id
        sess["user_email"] = pat2_email
        sess["user_role"] = "patient"
        sess["user_name"] = pat2_name

    # Attempt to access Patient 1's prescription
    resp = flask_client.get(f"/patient/prescriptions/{rx_pat1.id}")
    assert resp.status_code == 403


def test_pharmacy_dispense_fefo_inventory_deduction(flask_client, prescription_fixture, db_session):
    """
    Verifies that pharmacy dispensation applies First-Expiring, First-Out (FEFO) batch deduction.
    Batch A (expires in 30 days, 15 units) should be exhausted before Batch B (expires in 180 days, 50 units).
    """
    data = prescription_fixture
    med1_id = data["med1"].id
    batch_a_id = data["batch1_a"].id
    batch_b_id = data["batch1_b"].id

    # Prescribe 25 units of Amoxicillin
    rx = create_prescription(
        db_session=db_session,
        doctor_id=data["doctor_user"].id,
        patient_id=data["patient1_user"].id,
        items=[{
            "medicine_id": med1_id,
            "dosage": "500 mg",
            "frequency": "1-0-1",
            "duration_days": 12,
            "quantity_prescribed": 25
        }]
    )

    # Dispense via service
    result = dispense_prescription(
        db_session=db_session,
        prescription_id=rx.id,
        actor_id=data["pharm_user"].id
    )

    assert result["status"] == "dispensed"
    assert result["units_dispensed"] == 25

    # Check batch stock levels:
    # Batch A had 15 units -> should be 0
    # Batch B had 50 units -> should have 10 deducted -> 40 remaining
    batch_a = db_session.query(MedicineBatch).filter(MedicineBatch.id == batch_a_id).first()
    batch_b = db_session.query(MedicineBatch).filter(MedicineBatch.id == batch_b_id).first()

    assert batch_a.quantity_in_stock == 0
    assert batch_b.quantity_in_stock == 40

    # Check rx status
    rx_upd = db_session.query(Prescription).filter(Prescription.id == rx.id).first()
    assert rx_upd.status == PrescriptionStatusEnum.DISPENSED
    assert rx_upd.items[0].quantity_dispensed == 25

    # Check audit log
    audit = db_session.query(AuditLog).filter(
        AuditLog.resource_id == rx.id,
        AuditLog.action == "PRESCRIPTION_DISPENSED"
    ).first()
    assert audit is not None
    assert audit.details["total_units_dispensed"] == 25


def test_pharmacy_partial_dispensing_insufficient_stock(prescription_fixture, db_session):
    """
    Verifies that when total inventory is less than prescribed quantity,
    the available inventory is dispensed and status transitions to PARTIALLY_DISPENSED.
    """
    data = prescription_fixture
    med3_id = data["med3"].id  # Has 10 units in stock

    rx = create_prescription(
        db_session=db_session,
        doctor_id=data["doctor_user"].id,
        patient_id=data["patient1_user"].id,
        items=[{
            "medicine_id": med3_id,
            "dosage": "500 mg",
            "frequency": "1-0-0",
            "duration_days": 30,
            "quantity_prescribed": 30  # Needs 30, only 10 in stock
        }]
    )

    result = dispense_prescription(
        db_session=db_session,
        prescription_id=rx.id,
        actor_id=data["pharm_user"].id
    )

    assert result["status"] == "partially_dispensed"
    assert result["units_dispensed"] == 10

    rx_upd = db_session.query(Prescription).filter(Prescription.id == rx.id).first()
    assert rx_upd.status == PrescriptionStatusEnum.PARTIALLY_DISPENSED
    assert rx_upd.items[0].quantity_dispensed == 10


def test_prevent_dispensing_already_dispensed_prescription(prescription_fixture, db_session):
    """Verifies that attempting to dispense an already fulfilled order raises an error."""
    data = prescription_fixture
    rx = create_prescription(
        db_session=db_session,
        doctor_id=data["doctor_user"].id,
        patient_id=data["patient1_user"].id,
        items=[{
            "medicine_id": data["med2"].id,
            "dosage": "650 mg",
            "frequency": "1-0-1",
            "duration_days": 2,
            "quantity_prescribed": 4
        }]
    )

    # First dispensation fulfills it
    dispense_prescription(db_session, rx.id, actor_id=data["pharm_user"].id)

    # Second attempt must raise PrescriptionServiceError
    with pytest.raises(PrescriptionServiceError) as exc_info:
        dispense_prescription(db_session, rx.id, actor_id=data["pharm_user"].id)
    assert "already been completely dispensed" in str(exc_info.value)


def test_prescription_cancellation_and_audit_logging(prescription_fixture, db_session):
    """Verifies that an unfulfilled prescription can be cancelled with a clinical reason and audit trail."""
    data = prescription_fixture
    rx = create_prescription(
        db_session=db_session,
        doctor_id=data["doctor_user"].id,
        patient_id=data["patient1_user"].id,
        items=[{
            "medicine_id": data["med1"].id,
            "dosage": "500 mg",
            "frequency": "1-0-1",
            "duration_days": 5,
            "quantity_prescribed": 10
        }]
    )

    cancelled_rx = cancel_prescription(
        db_session=db_session,
        prescription_id=rx.id,
        actor_id=data["doctor_user"].id,
        cancellation_reason="Patient reported allergic rash"
    )

    assert cancelled_rx.status == PrescriptionStatusEnum.CANCELLED
    assert "Patient reported allergic rash" in cancelled_rx.notes

    # Verify audit log
    audit = db_session.query(AuditLog).filter(
        AuditLog.resource_id == rx.id,
        AuditLog.action == "PRESCRIPTION_CANCELLED"
    ).first()
    assert audit is not None
    assert audit.details["cancellation_reason"] == "Patient reported allergic rash"


def test_doctor_web_prescription_create_flow(flask_client, prescription_fixture, db_session):
    """Tests the doctor web interface for creating multi-medicine prescriptions."""
    data = prescription_fixture
    doc_id = data["doctor_user"].id
    doc_email = data["doctor_user"].email
    doc_name = data["doctor_user"].full_name
    pat_id = data["patient1_profile"].id
    pat_user_id = data["patient1_user"].id

    with flask_client.session_transaction() as sess:
        sess["user_id"] = doc_id
        sess["user_email"] = doc_email
        sess["user_role"] = "doctor"
        sess["user_name"] = doc_name

    # 1. GET creation form
    get_resp = flask_client.get(f"/doctor/patient/{pat_id}/prescription/new")
    assert get_resp.status_code == 200
    assert "Write Electronic Prescription" in get_resp.data.decode("utf-8")

    # 2. POST multi-medicine prescription
    post_data = {
        "medicine_id": [str(data["med1"].id), str(data["med2"].id)],
        "dosage": ["500mg", "650mg"],
        "frequency": ["1-0-1", "1-0-0"],
        "duration_days": ["7", "3"],
        "qty_prescribed": ["14", "3"],
        "instructions": ["With meals", "Morning only"],
        "rx_notes": "Clinical review after 7 days."
    }

    resp = flask_client.post(
        f"/doctor/patient/{pat_id}/prescription/new",
        data=post_data,
        follow_redirects=True
    )
    assert resp.status_code == 200

    # Check persistence
    created_rx = db_session.query(Prescription).filter(
        Prescription.patient_id == pat_user_id,
        Prescription.doctor_id == doc_id
    ).order_by(Prescription.id.desc()).first()

    assert created_rx is not None
    assert len(created_rx.items) == 2
    assert created_rx.notes == "Clinical review after 7 days."


def test_unauthorized_role_cannot_prescribe(flask_client, prescription_fixture, db_session):
    """Verifies that non-doctor/non-admin roles (e.g. receptionist, patient) are denied prescription creation access."""
    data = prescription_fixture
    rec_id = data["rec_user"].id
    rec_email = data["rec_user"].email
    rec_name = data["rec_user"].full_name
    pat_id = data["patient1_profile"].id

    with flask_client.session_transaction() as sess:
        sess["user_id"] = rec_id
        sess["user_email"] = rec_email
        sess["user_role"] = "receptionist"
        sess["user_name"] = rec_name

    resp = flask_client.post(
        f"/doctor/patient/{pat_id}/prescription/new",
        data={"medicine_id": [str(data["med1"].id)]},
        follow_redirects=True
    )
    # Blocked by @roles_required(RoleEnum.DOCTOR, RoleEnum.ADMIN)
    assert resp.status_code in [403, 302]
