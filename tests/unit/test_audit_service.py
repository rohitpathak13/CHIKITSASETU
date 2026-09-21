import pytest
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal

from backend.models import User, RoleEnum, Patient, PatientProfile
from backend.models.audit import AuditLog
from backend.security import get_password_hash
from backend.services import audit_service


def test_sanitize_metadata_redacts_sensitive_keys():
    """Verify recursive redaction of sensitive credentials, tokens, and PII."""
    payload = {
        "user_email": "patient@hospital.org",
        "password": "SuperSecretPassword123!",
        "confirm_password": "SuperSecretPassword123!",
        "nested": {
            "token": "bearer-jwt-token-value-xyz",
            "api_key": "sec_9837192837",
            "safe_field": "public notes",
            "card_number": "4111111111111234",
            "cvv": "999",
            "aadhaar_number": "1234-5678-9012"
        },
        "list_items": [
            {"password_hash": "argon2$hashed_val", "item_name": "Paracetamol"},
            {"secret": "hidden_salt", "amount": Decimal("150.75")}
        ],
        "created_date": date(2026, 9, 19),
        "status_enum": RoleEnum.DOCTOR
    }

    sanitized = audit_service.sanitize_metadata(payload)

    # Sensitive keys must be redacted
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["confirm_password"] == "[REDACTED]"
    assert sanitized["nested"]["token"] == "[REDACTED]"
    assert sanitized["nested"]["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["card_number"] == "[REDACTED]"
    assert sanitized["nested"]["cvv"] == "[REDACTED]"
    assert sanitized["nested"]["aadhaar_number"] == "[REDACTED]"
    assert sanitized["list_items"][0]["password_hash"] == "[REDACTED]"
    assert sanitized["list_items"][1]["secret"] == "[REDACTED]"

    # Safe keys must be preserved
    assert sanitized["user_email"] == "patient@hospital.org"
    assert sanitized["nested"]["safe_field"] == "public notes"
    assert sanitized["list_items"][0]["item_name"] == "Paracetamol"
    assert sanitized["list_items"][1]["amount"] == 150.75
    assert sanitized["created_date"] == "2026-09-19"
    assert sanitized["status_enum"] == "doctor"


def test_log_all_10_actions(db_session):
    """
    Validates tracking across all 10 core hospital actions:
    1. login
    2. logout
    3. patient creation
    4. patient update
    5. appointment changes
    6. medical record changes
    7. prescription changes
    8. billing changes
    9. inventory changes
    10. admission/discharge
    """
    user = User(
        email="doctor_audit@chikitsasetu.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.DOCTOR,
        first_name="Audit",
        last_name="Doctor",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()

    # 1. Login (Success & Failure)
    log_login_success = audit_service.log_login(
        db=db_session,
        user_id=user.id,
        ip_address="192.168.1.100",
        success=True,
        metadata={"email": user.email, "role": "doctor"}
    )
    assert log_login_success.action == audit_service.AuditActions.LOGIN
    assert log_login_success.resource_type == "User"
    assert log_login_success.user_id == user.id

    log_login_fail = audit_service.log_login(
        db=db_session,
        user_id=None,
        ip_address="192.168.1.200",
        success=False,
        metadata={"attempted_email": "unknown@hospital.org"}
    )
    assert log_login_fail.action == audit_service.AuditActions.LOGIN_FAILED

    # 2. Logout
    log_out = audit_service.log_logout(
        db=db_session,
        user_id=user.id,
        ip_address="192.168.1.100"
    )
    assert log_out.action == audit_service.AuditActions.LOGOUT
    assert log_out.resource_type == "User"

    # 3. Patient creation
    log_pat_create = audit_service.log_patient_creation(
        db=db_session,
        patient_id=101,
        user_id=user.id,
        actor_id=user.id,
        metadata={"medical_record_number": "MRN-101", "name": "John Doe"}
    )
    assert log_pat_create.action == audit_service.AuditActions.PATIENT_CREATE
    assert log_pat_create.resource_type == "Patient"
    assert log_pat_create.resource_id == 101

    # 4. Patient update
    log_pat_update = audit_service.log_patient_update(
        db=db_session,
        patient_id=101,
        user_id=user.id,
        actor_id=user.id,
        metadata={"updated_fields": ["phone", "address"]}
    )
    assert log_pat_update.action == audit_service.AuditActions.PATIENT_UPDATE
    assert log_pat_update.resource_type == "Patient"

    # 5. Appointment changes
    log_appt_change = audit_service.log_appointment_change(
        db=db_session,
        appointment_id=201,
        action=audit_service.AuditActions.APPOINTMENT_CREATE,
        actor_id=user.id,
        metadata={"doctor_id": user.id, "slot": "10:00 AM"}
    )
    assert log_appt_change.action == audit_service.AuditActions.APPOINTMENT_CREATE
    assert log_appt_change.resource_type == "Appointment"
    assert log_appt_change.resource_id == 201

    # 6. Medical record changes
    log_emr_change = audit_service.log_medical_record_change(
        db=db_session,
        record_id=301,
        action=audit_service.AuditActions.MEDICAL_RECORD_CREATE,
        actor_id=user.id,
        metadata={"diagnosis": "Essential Hypertension", "vitals": {"bp": "130/85"}}
    )
    assert log_emr_change.action == audit_service.AuditActions.MEDICAL_RECORD_CREATE
    assert log_emr_change.resource_type == "MedicalRecord"

    # 7. Prescription changes
    log_rx_change = audit_service.log_prescription_change(
        db=db_session,
        prescription_id=401,
        action=audit_service.AuditActions.PRESCRIPTION_CREATE,
        actor_id=user.id,
        metadata={"items_count": 2, "instructions": "After meals"}
    )
    assert log_rx_change.action == audit_service.AuditActions.PRESCRIPTION_CREATE
    assert log_rx_change.resource_type == "Prescription"

    # 8. Billing changes
    log_bill_change = audit_service.log_billing_change(
        db=db_session,
        bill_id=501,
        action=audit_service.AuditActions.BILLING_CREATE,
        actor_id=user.id,
        metadata={"invoice_number": "INV-501", "total_amount": 250.0}
    )
    assert log_bill_change.action == audit_service.AuditActions.BILLING_CREATE
    assert log_bill_change.resource_type == "Bill"

    # 9. Inventory changes
    log_inv_change = audit_service.log_inventory_change(
        db=db_session,
        resource_id=601,
        action=audit_service.AuditActions.STOCK_IN,
        resource_type="MedicineInventory",
        actor_id=user.id,
        metadata={"batch": "BATCH-001", "quantity": 100}
    )
    assert log_inv_change.action == audit_service.AuditActions.STOCK_IN
    assert log_inv_change.resource_type == "MedicineInventory"

    # 10. Admission / Discharge
    log_adm_change = audit_service.log_admission_discharge(
        db=db_session,
        admission_id=701,
        action=audit_service.AuditActions.ADMISSION_CREATE,
        actor_id=user.id,
        metadata={"bed_number": "BED-101", "ward": "General"}
    )
    assert log_adm_change.action == audit_service.AuditActions.ADMISSION_CREATE
    assert log_adm_change.resource_type == "Admission"

    log_dis_change = audit_service.log_admission_discharge(
        db=db_session,
        admission_id=701,
        action=audit_service.AuditActions.ADMISSION_DISCHARGE,
        actor_id=user.id,
        metadata={"discharge_summary": "Recovered in stable condition"}
    )
    assert log_dis_change.action == audit_service.AuditActions.ADMISSION_DISCHARGE
    assert log_dis_change.resource_type == "Admission"


def test_search_and_filter_audit_logs(db_session):
    """Verifies searching and filtering by action, resource, date, user, and text."""
    admin = User(
        email="admin_auditor@chikitsasetu.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.ADMIN,
        first_name="Chief",
        last_name="Auditor",
        is_active=True
    )
    nurse = User(
        email="nurse_auditor@chikitsasetu.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.NURSE,
        first_name="Nurse",
        last_name="Joy",
        is_active=True
    )
    db_session.add_all([admin, nurse])
    db_session.commit()

    # Seed diverse audit logs
    audit_service.log_login(db_session, user_id=admin.id, ip_address="10.0.0.1")
    audit_service.log_patient_creation(db_session, patient_id=1, user_id=admin.id, actor_id=admin.id, metadata={"name": "Alice"})
    audit_service.log_appointment_change(db_session, appointment_id=10, action=audit_service.AuditActions.APPOINTMENT_CREATE, actor_id=nurse.id)
    audit_service.log_billing_change(db_session, bill_id=99, action=audit_service.AuditActions.BILLING_CREATE, actor_id=admin.id, metadata={"invoice": "INV-099"})
    audit_service.log_admission_discharge(db_session, admission_id=5, action=audit_service.AuditActions.ADMISSION_DISCHARGE, actor_id=nurse.id)

    # 1. Filter by user_id
    nurse_logs, count_nurse = audit_service.search_audit_logs(db=db_session, user_id=nurse.id)
    assert count_nurse == 2
    assert all(log.user_id == nurse.id for log in nurse_logs)

    # 2. Filter by action
    login_logs, count_login = audit_service.search_audit_logs(db=db_session, action=audit_service.AuditActions.LOGIN)
    assert count_login == 1
    assert login_logs[0].action == audit_service.AuditActions.LOGIN

    # 3. Filter by resource_type
    bill_logs, count_bill = audit_service.search_audit_logs(db=db_session, resource_type="Bill")
    assert count_bill == 1
    assert bill_logs[0].resource_type == "Bill"

    # 4. Filter by resource_id
    res_logs, count_res = audit_service.search_audit_logs(db=db_session, resource_id=99)
    assert count_res == 1
    assert res_logs[0].resource_id == 99

    # 5. Free-text search across details and user name
    search_alice, count_alice = audit_service.search_audit_logs(db=db_session, search_query="Alice")
    assert count_alice == 1
    assert "Alice" in search_alice[0].details_json

    search_nurse, count_search_nurse = audit_service.search_audit_logs(db=db_session, search_query="Joy")
    assert count_search_nurse == 2

    # 6. Pagination
    page_1, total = audit_service.search_audit_logs(db=db_session, limit=2, offset=0)
    assert total == 5
    assert len(page_1) == 2

    page_2, _ = audit_service.search_audit_logs(db=db_session, limit=2, offset=2)
    assert len(page_2) == 2
    assert page_1[0].id != page_2[0].id


def test_distinct_helpers_and_stats(db_session):
    """Verifies listing distinct actions, resource types, and computing stats."""
    audit_service.log_action(db_session, action="TEST_ACT_1", resource_type="TestResourceA")
    audit_service.log_action(db_session, action="TEST_ACT_2", resource_type="TestResourceB")
    audit_service.log_action(db_session, action="TEST_ACT_1", resource_type="TestResourceA")

    actions = audit_service.get_distinct_actions(db_session)
    assert "TEST_ACT_1" in actions
    assert "TEST_ACT_2" in actions

    resources = audit_service.get_distinct_resource_types(db_session)
    assert "TestResourceA" in resources
    assert "TestResourceB" in resources

    stats = audit_service.get_audit_stats(db_session)
    assert stats["total_logs"] >= 3
    assert any(a["action"] == "TEST_ACT_1" and a["count"] == 2 for a in stats["top_actions"])
