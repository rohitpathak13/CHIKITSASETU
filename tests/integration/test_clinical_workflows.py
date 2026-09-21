import pytest
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from backend.models import (
    User, DoctorProfile, PatientProfile, Department, Appointment,
    MedicalRecord, Prescription, PrescriptionItem, Medicine, MedicineBatch,
    LabTestType, LabOrder, LabResult,
    Invoice, InvoiceItem, Payment,
    RoleEnum, GenderEnum, AppointmentStatusEnum, PrescriptionStatusEnum,
    LabOrderStatusEnum, InvoiceStatusEnum, ItemTypeEnum, PaymentMethodEnum
)

def test_full_clinical_lifecycle(db_session):
    # 1. Setup Department & Doctor
    dept = Department(name="Cardiology Clinical", code="CARD-TEST")
    db_session.add(dept)
    db_session.flush()

    doc_user = User(
        email="doctor.integration@chikitsasetu.ai",
        role=RoleEnum.DOCTOR,
        first_name="Marcus",
        last_name="Welby"
    )
    doc_user.set_password("DocPass123!")
    db_session.add(doc_user)
    db_session.flush()

    doc_profile = DoctorProfile(
        user_id=doc_user.id,
        department_id=dept.id,
        specialization="Cardiology",
        license_number="LIC-TEST-009",
        consultation_fee=Decimal("700.00"),
        qualification="MD Cardiology"
    )
    db_session.add(doc_profile)

    # 2. Setup Patient
    patient_user = User(
        email="patient.integration@example.com",
        role=RoleEnum.PATIENT,
        first_name="Jane",
        last_name="Doe"
    )
    patient_user.set_password("Patient123!")
    db_session.add(patient_user)
    db_session.flush()

    patient_profile = PatientProfile(
        user_id=patient_user.id,
        dob=date(1980, 6, 15),
        gender=GenderEnum.FEMALE,
        blood_group="O+"
    )
    db_session.add(patient_profile)

    # 3. Setup Medicine & Batch
    med = Medicine(
        name="CardioPill 10mg",
        category="Cardiovascular",
        unit="Tablet",
        unit_price=Decimal("15.00"),
        reorder_level=10
    )
    db_session.add(med)
    db_session.flush()

    batch = MedicineBatch(
        medicine_id=med.id,
        batch_number="CP-2026-01",
        expiry_date=date.today() + timedelta(days=200),
        quantity_in_stock=100,
        purchase_cost=Decimal("7.50")
    )
    db_session.add(batch)

    # 4. Setup Lab Test Type
    lab_test = LabTestType(
        name="Serum Potassium",
        test_code="K+",
        sample_type="Serum",
        unit="mmol/L",
        reference_range_min=3.5,
        reference_range_max=5.0,
        cost=Decimal("250.00")
    )
    db_session.add(lab_test)
    db_session.commit()

    # 5. Book Appointment
    appt = Appointment(
        patient_id=patient_user.id,
        doctor_id=doc_user.id,
        appointment_datetime=datetime.now(timezone.utc),
        status=AppointmentStatusEnum.SCHEDULED,
        reason="Routine cardiac rhythm evaluation",
        token_number=1,
        no_show_probability=0.10
    )
    db_session.add(appt)
    db_session.commit()

    # 6. Conduct Consultation & Document EMR
    emr = MedicalRecord(
        patient_id=patient_user.id,
        doctor_id=doc_user.id,
        appointment_id=appt.id,
        visit_date=date.today(),
        symptoms="Palpitations and fatigue",
        diagnosis="Sinus Tachycardia",
        vitals_bp="130/85",
        vitals_pulse=95
    )
    db_session.add(emr)
    db_session.flush()

    # Generate Prescription
    rx = Prescription(
        medical_record_id=emr.id,
        patient_id=patient_user.id,
        doctor_id=doc_user.id,
        status=PrescriptionStatusEnum.PENDING
    )
    db_session.add(rx)
    db_session.flush()

    rx_item = PrescriptionItem(
        prescription_id=rx.id,
        medicine_id=med.id,
        dosage="10mg",
        frequency="1-0-0",
        duration_days=14,
        quantity_prescribed=14
    )
    db_session.add(rx_item)

    # Order Lab Test
    order = LabOrder(
        patient_id=patient_user.id,
        doctor_id=doc_user.id,
        medical_record_id=emr.id,
        test_type_id=lab_test.id,
        status=LabOrderStatusEnum.ORDERED
    )
    db_session.add(order)
    appt.status = AppointmentStatusEnum.COMPLETED
    db_session.commit()

    # 7. Laboratory Processes Specimen and Enters Result
    order.status = LabOrderStatusEnum.SAMPLE_COLLECTED
    # Elevated potassium test (Hyperkalemia) -> should flag is_abnormal=True
    lab_res = LabResult(
        lab_order_id=order.id,
        measured_value=5.8,
        unit="mmol/L",
        is_abnormal=True,
        critical_alert=False,
        technician_notes="Mild hyperkalemia detected"
    )
    db_session.add(lab_res)
    order.status = LabOrderStatusEnum.COMPLETED
    db_session.commit()

    assert order.status == LabOrderStatusEnum.COMPLETED
    assert order.result.is_abnormal is True

    # 8. Pharmacy Dispenses Prescription
    assert batch.quantity_in_stock == 100
    batch.quantity_in_stock -= rx_item.quantity_prescribed
    rx_item.quantity_dispensed = rx_item.quantity_prescribed
    rx.status = PrescriptionStatusEnum.DISPENSED
    db_session.commit()

    assert batch.quantity_in_stock == 86
    assert rx.status == PrescriptionStatusEnum.DISPENSED

    # 9. Billing Generates Itemized Invoice
    inv = Invoice(
        invoice_number="INV-INTEG-001",
        patient_id=patient_user.id,
        appointment_id=appt.id,
        subtotal=Decimal("1160.00"), # 700 consult + 250 lab + (14 * 15) meds
        total_amount=Decimal("1160.00"),
        status=InvoiceStatusEnum.UNPAID
    )
    db_session.add(inv)
    db_session.flush()

    # Pay full invoice
    pay = Payment(
        invoice=inv,
        amount=Decimal("1160.00"),
        payment_method=PaymentMethodEnum.CARD,
        transaction_reference="CARD-TXN-SUCCESS"
    )
    db_session.add(pay)
    inv.recalculate()
    db_session.commit()

    assert inv.status == InvoiceStatusEnum.PAID
    assert inv.balance_due == 0.0
