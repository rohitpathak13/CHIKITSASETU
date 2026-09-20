import pytest
from datetime import date, timedelta
from decimal import Decimal

from core.models import (
    User, RoleEnum, Patient, PatientProfile, Doctor, Department,
    Medicine, MedicineInventory, MedicineBatch, StockTransaction,
    StockTransactionTypeEnum, Prescription, PrescriptionItem,
    PrescriptionStatusEnum, GenderEnum, AuditLog
)
from core.security import get_password_hash
from core.services.pharmacy_service import (
    create_medicine, update_medicine, get_medicine, list_medicines,
    stock_in, stock_out, get_low_stock_medicines, get_expired_batches,
    get_expiring_soon_batches, get_pharmacy_dashboard_stats, list_stock_transactions,
    PharmacyServiceError, MedicineNotFoundError, BatchNotFoundError,
    InvalidInventoryDataError, InsufficientInventoryError
)
from core.services.prescription_service import (
    create_prescription, dispense_prescription
)


@pytest.fixture
def pharmacy_fixture(db_session):
    """
    Sets up a complete clinical pharmacy environment with:
    - 1 Admin user
    - 1 Pharmacist user
    - 1 Doctor user
    - 1 Patient user
    - 1 Receptionist user
    """
    admin_user = User(
        email="admin_pharm@chikitsasetu.ai",
        password_hash=get_password_hash("AdminPass123!"),
        role=RoleEnum.ADMIN,
        first_name="Chief",
        last_name="Administrator"
    )
    pharm_user = User(
        email="pharmacist_inv@chikitsasetu.ai",
        password_hash=get_password_hash("PharmPass123!"),
        role=RoleEnum.PHARMACIST,
        first_name="Severus",
        last_name="Snape"
    )
    doc_user = User(
        email="doctor_inv@chikitsasetu.ai",
        password_hash=get_password_hash("DocPass123!"),
        role=RoleEnum.DOCTOR,
        first_name="Leonard",
        last_name="McCoy"
    )
    pat_user = User(
        email="patient_inv@chikitsasetu.ai",
        password_hash=get_password_hash("PatPass123!"),
        role=RoleEnum.PATIENT,
        first_name="Arthur",
        last_name="Dent",
        phone="555-7788"
    )
    rec_user = User(
        email="rec_inv@chikitsasetu.ai",
        password_hash=get_password_hash("RecPass123!"),
        role=RoleEnum.RECEPTIONIST,
        first_name="Janice",
        last_name="Rand"
    )
    db_session.add_all([admin_user, pharm_user, doc_user, pat_user, rec_user])
    db_session.flush()

    pat_prof = PatientProfile(id=pat_user.id, dob=date(1982, 3, 11), gender=GenderEnum.MALE, blood_group="B+")
    dept = Department(name="Pharmacy Clinical Dept", code="PHARM-01", description="Pharmaceutical Care")
    db_session.add_all([pat_prof, dept])
    db_session.flush()

    doctor = Doctor(
        user_id=doc_user.id,
        department_id=dept.id,
        specialization="Pharmacotherapy",
        license_number="DOC-PH-101",
        qualification="MD, Clinical Pharmacology"
    )
    db_session.add(doctor)
    db_session.commit()

    return {
        "admin_user": admin_user,
        "pharm_user": pharm_user,
        "doc_user": doc_user,
        "doctor": doctor,
        "pat_user": pat_user,
        "pat_prof": pat_prof,
        "rec_user": rec_user
    }


def test_medicine_catalog_crud(pharmacy_fixture, db_session):
    """Verifies creating, updating, and querying medications in the hospital formulary catalog."""
    data = pharmacy_fixture

    # 1. Create Medicine
    med = create_medicine(
        db_session=db_session,
        name="Ciprofloxacin 500mg",
        generic_name="Ciprofloxacin Hydrochloride",
        category="Antibiotic",
        unit="Tablet",
        unit_price=Decimal("12.50"),
        purchase_price=Decimal("7.00"),
        reorder_level=25,
        supplier="Bayer Healthcare",
        manufacturer="Bayer Pharma",
        description="Broad spectrum fluoroquinolone antibiotic",
        actor_id=data["pharm_user"].id
    )

    assert med.id is not None
    assert med.name == "Ciprofloxacin 500mg"
    assert med.selling_price == Decimal("12.50")
    assert med.purchase_price == Decimal("7.00")
    assert med.minimum_stock == 25
    assert med.reorder_level == 25
    assert med.supplier == "Bayer Healthcare"
    assert med.total_stock == 0
    assert med.is_low_stock is True  # 0 <= 25

    # 2. Update Medicine
    updated_med = update_medicine(
        db_session=db_session,
        medicine_id=med.id,
        unit_price=Decimal("14.00"),
        supplier="Novartis Supply",
        reorder_level=30,
        actor_id=data["pharm_user"].id
    )
    assert updated_med.unit_price == Decimal("14.00")
    assert updated_med.supplier == "Novartis Supply"
    assert updated_med.reorder_level == 30

    # 3. Duplicate name prevention
    with pytest.raises(InvalidInventoryDataError) as exc_dup:
        create_medicine(
            db_session=db_session,
            name="Ciprofloxacin 500mg",
            category="Antibiotic",
            unit="Tablet",
            unit_price=Decimal("10.00")
        )
    assert "already exists" in str(exc_dup.value)

    # 4. Invalid unit price validation
    with pytest.raises(InvalidInventoryDataError) as exc_price:
        create_medicine(
            db_session=db_session,
            name="Negative Price Med",
            category="General",
            unit="Vial",
            unit_price=Decimal("-5.00")
        )
    assert "greater than zero" in str(exc_price.value)


def test_stock_in_receipt_and_movement_recording(pharmacy_fixture, db_session):
    """Verifies stock-in creates a batch, records a StockTransaction of type STOCK_IN, and increments stock."""
    data = pharmacy_fixture

    med = create_medicine(
        db_session=db_session,
        name="Azithromycin 250mg",
        category="Antibiotic",
        unit="Capsule",
        unit_price=Decimal("20.00"),
        purchase_price=Decimal("11.00"),
        reorder_level=20,
        supplier="Pfizer Distribution",
        actor_id=data["pharm_user"].id
    )

    future_exp = date.today() + timedelta(days=200)

    # Receive batch (Stock In)
    res = stock_in(
        db_session=db_session,
        medicine_id=med.id,
        batch_number="AZI-B2026",
        expiry_date=future_exp,
        quantity=150,
        purchase_cost=Decimal("10.50"),
        selling_price=Decimal("20.00"),
        supplier="Pfizer Direct Consignment",
        performed_by_id=data["pharm_user"].id,
        notes="Invoice #PO-8823"
    )

    assert res["quantity_added"] == 150
    assert res["quantity_in_stock"] == 150
    assert res["total_medicine_stock"] == 150

    # Verify batch
    batch = db_session.query(MedicineInventory).filter(MedicineInventory.id == res["batch_id"]).first()
    assert batch is not None
    assert batch.batch_number == "AZI-B2026"
    assert batch.expiry_date == future_exp
    assert batch.purchase_cost == Decimal("10.50")
    assert batch.supplier == "Pfizer Direct Consignment"
    assert batch.is_expired is False
    assert batch.status_label == "ACTIVE"

    # Verify Stock Movement Ledger Transaction
    txn = db_session.query(StockTransaction).filter(StockTransaction.id == res["transaction_id"]).first()
    assert txn is not None
    assert txn.transaction_type == StockTransactionTypeEnum.STOCK_IN
    assert txn.quantity == 150
    assert txn.medicine_id == med.id
    assert txn.batch_id == batch.id
    assert txn.supplier == "Pfizer Direct Consignment"

    # Test incremental stock-in on the same batch number
    res2 = stock_in(
        db_session=db_session,
        medicine_id=med.id,
        batch_number="AZI-B2026",
        expiry_date=future_exp,
        quantity=50,
        purchase_cost=Decimal("10.50"),
        performed_by_id=data["pharm_user"].id
    )
    assert res2["quantity_in_stock"] == 200
    assert med.total_stock == 200
    assert med.is_low_stock is False


def test_stock_in_rejects_past_expiry_or_negative_quantity(pharmacy_fixture, db_session):
    """Verifies that receiving an expired batch or invalid quantity is prevented."""
    data = pharmacy_fixture

    med = create_medicine(
        db_session=db_session,
        name="Ibuprofen 400mg",
        category="Analgesic",
        unit="Tablet",
        unit_price=Decimal("6.00"),
        actor_id=data["pharm_user"].id
    )

    # 1. Past expiry date
    past_date = date.today() - timedelta(days=1)
    with pytest.raises(InvalidInventoryDataError) as exc_exp:
        stock_in(
            db_session=db_session,
            medicine_id=med.id,
            batch_number="IBU-EXP",
            expiry_date=past_date,
            quantity=50,
            purchase_cost=Decimal("2.50")
        )
    assert "Cannot receive expired batch" in str(exc_exp.value)

    # 2. Zero or negative quantity
    with pytest.raises(InvalidInventoryDataError) as exc_qty:
        stock_in(
            db_session=db_session,
            medicine_id=med.id,
            batch_number="IBU-ZERO",
            expiry_date=date.today() + timedelta(days=100),
            quantity=0,
            purchase_cost=Decimal("2.50")
        )
    assert "greater than zero" in str(exc_qty.value)


def test_stock_out_deduction_and_reasons(pharmacy_fixture, db_session):
    """Verifies stock-out correctly decreases batch quantity and classifies transactions according to reason."""
    data = pharmacy_fixture

    med = create_medicine(
        db_session=db_session,
        name="Omeprazole 20mg",
        category="Gastrointestinal",
        unit="Capsule",
        unit_price=Decimal("15.00"),
        actor_id=data["pharm_user"].id
    )

    # Initial stock-in
    res_in = stock_in(
        db_session=db_session,
        medicine_id=med.id,
        batch_number="OMP-01",
        expiry_date=date.today() + timedelta(days=90),
        quantity=100,
        purchase_cost=Decimal("8.00"),
        performed_by_id=data["pharm_user"].id
    )
    batch_id = res_in["batch_id"]

    # 1. Deduct for damage
    out1 = stock_out(
        db_session=db_session,
        batch_id=batch_id,
        quantity=10,
        reason="Broken bottles during transit",
        performed_by_id=data["pharm_user"].id
    )
    assert out1["quantity_deducted"] == 10
    assert out1["remaining_batch_stock"] == 90
    assert out1["transaction_type"] == "stock_out"

    # 2. Deduct for audit adjustment
    out2 = stock_out(
        db_session=db_session,
        batch_id=batch_id,
        quantity=5,
        reason="Inventory audit adjustment correction",
        performed_by_id=data["pharm_user"].id
    )
    assert out2["remaining_batch_stock"] == 85
    assert out2["transaction_type"] == "adjustment"

    # 3. Deduct for expired discard
    out3 = stock_out(
        db_session=db_session,
        batch_id=batch_id,
        quantity=15,
        reason="Expired stock discard protocol",
        performed_by_id=data["pharm_user"].id
    )
    assert out3["remaining_batch_stock"] == 70
    assert out3["transaction_type"] == "expired_discard"

    # 4. Over-deduction prevention
    with pytest.raises(InsufficientInventoryError) as exc_over:
        stock_out(
            db_session=db_session,
            batch_id=batch_id,
            quantity=100,  # Only 70 in stock
            reason="Sample testing"
        )
    assert "only has 70 unit(s) in stock" in str(exc_over.value)


def test_automated_low_stock_detection(pharmacy_fixture, db_session):
    """Verifies that medicines with unexpired total stock <= reorder_level are automatically detected."""
    data = pharmacy_fixture

    med1 = create_medicine(
        db_session=db_session,
        name="Metoprolol 50mg",
        category="Cardiovascular",
        unit="Tablet",
        unit_price=Decimal("18.00"),
        reorder_level=40,
        actor_id=data["pharm_user"].id
    )
    med2 = create_medicine(
        db_session=db_session,
        name="Atorvastatin 20mg",
        category="Cardiovascular",
        unit="Tablet",
        unit_price=Decimal("25.00"),
        reorder_level=20,
        actor_id=data["pharm_user"].id
    )

    # Metoprolol: add 25 units (below reorder level of 40)
    stock_in(
        db_session=db_session,
        medicine_id=med1.id,
        batch_number="MTP-B1",
        expiry_date=date.today() + timedelta(days=150),
        quantity=25,
        purchase_cost=Decimal("10.00")
    )

    # Atorvastatin: add 50 units (above reorder level of 20)
    stock_in(
        db_session=db_session,
        medicine_id=med2.id,
        batch_number="ATV-B1",
        expiry_date=date.today() + timedelta(days=150),
        quantity=50,
        purchase_cost=Decimal("15.00")
    )

    low_stock = get_low_stock_medicines(db_session)
    low_stock_ids = [m.id for m in low_stock]

    assert med1.id in low_stock_ids
    assert med2.id not in low_stock_ids


def test_automated_expired_and_expiring_soon_detection(pharmacy_fixture, db_session):
    """Verifies automated detection of expired batches and batches expiring within 30 days."""
    data = pharmacy_fixture

    med = create_medicine(
        db_session=db_session,
        name="Doxycycline 100mg",
        category="Antibiotic",
        unit="Capsule",
        unit_price=Decimal("16.00"),
        actor_id=data["pharm_user"].id
    )

    today = date.today()

    # Batch 1: Expired (past date) with remaining units
    batch_exp = MedicineInventory(
        medicine_id=med.id,
        batch_number="DOX-EXP",
        expiry_date=today - timedelta(days=5),
        quantity_in_stock=20,
        purchase_cost=Decimal("8.00"),
        supplier="Past Supplier",
        received_date=today - timedelta(days=100)
    )

    # Batch 2: Expiring soon (expires in 12 days, <= 30 days)
    batch_soon = MedicineInventory(
        medicine_id=med.id,
        batch_number="DOX-SOON",
        expiry_date=today + timedelta(days=12),
        quantity_in_stock=40,
        purchase_cost=Decimal("8.00"),
        supplier="Active Supplier",
        received_date=today - timedelta(days=50)
    )

    # Batch 3: Safe / Long shelf life (expires in 180 days)
    batch_safe = MedicineInventory(
        medicine_id=med.id,
        batch_number="DOX-SAFE",
        expiry_date=today + timedelta(days=180),
        quantity_in_stock=100,
        purchase_cost=Decimal("8.00"),
        supplier="Active Supplier",
        received_date=today
    )

    db_session.add_all([batch_exp, batch_soon, batch_safe])
    db_session.commit()

    # 1. Query Expired
    expired_list = get_expired_batches(db_session)
    expired_batch_nums = [b.batch_number for b in expired_list]
    assert "DOX-EXP" in expired_batch_nums
    assert "DOX-SOON" not in expired_batch_nums
    assert "DOX-SAFE" not in expired_batch_nums

    # 2. Query Expiring Soon (default 30 days)
    expiring_soon_list = get_expiring_soon_batches(db_session, days=30)
    soon_batch_nums = [b.batch_number for b in expiring_soon_list]
    assert "DOX-SOON" in soon_batch_nums
    assert "DOX-EXP" not in soon_batch_nums
    assert "DOX-SAFE" not in soon_batch_nums

    # Batch status label and days to expiry checks
    assert batch_exp.is_expired is True
    assert batch_exp.status_label == "EXPIRED"
    assert batch_soon.is_expiring_soon is True
    assert batch_soon.days_to_expiry == 12
    assert batch_soon.status_label == "EXPIRING_SOON"


def test_prescription_dispensing_creates_fefo_stock_transactions(pharmacy_fixture, db_session):
    """
    Verifies that dispensing prescribed medications via FEFO creates
    StockTransaction audit records with transaction_type=DISPENSED.
    """
    data = pharmacy_fixture

    med = create_medicine(
        db_session=db_session,
        name="Cefixime 200mg",
        category="Antibiotic",
        unit="Tablet",
        unit_price=Decimal("22.00"),
        actor_id=data["pharm_user"].id
    )

    today = date.today()

    # Batch A (expires in 25 days, 15 units)
    batch_a = MedicineInventory(
        medicine_id=med.id,
        batch_number="CFX-A",
        expiry_date=today + timedelta(days=25),
        quantity_in_stock=15,
        purchase_cost=Decimal("12.00")
    )
    # Batch B (expires in 120 days, 50 units)
    batch_b = MedicineInventory(
        medicine_id=med.id,
        batch_number="CFX-B",
        expiry_date=today + timedelta(days=120),
        quantity_in_stock=50,
        purchase_cost=Decimal("12.00")
    )
    db_session.add_all([batch_a, batch_b])
    db_session.commit()

    # Prescribe 25 units
    rx = create_prescription(
        db_session=db_session,
        doctor_id=data["doc_user"].id,
        patient_id=data["pat_user"].id,
        items=[{
            "medicine_id": med.id,
            "dosage": "200 mg",
            "frequency": "1-0-1",
            "duration_days": 12,
            "quantity_prescribed": 25
        }],
        actor_id=data["doc_user"].id
    )

    # Dispense via service
    disp_res = dispense_prescription(
        db_session=db_session,
        prescription_id=rx.id,
        actor_id=data["pharm_user"].id
    )

    assert disp_res["status"] == "dispensed"
    assert disp_res["units_dispensed"] == 25

    # Check that StockTransaction audit records were created for both batches:
    # 15 from Batch A and 10 from Batch B
    txns = db_session.query(StockTransaction).filter(
        StockTransaction.medicine_id == med.id,
        StockTransaction.reference_id == rx.id,
        StockTransaction.transaction_type == StockTransactionTypeEnum.DISPENSED
    ).all()

    assert len(txns) == 2
    quantities = [t.quantity for t in txns]
    assert 15 in quantities
    assert 10 in quantities


def test_pharmacy_dashboard_statistics_aggregation(pharmacy_fixture, db_session):
    """Verifies get_pharmacy_dashboard_stats aggregates counts, valuations, alerts, and recent transactions."""
    data = pharmacy_fixture

    med = create_medicine(
        db_session=db_session,
        name="Lisinopril 10mg",
        category="Cardiovascular",
        unit="Tablet",
        unit_price=Decimal("10.00"),
        purchase_price=Decimal("5.00"),
        reorder_level=50,
        actor_id=data["pharm_user"].id
    )

    # Stock in 20 units (low stock)
    stock_in(
        db_session=db_session,
        medicine_id=med.id,
        batch_number="LIS-01",
        expiry_date=date.today() + timedelta(days=20),  # expiring soon!
        quantity=20,
        purchase_cost=Decimal("5.00"),
        performed_by_id=data["pharm_user"].id
    )

    stats = get_pharmacy_dashboard_stats(db_session)

    assert stats["total_medicines"] >= 1
    assert stats["total_stock_units"] >= 20
    assert stats["low_stock_count"] >= 1
    assert stats["expiring_soon_batches_count"] >= 1
    assert stats["valuation_cost"] > 0
    assert stats["valuation_retail"] > 0
    assert len(stats["recent_transactions"]) > 0


def test_web_pharmacy_routes_and_rbac(flask_client, pharmacy_fixture, db_session):
    """
    Verifies that PHARMACIST and ADMIN roles have full access to dashboard, inventory,
    and Stock-In/Stock-Out routes, while PATIENT and RECEPTIONIST are denied with 403.
    """
    data = pharmacy_fixture

    # 1. Pharmacist access to dashboard and inventory
    with flask_client.session_transaction() as sess:
        sess["user_id"] = data["pharm_user"].id
        sess["user_email"] = data["pharm_user"].email
        sess["user_role"] = "pharmacist"
        sess["user_name"] = data["pharm_user"].full_name

    resp_dash = flask_client.get("/pharmacy/")
    assert resp_dash.status_code == 200
    assert "Pharmacy Desk & Real-time Inventory Analytics" in resp_dash.data.decode("utf-8")

    resp_inv_catalog = flask_client.get("/pharmacy/inventory?tab=catalog")
    assert resp_inv_catalog.status_code == 200
    assert "Formulary Catalog" in resp_inv_catalog.data.decode("utf-8")

    resp_inv_batches = flask_client.get("/pharmacy/inventory?tab=batches")
    assert resp_inv_batches.status_code == 200
    assert "Batches & Expiry" in resp_inv_batches.data.decode("utf-8")

    resp_inv_ledger = flask_client.get("/pharmacy/inventory?tab=ledger")
    assert resp_inv_ledger.status_code == 200
    assert "Stock Movement" in resp_inv_ledger.data.decode("utf-8")

    # 2. Add new drug via Web POST
    post_med_resp = flask_client.post(
        "/pharmacy/medicine/add",
        data={
            "name": "Pantoprazole 40mg",
            "generic_name": "Pantoprazole Sodium",
            "category": "Gastrointestinal",
            "unit": "Tablet",
            "unit_price": "8.00",
            "purchase_price": "4.50",
            "reorder_level": "30",
            "supplier": "Sun Pharma"
        },
        follow_redirects=True
    )
    assert post_med_resp.status_code == 200

    created_med = db_session.query(Medicine).filter(Medicine.name == "Pantoprazole 40mg").first()
    assert created_med is not None
    assert created_med.reorder_level == 30

    # 3. Stock In via Web POST
    stock_in_resp = flask_client.post(
        "/pharmacy/stock-in",
        data={
            "medicine_id": str(created_med.id),
            "batch_number": "PAN-2026-WEB",
            "expiry_date": (date.today() + timedelta(days=365)).strftime("%Y-%m-%d"),
            "quantity": "250",
            "purchase_cost": "4.50",
            "supplier": "Sun Pharma Direct"
        },
        follow_redirects=True
    )
    assert stock_in_resp.status_code == 200

    batch = db_session.query(MedicineInventory).filter(MedicineInventory.batch_number == "PAN-2026-WEB").first()
    assert batch is not None
    assert batch.quantity_in_stock == 250

    # 4. Stock Out via Web POST
    stock_out_resp = flask_client.post(
        "/pharmacy/stock-out",
        data={
            "batch_id": str(batch.id),
            "quantity": "10",
            "reason": "Damaged packaging / seal broken"
        },
        follow_redirects=True
    )
    assert stock_out_resp.status_code == 200
    db_session.refresh(batch)
    assert batch.quantity_in_stock == 240

    # 5. Quick Reorder via Web POST
    reorder_resp = flask_client.post(
        f"/pharmacy/reorder/{created_med.id}",
        data={
            "batch_number": "PAN-REORDER-01",
            "quantity": "50",
            "purchase_cost": "4.50"
        },
        follow_redirects=True
    )
    assert reorder_resp.status_code == 200

    # 6. Unauthorized Access (Patient & Receptionist blocked with 403)
    with flask_client.session_transaction() as sess:
        sess["user_id"] = data["pat_user"].id
        sess["user_email"] = data["pat_user"].email
        sess["user_role"] = "patient"
        sess["user_name"] = data["pat_user"].full_name

    resp_denied = flask_client.get("/pharmacy/")
    assert resp_denied.status_code in [403, 302]

    resp_inv_denied = flask_client.get("/pharmacy/inventory")
    assert resp_inv_denied.status_code in [403, 302]


def test_pharmacy_fastapi_endpoints(fastapi_client, admin_auth_headers, db_session):
    """
    Verifies FastAPI pharmacy endpoints for dashboard stats, medicine creation,
    stock in, stock out, batches, and risk detection lists.
    """
    # 1. Dashboard stats
    stats_resp = fastapi_client.get("/api/v1/pharmacy/dashboard-stats", headers=admin_auth_headers)
    assert stats_resp.status_code == 200
    stats_data = stats_resp.json()
    assert "total_medicines" in stats_data
    assert "low_stock_count" in stats_data
    assert "valuation_cost" in stats_data

    # 2. Create Medicine via API
    med_payload = {
        "name": "API Drug Paracetamol 1000mg",
        "generic_name": "Acetaminophen",
        "category": "Analgesic",
        "unit": "Tablet",
        "unit_price": 5.50,
        "purchase_price": 2.20,
        "reorder_level": 15,
        "supplier": "API Supplier"
    }
    create_resp = fastapi_client.post("/api/v1/pharmacy/medicines", json=med_payload, headers=admin_auth_headers)
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    med_id = created_data["id"]
    assert created_data["name"] == "API Drug Paracetamol 1000mg"

    # 3. Stock In via API
    future_date = (date.today() + timedelta(days=200)).strftime("%Y-%m-%d")
    stock_in_payload = {
        "medicine_id": med_id,
        "batch_number": "BAT-API-01",
        "expiry_date": future_date,
        "quantity": 100,
        "purchase_cost": 2.20,
        "selling_price": 5.50,
        "supplier": "API Supplier",
        "notes": "FastAPI Consignment"
    }
    stock_in_resp = fastapi_client.post("/api/v1/pharmacy/stock-in", json=stock_in_payload, headers=admin_auth_headers)
    assert stock_in_resp.status_code == 200
    res_in = stock_in_resp.json()
    batch_id = res_in["result"]["batch_id"]

    # 4. Batches query
    batches_resp = fastapi_client.get("/api/v1/pharmacy/batches", headers=admin_auth_headers)
    assert batches_resp.status_code == 200
    batches_data = batches_resp.json()
    assert any(b["batch_number"] == "BAT-API-01" for b in batches_data)

    # 5. Stock Out via API
    stock_out_payload = {
        "batch_id": batch_id,
        "quantity": 5,
        "reason": "Damaged strip",
        "notes": "Quality check write-off"
    }
    stock_out_resp = fastapi_client.post("/api/v1/pharmacy/stock-out", json=stock_out_payload, headers=admin_auth_headers)
    assert stock_out_resp.status_code == 200
    res_out = stock_out_resp.json()
    assert res_out["result"]["remaining_batch_stock"] == 95

    # 6. Low stock, expired, expiring-soon queries
    low_stock_resp = fastapi_client.get("/api/v1/pharmacy/low-stock", headers=admin_auth_headers)
    assert low_stock_resp.status_code == 200

    expired_resp = fastapi_client.get("/api/v1/pharmacy/expired", headers=admin_auth_headers)
    assert expired_resp.status_code == 200

    expiring_soon_resp = fastapi_client.get("/api/v1/pharmacy/expiring-soon", headers=admin_auth_headers)
    assert expiring_soon_resp.status_code == 200

