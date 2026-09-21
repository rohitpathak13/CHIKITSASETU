import pytest
from datetime import date, timedelta
from decimal import Decimal
from backend.models import User, Medicine, MedicineBatch, PatientProfile, RoleEnum, GenderEnum
from backend.security import get_password_hash

def test_pharmacy_stock_reorder(flask_client, db_session):
    """Tests 1-click batch reordering when stock is low."""
    # Create pharmacist
    pharm = User(
        email="pharmacist_reorder@chikitsasetu.ai",
        password_hash=get_password_hash("Pass123!"),
        role=RoleEnum.PHARMACIST,
        first_name="David",
        last_name="Reorder"
    )
    db_session.add(pharm)
    db_session.flush()

    # Create low stock medicine
    med = Medicine(
        name="Amoxicillin 250mg",
        generic_name="Amoxicillin",
        category="Antibiotic",
        unit="Capsule",
        unit_price=Decimal("12.00"),
        reorder_level=50
    )
    db_session.add(med)
    db_session.flush()

    batch_initial = MedicineBatch(
        medicine_id=med.id,
        batch_number="OLD-BATCH-1",
        expiry_date=date.today() + timedelta(days=60),
        quantity_in_stock=10, # Below 50!
        purchase_cost=Decimal("6.00")
    )
    db_session.add(batch_initial)
    db_session.commit()

    assert med.is_low_stock is True

    # Authenticate as pharmacist
    with flask_client.session_transaction() as sess:
        sess["user_id"] = pharm.id
        sess["user_email"] = pharm.email
        sess["user_role"] = pharm.role.value
        sess["user_name"] = pharm.full_name

    # Post reorder
    resp = flask_client.post(f"/pharmacy/reorder/{med.id}", data={
        "batch_number": "NEW-BATCH-2026",
        "quantity": "250",
        "expiry_date": (date.today() + timedelta(days=500)).strftime("%Y-%m-%d"),
        "purchase_cost": "7.50"
    }, follow_redirects=True)

    assert resp.status_code == 200
    med_upd = db_session.query(Medicine).filter(Medicine.id == med.id).first()
    assert med_upd.total_stock == 260
    assert med_upd.is_low_stock is False

def test_receptionist_patient_directory_search(flask_client, db_session):
    """Tests receptionist patient directory lookup and search filter."""
    rec = User(
        email="reception_dir@chikitsasetu.ai",
        password_hash=get_password_hash("Pass123!"),
        role=RoleEnum.RECEPTIONIST,
        first_name="Clara",
        last_name="Oswald"
    )
    p_user = User(
        email="unique_patient@gmail.com",
        password_hash=get_password_hash("Pass123!"),
        role=RoleEnum.PATIENT,
        first_name="Benedict",
        last_name="Cumberbatch",
        phone="9876543210"
    )
    db_session.add_all([rec, p_user])
    db_session.flush()

    p_prof = PatientProfile(
        user_id=p_user.id,
        dob=date(1976, 7, 19),
        gender=GenderEnum.MALE,
        blood_group="B+"
    )
    db_session.add(p_prof)
    db_session.commit()

    with flask_client.session_transaction() as sess:
        sess["user_id"] = rec.id
        sess["user_email"] = rec.email
        sess["user_role"] = rec.role.value
        sess["user_name"] = rec.full_name

    # Search for Benedict
    resp = flask_client.get("/receptionist/patients?q=Benedict")
    assert resp.status_code == 200
    assert b"Benedict Cumberbatch" in resp.data
    assert b"9876543210" in resp.data

    # Search for non-existent name
    resp_empty = flask_client.get("/receptionist/patients?q=NonExistentPerson")
    assert resp_empty.status_code == 200
    assert b"No patients found matching your search" in resp_empty.data
