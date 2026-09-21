import pytest
from datetime import date, timedelta
from decimal import Decimal
from backend.models import (
    User, RoleEnum, Medicine, MedicineBatch,
    Ward, Bed, WardTypeEnum, BedStatusEnum,
    Invoice, InvoiceItem, Payment, ItemTypeEnum, InvoiceStatusEnum, PaymentMethodEnum
)

def test_user_password_hashing(db_session):
    user = User(
        email="test_user@example.com",
        role=RoleEnum.PATIENT,
        first_name="Alice",
        last_name="Smith"
    )
    user.set_password("Secret1234!")
    db_session.add(user)
    db_session.commit()

    assert user.password_hash != "Secret1234!"
    assert user.check_password("Secret1234!") is True
    assert user.check_password("WrongPassword") is False
    assert user.full_name == "Alice Smith"

def test_medicine_stock_calculation(db_session):
    med = Medicine(
        name="Test Antibiotic 250mg",
        category="Antibiotic",
        unit="Capsule",
        unit_price=Decimal("12.00"),
        reorder_level=20
    )
    db_session.add(med)
    db_session.commit()

    # Add active batch
    b1 = MedicineBatch(
        medicine_id=med.id,
        batch_number="B-101",
        expiry_date=date.today() + timedelta(days=100),
        quantity_in_stock=50,
        purchase_cost=Decimal("6.00")
    )
    # Add expired batch (should not be counted in total_stock)
    b2 = MedicineBatch(
        medicine_id=med.id,
        batch_number="B-102",
        expiry_date=date.today() - timedelta(days=10),
        quantity_in_stock=30,
        purchase_cost=Decimal("6.00")
    )
    db_session.add_all([b1, b2])
    db_session.commit()

    assert med.total_stock == 50
    assert med.is_low_stock is False

def test_invoice_recalculation(db_session):
    # Create test patient
    patient = User(
        email="inv_patient@example.com",
        role=RoleEnum.PATIENT,
        first_name="Bob",
        last_name="Builder"
    )
    patient.set_password("Pass123!")
    db_session.add(patient)
    db_session.flush()

    inv = Invoice(
        invoice_number="INV-TEST-001",
        patient_id=patient.id,
        tax=Decimal("10.00"),
        discount=Decimal("5.00"),
        status=InvoiceStatusEnum.UNPAID
    )
    db_session.add(inv)
    db_session.flush()

    item1 = InvoiceItem(
        invoice_id=inv.id,
        item_type=ItemTypeEnum.CONSULTATION,
        description="Doctor Consultation",
        unit_price=Decimal("100.00"),
        quantity=1,
        subtotal=Decimal("100.00")
    )
    item2 = InvoiceItem(
        invoice_id=inv.id,
        item_type=ItemTypeEnum.LAB_TEST,
        description="CBC Assay",
        unit_price=Decimal("50.00"),
        quantity=1,
        subtotal=Decimal("50.00")
    )
    db_session.add_all([item1, item2])
    db_session.flush()

    inv.recalculate()
    assert float(inv.subtotal) == 150.00
    assert float(inv.total_amount) == 155.00  # 150 + 10 - 5
    assert inv.balance_due == 155.00
    assert inv.status == InvoiceStatusEnum.UNPAID

    # Record partial payment
    p1 = Payment(
        invoice=inv,
        amount=Decimal("100.00"),
        payment_method=PaymentMethodEnum.CASH
    )
    db_session.add(p1)
    db_session.flush()

    inv.recalculate()
    assert inv.amount_paid == 100.00
    assert inv.balance_due == 55.00
    assert inv.status == InvoiceStatusEnum.PARTIALLY_PAID

    # Pay remaining balance
    p2 = Payment(
        invoice=inv,
        amount=Decimal("55.00"),
        payment_method=PaymentMethodEnum.CARD
    )
    db_session.add(p2)
    db_session.flush()

    inv.recalculate()
    assert inv.amount_paid == 155.00
    assert inv.balance_due == 0.00
    assert inv.status == InvoiceStatusEnum.PAID
