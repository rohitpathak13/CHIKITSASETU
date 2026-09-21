import pytest
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal

from backend.models import (
    User, DoctorProfile, PatientProfile, Department,
    LabTest, LabTestType, LabOrder, LabResult,
    Notification, NotificationTypeEnum,
    RoleEnum, GenderEnum, LabOrderStatusEnum
)
from backend.services.laboratory_service import (
    order_lab_tests, receive_and_collect_sample, start_processing_order,
    enter_lab_result, doctor_review_lab_result, cancel_lab_order,
    get_lab_order_detail, list_lab_orders, get_patient_lab_history,
    create_or_update_lab_test,
    LaboratoryServiceError, InvalidLabDataError, LabOrderNotFoundError,
    LabPermissionError, LabInvalidStateTransitionError
)


@pytest.fixture
def lab_setup(db_session):
    """Sets up doctor, patient, lab technician, and department for laboratory tests."""
    dept = Department(name="Pathology & Laboratory", code="PATH-01")
    db_session.add(dept)
    db_session.flush()

    # 1. Doctor
    doc_user = User(
        email="doctor.pathology@chikitsasetu.ai",
        role=RoleEnum.DOCTOR,
        first_name="Gregory",
        last_name="House"
    )
    doc_user.set_password("DocPass123!")
    db_session.add(doc_user)
    db_session.flush()

    doc_profile = DoctorProfile(
        user_id=doc_user.id,
        department_id=dept.id,
        specialization="Diagnostic Medicine",
        license_number="LIC-LAB-001",
        consultation_fee=Decimal("600.00"),
        qualification="MD Internal Medicine"
    )
    db_session.add(doc_profile)

    # 2. Patient 1 (Alice)
    pat_user_1 = User(
        email="alice.smith@example.com",
        role=RoleEnum.PATIENT,
        first_name="Alice",
        last_name="Smith"
    )
    pat_user_1.set_password("Patient123!")
    db_session.add(pat_user_1)
    db_session.flush()

    pat_profile_1 = PatientProfile(
        user_id=pat_user_1.id,
        dob=date(1990, 5, 20),
        gender=GenderEnum.FEMALE,
        blood_group="A+"
    )
    db_session.add(pat_profile_1)

    # 3. Patient 2 (Bob)
    pat_user_2 = User(
        email="bob.jones@example.com",
        role=RoleEnum.PATIENT,
        first_name="Bob",
        last_name="Jones"
    )
    pat_user_2.set_password("Patient123!")
    db_session.add(pat_user_2)
    db_session.flush()

    pat_profile_2 = PatientProfile(
        user_id=pat_user_2.id,
        dob=date(1985, 11, 10),
        gender=GenderEnum.MALE,
        blood_group="O-"
    )
    db_session.add(pat_profile_2)

    # 4. Lab Technician
    tech_user = User(
        email="tech.lab@chikitsasetu.ai",
        role=RoleEnum.LAB_TECH,
        first_name="Dexter",
        last_name="Morgan"
    )
    tech_user.set_password("TechPass123!")
    db_session.add(tech_user)
    db_session.flush()

    # 5. Diagnostic Tests
    test_cbc = LabTest(
        name="Complete Blood Count",
        test_code="CBC",
        department_id=dept.id,
        sample_type="Whole Blood EDTA",
        unit="g/dL",
        reference_range_min=12.0,
        reference_range_max=16.0,
        cost=Decimal("150.00"),
        description="Comprehensive hematology panel"
    )
    test_glucose = LabTest(
        name="Fasting Blood Glucose",
        test_code="FBG",
        department_id=dept.id,
        sample_type="Fluoride Plasma",
        unit="mg/dL",
        reference_range_min=70.0,
        reference_range_max=100.0,
        cost=Decimal("120.00"),
        description="Fasting glycemic evaluation"
    )
    db_session.add_all([test_cbc, test_glucose])
    db_session.commit()

    return {
        "dept": dept,
        "doctor": doc_profile,
        "doctor_user": doc_user,
        "patient1": pat_profile_1,
        "patient1_user": pat_user_1,
        "patient2": pat_profile_2,
        "patient2_user": pat_user_2,
        "tech": tech_user,
        "cbc": test_cbc,
        "glucose": test_glucose
    }



# =====================================================================
# 1. Test Catalog Formulary Tests
# =====================================================================

def test_catalog_create_and_validation(db_session, lab_setup):
    """Verifies catalog additions, edits, and validation constraints."""
    tech = lab_setup["tech"]
    dept = lab_setup["dept"]

    # 1. Successful creation
    test = create_or_update_lab_test(
        db_session=db_session,
        name="Serum Creatinine",
        test_code="CREAT",
        sample_type="Serum",
        cost=180.00,
        unit="mg/dL",
        reference_range_min=0.6,
        reference_range_max=1.2,
        description="Renal function marker",
        department_id=dept.id,
        user_role="lab_tech"
    )
    assert test.id is not None
    assert test.test_code == "CREAT"
    assert test.cost == Decimal("180.00")

    # 2. Validation: Min > Max raises InvalidLabDataError
    with pytest.raises(InvalidLabDataError, match="Reference range minimum cannot exceed"):
        create_or_update_lab_test(
            db_session=db_session,
            name="Invalid Range Test",
            test_code="INV",
            sample_type="Serum",
            cost=100.00,
            reference_range_min=150.0,
            reference_range_max=50.0,
            user_role="lab_tech"
        )

    # 3. Validation: Duplicate test code raises InvalidLabDataError
    with pytest.raises(InvalidLabDataError, match="already exists"):
        create_or_update_lab_test(
            db_session=db_session,
            name="Another CBC Test",
            test_code="CBC",
            sample_type="Blood",
            cost=200.00,
            user_role="lab_tech"
        )

    # 4. RBAC: Unauthorized role (Patient) cannot add catalog formulary test
    with pytest.raises(LabPermissionError):
        create_or_update_lab_test(
            db_session=db_session,
            name="Unauthorized Test",
            test_code="UNAUTH",
            sample_type="Blood",
            cost=100.00,
            user_role="patient"
        )


# =====================================================================
# 2. Complete 7-Step Workflow Lifecycle
# =====================================================================

def test_complete_laboratory_workflow_normal(db_session, lab_setup):
    """
    Validates complete clinical lifecycle with normal result:
    Doctor orders → Tech receives & collects sample → Processing → Result entered → Doctor reviews → Patient views.
    """
    doc = lab_setup["doctor"]
    pat = lab_setup["patient1"]
    tech = lab_setup["tech"]
    cbc = lab_setup["cbc"]

    # Step 1: Doctor orders test
    orders = order_lab_tests(
        db_session=db_session,
        patient_id=pat.id,
        doctor_id=doc.id,
        test_ids=[cbc.id],
        priority="routine",
        clinical_notes="Routine checkup panel",
        ordering_user_id=doc.id,
        user_role="doctor"
    )
    assert len(orders) == 1
    order = orders[0]
    assert order.status == LabOrderStatusEnum.ORDERED
    assert order.priority == "routine"
    assert order.doctor_reviewed is False
    assert order.sample_collected_at is None

    # Step 2: Lab technician collects sample
    order = receive_and_collect_sample(
        db_session=db_session,
        order_id=order.id,
        technician_id=tech.id,
        notes="Venipuncture left antecubital fossa",
        user_role="lab_tech"
    )
    assert order.status == LabOrderStatusEnum.SAMPLE_COLLECTED
    assert order.sample_collected_at is not None
    assert order.sample_collected_by_id == tech.id

    # Step 3: Processing started
    order = start_processing_order(
        db_session=db_session,
        order_id=order.id,
        technician_id=tech.id,
        user_role="lab_tech"
    )
    assert order.status == LabOrderStatusEnum.PROCESSING
    assert order.processing_started_at is not None

    # Step 4: Result entered (Normal: 14.2 g/dL, within 12.0 - 16.0)
    order = enter_lab_result(
        db_session=db_session,
        order_id=order.id,
        measured_value=14.2,
        technician_id=tech.id,
        technician_notes="Hemolysis index normal",
        result_text="Normal hematocrit and hemoglobin count",
        user_role="lab_tech"
    )
    assert order.status == LabOrderStatusEnum.COMPLETED
    assert order.completed_at is not None
    assert order.result is not None
    assert order.result.measured_value == 14.2
    assert order.result.is_abnormal is False
    assert order.result.critical_alert is False

    # Check notification to doctor
    notif = db_session.query(Notification).filter(
        Notification.user_id == doc.id,
        Notification.title.contains("Normal Result")
    ).first()
    assert notif is not None

    # Step 5: Doctor reviews result
    order = doctor_review_lab_result(
        db_session=db_session,
        order_id=order.id,
        doctor_id=doc.id,
        review_notes="Hemoglobin healthy. No intervention required.",
        user_role="doctor"
    )
    assert order.doctor_reviewed is True
    assert order.doctor_reviewed_at is not None
    assert "No intervention required" in order.doctor_review_notes

    # Check notification to patient
    pat_notif = db_session.query(Notification).filter(
        Notification.user_id == pat.id,
        Notification.title.contains("Lab Results Reviewed")
    ).first()
    assert pat_notif is not None

    # Step 6: Patient can view result
    viewed = get_lab_order_detail(
        db_session=db_session,
        order_id=order.id,
        requester_user_id=pat.id,
        requester_role="patient"
    )
    assert viewed.id == order.id
    assert viewed.result.measured_value == 14.2


def test_abnormal_and_critical_result_evaluations(db_session, lab_setup):
    """Verifies reference range threshold evaluations for abnormal and critical findings."""
    doc = lab_setup["doctor"]
    pat = lab_setup["patient1"]
    tech = lab_setup["tech"]
    glucose = lab_setup["glucose"]  # Ref: 70 - 100 mg/dL

    # --- Test Case A: Mildly Abnormal (115 mg/dL: > 100, but < 100 * 1.4 = 140) ---
    orders_a = order_lab_tests(
        db_session=db_session,
        patient_id=pat.id,
        doctor_id=doc.id,
        test_ids=[glucose.id],
        user_role="doctor"
    )
    order_a = orders_a[0]
    receive_and_collect_sample(db_session, order_a.id, tech.id, user_role="lab_tech")
    start_processing_order(db_session, order_a.id, tech.id, user_role="lab_tech")

    order_a = enter_lab_result(
        db_session=db_session,
        order_id=order_a.id,
        measured_value=115.0,
        technician_id=tech.id,
        user_role="lab_tech"
    )
    assert order_a.result.is_abnormal is True
    assert order_a.result.critical_alert is False

    # --- Test Case B: Critically High Glucose (250 mg/dL: > 100 * 1.4 = 140) ---
    orders_b = order_lab_tests(
        db_session=db_session,
        patient_id=pat.id,
        doctor_id=doc.id,
        test_ids=[glucose.id],
        priority="stat",
        user_role="doctor"
    )
    order_b = orders_b[0]
    receive_and_collect_sample(db_session, order_b.id, tech.id, user_role="lab_tech")
    start_processing_order(db_session, order_b.id, tech.id, user_role="lab_tech")

    order_b = enter_lab_result(
        db_session=db_session,
        order_id=order_b.id,
        measured_value=250.0,
        technician_id=tech.id,
        user_role="lab_tech"
    )
    assert order_b.result.is_abnormal is True
    assert order_b.result.critical_alert is True

    # Critical alert notification
    crit_notif = db_session.query(Notification).filter(
        Notification.user_id == doc.id,
        Notification.type == NotificationTypeEnum.CRITICAL
    ).first()
    assert crit_notif is not None


# =====================================================================
# 3. Cancellation Workflow Tests
# =====================================================================

def test_order_cancellation(db_session, lab_setup):
    """Tests cancellation of pending lab orders and restriction on completed orders."""
    doc = lab_setup["doctor"]
    pat = lab_setup["patient1"]
    tech = lab_setup["tech"]
    cbc = lab_setup["cbc"]

    orders = order_lab_tests(
        db_session=db_session,
        patient_id=pat.id,
        doctor_id=doc.id,
        test_ids=[cbc.id],
        user_role="doctor"
    )
    order = orders[0]

    # 1. Cancel without reason raises InvalidLabDataError
    with pytest.raises(InvalidLabDataError, match="reason is mandatory"):
        cancel_lab_order(db_session, order.id, doc.id, reason="", user_role="doctor")

    # 2. Successful cancellation
    order = cancel_lab_order(
        db_session=db_session,
        order_id=order.id,
        user_id=doc.id,
        reason="Patient duplicate requisition",
        user_role="doctor"
    )
    assert order.status == LabOrderStatusEnum.CANCELLED
    assert order.cancellation_reason == "Patient duplicate requisition"
    assert order.cancelled_at is not None

    # 3. Attempting to collect sample on cancelled order fails
    with pytest.raises(LabInvalidStateTransitionError, match="cancelled"):
        receive_and_collect_sample(db_session, order.id, tech.id, user_role="lab_tech")

    # 4. Attempting to cancel a completed order fails
    order2 = order_lab_tests(db_session, pat.id, doc.id, [cbc.id], user_role="doctor")[0]
    receive_and_collect_sample(db_session, order2.id, tech.id, user_role="lab_tech")
    start_processing_order(db_session, order2.id, tech.id, user_role="lab_tech")
    enter_lab_result(db_session, order2.id, 13.5, tech.id, user_role="lab_tech")

    with pytest.raises(LabInvalidStateTransitionError, match="cannot be cancelled"):
        cancel_lab_order(db_session, order2.id, doc.id, "Attempted cancel", user_role="doctor")


# =====================================================================
# 4. Role Permissions & Privacy Constraints
# =====================================================================

def test_patient_cross_access_forbidden(db_session, lab_setup):
    """Ensures Patient A cannot view Patient B's laboratory results."""
    doc = lab_setup["doctor"]
    pat1 = lab_setup["patient1"]
    pat2 = lab_setup["patient2"]
    cbc = lab_setup["cbc"]

    order = order_lab_tests(db_session, pat1.id, doc.id, [cbc.id], user_role="doctor")[0]

    # Patient 1 views own order -> OK
    res = get_lab_order_detail(db_session, order.id, requester_user_id=pat1.id, requester_role="patient")
    assert res.id == order.id

    # Patient 2 attempts to view Patient 1's order -> LabPermissionError
    with pytest.raises(LabPermissionError, match="Access denied"):
        get_lab_order_detail(db_session, order.id, requester_user_id=pat2.id, requester_role="patient")


def test_invalid_state_transitions(db_session, lab_setup):
    """Tests guard conditions for invalid workflow transitions."""
    doc = lab_setup["doctor"]
    pat = lab_setup["patient1"]
    tech = lab_setup["tech"]
    cbc = lab_setup["cbc"]

    order = order_lab_tests(db_session, pat.id, doc.id, [cbc.id], user_role="doctor")[0]

    # Cannot jump to processing directly from ORDERED (must collect sample first)
    with pytest.raises(LabInvalidStateTransitionError, match="Specimen must be collected"):
        start_processing_order(db_session, order.id, tech.id, user_role="lab_tech")

    # Cannot enter result directly from ORDERED
    with pytest.raises(LabInvalidStateTransitionError, match="Specimen must be collected"):
        enter_lab_result(db_session, order.id, 14.0, tech.id, user_role="lab_tech")

    # Cannot doctor review an uncompleted order
    with pytest.raises(LabInvalidStateTransitionError, match="not COMPLETED"):
        doctor_review_lab_result(db_session, order.id, doc.id, user_role="doctor")


# =====================================================================
# 5. Search and Multi-Criteria Filtering
# =====================================================================

def test_search_and_filters(db_session, lab_setup):
    """Tests status filtering, text search across patient name and test code, and priority."""
    doc = lab_setup["doctor"]
    pat1 = lab_setup["patient1"]
    pat2 = lab_setup["patient2"]
    tech = lab_setup["tech"]
    cbc = lab_setup["cbc"]
    glucose = lab_setup["glucose"]

    # Order 1: Alice - CBC - STAT
    order1 = order_lab_tests(db_session, pat1.id, doc.id, [cbc.id], priority="stat", user_role="doctor")[0]

    # Order 2: Bob - Glucose - Routine
    order2 = order_lab_tests(db_session, pat2.id, doc.id, [glucose.id], priority="routine", user_role="doctor")[0]
    receive_and_collect_sample(db_session, order2.id, tech.id, user_role="lab_tech")

    # Filter by status: ORDERED -> only order1
    ordered_list = list_lab_orders(db_session, status_filter="ordered")
    assert any(o.id == order1.id for o in ordered_list)
    assert not any(o.id == order2.id for o in ordered_list)

    # Filter by priority: STAT -> order1
    stat_list = list_lab_orders(db_session, priority="stat")
    assert any(o.id == order1.id for o in stat_list)
    assert not any(o.id == order2.id for o in stat_list)

    # Search by Patient Name: "Bob" -> order2
    bob_list = list_lab_orders(db_session, search_query="Bob")
    assert any(o.id == order2.id for o in bob_list)
    assert not any(o.id == order1.id for o in bob_list)

    # Search by Test Code: "CBC" -> order1
    cbc_list = list_lab_orders(db_session, search_query="CBC")
    assert any(o.id == order1.id for o in cbc_list)


# =====================================================================
# 6. Web Flask Client Integration & HTTP Endpoints
# =====================================================================

def test_web_laboratory_flask_flow(flask_client, db_session, lab_setup):
    """Tests the full Flask web user journey across Lab Tech, Doctor, and Patient."""
    doc = lab_setup["doctor"]
    doc_user = lab_setup["doctor_user"]
    pat = lab_setup["patient1"]
    pat_user = lab_setup["patient1_user"]
    pat2_user = lab_setup["patient2_user"]
    tech = lab_setup["tech"]
    cbc = lab_setup["cbc"]

    # 1. Doctor logs in and orders a test via Web Form
    with flask_client.session_transaction() as sess:
        sess["user_id"] = doc.id
        sess["user_role"] = "doctor"
        sess["user_email"] = doc_user.email

    order_resp = flask_client.post(f"/doctor/patient/{pat.id}/lab-order", data={
        "test_ids": [str(cbc.id)],
        "priority": "urgent",
        "clinical_notes": "Post-admission CBC check"
    }, follow_redirects=True)
    assert order_resp.status_code == 200

    order = db_session.query(LabOrder).filter(
        LabOrder.patient_id == pat.id,
        LabOrder.test_id == cbc.id
    ).first()
    assert order is not None
    assert order.status == LabOrderStatusEnum.ORDERED

    # 2. Lab Technician logs in and views dashboard
    with flask_client.session_transaction() as sess:
        sess["user_id"] = tech.id
        sess["user_role"] = "lab_tech"
        sess["user_email"] = tech.email

    dash_resp = flask_client.get("/laboratory/")
    assert dash_resp.status_code == 200
    assert bytes(order.test.name, "utf-8") in dash_resp.data

    # Technician logs sample collection
    collect_resp = flask_client.post(f"/laboratory/collect/{order.id}", data={"notes": "Adequate sample volume"}, follow_redirects=True)
    assert collect_resp.status_code == 200
    db_session.refresh(order)
    assert order.status == LabOrderStatusEnum.SAMPLE_COLLECTED

    # Technician starts processing
    proc_resp = flask_client.post(f"/laboratory/process/{order.id}", follow_redirects=True)
    assert proc_resp.status_code == 200
    db_session.refresh(order)
    assert order.status == LabOrderStatusEnum.PROCESSING

    # Technician enters result
    res_resp = flask_client.post(f"/laboratory/result/{order.id}", data={
        "measured_value": "13.8",
        "result_text": "Normal RBC morphology",
        "notes": "Automated counter verified"
    }, follow_redirects=True)
    assert res_resp.status_code == 200
    db_session.refresh(order)
    assert order.status == LabOrderStatusEnum.COMPLETED

    # 3. Doctor reviews result
    with flask_client.session_transaction() as sess:
        sess["user_id"] = doc.id
        sess["user_role"] = "doctor"
        sess["user_email"] = doc_user.email

    review_resp = flask_client.post(f"/doctor/lab-orders/{order.id}/review", data={
        "review_notes": "Hematocrit and hemoglobin are within normal limits."
    }, follow_redirects=True)
    assert review_resp.status_code == 200
    db_session.refresh(order)
    assert order.doctor_reviewed is True

    # 4. Patient logs in and views reports
    with flask_client.session_transaction() as sess:
        sess["user_id"] = pat.id
        sess["user_role"] = "patient"
        sess["user_email"] = pat_user.email

    pat_resp = flask_client.get("/patient/labs")
    assert pat_resp.status_code == 200
    assert bytes(order.test.name, "utf-8") in pat_resp.data

    # Patient views printable pathology report
    detail_resp = flask_client.get(f"/patient/labs/{order.id}")
    assert detail_resp.status_code == 200
    assert b"13.8" in detail_resp.data
    assert b"Normal RBC morphology" in detail_resp.data
    assert b"Hematocrit and hemoglobin are within normal limits." in detail_resp.data

    # 5. Patient 2 attempts to view Patient 1's report -> 403 Forbidden
    with flask_client.session_transaction() as sess:
        sess["user_id"] = pat2_user.id
        sess["user_role"] = "patient"
        sess["user_email"] = pat2_user.email

    forbidden_resp = flask_client.get(f"/patient/labs/{order.id}")
    assert forbidden_resp.status_code == 403


