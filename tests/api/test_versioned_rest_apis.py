"""
Comprehensive integration tests for all 11 versioned REST APIs under /api/v1/.
Verifies endpoints, OpenAPI documentation, validation, status codes, and service-layer reuse.
"""

import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from core.models import (
    User, Patient, Doctor, Department, Room, Bed, Medicine, LabTest,
    RoleEnum, GenderEnum, RoomTypeEnum, BedStatusEnum
)


# ===========================================================================
# 0. OpenAPI Documentation & Health
# ===========================================================================

def test_openapi_documentation_generation(fastapi_client):
    """Verifies that OpenAPI documentation and schema are dynamically generated with all 11 tags."""
    # 1. OpenAPI JSON specification
    res_schema = fastapi_client.get("/openapi.json")
    assert res_schema.status_code == 200
    schema = res_schema.json()
    assert "openapi" in schema
    assert "paths" in schema

    # Verify all 11 API domain prefixes are documented in OpenAPI schema
    expected_paths = [
        "/api/v1/auth",
        "/api/v1/patients",
        "/api/v1/doctors",
        "/api/v1/appointments",
        "/api/v1/medical-records",
        "/api/v1/prescriptions",
        "/api/v1/laboratory",
        "/api/v1/pharmacy",
        "/api/v1/admissions",
        "/api/v1/billing",
        "/api/v1/analytics"
    ]
    paths_str = " ".join(schema["paths"].keys())
    for p in expected_paths:
        assert p in paths_str, f"Missing OpenAPI endpoint path for: {p}"

    # 2. Swagger UI /docs
    res_docs = fastapi_client.get("/docs")
    assert res_docs.status_code == 200

    # 3. Root health
    res_root = fastapi_client.get("/")
    assert res_root.status_code == 200
    assert res_root.json()["status"] == "operational"


# ===========================================================================
# 1. /api/v1/auth
# ===========================================================================

def test_api_v1_auth(fastapi_client, admin_user):
    # JSON Login
    res_json = fastapi_client.post("/api/v1/auth/login", json={
        "email": admin_user.email,
        "password": "Password123!"
    })
    assert res_json.status_code == 200
    token = res_json.json()["access_token"]

    # Form Login
    res_form = fastapi_client.post("/api/v1/auth/token", data={
        "username": admin_user.email,
        "password": "Password123!"
    })
    assert res_form.status_code == 200

    # Read Current Profile
    res_me = fastapi_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res_me.status_code == 200
    assert res_me.json()["email"] == admin_user.email


# ===========================================================================
# 2. /api/v1/patients
# ===========================================================================

def test_api_v1_patients(fastapi_client, admin_auth_headers):
    # Create Patient
    create_payload = {
        "email": "rest_pat_01@medicare.ai",
        "first_name": "Rest",
        "last_name": "Patient",
        "dob": "1994-06-15",
        "gender": "female",
        "blood_group": "A+",
        "phone": "+1987654321",
        "allergies": "Penicillin"
    }
    res_create = fastapi_client.post("/api/v1/patients/", json=create_payload, headers=admin_auth_headers)
    assert res_create.status_code == 201
    pat_data = res_create.json()
    pat_id = pat_data["user_id"]
    assert pat_data["email"] == "rest_pat_01@medicare.ai"

    # List Patients
    res_list = fastapi_client.get("/api/v1/patients/", headers=admin_auth_headers)
    assert res_list.status_code == 200
    assert any(p["user_id"] == pat_id for p in res_list.json())

    # Get Patient Detail
    res_get = fastapi_client.get(f"/api/v1/patients/{pat_id}", headers=admin_auth_headers)
    assert res_get.status_code == 200
    assert res_get.json()["first_name"] == "Rest"

    # Update Patient
    res_put = fastapi_client.put(f"/api/v1/patients/{pat_id}", json={"allergies": "Penicillin, NSAIDs"}, headers=admin_auth_headers)
    assert res_put.status_code == 200
    assert "NSAIDs" in res_put.json()["allergies"]

    # Sub-resources
    assert fastapi_client.get(f"/api/v1/patients/{pat_id}/medical-records", headers=admin_auth_headers).status_code == 200
    assert fastapi_client.get(f"/api/v1/patients/{pat_id}/prescriptions", headers=admin_auth_headers).status_code == 200
    assert fastapi_client.get(f"/api/v1/patients/{pat_id}/appointments", headers=admin_auth_headers).status_code == 200
    assert fastapi_client.get(f"/api/v1/patients/{pat_id}/admissions", headers=admin_auth_headers).status_code == 200
    assert fastapi_client.get(f"/api/v1/patients/{pat_id}/invoices", headers=admin_auth_headers).status_code == 200


# ===========================================================================
# 3. /api/v1/doctors
# ===========================================================================

def test_api_v1_doctors(fastapi_client, admin_auth_headers, db_session):
    # Setup department
    dept = Department(name="Cardiology REST", code="CARD-R", description="Cardiology department")
    db_session.add(dept)
    db_session.commit()

    # Create Doctor
    doc_payload = {
        "email": "rest_doc_01@medicare.ai",
        "first_name": "Cardio",
        "last_name": "Specialist",
        "department_id": dept.id,
        "specialization": "Interventional Cardiology",
        "license_number": "LIC-REST-CARD-01",
        "consultation_fee": 750.00,
        "qualification": "MBBS, MD, DM",
        "room_number": "304",
        "available_days": "Mon,Wed,Fri"
    }
    res_create = fastapi_client.post("/api/v1/doctors/", json=doc_payload, headers=admin_auth_headers)
    assert res_create.status_code == 201
    doc_id = res_create.json()["id"]

    # List Doctors
    res_list = fastapi_client.get("/api/v1/doctors/", headers=admin_auth_headers)
    assert res_list.status_code == 200
    assert any(d["id"] == doc_id for d in res_list.json())

    # Get Doctor Detail
    res_get = fastapi_client.get(f"/api/v1/doctors/{doc_id}", headers=admin_auth_headers)
    assert res_get.status_code == 200
    assert res_get.json()["department_name"] == "Cardiology REST"

    # Update Doctor Profile
    res_put = fastapi_client.put(f"/api/v1/doctors/{doc_id}", json={"consultation_fee": 800.00}, headers=admin_auth_headers)
    assert res_put.status_code == 200
    assert res_put.json()["consultation_fee"] == 800.00

    # Doctor Workload
    res_workload = fastapi_client.get(f"/api/v1/doctors/{doc_id}/workload", headers=admin_auth_headers)
    assert res_workload.status_code == 200
    assert "total_appointments" in res_workload.json()


# ===========================================================================
# 4. /api/v1/appointments
# ===========================================================================

def test_api_v1_appointments(fastapi_client, admin_auth_headers, db_session):
    # Seed patient and doctor
    u_p = User(email="app_pat@medicare.ai", password_hash="h", role=RoleEnum.PATIENT, first_name="App", last_name="Pat")
    u_d = User(email="app_doc@medicare.ai", password_hash="h", role=RoleEnum.DOCTOR, first_name="App", last_name="Doc")
    db_session.add_all([u_p, u_d])
    db_session.flush()

    pat = Patient(id=u_p.id, dob=date(1990, 1, 1), gender=GenderEnum.MALE)
    doc = Doctor(id=u_d.id, specialization="General", license_number="LIC-APP-01", qualification="MD")
    db_session.add_all([pat, doc])
    db_session.commit()

    # Schedule Appointment (triggers ML No-Show Prediction)
    app_dt = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    res_create = fastapi_client.post("/api/v1/appointments/", json={
        "patient_id": pat.id,
        "doctor_id": doc.id,
        "appointment_datetime": app_dt,
        "reason": "Routine Consultation",
        "sms_reminder_sent": 1
    }, headers=admin_auth_headers)
    assert res_create.status_code == 201
    app_data = res_create.json()
    app_id = app_data["id"]
    assert app_data["status"] == "scheduled"
    assert app_data["no_show_probability"] is not None

    # Get Detail
    res_get = fastapi_client.get(f"/api/v1/appointments/{app_id}", headers=admin_auth_headers)
    assert res_get.status_code == 200
    assert res_get.json()["id"] == app_id

    # Update Status to confirmed
    res_status = fastapi_client.patch(f"/api/v1/appointments/{app_id}/status", json={"status": "confirmed"}, headers=admin_auth_headers)
    assert res_status.status_code == 200
    assert res_status.json()["status"] == "confirmed"

    # Cancel Appointment
    res_cancel = fastapi_client.post(f"/api/v1/appointments/{app_id}/cancel", headers=admin_auth_headers)
    assert res_cancel.status_code == 200
    assert res_cancel.json()["status"] == "cancelled"


# ===========================================================================
# 5. /api/v1/medical-records
# ===========================================================================

def test_api_v1_medical_records(fastapi_client, admin_auth_headers, db_session):
    u_p = User(email="emr_pat@medicare.ai", password_hash="h", role=RoleEnum.PATIENT, first_name="EMR", last_name="Pat")
    db_session.add(u_p)
    db_session.flush()
    pat = Patient(id=u_p.id, dob=date(1988, 4, 12), gender=GenderEnum.MALE)
    db_session.add(pat)
    db_session.commit()

    # Create Medical Record
    emr_payload = {
        "patient_id": pat.id,
        "symptoms": "Persistent dry cough, mild fever",
        "diagnosis": "Acute Bronchitis",
        "clinical_notes": "Chest clear on auscultation",
        "vitals_bp": "120/80",
        "vitals_pulse": 78,
        "vitals_temp": 38.2,
        "vitals_spo2": 98,
        "treatment_plan": "Oral hydration, bronchodilator",
        "follow_up_date": (date.today() + timedelta(days=7)).isoformat()
    }
    res_create = fastapi_client.post("/api/v1/medical-records/", json=emr_payload, headers=admin_auth_headers)
    assert res_create.status_code == 201
    rec_id = res_create.json()["id"]

    # List
    res_list = fastapi_client.get("/api/v1/medical-records/", headers=admin_auth_headers)
    assert res_list.status_code == 200
    assert any(r["id"] == rec_id for r in res_list.json())

    # Get Single
    res_get = fastapi_client.get(f"/api/v1/medical-records/{rec_id}", headers=admin_auth_headers)
    assert res_get.status_code == 200
    assert res_get.json()["diagnosis"] == "Acute Bronchitis"

    # Longitudinal History
    res_hist = fastapi_client.get(f"/api/v1/medical-records/patient/{pat.id}", headers=admin_auth_headers)
    assert res_hist.status_code == 200
    assert len(res_hist.json()) >= 1


# ===========================================================================
# 6. /api/v1/prescriptions & 7. /api/v1/pharmacy
# ===========================================================================

def test_api_v1_pharmacy_and_prescriptions(fastapi_client, admin_auth_headers, db_session):
    # 1. Pharmacy: Create Medicine
    med_res = fastapi_client.post("/api/v1/pharmacy/medicines", json={
        "name": "Azithromycin 500mg REST",
        "category": "Antibiotic",
        "unit": "Tablet",
        "unit_price": 25.00,
        "reorder_level": 30
    }, headers=admin_auth_headers)
    assert med_res.status_code == 201
    med_id = med_res.json()["id"]

    # 2. Pharmacy: Stock In
    today = date.today()
    exp = (today + timedelta(days=180)).isoformat()
    stock_res = fastapi_client.post("/api/v1/pharmacy/stock-in", json={
        "medicine_id": med_id,
        "batch_number": "BAT-AZ-001",
        "expiry_date": exp,
        "quantity": 100,
        "purchase_cost": 15.00
    }, headers=admin_auth_headers)
    assert stock_res.status_code == 200

    # 3. Pharmacy: Dashboard Stats
    stats_res = fastapi_client.get("/api/v1/pharmacy/dashboard-stats", headers=admin_auth_headers)
    assert stats_res.status_code == 200
    assert stats_res.json()["total_stock_units"] >= 100

    # 4. Prescriptions: Create Prescription
    u_p = User(email="rx_pat@medicare.ai", password_hash="h", role=RoleEnum.PATIENT, first_name="Rx", last_name="User")
    db_session.add(u_p)
    db_session.flush()
    pat = Patient(id=u_p.id, dob=date(1992, 2, 2), gender=GenderEnum.FEMALE)
    db_session.add(pat)
    db_session.commit()

    rx_res = fastapi_client.post("/api/v1/prescriptions/", json={
        "patient_id": pat.id,
        "items": [{
            "medicine_id": med_id,
            "dosage": "500 mg",
            "frequency": "Once daily",
            "duration_days": 3,
            "quantity_prescribed": 3
        }],
        "notes": "Take after meals"
    }, headers=admin_auth_headers)
    assert rx_res.status_code == 201
    rx_id = rx_res.json()["id"]

    # 5. Prescriptions: Get Detail
    get_rx = fastapi_client.get(f"/api/v1/prescriptions/{rx_id}", headers=admin_auth_headers)
    assert get_rx.status_code == 200
    assert len(get_rx.json()["items"]) == 1

    # 6. Prescriptions: Dispense (FEFO deduction)
    disp_res = fastapi_client.post(f"/api/v1/prescriptions/{rx_id}/dispense", headers=admin_auth_headers)
    assert disp_res.status_code == 200
    assert disp_res.json()["units_dispensed"] == 3


# ===========================================================================
# 8. /api/v1/laboratory
# ===========================================================================

def test_api_v1_laboratory(fastapi_client, admin_auth_headers, db_session):
    u_p = User(email="lab_user@medicare.ai", password_hash="h", role=RoleEnum.PATIENT, first_name="Lab", last_name="TestPat")
    db_session.add(u_p)
    db_session.flush()
    pat = Patient(id=u_p.id, dob=date(1985, 8, 8), gender=GenderEnum.MALE)
    test = LabTest(name="Liver Function Test REST", test_code="LFT-R", sample_type="Blood", cost=Decimal("450.00"))
    db_session.add_all([pat, test])
    db_session.commit()

    # Create Order
    order_res = fastapi_client.post("/api/v1/laboratory/orders", json={
        "patient_id": pat.id,
        "test_id": test.id,
        "priority": "urgent"
    }, headers=admin_auth_headers)
    assert order_res.status_code == 201
    ord_id = order_res.json()["id"]

    # Sample Collection
    coll_res = fastapi_client.post(f"/api/v1/laboratory/orders/{ord_id}/collect-sample", headers=admin_auth_headers)
    assert coll_res.status_code == 200
    assert coll_res.json()["status"] == "sample_collected"

    # Start Processing
    proc_res = fastapi_client.post(f"/api/v1/laboratory/orders/{ord_id}/start-processing", headers=admin_auth_headers)
    assert proc_res.status_code == 200
    assert proc_res.json()["status"] == "processing"

    # Enter Result
    res_entry = fastapi_client.post(f"/api/v1/laboratory/orders/{ord_id}/result", json={
        "measured_value": 42.5,
        "unit": "IU/L",
        "is_abnormal": False
    }, headers=admin_auth_headers)
    assert res_entry.status_code == 200
    assert res_entry.json()["status"] == "completed"

    # Doctor Review
    rev_res = fastapi_client.post(f"/api/v1/laboratory/orders/{ord_id}/review", json={
        "doctor_review_notes": "Enzyme levels within normal range"
    }, headers=admin_auth_headers)
    assert rev_res.status_code == 200
    assert rev_res.json()["doctor_reviewed"] is True


# ===========================================================================
# 9. /api/v1/admissions
# ===========================================================================

def test_api_v1_admissions(fastapi_client, admin_auth_headers, db_session):
    # Setup Room and Bed
    room = Room(room_number="SURG-201", room_type=RoomTypeEnum.SURGICAL, floor=2, total_beds=2, daily_rate=Decimal("1800.00"))
    db_session.add(room)
    db_session.flush()

    b1 = Bed(room_id=room.id, bed_number="SURG-201-A", status=BedStatusEnum.AVAILABLE)
    b2 = Bed(room_id=room.id, bed_number="SURG-201-B", status=BedStatusEnum.AVAILABLE)
    db_session.add_all([b1, b2])

    u_p = User(email="ipd_user@medicare.ai", password_hash="h", role=RoleEnum.PATIENT, first_name="IPD", last_name="Candidate")
    db_session.add(u_p)
    db_session.flush()
    pat = Patient(id=u_p.id, dob=date(1975, 11, 20), gender=GenderEnum.MALE)
    db_session.add(pat)
    db_session.commit()

    # 1. Admit Patient (triggers ML Readmission Risk prediction)
    admit_res = fastapi_client.post("/api/v1/admissions/", json={
        "patient_id": pat.id,
        "bed_id": b1.id,
        "admission_reason": "Pre-op Cholecystectomy Evaluation"
    }, headers=admin_auth_headers)
    assert admit_res.status_code == 201
    adm_id = admit_res.json()["id"]
    assert admit_res.json()["readmission_risk_score"] is not None

    # 2. Bed Occupancy check
    beds_res = fastapi_client.get("/api/v1/admissions/beds", headers=admin_auth_headers)
    assert beds_res.status_code == 200
    b1_check = next(b for b in beds_res.json() if b["id"] == b1.id)
    assert b1_check["status"] == "occupied"

    # 3. Transfer Patient to Bed 2
    trans_res = fastapi_client.post(f"/api/v1/admissions/{adm_id}/transfer", json={
        "to_bed_id": b2.id,
        "reason": "Transfer to surgical post-op suite"
    }, headers=admin_auth_headers)
    assert trans_res.status_code == 200
    assert trans_res.json()["to_bed_id"] == b2.id

    # 4. Discharge Patient & Auto-Invoice
    disc_res = fastapi_client.post(f"/api/v1/admissions/{adm_id}/discharge", json={
        "discharge_summary": "Surgical recovery uneventful, vitals stable"
    }, headers=admin_auth_headers)
    assert disc_res.status_code == 200
    assert "invoice_id" in disc_res.json()
    assert disc_res.json()["bed_status"] == "maintenance"


# ===========================================================================
# 10. /api/v1/billing
# ===========================================================================

def test_api_v1_billing(fastapi_client, admin_auth_headers, db_session):
    u_p = User(email="bill_user@medicare.ai", password_hash="h", role=RoleEnum.PATIENT, first_name="Bill", last_name="Customer")
    db_session.add(u_p)
    db_session.flush()
    pat = Patient(id=u_p.id, dob=date(1989, 9, 9), gender=GenderEnum.FEMALE)
    db_session.add(pat)
    db_session.commit()

    # 1. Create Invoice across components
    inv_payload = {
        "patient_id": pat.id,
        "discount_type": "fixed",
        "discount_value": 50.00,
        "tax_rate": 0.05,
        "notes": "Hospital Executive Care Invoice",
        "items": [
            {"item_type": "consultation", "description": "Senior Specialist Consult", "quantity": 1, "unit_price": 600.00},
            {"item_type": "laboratory", "description": "Cardiac Enzyme Panel", "quantity": 1, "unit_price": 400.00}
        ]
    }
    inv_res = fastapi_client.post("/api/v1/billing/invoices", json=inv_payload, headers=admin_auth_headers)
    assert inv_res.status_code == 201
    bill_data = inv_res.json()
    bill_id = bill_data["id"]
    # Subtotal 1000 - Discount 50 = 950. Tax 5% on 950 = 47.50. Total = 997.50
    assert float(bill_data["subtotal"]) == 1000.00
    assert float(bill_data["discount"]) == 50.00
    assert float(bill_data["tax"]) == 47.50
    assert float(bill_data.get("final_amount") or bill_data.get("total_amount")) == 997.50
    assert bill_data["status"] == "pending"

    # 2. Record Payment: $500 (transitions to PARTIAL)
    pay_res = fastapi_client.post("/api/v1/billing/payments", json={
        "bill_id": bill_id,
        "amount": 500.00,
        "payment_method": "credit_card",
        "transaction_reference": "TXN-REST-01"
    }, headers=admin_auth_headers)
    assert pay_res.status_code == 201
    assert pay_res.json()["bill_status"] == "partial"
    assert pay_res.json()["new_balance"] == 497.50

    # 3. Settle remainder: $497.50 (transitions to PAID)
    pay_res_2 = fastapi_client.post("/api/v1/billing/payments", json={
        "bill_id": bill_id,
        "amount": 497.50,
        "payment_method": "cash",
        "transaction_reference": "TXN-REST-02"
    }, headers=admin_auth_headers)
    assert pay_res_2.status_code == 201
    assert pay_res_2.json()["bill_status"] == "paid"
    assert pay_res_2.json()["new_balance"] == 0.00

    # 4. Refund Payment
    ref_res = fastapi_client.post(f"/api/v1/billing/invoices/{bill_id}/refund", json={
        "amount": 100.00,
        "reason": "Overcharge adjustment"
    }, headers=admin_auth_headers)
    assert ref_res.status_code == 200
    assert ref_res.json()["bill_status"] == "partial"

    # 5. Billing Dashboard Stats
    stats_res = fastapi_client.get("/api/v1/billing/dashboard-stats", headers=admin_auth_headers)
    assert stats_res.status_code == 200
    assert stats_res.json()["total_invoiced"] >= 997.50


# ===========================================================================
# 11. /api/v1/analytics
# ===========================================================================

def test_api_v1_analytics(fastapi_client, admin_auth_headers):
    # Summary
    res_sum = fastapi_client.get("/api/v1/analytics/summary", headers=admin_auth_headers)
    assert res_sum.status_code == 200
    assert "bed_occupancy_rate" in res_sum.json()

    # Charts JSON specs
    res_charts = fastapi_client.get("/api/v1/analytics/charts", headers=admin_auth_headers)
    assert res_charts.status_code == 200
    assert "chart_patient_growth" in res_charts.json()

    # Individual domain endpoints
    assert fastapi_client.get("/api/v1/analytics/patient-growth", headers=admin_auth_headers).status_code == 200
    assert fastapi_client.get("/api/v1/analytics/bed-occupancy", headers=admin_auth_headers).status_code == 200
    assert fastapi_client.get("/api/v1/analytics/revenue-trends", headers=admin_auth_headers).status_code == 200
    assert fastapi_client.get("/api/v1/analytics/appointment-trends", headers=admin_auth_headers).status_code == 200
