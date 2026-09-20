"""
Integration and Calculation Accuracy Tests for Hospital Billing.

Validates:
1. Pure calculation engine precision (Subtotal, Discount, Tax, Final Amount, Paid, Balance).
2. All 7 Clinical Bill Components (Consultation, Laboratory, Medicines, Room, Bed, Procedures, Other services).
3. Payment Status Lifecycle (PENDING -> PARTIAL -> PAID -> REFUNDED).
4. Full and partial refund accounting.
5. Billing search, multi-facet filtering, and longitudinal patient history.
6. Web routes (/billing/, /billing/create, /billing/invoice/<id>, /billing/pay/<id>, /billing/refund/<id>).
7. FastAPI REST endpoints.
"""

import pytest
from decimal import Decimal
from datetime import datetime, date, timezone, timedelta

from core.models import (
    User, Role, RoleEnum, GenderEnum, Patient, PatientProfile,
    Bill, BillItem, Payment, Insurance,
    BillStatusEnum, PaymentStatusEnum, ItemTypeEnum, PaymentMethodEnum
)
from core.services import billing_service


# =====================================================================
# 1. Calculation Engine Accuracy Tests
# =====================================================================

def test_calculation_engine_subtotal_and_rounding():
    """Tests subtotal calculation with multi-item quantities, fractions, and Decimal precision."""
    items = [
        {"quantity": 3, "unit_price": "120.50"},   # 361.50
        {"quantity": 2, "unit_price": "45.25"},    # 90.50
        {"quantity": 1, "unit_price": "800.00"},   # 800.00
        {"quantity": 5, "unit_price": "12.33"},    # 61.65
    ]
    calc = billing_service.calculate_bill_totals(
        items=items,
        discount="0.00",
        tax_rate="0.00",
        insurance_covered="0.00",
        amount_paid="0.00"
    )

    expected_subtotal = Decimal("361.50") + Decimal("90.50") + Decimal("800.00") + Decimal("61.65")
    assert calc["subtotal"] == expected_subtotal
    assert calc["final_amount"] == expected_subtotal
    assert calc["balance"] == expected_subtotal
    assert calc["amount_paid"] == Decimal("0.00")


def test_calculation_engine_discount_fixed_and_percent():
    """Tests fixed amount discount vs percentage discount deductions."""
    items = [{"quantity": 1, "unit_price": "1000.00"}]

    # Flat discount $150
    calc_flat = billing_service.calculate_bill_totals(
        items=items,
        discount="150.00",
        discount_type="amount",
        tax_rate="0.00"
    )
    assert calc_flat["subtotal"] == Decimal("1000.00")
    assert calc_flat["discount"] == Decimal("150.00")
    assert calc_flat["final_amount"] == Decimal("850.00")

    # Percentage discount 15% ($150)
    calc_pct = billing_service.calculate_bill_totals(
        items=items,
        discount="15.0",
        discount_type="percent",
        tax_rate="0.00"
    )
    assert calc_pct["discount"] == Decimal("150.00")
    assert calc_pct["final_amount"] == Decimal("850.00")

    # Discount exceeding subtotal capped at subtotal
    calc_cap = billing_service.calculate_bill_totals(
        items=items,
        discount="1500.00",
        discount_type="amount",
        tax_rate="0.00"
    )
    assert calc_cap["discount"] == Decimal("1000.00")
    assert calc_cap["final_amount"] == Decimal("0.00")


def test_calculation_engine_tax_and_insurance_formulas():
    """
    Tests exact tax rate computation on taxable base (subtotal - discount)
    and insurance deduction.
    Formula: Final Amount = max(0, Subtotal - Discount + Tax - Insurance)
    """
    items = [
        {"quantity": 1, "unit_price": "2000.00"}
    ]
    # Subtotal = 2000.00
    # Discount = 200.00 -> Taxable Base = 1800.00
    # Tax @ 5% = 1800.00 * 0.05 = 90.00
    # Insurance Covered = 500.00
    # Final Amount = 2000.00 - 200.00 + 90.00 - 500.00 = 1390.00
    calc = billing_service.calculate_bill_totals(
        items=items,
        discount="200.00",
        discount_type="amount",
        tax_rate="0.05",
        insurance_covered="500.00",
        amount_paid="390.00"
    )

    assert calc["subtotal"] == Decimal("2000.00")
    assert calc["discount"] == Decimal("200.00")
    assert calc["tax"] == Decimal("90.00")
    assert calc["insurance_covered"] == Decimal("500.00")
    assert calc["final_amount"] == Decimal("1390.00")
    assert calc["amount_paid"] == Decimal("390.00")
    assert calc["balance"] == Decimal("1000.00")


# =====================================================================
# 2. All 7 Components Bill Creation & Model Verification
# =====================================================================

def test_all_seven_bill_components_itemization(db_session):
    """
    Verifies creation of a hospital bill containing all 7 components:
    Consultation, Laboratory, Medicines, Room, Bed, Procedures, Other services.
    """
    user = User(
        email="billing_patient@hospital.org",
        first_name="Anita",
        last_name="Deshmukh",
        role=RoleEnum.PATIENT
    )
    user.set_password("PatientPass123!")
    db_session.add(user)
    db_session.flush()

    patient = Patient(id=user.id, dob=date(1992, 5, 10), gender=GenderEnum.FEMALE)
    db_session.add(patient)
    db_session.flush()

    items = [
        {"item_type": "consultation", "description": "Senior Cardiologist Consultation", "unit_price": "750.00", "quantity": 1},
        {"item_type": "laboratory", "description": "Complete Blood Count + Lipid Panel", "unit_price": "450.00", "quantity": 1},
        {"item_type": "medicines", "description": "Inpatient Antibiotic IV Infusions", "unit_price": "85.00", "quantity": 4},   # 340.00
        {"item_type": "room", "description": "Deluxe Private Inpatient Room (2 Days)", "unit_price": "1200.00", "quantity": 2}, # 2400.00
        {"item_type": "bed", "description": "Clinical Bed & Vital Monitoring", "unit_price": "300.00", "quantity": 2},         # 600.00
        {"item_type": "procedures", "description": "Bedside Echocardiogram & Doppler", "unit_price": "1500.00", "quantity": 1},
        {"item_type": "other_services", "description": "Hospital Dietary Care & Physiotherapy", "unit_price": "250.00", "quantity": 1}
    ]

    bill = billing_service.create_bill(
        db=db_session,
        patient_id=patient.id,
        items=items,
        discount=Decimal("200.00"),
        discount_type="amount",
        tax_rate=Decimal("0.05"),
        insurance_covered=Decimal("1000.00"),
        notes="Cardiology inpatient admission with comprehensive clinical workup"
    )
    db_session.commit()

    # Subtotal: 750 + 450 + 340 + 2400 + 600 + 1500 + 250 = 6290.00
    expected_subtotal = Decimal("6290.00")
    assert bill.subtotal == expected_subtotal
    assert bill.discount == Decimal("200.00")

    # Taxable Base = 6290 - 200 = 6090.00. Tax @ 5% = 304.50
    expected_tax = Decimal("304.50")
    assert bill.tax == expected_tax
    assert bill.insurance_covered == Decimal("1000.00")

    # Final Amount = 6290 - 200 + 304.50 - 1000 = 5394.50
    expected_final = Decimal("5394.50")
    assert bill.total_amount == expected_final
    assert bill.final_amount == expected_final

    # Initial Status PENDING
    assert bill.status == BillStatusEnum.PENDING
    assert bill.payment_status == BillStatusEnum.PENDING
    assert bill.amount_paid == 0.0
    assert bill.balance_due == pytest.approx(5394.50, 0.01)

    # Verify all 7 components are persisted and itemized
    db_items = db_session.query(BillItem).filter(BillItem.bill_id == bill.id).all()
    assert len(db_items) == 7

    types = {item.item_type for item in db_items}
    assert ItemTypeEnum.CONSULTATION in types
    assert ItemTypeEnum.LABORATORY in types
    assert ItemTypeEnum.MEDICINES in types
    assert ItemTypeEnum.ROOM in types
    assert ItemTypeEnum.BED in types
    assert ItemTypeEnum.PROCEDURES in types
    assert ItemTypeEnum.OTHER_SERVICES in types

    # Check category display
    category_names = [item.category_display for item in db_items]
    assert "Consultation" in category_names
    assert "Laboratory" in category_names
    assert "Medicines" in category_names
    assert "Room" in category_names
    assert "Bed" in category_names
    assert "Procedures" in category_names
    assert "Other Services" in category_names


# =====================================================================
# 3. Payment Status Lifecycle: PENDING -> PARTIAL -> PAID
# =====================================================================

def test_payment_lifecycle_and_balance_tracking(db_session):
    """
    Validates state transitions:
    PENDING -> PARTIAL (partial payment) -> PAID (full balance settled)
    """
    user = User(email="lifecycle_patient@hospital.org", first_name="Ramesh", last_name="Kumar", role=RoleEnum.PATIENT)
    user.set_password("SecurePass123!")
    db_session.add(user)
    db_session.flush()
    patient = Patient(id=user.id, dob=date(1985, 4, 15), gender=GenderEnum.MALE)
    db_session.add(patient)
    db_session.flush()

    # Bill of $1000.00 (tax exempt, no discount)
    bill = billing_service.create_bill(
        db=db_session,
        patient_id=patient.id,
        items=[{"item_type": "consultation", "description": "OPD Consultation", "unit_price": "1000.00", "quantity": 1}],
        discount="0.00",
        tax_rate="0.00",
        insurance_covered="0.00"
    )
    db_session.commit()

    # 1. PENDING State
    assert bill.status == BillStatusEnum.PENDING
    assert bill.amount_paid == 0.0
    assert bill.balance_due == 1000.00

    # 2. First Partial Payment: $300.00 -> status PARTIAL
    pay1, bill = billing_service.record_payment(
        db=db_session,
        bill_id=bill.id,
        amount=Decimal("300.00"),
        payment_method=PaymentMethodEnum.UPI,
        transaction_reference="UPI-REF-001"
    )
    db_session.commit()

    assert bill.status == BillStatusEnum.PARTIAL
    assert bill.payment_status == BillStatusEnum.PARTIAL
    assert bill.amount_paid == 300.00
    assert bill.balance_due == 700.00

    # 3. Second Partial Payment: $400.00 -> status remains PARTIAL
    pay2, bill = billing_service.record_payment(
        db=db_session,
        bill_id=bill.id,
        amount=Decimal("400.00"),
        payment_method=PaymentMethodEnum.CARD,
        transaction_reference="CARD-REF-002"
    )
    db_session.commit()

    assert bill.status == BillStatusEnum.PARTIAL
    assert bill.amount_paid == 700.00
    assert bill.balance_due == 300.00

    # 4. Attempting to overpay ($500 when balance is $300) should raise error
    with pytest.raises(billing_service.PaymentExceedsBalanceError):
        billing_service.record_payment(
            db=db_session,
            bill_id=bill.id,
            amount=Decimal("500.00")
        )

    # 5. Final Settling Payment: $300.00 -> status PAID
    pay3, bill = billing_service.record_payment(
        db=db_session,
        bill_id=bill.id,
        amount=Decimal("300.00"),
        payment_method=PaymentMethodEnum.CASH
    )
    db_session.commit()

    assert bill.status == BillStatusEnum.PAID
    assert bill.payment_status == BillStatusEnum.PAID
    assert bill.amount_paid == 1000.00
    assert bill.balance_due == 0.00


# =====================================================================
# 4. Refund Lifecycle: Full & Partial Refunds -> REFUNDED
# =====================================================================

def test_refund_workflow_and_status_transition(db_session):
    """
    Validates refund issuance:
    1. Full refund transitions invoice to REFUNDED.
    2. Partial refund transitions invoice to PARTIAL.
    """
    user = User(email="refund_patient@hospital.org", first_name="Sunil", last_name="Verma", role=RoleEnum.PATIENT)
    user.set_password("SecurePass123!")
    db_session.add(user)
    db_session.flush()
    patient = Patient(id=user.id, dob=date(1978, 11, 20), gender=GenderEnum.MALE)
    db_session.add(patient)
    db_session.flush()

    bill = billing_service.create_bill(
        db=db_session,
        patient_id=patient.id,
        items=[{"item_type": "laboratory", "description": "MRI Brain Scan", "unit_price": "5000.00", "quantity": 1}],
        discount="0.00",
        tax_rate="0.00"
    )
    db_session.commit()

    # Pay full $5000
    billing_service.record_payment(
        db=db_session,
        bill_id=bill.id,
        amount=Decimal("5000.00"),
        payment_method=PaymentMethodEnum.CARD,
        transaction_reference="CARD-SETTLE-5000"
    )
    db_session.commit()
    assert bill.status == BillStatusEnum.PAID

    # Cannot refund more than paid ($6000)
    with pytest.raises(billing_service.InvalidRefundError):
        billing_service.process_refund(
            db=db_session,
            bill_id=bill.id,
            amount=Decimal("6000.00"),
            reason="Illegal over-refund"
        )

    # Partial refund of $2000 (e.g. contrast agent fee reversal)
    ref_pmt, bill = billing_service.process_refund(
        db=db_session,
        bill_id=bill.id,
        amount=Decimal("2000.00"),
        reason="Contrast agent test not performed"
    )
    db_session.commit()

    assert ref_pmt.is_refund == True
    assert bill.amount_paid == 3000.00
    assert bill.balance_due == 2000.00
    assert bill.status == BillStatusEnum.PARTIAL

    # Full remaining refund of $3000 -> status REFUNDED
    ref_pmt2, bill = billing_service.process_refund(
        db=db_session,
        bill_id=bill.id,
        amount=Decimal("3000.00"),
        reason="Procedure completely cancelled by clinical team"
    )
    db_session.commit()

    assert bill.amount_paid == 0.00
    assert bill.status == BillStatusEnum.REFUNDED
    assert bill.payment_status == BillStatusEnum.REFUNDED


# =====================================================================
# 5. Billing History, Search, and Executive Dashboard Stats
# =====================================================================

def test_billing_search_and_patient_history(db_session):
    """Tests search queries, status filters, patient longitudinal history, and stats."""
    u1 = User(email="search_pat1@hospital.org", first_name="Vikram", last_name="Singhania", phone="9876543210", role=RoleEnum.PATIENT)
    u1.set_password("SecurePass123!")
    u2 = User(email="search_pat2@hospital.org", first_name="Pooja", last_name="Hegde", phone="9123456789", role=RoleEnum.PATIENT)
    u2.set_password("SecurePass123!")
    db_session.add_all([u1, u2])
    db_session.flush()

    p1 = Patient(id=u1.id, dob=date(1990, 1, 1), gender=GenderEnum.MALE)
    p2 = Patient(id=u2.id, dob=date(1995, 2, 2), gender=GenderEnum.FEMALE)
    db_session.add_all([p1, p2])
    db_session.flush()

    # Seed 3 bills for p1 and 1 bill for p2
    b1 = billing_service.create_bill(
        db=db_session, patient_id=p1.id,
        items=[{"item_type": "consultation", "description": "Cardiology OPD", "unit_price": "500.00", "quantity": 1}],
        tax_rate="0.00"
    )
    b2 = billing_service.create_bill(
        db=db_session, patient_id=p1.id,
        items=[{"item_type": "laboratory", "description": "Troponin I", "unit_price": "1200.00", "quantity": 1}],
        tax_rate="0.00"
    )
    billing_service.record_payment(db=db_session, bill_id=b2.id, amount=Decimal("1200.00"))

    b3 = billing_service.create_bill(
        db=db_session, patient_id=p2.id,
        items=[{"item_type": "medicines", "description": "Inpatient Antibiotics", "unit_price": "800.00", "quantity": 1}],
        tax_rate="0.00"
    )
    db_session.commit()

    # Search by patient name
    res_name, count_name = billing_service.search_and_filter_bills(db=db_session, query="Vikram")
    assert count_name == 2
    assert all(b.patient_id == p1.id for b in res_name)

    # Search by invoice number
    res_num, count_num = billing_service.search_and_filter_bills(db=db_session, query=b1.bill_number)
    assert count_num == 1
    assert res_num[0].id == b1.id

    # Filter by status 'paid'
    res_paid, count_paid = billing_service.search_and_filter_bills(db=db_session, status="paid")
    assert any(b.id == b2.id for b in res_paid)

    # Filter by component 'medicines'
    res_med, count_med = billing_service.search_and_filter_bills(db=db_session, item_type="medicines")
    assert any(b.id == b3.id for b in res_med)

    # Patient longitudinal history
    hist = billing_service.get_patient_billing_history(db=db_session, patient_id=p1.id)
    assert hist["total_bills_count"] == 2
    assert hist["total_invoiced"] == 1700.00
    assert hist["total_paid"] == 1200.00
    assert hist["total_balance_due"] == 500.00

    # Dashboard stats
    stats = billing_service.get_billing_dashboard_stats(db_session)
    assert stats["total_billed"] >= 2500.00
    assert stats["total_collected"] >= 1200.00


# =====================================================================
# 6. Web Blueprint Routes & Professional Invoice Rendering
# =====================================================================

def test_web_billing_routes_and_invoice_page(flask_client, db_session):
    """
    Tests web endpoints:
    - /billing/ (Dashboard with KPI stats)
    - /billing/create (Create new bill)
    - /billing/invoice/<id> (Professional Invoice Page)
    - /billing/pay/<id> (Record payment)
    - /billing/refund/<id> (Process refund)
    """
    admin = User(email="billing_admin@hospital.org", first_name="Bill", last_name="Admin", role=RoleEnum.ADMIN)
    admin.set_password("AdminPass123!")
    db_session.add(admin)
    db_session.flush()

    patient_user = User(email="web_patient@hospital.org", first_name="Kavita", last_name="Shah", role=RoleEnum.PATIENT)
    patient_user.set_password("PatientPass123!")
    db_session.add(patient_user)
    db_session.flush()

    patient = Patient(id=patient_user.id, dob=date(1994, 6, 18), gender=GenderEnum.FEMALE)
    db_session.add(patient)
    db_session.commit()

    # Login as Admin
    login_res = flask_client.post("/login", data={
        "email": "billing_admin@hospital.org",
        "password": "AdminPass123!"
    }, follow_redirects=True)
    assert login_res.status_code == 200

    # 1. GET Dashboard
    dash_res = flask_client.get("/billing/")
    assert dash_res.status_code == 200
    assert b"Total Invoiced Billing" in dash_res.data
    assert b"Pending Receivables" in dash_res.data

    # 2. GET Create Bill form
    create_get = flask_client.get("/billing/create")
    assert create_get.status_code == 200
    assert b"Create New Hospital Invoice" in create_get.data

    # 3. POST Create Bill with 3 components
    create_post = flask_client.post("/billing/create", data={
        "patient_id": patient.id,
        "discount": "50.00",
        "discount_type": "amount",
        "tax_rate": "0.05",
        "insurance_covered": "0.00",
        "notes": "Web testing bill",
        "item_type[]": ["consultation", "laboratory", "medicines"],
        "description[]": ["Cardiology Consult", "ECG 12-Lead", "Aspirin 75mg"],
        "unit_price[]": ["500.00", "300.00", "50.00"],
        "quantity[]": ["1", "1", "2"]
    }, follow_redirects=True)
    assert create_post.status_code == 200

    # Fetch newly created bill
    new_bill = db_session.query(Bill).filter(Bill.patient_id == patient.id).order_by(Bill.id.desc()).first()
    assert new_bill is not None
    # Subtotal: 500 + 300 + 100 = 900.00
    # Discount: 50.00 -> Base = 850.00
    # Tax @ 5%: 42.50
    # Total: 892.50
    assert new_bill.subtotal == Decimal("900.00")
    assert new_bill.total_amount == Decimal("892.50")
    assert new_bill.status == BillStatusEnum.PENDING

    # 4. View Professional Invoice Page
    inv_res = flask_client.get(f"/billing/invoice/{new_bill.id}")
    assert inv_res.status_code == 200
    assert b"MediCare" in inv_res.data
    assert b"TAX INVOICE" in inv_res.data
    assert b"Billed Patient" in inv_res.data
    assert b"Kavita Shah" in inv_res.data
    assert b"Itemized Service Breakdown" in inv_res.data
    assert b"Cardiology Consult" in inv_res.data
    assert b"ECG 12-Lead" in inv_res.data
    assert b"Print / Download PDF" in inv_res.data

    # 5. POST Payment (Partial: $400.00)
    pay_res = flask_client.post(f"/billing/pay/{new_bill.id}", data={
        "amount": "400.00",
        "payment_method": "upi",
        "transaction_reference": "UPI-WEB-001"
    }, follow_redirects=True)
    assert pay_res.status_code == 200
    db_session.refresh(new_bill)
    assert new_bill.status == BillStatusEnum.PARTIAL
    assert new_bill.amount_paid == 400.00

    # 6. Settle Remaining Balance ($492.50)
    pay_res2 = flask_client.post(f"/billing/pay/{new_bill.id}", data={
        "amount": "492.50",
        "payment_method": "cash"
    }, follow_redirects=True)
    assert pay_res2.status_code == 200
    db_session.refresh(new_bill)
    assert new_bill.status == BillStatusEnum.PAID

    # 7. Process Refund ($892.50)
    refund_res = flask_client.post(f"/billing/refund/{new_bill.id}", data={
        "refund_amount": "892.50",
        "reason": "Test full patient refund clearance"
    }, follow_redirects=True)
    assert refund_res.status_code == 200
    db_session.refresh(new_bill)
    assert new_bill.status == BillStatusEnum.REFUNDED


# =====================================================================
# 7. FastAPI Endpoints
# =====================================================================

def test_fastapi_billing_endpoints(fastapi_client, db_session):
    """Tests FastAPI REST endpoints for invoices, payments, refunds, and stats."""
    admin = User(email="api_billing_admin@hospital.org", first_name="API", last_name="Admin", role=RoleEnum.ADMIN)
    admin.set_password("AdminApi123!")
    db_session.add(admin)
    db_session.flush()

    patient_user = User(email="api_billing_patient@hospital.org", first_name="Devendra", last_name="Joshi", role=RoleEnum.PATIENT)
    patient_user.set_password("PatientApi123!")
    db_session.add(patient_user)
    db_session.flush()

    patient = Patient(id=patient_user.id, dob=date(1987, 8, 24), gender=GenderEnum.MALE)
    db_session.add(patient)
    db_session.commit()

    # Login to get bearer token
    token_res = fastapi_client.post("/api/v1/auth/login", json={
        "email": "api_billing_admin@hospital.org",
        "password": "AdminApi123!"
    })
    token = token_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. POST /api/v1/billing/invoices (Create Bill)
    create_payload = {
        "patient_id": patient.id,
        "items": [
            {"item_type": "consultation", "description": "Cardiology Visit", "unit_price": "600.00", "quantity": 1},
            {"item_type": "laboratory", "description": "Troponin Assay", "unit_price": "1400.00", "quantity": 1}
        ],
        "discount": "200.00",
        "tax_rate": "0.05",
        "insurance_covered": "500.00",
        "notes": "FastAPI bill creation test"
    }
    create_res = fastapi_client.post("/api/v1/billing/invoices", json=create_payload, headers=headers)
    assert create_res.status_code == 201
    created_data = create_res.json()
    bill_id = created_data["id"]

    # Subtotal = 2000, Disc = 200, Tax = 90, Ins = 500 -> Total = 1390
    assert float(created_data["subtotal"]) == 2000.00
    assert float(created_data["total_amount"]) == 1390.00
    assert created_data["status"] == "pending"

    # 2. GET /api/v1/billing/invoices/{id}
    detail_res = fastapi_client.get(f"/api/v1/billing/invoices/{bill_id}", headers=headers)
    assert detail_res.status_code == 200
    assert len(detail_res.json()["items"]) == 2

    # 3. POST /api/v1/billing/payments
    pay_res = fastapi_client.post("/api/v1/billing/payments", json={
        "invoice_id": bill_id,
        "amount": "1390.00",
        "payment_method": "card",
        "transaction_reference": "TXN-API-1390"
    }, headers=headers)
    assert pay_res.status_code == 201
    assert pay_res.json()["invoice_status"] == "paid"
    assert pay_res.json()["balance_due"] == 0.0

    # 4. POST /api/v1/billing/invoices/{id}/refund
    refund_res = fastapi_client.post(f"/api/v1/billing/invoices/{bill_id}/refund", json={
        "refund_amount": "1390.00",
        "reason": "Full clinical refund clearance via API"
    }, headers=headers)
    assert refund_res.status_code == 200
    assert refund_res.json()["invoice_status"] == "refunded"

    # 5. GET /api/v1/billing/dashboard-stats
    stats_res = fastapi_client.get("/api/v1/billing/dashboard-stats", headers=headers)
    assert stats_res.status_code == 200
    assert "total_billed" in stats_res.json()
    assert "total_collected" in stats_res.json()
    assert "total_refunds" in stats_res.json()
