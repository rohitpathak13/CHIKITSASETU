"""
Unit Tests for In-App Notification System and NotificationService.
Validates model definitions, role-based visibility isolation, unread counters,
single & bulk mark-as-read updates, history pagination, and 6 domain-specific generators:
- Appointment Reminders
- Lab Results with Critical Triage
- Low Stock Alerts with Deduplication
- Medicine Expiry Alerts
- Pending Payment Reminders
- Inpatient Admission & Discharge Events
- Automated Operational Event Scanners
"""

import pytest
from datetime import datetime, date, timedelta, timezone

from core.models.user import User, RoleEnum
from core.models.notification import (
    Notification,
    NotificationTypeEnum,
    NotificationPriorityEnum
)
from core.models.pharmacy import Medicine, MedicineInventory
from core.services.notification_service import NotificationService
from core.security import get_password_hash


@pytest.fixture
def test_users(db_session):
    """Creates isolated test users with distinct roles."""
    doc = User(
        email="notif_doc@chikitsasetu.ai",
        password_hash=get_password_hash("DocPass123!"),
        role=RoleEnum.DOCTOR,
        first_name="Priya",
        last_name="Sharma",
        is_active=True
    )
    pat = User(
        email="notif_pat@chikitsasetu.ai",
        password_hash=get_password_hash("PatPass123!"),
        role=RoleEnum.PATIENT,
        first_name="Ramesh",
        last_name="Verma",
        is_active=True
    )
    pharm = User(
        email="notif_pharm@chikitsasetu.ai",
        password_hash=get_password_hash("PharmPass123!"),
        role=RoleEnum.PHARMACIST,
        first_name="Sunil",
        last_name="Gupta",
        is_active=True
    )
    nurse = User(
        email="notif_nurse@chikitsasetu.ai",
        password_hash=get_password_hash("NursePass123!"),
        role=RoleEnum.NURSE,
        first_name="Anjali",
        last_name="Mehta",
        is_active=True
    )
    rec = User(
        email="notif_rec@chikitsasetu.ai",
        password_hash=get_password_hash("RecPass123!"),
        role=RoleEnum.RECEPTIONIST,
        first_name="Deepak",
        last_name="Kumar",
        is_active=True
    )

    db_session.add_all([doc, pat, pharm, nurse, rec])
    db_session.commit()
    for u in [doc, pat, pharm, nurse, rec]:
        db_session.refresh(u)

    return {
        "doctor": doc,
        "patient": pat,
        "pharmacist": pharm,
        "nurse": nurse,
        "receptionist": rec
    }


# ===========================================================================
# 1. Model Creation & Attributes
# ===========================================================================

def test_notification_creation_and_attributes(db_session, test_users):
    """Verifies notification creation with full metadata, priority, and serialization."""
    pat = test_users["patient"]
    notif = NotificationService.create_notification(
        db=db_session,
        user_id=pat.id,
        title="Welcome to CHIKITSASETU",
        message="Your patient portal account has been configured.",
        type=NotificationTypeEnum.SYSTEM,
        priority=NotificationPriorityEnum.NORMAL,
        reference_type="Patient",
        reference_id=pat.id,
        action_url="/patient/dashboard",
        metadata={"onboarding_step": 1}
    )

    assert notif.id is not None
    assert notif.user_id == pat.id
    assert notif.is_read is False
    assert notif.read_at is None
    assert notif.type == NotificationTypeEnum.SYSTEM
    assert notif.priority == NotificationPriorityEnum.NORMAL

    # Test serialization
    data = notif.to_dict()
    assert data["title"] == "Welcome to CHIKITSASETU"
    assert data["metadata"]["onboarding_step"] == 1
    assert data["action_url"] == "/patient/dashboard"


# ===========================================================================
# 2. Role-Based Visibility Isolation
# ===========================================================================

def test_role_based_visibility_isolation(db_session, test_users):
    """Verifies that personal and role-broadcast notifications are strictly isolated."""
    pat = test_users["patient"]
    doc = test_users["doctor"]
    pharm = test_users["pharmacist"]

    # 1. Personal notification for patient
    NotificationService.create_notification(
        db=db_session,
        user_id=pat.id,
        title="Personal Patient Test",
        message="Only visible to patient",
        type=NotificationTypeEnum.APPOINTMENT_REMINDER
    )

    # 2. Role broadcast for pharmacists
    NotificationService.create_notification(
        db=db_session,
        target_role=RoleEnum.PHARMACIST,
        title="Pharmacy Inventory Alert",
        message="Visible to all pharmacists",
        type=NotificationTypeEnum.LOW_STOCK
    )

    # 3. Role broadcast for doctors
    NotificationService.create_notification(
        db=db_session,
        target_role=RoleEnum.DOCTOR,
        title="Clinical Protocol Update",
        message="Visible to doctors",
        type=NotificationTypeEnum.SYSTEM
    )

    # Patient visibility
    pat_items, pat_total = NotificationService.get_notification_history(
        db=db_session, user_id=pat.id, role=RoleEnum.PATIENT
    )
    assert pat_total == 1
    assert pat_items[0].title == "Personal Patient Test"

    # Pharmacist visibility
    pharm_items, pharm_total = NotificationService.get_notification_history(
        db=db_session, user_id=pharm.id, role=RoleEnum.PHARMACIST
    )
    assert pharm_total == 1
    assert pharm_items[0].title == "Pharmacy Inventory Alert"

    # Doctor visibility
    doc_items, doc_total = NotificationService.get_notification_history(
        db=db_session, user_id=doc.id, role=RoleEnum.DOCTOR
    )
    assert doc_total == 1
    assert doc_items[0].title == "Clinical Protocol Update"


# ===========================================================================
# 3. Unread Count Tracking
# ===========================================================================

def test_unread_count_calculation(db_session, test_users):
    """Verifies unread count changes as notifications are created and marked read."""
    pat = test_users["patient"]
    assert NotificationService.get_unread_count(db_session, user_id=pat.id, role=RoleEnum.PATIENT) == 0

    # Add 2 unread notifications
    n1 = NotificationService.create_notification(db=db_session, user_id=pat.id, title="N1", message="M1")
    n2 = NotificationService.create_notification(db=db_session, user_id=pat.id, title="N2", message="M2")
    assert NotificationService.get_unread_count(db_session, user_id=pat.id, role=RoleEnum.PATIENT) == 2

    # Mark one read
    NotificationService.mark_as_read(db_session, notification_id=n1.id, user_id=pat.id, role=RoleEnum.PATIENT)
    assert NotificationService.get_unread_count(db_session, user_id=pat.id, role=RoleEnum.PATIENT) == 1


# ===========================================================================
# 4. Mark As Read & Mark All As Read
# ===========================================================================

def test_mark_as_read_authorization_and_timestamp(db_session, test_users):
    """Verifies that mark_as_read sets read_at timestamp and enforces ownership."""
    pat = test_users["patient"]
    doc = test_users["doctor"]

    notif = NotificationService.create_notification(
        db=db_session,
        user_id=pat.id,
        title="Private Result",
        message="Your checkup report is ready"
    )

    # Unauthorized user (doctor) attempting to mark patient's personal notification
    unauthorized_res = NotificationService.mark_as_read(
        db=db_session,
        notification_id=notif.id,
        user_id=doc.id,
        role=RoleEnum.DOCTOR
    )
    assert unauthorized_res is None
    assert notif.is_read is False

    # Authorized user marks it read
    authorized_res = NotificationService.mark_as_read(
        db=db_session,
        notification_id=notif.id,
        user_id=pat.id,
        role=RoleEnum.PATIENT
    )
    assert authorized_res is not None
    assert authorized_res.is_read is True
    assert authorized_res.read_at is not None


def test_mark_all_as_read_bulk(db_session, test_users):
    """Verifies mark_all_as_read updates all unread visible notifications simultaneously."""
    pharm = test_users["pharmacist"]

    # Create 3 unread notifications for pharmacist
    NotificationService.create_notification(db=db_session, target_role=RoleEnum.PHARMACIST, title="P1", message="M1")
    NotificationService.create_notification(db=db_session, target_role=RoleEnum.PHARMACIST, title="P2", message="M2")
    NotificationService.create_notification(db=db_session, user_id=pharm.id, title="P3", message="M3")

    assert NotificationService.get_unread_count(db_session, user_id=pharm.id, role=RoleEnum.PHARMACIST) == 3

    marked = NotificationService.mark_all_as_read(db_session, user_id=pharm.id, role=RoleEnum.PHARMACIST)
    assert marked == 3
    assert NotificationService.get_unread_count(db_session, user_id=pharm.id, role=RoleEnum.PHARMACIST) == 0


# ===========================================================================
# 5. History Filtering & Pagination
# ===========================================================================

def test_notification_history_filters_and_pagination(db_session, test_users):
    """Verifies filtering by category and pagination limit/offsets."""
    doc = test_users["doctor"]

    NotificationService.create_notification(
        db=db_session, user_id=doc.id, title="Appt 1", message="M",
        type=NotificationTypeEnum.APPOINTMENT_REMINDER
    )
    NotificationService.create_notification(
        db=db_session, user_id=doc.id, title="Lab 1", message="M",
        type=NotificationTypeEnum.LAB_RESULT
    )
    NotificationService.create_notification(
        db=db_session, user_id=doc.id, title="Lab 2", message="M",
        type=NotificationTypeEnum.LAB_RESULT
    )

    # Filter by type LAB_RESULT
    items, total = NotificationService.get_notification_history(
        db=db_session, user_id=doc.id, role=RoleEnum.DOCTOR,
        type=NotificationTypeEnum.LAB_RESULT
    )
    assert total == 2
    for it in items:
        assert it.type == NotificationTypeEnum.LAB_RESULT

    # Pagination test: limit 1, offset 1
    paged, total_all = NotificationService.get_notification_history(
        db=db_session, user_id=doc.id, role=RoleEnum.DOCTOR,
        limit=1, offset=1
    )
    assert total_all == 3
    assert len(paged) == 1


# ===========================================================================
# 6. Specific Domain Generators
# ===========================================================================

def test_notify_appointment_reminder(db_session, test_users):
    """Verifies bidirectional appointment reminders for patient and doctor."""
    pat = test_users["patient"]
    doc = test_users["doctor"]
    appt_time = datetime.now(timezone.utc) + timedelta(days=1)

    notifs = NotificationService.notify_appointment_reminder(
        db=db_session,
        appointment_id=101,
        patient_user_id=pat.id,
        doctor_user_id=doc.id,
        appointment_time=appt_time,
        doctor_name="Priya Sharma",
        patient_name="Ramesh Verma",
        department_name="Cardiology"
    )

    assert len(notifs) == 2
    patient_notif = next(n for n in notifs if n.user_id == pat.id)
    doc_notif = next(n for n in notifs if n.user_id == doc.id)

    assert "Upcoming Appointment Reminder" in patient_notif.title
    assert "Dr. Priya Sharma" in patient_notif.message
    assert patient_notif.type == NotificationTypeEnum.APPOINTMENT_REMINDER
    assert patient_notif.reference_id == 101

    assert "Scheduled Patient Consultation" in doc_notif.title
    assert "Ramesh Verma" in doc_notif.message


def test_notify_lab_result_available_triage(db_session, test_users):
    """Verifies clinical priority escalation for critical and abnormal lab results."""
    pat = test_users["patient"]
    doc = test_users["doctor"]

    # 1. Critical test result
    notifs_crit = NotificationService.notify_lab_result_available(
        db=db_session,
        lab_order_id=201,
        test_name="Cardiac Troponin I",
        patient_user_id=pat.id,
        doctor_user_id=doc.id,
        is_critical=True
    )
    doc_crit = next(n for n in notifs_crit if n.user_id == doc.id)
    assert doc_crit.priority == NotificationPriorityEnum.CRITICAL
    assert "CRITICAL ALERT" in doc_crit.title

    # 2. Abnormal test result
    notifs_abnorm = NotificationService.notify_lab_result_available(
        db=db_session,
        lab_order_id=202,
        test_name="Fasting Lipid Profile",
        patient_user_id=pat.id,
        doctor_user_id=doc.id,
        is_abnormal=True
    )
    doc_abnorm = next(n for n in notifs_abnorm if n.user_id == doc.id)
    assert doc_abnorm.priority == NotificationPriorityEnum.HIGH
    assert "Attention Required" in doc_abnorm.title


def test_notify_low_stock_and_deduplication(db_session):
    """Verifies low stock dispatch to pharmacists and 24h deduplication protection."""
    # First dispatch: successful
    n1 = NotificationService.notify_low_stock(
        db=db_session,
        medicine_id=55,
        medicine_name="Amoxicillin 500mg",
        current_stock=10,
        reorder_level=50
    )
    assert n1 is not None
    assert n1.target_role == RoleEnum.PHARMACIST
    assert n1.type == NotificationTypeEnum.LOW_STOCK
    assert n1.priority == NotificationPriorityEnum.HIGH

    # Second immediate dispatch for same drug: deduplicated
    n2 = NotificationService.notify_low_stock(
        db=db_session,
        medicine_id=55,
        medicine_name="Amoxicillin 500mg",
        current_stock=10,
        reorder_level=50
    )
    assert n2 is None


def test_notify_medicine_expiry(db_session):
    """Verifies medicine batch expiry alerts and critical escalation for near-term dates."""
    n = NotificationService.notify_medicine_expiry(
        db=db_session,
        batch_id=77,
        medicine_name="Ciprofloxacin 250mg",
        batch_number="BATCH-2026-X",
        expiry_date=date.today() + timedelta(days=5),
        days_until_expiry=5
    )
    assert n is not None
    assert n.priority == NotificationPriorityEnum.CRITICAL
    assert n.target_role == RoleEnum.PHARMACIST
    assert "expires in 5 days" in n.message


def test_notify_pending_payment(db_session, test_users):
    """Verifies pending payment reminders for patient and receptionist."""
    pat = test_users["patient"]
    notifs = NotificationService.notify_pending_payment(
        db=db_session,
        bill_id=505,
        invoice_number="INV-2026-999",
        patient_user_id=pat.id,
        outstanding_amount=2450.00,
        due_date=date.today() + timedelta(days=7)
    )

    assert len(notifs) == 2
    pat_n = next(n for n in notifs if n.user_id == pat.id)
    desk_n = next(n for n in notifs if n.target_role == RoleEnum.RECEPTIONIST)

    assert "2,450.00" in pat_n.message
    assert pat_n.type == NotificationTypeEnum.PENDING_PAYMENT
    assert desk_n.target_role == RoleEnum.RECEPTIONIST


def test_notify_admission_and_discharge_events(db_session, test_users):
    """Verifies admission and discharge broadcast events."""
    pat = test_users["patient"]
    doc = test_users["doctor"]

    # 1. Admission Event
    adm_notifs = NotificationService.notify_admission_discharge_event(
        db=db_session,
        admission_id=88,
        event_type="ADMISSION",
        patient_name="Ramesh Verma",
        patient_user_id=pat.id,
        doctor_user_id=doc.id,
        ward_name="ICU Ward",
        bed_number="Bed-101"
    )
    assert len(adm_notifs) == 3
    nurse_adm = next(n for n in adm_notifs if n.target_role == RoleEnum.NURSE)
    assert "New Patient Admission" in nurse_adm.title
    assert "ICU Ward, Bed Bed-101" in nurse_adm.message

    # 2. Discharge Event (also notifies receptionist for billing clearance)
    dis_notifs = NotificationService.notify_admission_discharge_event(
        db=db_session,
        admission_id=88,
        event_type="DISCHARGE",
        patient_name="Ramesh Verma",
        patient_user_id=pat.id,
        doctor_user_id=doc.id,
        ward_name="ICU Ward",
        bed_number="Bed-101"
    )
    assert len(dis_notifs) == 4
    rec_dis = next(n for n in dis_notifs if n.target_role == RoleEnum.RECEPTIONIST)
    assert "Discharge Complete" in rec_dis.title


# ===========================================================================
# 7. Operational Scanner Execution
# ===========================================================================

def test_scan_and_generate_operational_notifications(db_session):
    """Verifies operational scanner triggers on database conditions."""
    # Create low stock inventory record
    med = Medicine(name="Metformin 500mg", generic_name="Metformin", category="Antidiabetic", unit="Tablet", unit_price=5.0, reorder_level=25)
    db_session.add(med)
    db_session.commit()

    inv = MedicineInventory(
        medicine_id=med.id,
        batch_number="MET-2026-01",
        expiry_date=date.today() + timedelta(days=90),
        quantity_in_stock=3,
        purchase_cost=3.50
    )
    db_session.add(inv)
    db_session.commit()

    stats = NotificationService.scan_and_generate_operational_notifications(db_session)
    assert "low_stock_generated" in stats
    assert stats["low_stock_generated"] >= 1
