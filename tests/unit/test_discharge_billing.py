import pytest
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from core.models import (
    User, DoctorProfile, PatientProfile, Department, Ward, Bed,
    Admission, Medicine, MedicineBatch, Prescription, PrescriptionItem,
    LabTestType, LabOrder, LabResult, Invoice, InvoiceItem, Notification, MedicalRecord,
    RoleEnum, GenderEnum, WardTypeEnum, BedStatusEnum, AdmissionStatusEnum,
    InvoiceStatusEnum, ItemTypeEnum, PrescriptionStatusEnum, LabOrderStatusEnum
)
from core.security import get_password_hash
from core.services.discharge_billing import process_inpatient_discharge_and_billing

def test_inpatient_discharge_auto_billing(db_session):
    """
    Tests the end-to-end inpatient discharge and automated itemized billing engine:
    - Verifies bed length-of-stay charges
    - Verifies pharmacy medication consolidation
    - Verifies diagnostic lab test consolidation
    - Verifies 5% healthcare tax calculation
    - Verifies bed transition to MAINTENANCE
    - Verifies automated notification dispatch
    """
    # 1. Setup Doctor & Patient
    doc_user = User(
        email="dr_discharge@medicare.ai",
        password_hash=get_password_hash("Pass123!"),
        role=RoleEnum.DOCTOR,
        first_name="Arthur",
        last_name="Conan"
    )
    pat_user = User(
        email="patient_discharge@medicare.ai",
        password_hash=get_password_hash("Pass123!"),
        role=RoleEnum.PATIENT,
        first_name="Robert",
        last_name="Langdon"
    )
    db_session.add_all([doc_user, pat_user])
    db_session.flush()

    dept = Department(name="General Medicine", code="GMED")
    db_session.add(dept)
    db_session.flush()

    doc_prof = DoctorProfile(
        user_id=doc_user.id,
        department_id=dept.id,
        specialization="Internal Medicine",
        license_number="LIC-DISC-01",
        consultation_fee=Decimal("500.00"),
        qualification="MBBS, MD"
    )
    pat_prof = PatientProfile(
        user_id=pat_user.id,
        dob=date(1980, 5, 20),
        gender=GenderEnum.MALE,
        blood_group="O+"
    )
    db_session.add_all([doc_prof, pat_prof])
    db_session.flush()

    # 2. Setup Ward & Bed
    ward = Ward(name="Recovery Ward A", ward_type=WardTypeEnum.GENERAL, floor=2, department_id=dept.id, total_beds=5)
    db_session.add(ward)
    db_session.flush()

    bed = Bed(ward_id=ward.id, bed_number="REC-201", status=BedStatusEnum.OCCUPIED, daily_rate=Decimal("1200.00"))
    db_session.add(bed)
    db_session.flush()

    # 3. Setup Admission 3 days ago
    admission_time = datetime.now(timezone.utc) - timedelta(days=3)
    admission = Admission(
        patient_id=pat_prof.user_id,
        admitting_doctor_id=doc_prof.user_id,
        bed_id=bed.id,
        admission_date=admission_time,
        status=AdmissionStatusEnum.ADMITTED,
        admission_reason="Severe acute gastroenteritis with dehydration"
    )
    db_session.add(admission)
    db_session.flush()

    # 4. Setup Medical Record and Dispensed Medicine during stay
    med = Medicine(
        name="Ciprofloxacin 500mg",
        generic_name="Ciprofloxacin",
        category="Antibiotic",
        unit="Tablet",
        unit_price=Decimal("25.00"),
        reorder_level=20
    )
    db_session.add(med)
    db_session.flush()

    record = MedicalRecord(
        patient_id=pat_prof.user_id,
        doctor_id=doc_prof.user_id,
        visit_date=admission_time.date(),
        symptoms="Acute abdominal cramps and nausea",
        diagnosis="Acute Gastroenteritis"
    )
    db_session.add(record)
    db_session.flush()

    rx = Prescription(
        medical_record_id=record.id,
        patient_id=pat_prof.user_id,
        doctor_id=doc_prof.user_id,
        status=PrescriptionStatusEnum.DISPENSED,
        created_at=admission_time + timedelta(hours=2)
    )
    db_session.add(rx)
    db_session.flush()

    rx_item = PrescriptionItem(
        prescription_id=rx.id,
        medicine_id=med.id,
        dosage="500mg",
        frequency="1-0-1",
        duration_days=5,
        quantity_prescribed=10,
        quantity_dispensed=10 # 10 * 25 = 250.00
    )
    db_session.add(rx_item)

    # 5. Setup Completed Lab Test during stay
    lab_test = LabTestType(
        name="Complete Blood Count",
        test_code="CBC-DISC",
        department_id=dept.id,
        sample_type="Whole Blood",
        unit="cells/mcL",
        cost=Decimal("450.00")
    )
    db_session.add(lab_test)
    db_session.flush()

    lab_order = LabOrder(
        patient_id=pat_prof.user_id,
        doctor_id=doc_prof.user_id,
        test_type_id=lab_test.id,
        status=LabOrderStatusEnum.COMPLETED,
        ordered_at=admission_time + timedelta(hours=4)
    )
    db_session.add(lab_order)
    db_session.flush()

    # 6. Execute Discharge & Auto-Billing
    adm_result, invoice = process_inpatient_discharge_and_billing(
        admission_id=admission.id,
        discharge_summary="Patient fully stabilized and rehydrated. Discharge approved.",
        db=db_session,
        actor_id=doc_user.id
    )
    db_session.commit()

    # 7. Verification Assertions
    # Status & Dates
    assert adm_result.status == AdmissionStatusEnum.DISCHARGED
    assert adm_result.discharge_date is not None
    assert "fully stabilized" in adm_result.discharge_summary
    assert bed.status == BedStatusEnum.MAINTENANCE

    # Invoice verification
    assert invoice is not None
    assert invoice.patient_id == pat_prof.user_id
    assert invoice.status == InvoiceStatusEnum.UNPAID
    
    # Stay days = 3 days * $1200 = $3600.00
    # Meds = 10 * $25 = $250.00
    # Lab test = $450.00
    # Subtotal = 3600 + 250 + 450 = $4300.00
    # Tax (5%) = 4300 * 0.05 = $215.00
    # Total Amount = $4515.00
    assert float(invoice.subtotal) == pytest.approx(4300.00, 0.01)
    assert float(invoice.tax) == pytest.approx(215.00, 0.01)
    assert float(invoice.total_amount) == pytest.approx(4515.00, 0.01)

    # Check itemized breakdown
    items = db_session.query(InvoiceItem).filter(InvoiceItem.invoice_id == invoice.id).all()
    item_types = [item.item_type for item in items]
    assert ItemTypeEnum.BED_CHARGE in item_types
    assert ItemTypeEnum.PHARMACY in item_types
    assert ItemTypeEnum.LAB_TEST in item_types

    # Check notification sent to patient
    notifs = db_session.query(Notification).filter(Notification.user_id == pat_user.id).all()
    assert len(notifs) >= 1
    assert "Discharge Clearance Completed" in notifs[0].title
