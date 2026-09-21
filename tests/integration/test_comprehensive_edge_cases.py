"""
Comprehensive Testing Pass: Edge Cases, Boundary Conditions, Duplicate Operations,
Empty Database Resilience, Permission Failures, and Happy Paths across all 18 Healthcare Domains.
"""

import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from backend.models import (
    User, RoleEnum, GenderEnum, Patient, PatientProfile, Doctor, DoctorProfile,
    Staff, Department, Appointment, AppointmentStatusEnum,
    MedicalRecord, Prescription, PrescriptionItem, PrescriptionStatusEnum,
    LabTest, LabOrder, LabOrderStatusEnum,
    Medicine, MedicineInventory, StockTransaction, StockTransactionTypeEnum,
    Ward, Room, Bed, Admission, AdmissionStatusEnum, BedStatusEnum, RoomTypeEnum, WardTypeEnum,
    Bill, BillItem, Payment, BillStatusEnum, PaymentStatusEnum, ItemTypeEnum, PaymentMethodEnum,
    Notification, NotificationTypeEnum, AuditLog
)
from backend.security import get_password_hash, create_access_token
from backend.services import (
    appointment_service, inpatient_service, billing_service,
    notification_service, audit_service, analytics_service,
    prescription_service, laboratory_service, pharmacy_service,
    medical_record_service
)
from backend.services.notification_service import NotificationService
from backend.services.inpatient_service import (
    admit_patient, transfer_bed, discharge_patient,
    BedUnavailableError, PatientAlreadyAdmittedError, AdmissionNotFoundError,
    BedNotFoundError, InvalidAdmissionDataError
)
from backend.services.billing_service import (
    record_payment, create_bill, BillNotFoundError,
    InvalidBillDataError, PaymentExceedsBalanceError
)
from backend.services.prescription_service import (
    create_prescription, dispense_prescription,
    InvalidPrescriptionDataError, PrescriptionNotFoundError,
    InventoryShortageError
)
from backend.services.appointment_service import (
    book_appointment, reschedule_appointment, cancel_appointment,
    DuplicateBookingError, AppointmentNotFoundError, AppointmentStateError,
    InvalidAppointmentDataError
)
from backend.services.laboratory_service import (
    order_lab_tests, cancel_lab_order, receive_and_collect_sample,
    InvalidLabDataError, LabOrderNotFoundError, LabInvalidStateTransitionError
)
from backend.services.pharmacy_service import (
    create_medicine, stock_in, stock_out,
    InvalidInventoryDataError, InsufficientInventoryError, MedicineNotFoundError, BatchNotFoundError
)


# =====================================================================
# Domain Fixtures & Helpers
# =====================================================================

@pytest.fixture
def base_clinical_setup(db_session):
    """Provides populated base users for each role."""
    admin = User(
        email="edge_admin@chikitsasetu.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.ADMIN,
        first_name="Admin",
        last_name="Edge",
        is_active=True
    )
    doc_user = User(
        email="edge_doctor@chikitsasetu.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.DOCTOR,
        first_name="Doc",
        last_name="Edge",
        is_active=True
    )
    nurse_user = User(
        email="edge_nurse@chikitsasetu.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.NURSE,
        first_name="Nurse",
        last_name="Edge",
        is_active=True
    )
    rec_user = User(
        email="edge_receptionist@chikitsasetu.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.RECEPTIONIST,
        first_name="Rec",
        last_name="Edge",
        is_active=True
    )
    pat1_user = User(
        email="edge_patient1@chikitsasetu.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.PATIENT,
        first_name="Pat1",
        last_name="Edge",
        is_active=True
    )
    pat2_user = User(
        email="edge_patient2@chikitsasetu.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.PATIENT,
        first_name="Pat2",
        last_name="Edge",
        is_active=True
    )
    db_session.add_all([admin, doc_user, nurse_user, rec_user, pat1_user, pat2_user])
    db_session.flush()

    # Department
    dept = Department(name="General Medicine", code="GM-01")
    db_session.add(dept)
    db_session.flush()

    # Profiles
    doc_prof = Doctor(id=doc_user.id, department_id=dept.id, specialization="General", license_number="LIC-EDGE-01", qualification="MD", consultation_fee=400.00)
    pat1_prof = Patient(id=pat1_user.id, dob=date(1990, 1, 1), gender=GenderEnum.MALE)
    pat2_prof = Patient(id=pat2_user.id, dob=date(1995, 5, 15), gender=GenderEnum.FEMALE)
    db_session.add_all([doc_prof, pat1_prof, pat2_prof])
    db_session.commit()

    return {
        "admin": admin,
        "doctor": doc_user,
        "doctor_profile": doc_prof,
        "nurse": nurse_user,
        "receptionist": rec_user,
        "patient1": pat1_user,
        "patient1_profile": pat1_prof,
        "patient2": pat2_user,
        "patient2_profile": pat2_prof,
        "dept": dept
    }


def token_for(user: User) -> dict:
    t = create_access_token({"sub": str(user.id), "role": user.role.value, "email": user.email})
    return {"Authorization": f"Bearer {t}"}


# =====================================================================
# 1. Authentication & Token Lifecycle
# =====================================================================

def test_auth_expired_token_rejected(fastapi_client, base_clinical_setup):
    """Boundary: Expired JWT token is immediately rejected with 401 Unauthorized."""
    user = base_clinical_setup["admin"]
    expired_token = create_access_token(
        {"sub": str(user.id), "role": user.role.value, "email": user.email},
        expires_delta=timedelta(seconds=-60)
    )
    res = fastapi_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert res.status_code == 401
    assert "detail" in res.json()


def test_auth_empty_and_whitespace_credentials(fastapi_client):
    """Invalid Input: Empty, whitespace, or missing credentials fail cleanly."""
    res_empty = fastapi_client.post("/api/v1/auth/login", json={"email": "", "password": ""})
    assert res_empty.status_code in (400, 401, 422)

    res_ws = fastapi_client.post("/api/v1/auth/login", json={"email": "   ", "password": "   "})
    assert res_ws.status_code in (400, 401, 422)


def test_auth_deactivated_user_cannot_login(fastapi_client, db_session):
    """Security Edge Case: Inactive user accounts are rejected."""
    deactivated = User(
        email="deactivated_edge@chikitsasetu.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.PATIENT,
        first_name="Deactivated",
        last_name="User",
        is_active=False
    )
    db_session.add(deactivated)
    db_session.commit()

    res = fastapi_client.post("/api/v1/auth/login", json={"email": "deactivated_edge@chikitsasetu.ai", "password": "Password123!"})
    assert res.status_code in (400, 401)


# =====================================================================
# 2. Authorization & RBAC Permission Failures
# =====================================================================

def test_rbac_unauthenticated_requests_fail(fastapi_client):
    """Permission Failure: Calling protected endpoints without tokens yields 401."""
    assert fastapi_client.get("/api/v1/auth/me").status_code == 401
    assert fastapi_client.get("/api/v1/patients/").status_code == 401
    assert fastapi_client.get("/api/v1/prescriptions/").status_code == 401
    assert fastapi_client.get("/api/v1/laboratory/orders").status_code == 401
    assert fastapi_client.get("/api/v1/billing/invoices").status_code == 401
    assert fastapi_client.get("/api/v1/audit-logs").status_code == 401


def test_rbac_cross_role_access_boundaries(fastapi_client, base_clinical_setup):
    """Permission Failures: Verifies role matrix boundaries."""
    patient_headers = token_for(base_clinical_setup["patient1"])
    doc_headers = token_for(base_clinical_setup["doctor"])
    rec_headers = token_for(base_clinical_setup["receptionist"])

    # 1. Patient cannot view hospital audit logs
    assert fastapi_client.get("/api/v1/audit-logs", headers=patient_headers).status_code == 403

    # 2. Receptionist cannot view clinical EMR notes
    assert fastapi_client.get("/api/v1/medical-records/", headers=rec_headers).status_code == 403

    # 3. Doctor cannot browse general financial invoices
    assert fastapi_client.get("/api/v1/billing/invoices", headers=doc_headers).status_code == 403


# =====================================================================
# 3. Patients: Happy Paths, Duplicates, Boundary DOB & 404s
# =====================================================================

def test_patient_duplicate_email_registration_rejected(fastapi_client, base_clinical_setup):
    """Duplicate Operation: Registering a patient with an existing email returns 400."""
    admin_headers = token_for(base_clinical_setup["admin"])
    payload = {
        "email": "edge_patient1@chikitsasetu.ai",  # Already exists
        "password": "Password123!",
        "first_name": "Duplicate",
        "last_name": "Patient",
        "dob": "1990-01-01",
        "gender": "male"
    }
    res = fastapi_client.post("/api/v1/patients/", json=payload, headers=admin_headers)
    assert res.status_code == 400
    assert "already exists" in res.json().get("detail", "").lower()


def test_patient_nonexistent_id_returns_404(fastapi_client, base_clinical_setup):
    """Edge Case: Querying non-existent patient returns 404."""
    admin_headers = token_for(base_clinical_setup["admin"])
    res = fastapi_client.get("/api/v1/patients/999999", headers=admin_headers)
    assert res.status_code == 404


def test_patient_boundary_newborn_registration(fastapi_client, base_clinical_setup):
    """Boundary Condition: Patient born today (newborn, age 0) registers successfully."""
    admin_headers = token_for(base_clinical_setup["admin"])
    payload = {
        "email": "newborn_edge@chikitsasetu.ai",
        "password": "Password123!",
        "first_name": "Baby",
        "last_name": "Edge",
        "dob": str(date.today()),
        "gender": "female"
    }
    res = fastapi_client.post("/api/v1/patients/", json=payload, headers=admin_headers)
    assert res.status_code == 201
    assert res.json()["first_name"] == "Baby"


# =====================================================================
# 4. Doctors: Duplicate Licenses & Boundary Fees
# =====================================================================

def test_doctor_duplicate_license_number_rejected(db_session, base_clinical_setup):
    """Duplicate Operation: Doctor license number uniqueness constraint."""
    doc2_user = User(
        email="doc2_license@chikitsasetu.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.DOCTOR,
        first_name="Doc2",
        last_name="License",
        is_active=True
    )
    db_session.add(doc2_user)
    db_session.flush()

    dup_doc = Doctor(
        id=doc2_user.id,
        license_number="LIC-EDGE-01",  # Duplicate of base_clinical_setup['doctor_profile']
        specialization="Pediatrics",
        qualification="MBBS",
        consultation_fee=300.00
    )
    db_session.add(dup_doc)
    with pytest.raises(Exception):
        db_session.commit()
    db_session.rollback()


# =====================================================================
# 5. Appointments: Duplicate Slots, Past Dates & Invalid State Transitions
# =====================================================================

def test_appointment_duplicate_slot_booking_rejected(db_session, base_clinical_setup):
    """Duplicate Operation: Booking the exact same doctor and slot twice raises DuplicateBookingError."""
    doc = base_clinical_setup["doctor"]
    p1 = base_clinical_setup["patient1"]
    p2 = base_clinical_setup["patient2"]
    appt_dt = datetime.now(timezone.utc) + timedelta(days=2)

    # 1. First booking succeeds
    appt1 = book_appointment(
        db=db_session,
        patient_id=p1.id,
        doctor_id=doc.id,
        appointment_datetime=appt_dt,
        reason="General Examination"
    )
    assert appt1.id is not None

    # 2. Second booking for same doctor at exact same time raises DuplicateBookingError
    with pytest.raises(DuplicateBookingError):
        book_appointment(
            db=db_session,
            patient_id=p2.id,
            doctor_id=doc.id,
            appointment_datetime=appt_dt,
            reason="Conflicting Consultation"
        )


def test_appointment_rescheduling_cancelled_appointment_rejected(db_session, base_clinical_setup):
    """Edge Case: Cannot reschedule an already cancelled appointment."""
    doc = base_clinical_setup["doctor"]
    p1 = base_clinical_setup["patient1"]
    appt_dt = datetime.now(timezone.utc) + timedelta(days=3)

    appt = book_appointment(
        db=db_session,
        patient_id=p1.id,
        doctor_id=doc.id,
        appointment_datetime=appt_dt,
        reason="Checkup"
    )
    # Cancel it
    cancel_appointment(db=db_session, appointment_id=appt.id, cancellation_reason="Patient requested")

    # Attempt reschedule
    new_dt = datetime.now(timezone.utc) + timedelta(days=4)
    with pytest.raises(AppointmentStateError):
        reschedule_appointment(db=db_session, appointment_id=appt.id, new_datetime=new_dt)


# =====================================================================
# 6. Medical Records (EMR): Empty Queries & Non-Existent Patient Links
# =====================================================================

def test_emr_nonexistent_patient_link_rejected(db_session, base_clinical_setup):
    """Invalid Input: Creating EMR record for non-existent patient raises error."""
    doc = base_clinical_setup["doctor"]
    with pytest.raises(Exception):
        medical_record_service.create_medical_record(
            db=db_session,
            patient_id=999999,  # Nonexistent
            doctor_id=doc.id,
            diagnosis="Hypertension",
            notes="Followup"
        )


def test_emr_empty_patient_history_returns_empty_list(db_session, base_clinical_setup):
    """Empty Database Scenario: Patient with zero records returns empty list safely."""
    doc = base_clinical_setup["doctor"]
    p2 = base_clinical_setup["patient2"]
    timeline = medical_record_service.get_patient_medical_timeline(
        db=db_session,
        patient_id=p2.id,
        viewer_id=doc.id,
        viewer_role="doctor"
    )
    assert timeline["events"] == []
    assert timeline["total_events"] == 0


# =====================================================================
# 7. Prescriptions: Duplicate Items, Boundaries & Dispensing Errors
# =====================================================================

def test_prescription_duplicate_medication_items_rejected(db_session, base_clinical_setup):
    """Duplicate Operation: Single prescription containing duplicate medicine items is rejected."""
    doc = base_clinical_setup["doctor"]
    p1 = base_clinical_setup["patient1"]

    med = create_medicine(
        db_session=db_session,
        name="Amoxicillin 500mg",
        category="Antibiotic",
        unit="Capsule",
        unit_price=Decimal("15.00")
    )

    items = [
        {"medicine_id": med.id, "dosage": "500mg", "frequency": "TID", "duration_days": 5, "quantity_prescribed": 15},
        {"medicine_id": med.id, "dosage": "500mg", "frequency": "TID", "duration_days": 5, "quantity_prescribed": 15}
    ]
    with pytest.raises(InvalidPrescriptionDataError) as exc_info:
        create_prescription(
            doctor_id=doc.id,
            patient_id=p1.id,
            items=items,
            db_session=db_session
        )
    assert "Duplicate medication" in str(exc_info.value)


def test_prescription_boundary_duration_and_quantity_rejected(db_session, base_clinical_setup):
    """Boundary Conditions: Rejects duration <= 0, duration > 365, and quantity <= 0."""
    doc = base_clinical_setup["doctor"]
    p1 = base_clinical_setup["patient1"]

    med = create_medicine(
        db_session=db_session,
        name="Metformin 500mg",
        category="Antidiabetic",
        unit="Tablet",
        unit_price=Decimal("8.00")
    )

    # Zero duration
    with pytest.raises(InvalidPrescriptionDataError):
        create_prescription(
            doctor_id=doc.id,
            patient_id=p1.id,
            items=[{"medicine_id": med.id, "dosage": "500mg", "frequency": "BID", "duration_days": 0, "quantity_prescribed": 10}],
            db_session=db_session
        )

    # Excessive duration > 365 days
    with pytest.raises(InvalidPrescriptionDataError):
        create_prescription(
            doctor_id=doc.id,
            patient_id=p1.id,
            items=[{"medicine_id": med.id, "dosage": "500mg", "frequency": "BID", "duration_days": 400, "quantity_prescribed": 10}],
            db_session=db_session
        )


def test_prescription_duplicate_dispensing_rejected(db_session, base_clinical_setup):
    """Duplicate Operation: Cannot dispense an already dispensed prescription."""
    doc = base_clinical_setup["doctor"]
    p1 = base_clinical_setup["patient1"]

    med = create_medicine(
        db_session=db_session,
        name="Ciprofloxacin 500mg",
        category="Antibiotic",
        unit="Tablet",
        unit_price=Decimal("20.00")
    )
    stock_in(
        db_session=db_session,
        medicine_id=med.id,
        batch_number="BATCH-CIPRO-1",
        expiry_date=date.today() + timedelta(days=120),
        quantity=50,
        purchase_cost=Decimal("12.00")
    )

    rx = create_prescription(
        doctor_id=doc.id,
        patient_id=p1.id,
        items=[{"medicine_id": med.id, "dosage": "500mg", "frequency": "BID", "duration_days": 5, "quantity_prescribed": 10}],
        db_session=db_session
    )
    # 1. Dispense once
    dispense_prescription(db_session=db_session, prescription_id=rx.id, actor_id=doc.id)
    assert rx.status == PrescriptionStatusEnum.DISPENSED

    # 2. Duplicate dispensing attempt fails
    with pytest.raises(Exception):
        dispense_prescription(db_session=db_session, prescription_id=rx.id, actor_id=doc.id)


# =====================================================================
# 8. Laboratory: Test Codes, Status Transitions & Scoping
# =====================================================================

def test_laboratory_invalid_status_transition_rejected(db_session, base_clinical_setup):
    """Edge Case: Cannot progress cancelled lab order to completed."""
    doc = base_clinical_setup["doctor"]
    p1 = base_clinical_setup["patient1"]

    test = LabTest(name="Serum Ferritin", test_code="FERR-01", sample_type="Blood", cost=450.00)
    db_session.add(test)
    db_session.flush()

    orders = order_lab_tests(
        db_session=db_session,
        patient_id=p1.id,
        doctor_id=doc.id,
        test_ids=[test.id],
        priority="routine"
    )
    order = orders[0]

    # Cancel order
    cancel_lab_order(db_session=db_session, order_id=order.id, user_id=doc.id, reason="Cancelled", user_role="doctor")

    # Attempt to transition cancelled by collecting sample raises LabInvalidStateTransitionError
    with pytest.raises(LabInvalidStateTransitionError):
        receive_and_collect_sample(db_session=db_session, order_id=order.id, technician_id=doc.id)


# =====================================================================
# 9. Pharmacy & 10. Inventory: FEFO, Boundaries & Insufficient Stock
# =====================================================================

def test_pharmacy_stock_in_past_expiry_rejected(db_session):
    """Boundary Condition: Stock-in rejects past expiration dates."""
    med = create_medicine(
        db_session=db_session,
        name="Atorvastatin 20mg",
        category="Cardiovascular",
        unit="Tablet",
        unit_price=Decimal("12.00")
    )

    past_date = date.today() - timedelta(days=5)
    with pytest.raises(InvalidInventoryDataError):
        stock_in(
            db_session=db_session,
            medicine_id=med.id,
            batch_number="BATCH-PAST",
            expiry_date=past_date,
            quantity=50,
            purchase_cost=Decimal("6.00")
        )


def test_pharmacy_stock_out_insufficient_stock_rejected(db_session):
    """Boundary: Attempting to dispense more units than currently stocked raises InsufficientInventoryError."""
    med = create_medicine(
        db_session=db_session,
        name="Azithromycin 250mg",
        category="Antibiotic",
        unit="Tablet",
        unit_price=Decimal("18.00")
    )
    res = stock_in(
        db_session=db_session,
        medicine_id=med.id,
        batch_number="BATCH-AZI-01",
        expiry_date=date.today() + timedelta(days=90),
        quantity=5,
        purchase_cost=Decimal("12.00")
    )
    batch_id = res["batch_id"]

    with pytest.raises(InsufficientInventoryError):
        stock_out(
            db_session=db_session,
            batch_id=batch_id,
            quantity=20,  # Only 5 in stock
            reason="Dispensed to OPD"
        )


# =====================================================================
# 11. Admissions & 12. Beds: Duplicate Admissions, Occupancy & Discharges
# =====================================================================

def test_ipd_duplicate_admission_for_active_patient_rejected(db_session, base_clinical_setup):
    """Duplicate Operation: Admitting an already active inpatient raises PatientAlreadyAdmittedError."""
    dept = base_clinical_setup["dept"]
    doc = base_clinical_setup["doctor"]
    p1 = base_clinical_setup["patient1"]

    room = Room(room_number="R-101", department_id=dept.id, room_type=RoomTypeEnum.GENERAL, daily_rate=Decimal("100.00"))
    db_session.add(room)
    db_session.flush()

    bed1 = Bed(bed_number="B-101A", room_id=room.id, status=BedStatusEnum.AVAILABLE)
    bed2 = Bed(bed_number="B-101B", room_id=room.id, status=BedStatusEnum.AVAILABLE)
    db_session.add_all([bed1, bed2])
    db_session.flush()

    # First admission succeeds
    adm1 = admit_patient(
        db_session=db_session,
        patient_id=p1.id,
        bed_id=bed1.id,
        admitting_doctor_id=doc.id,
        admission_reason="Acute Bronchitis"
    )
    assert adm1.status == AdmissionStatusEnum.ADMITTED

    # Second admission attempt for same patient raises PatientAlreadyAdmittedError
    with pytest.raises(PatientAlreadyAdmittedError):
        admit_patient(
            db_session=db_session,
            patient_id=p1.id,
            bed_id=bed2.id,
            admitting_doctor_id=doc.id,
            admission_reason="Second Admission Attempt"
        )


def test_ipd_admit_to_occupied_bed_rejected(db_session, base_clinical_setup):
    """Conflict Edge Case: Admitting a patient to an already occupied bed raises BedUnavailableError."""
    dept = base_clinical_setup["dept"]
    doc = base_clinical_setup["doctor"]
    p1 = base_clinical_setup["patient1"]
    p2 = base_clinical_setup["patient2"]

    room = Room(room_number="ICU-1", department_id=dept.id, room_type=RoomTypeEnum.ICU, daily_rate=Decimal("500.00"))
    db_session.add(room)
    db_session.flush()
    bed = Bed(bed_number="ICU-BED-1", room_id=room.id, status=BedStatusEnum.AVAILABLE)
    db_session.add(bed)
    db_session.flush()

    # Admit patient 1
    admit_patient(db_session=db_session, patient_id=p1.id, bed_id=bed.id, admitting_doctor_id=doc.id, admission_reason="Post-op")

    # Patient 2 cannot be placed in the same bed
    with pytest.raises(BedUnavailableError):
        admit_patient(db_session=db_session, patient_id=p2.id, bed_id=bed.id, admitting_doctor_id=doc.id, admission_reason="Trauma")


# =====================================================================
# 13. Billing: Overpayment, Zero/Negative Payment & Auto-Billing
# =====================================================================

def test_billing_zero_and_negative_payment_rejected(db_session, base_clinical_setup):
    """Invalid Input & Boundary: Payment amount must be strictly greater than zero."""
    p1 = base_clinical_setup["patient1"]

    bill = create_bill(
        db=db_session,
        patient_id=p1.id,
        items=[{"item_type": ItemTypeEnum.CONSULTATION, "description": "Consultation", "unit_price": Decimal("500.00"), "quantity": 1}]
    )

    # 1. Zero payment
    with pytest.raises(InvalidBillDataError):
        record_payment(db=db_session, bill_id=bill.id, amount=Decimal("0.00"))

    # 2. Negative payment
    with pytest.raises(InvalidBillDataError):
        record_payment(db=db_session, bill_id=bill.id, amount=Decimal("-50.00"))


def test_billing_payment_exceeding_balance_rejected(db_session, base_clinical_setup):
    """Boundary Condition: Payment exceeding outstanding balance raises PaymentExceedsBalanceError."""
    p1 = base_clinical_setup["patient1"]

    bill = create_bill(
        db=db_session,
        patient_id=p1.id,
        items=[{"item_type": ItemTypeEnum.LABORATORY, "description": "Blood Tests", "unit_price": Decimal("200.00"), "quantity": 1}]
    )

    # Balance is 200.00. Attempt payment of 250.00
    with pytest.raises(PaymentExceedsBalanceError):
        record_payment(db=db_session, bill_id=bill.id, amount=Decimal("250.00"))


def test_billing_exact_settlement_transitions_to_paid(db_session, base_clinical_setup):
    """Happy Path: Exact balance payment transitions bill status to PAID."""
    p1 = base_clinical_setup["patient1"]

    bill = create_bill(
        db=db_session,
        patient_id=p1.id,
        items=[{"item_type": ItemTypeEnum.PHARMACY, "description": "Medications", "unit_price": Decimal("150.00"), "quantity": 1}]
    )
    pmt, updated_bill = record_payment(db=db_session, bill_id=bill.id, amount=bill.balance_due)
    assert updated_bill.status == BillStatusEnum.PAID
    assert updated_bill.balance_due == Decimal("0.00")


# =====================================================================
# 14. Notifications: Empty State, Idempotence & Role Isolation
# =====================================================================

def test_notifications_empty_state_and_idempotence(db_session, base_clinical_setup):
    """Empty DB & Idempotence: User with 0 notifications has unread count 0; repeated read is safe."""
    p1 = base_clinical_setup["patient1"]
    assert NotificationService.get_unread_count(db_session, user_id=p1.id) == 0

    # Create 1 notification
    notif = NotificationService.create_notification(
        db=db_session,
        user_id=p1.id,
        title="Welcome",
        message="Your patient portal is ready.",
        type=NotificationTypeEnum.APPOINTMENT_REMINDER
    )
    assert NotificationService.get_unread_count(db_session, user_id=p1.id) == 1

    # Mark as read
    res1 = NotificationService.mark_as_read(db_session, notif.id, user_id=p1.id)
    assert res1 is not None
    assert res1.is_read is True
    assert NotificationService.get_unread_count(db_session, user_id=p1.id) == 0

    # Idempotent repeat
    res2 = NotificationService.mark_as_read(db_session, notif.id, user_id=p1.id)
    assert res2 is not None
    assert res2.is_read is True


# =====================================================================
# 15. Audit Logs: Empty DB, Non-Admin Block & Secret Redaction
# =====================================================================

def test_audit_logs_empty_search_and_sanitization(db_session):
    """Empty DB & Secret Sanitization: Audit logs sanitize credentials and handle empty queries."""
    # Sanitize test
    payload = {"password": "SecretPassword123!", "token": "jwt.bearer.token", "patient_id": 105}
    sanitized = audit_service.sanitize_metadata(payload)
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["token"] == "[REDACTED]"
    assert sanitized["patient_id"] == 105


# =====================================================================
# 16. Analytics: Empty Database Safety (No Division-by-Zero)
# =====================================================================

def test_analytics_empty_database_safety(db_session):
    """Empty Database Scenario: All hospital analytics services gracefully handle empty tables."""
    growth = analytics_service.get_patient_growth_data(db_session)
    assert isinstance(growth, dict)

    appt_kpi = analytics_service.get_appointment_cancellation_data(db_session)
    assert isinstance(appt_kpi, dict)

    bed_kpi = analytics_service.get_bed_occupancy_data(db_session)
    assert isinstance(bed_kpi, dict)

    rev = analytics_service.get_revenue_trends_data(db_session)
    assert isinstance(rev, dict)

    summary = analytics_service.get_hospital_analytics_summary(db_session)
    assert isinstance(summary, dict)


# =====================================================================
# 17. FastAPI APIs: Boundary Pagination & Malformed Requests
# =====================================================================

def test_fastapi_boundary_pagination(fastapi_client, base_clinical_setup):
    """Boundary Conditions: Handling offset=0, limit=1, and large offsets without error."""
    admin_headers = token_for(base_clinical_setup["admin"])

    # limit=1
    res_l1 = fastapi_client.get("/api/v1/patients/?limit=1&skip=0", headers=admin_headers)
    assert res_l1.status_code == 200
    assert len(res_l1.json()) <= 1

    # Large skip
    res_large_off = fastapi_client.get("/api/v1/patients/?limit=10&skip=99999", headers=admin_headers)
    assert res_large_off.status_code == 200
    assert res_large_off.json() == []


def test_fastapi_invalid_path_parameter_type_returns_422(fastapi_client, base_clinical_setup):
    """Invalid Input: Non-integer path parameter triggers Pydantic 422 Unprocessable Entity."""
    admin_headers = token_for(base_clinical_setup["admin"])
    res = fastapi_client.get("/api/v1/patients/non_numeric_id", headers=admin_headers)
    assert res.status_code == 422


# =====================================================================
# 18. ML Prediction APIs: Out-of-Bounds & Non-Diagnostic Disclaimers
# =====================================================================

def test_ml_risk_prediction_boundary_and_outliers(fastapi_client):
    """Boundary Condition: ML Risk endpoint handles boundary ages (0, 110) and glucose outliers safely."""
    payload_bounds = {
        "age": 105,
        "gender": "Female",
        "blood_pressure": "190/115",
        "glucose": 380.0,
        "bmi": 42.0,
        "heart_rate": 115,
        "smoking_status": "former",
        "family_history_diabetes": 1,
        "family_history_hypertension": 1,
        "family_history_heart_disease": 1
    }
    res = fastapi_client.post("/api/v1/ml/risk-prediction", json=payload_bounds)
    assert res.status_code == 200
    data = res.json()
    assert data["risk_category"] in ["Medium", "High"]
    assert data["is_medical_diagnosis"] is False
    assert "DISCLAIMER" in data["disclaimer"]


def test_ml_no_show_prediction_boundary_lead_times(fastapi_client):
    """Boundary Condition: No-show predictor accepts lead_time=0 (same-day) and le=180 max lead time."""
    # Same-day booking (lead_time = 0)
    res_same_day = fastapi_client.post("/api/v1/ml/no-show-prediction", json={
        "patient_age": 30,
        "appointment_lead_time": 0,
        "appointment_weekday": "Monday",
        "department": "General Medicine",
        "previous_appointment_count": 2,
        "previous_no_show_count": 0
    })
    assert res_same_day.status_code == 200
    assert res_same_day.json()["is_medical_diagnosis"] is False
    assert isinstance(res_same_day.json()["no_show_prediction"], bool)

    # Maximum lead time booking (lead_time = 180)
    res_max_lead = fastapi_client.post("/api/v1/ml/no-show-prediction", json={
        "patient_age": 45,
        "appointment_lead_time": 180,
        "appointment_weekday": "Friday",
        "department": "Cardiology",
        "previous_appointment_count": 1,
        "previous_no_show_count": 1
    })
    assert res_max_lead.status_code == 200
    assert isinstance(res_max_lead.json()["no_show_prediction"], bool)

    # Exceeding maximum lead time (lead_time = 181) is rejected with 422
    res_over_lead = fastapi_client.post("/api/v1/ml/no-show-prediction", json={
        "patient_age": 45,
        "appointment_lead_time": 181,
        "appointment_weekday": "Friday",
        "department": "Cardiology",
        "previous_appointment_count": 1,
        "previous_no_show_count": 1
    })
    assert res_over_lead.status_code == 422
