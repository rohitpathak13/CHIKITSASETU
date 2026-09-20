"""
Unit tests for Hospital Analytics & BI calculation accuracy and resilience.
Tests calculation formulas, edge cases, and empty datasets across all 15 domains.
"""

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import pytest

from core.models import (
    User, Patient, Doctor, Department,
    Appointment, AppointmentStatusEnum,
    MedicalRecord, Diagnosis,
    Room, Bed, Admission, RoomTypeEnum, BedStatusEnum, AdmissionStatusEnum,
    Bill, BillItem, Payment, ItemTypeEnum, BillStatusEnum, PaymentMethodEnum,
    LabTest, LabOrder, LabResult, LabOrderStatusEnum,
    Medicine, MedicineInventory, StockTransaction,
    RoleEnum, GenderEnum
)
from core.services.analytics_service import (
    get_patient_growth_data,
    get_appointment_trends_data,
    get_department_statistics_data,
    get_doctor_workload_data,
    get_disease_distribution_data,
    get_age_distribution_data,
    get_gender_distribution_data,
    get_admission_trends_data,
    get_discharge_trends_data,
    get_bed_occupancy_data,
    get_revenue_trends_data,
    get_lab_test_trends_data,
    get_pharmacy_inventory_data,
    get_appointment_cancellation_data,
    get_appointment_no_show_data,
    get_hospital_analytics_summary
)
from ml.analytics.plotly_charts import (
    build_patient_growth_chart,
    build_appointment_trends_chart,
    build_department_stats_chart,
    build_doctor_workload_chart,
    build_disease_distribution_chart,
    build_age_distribution_chart,
    build_gender_distribution_chart,
    build_admission_trends_chart,
    build_discharge_trends_chart,
    build_bed_occupancy_gauge,
    build_ward_breakdown_bar,
    build_revenue_trends_chart,
    build_revenue_donut_chart,
    build_lab_trends_chart,
    build_pharmacy_inventory_chart,
    build_cancellation_chart,
    build_no_show_chart,
    build_patient_census_trend
)


# ===========================================================================
# 1. Empty Dataset Resilience Tests
# ===========================================================================

def test_empty_database_safety(db_session):
    """
    Verifies that all 15 analytics functions execute safely without errors
    when queried against completely empty database tables.
    """
    # 1. Patient growth
    pg = get_patient_growth_data(db_session)
    assert pg["total_registered"] == 0
    assert pg["dates"] == []

    # 2. Appointment trends
    at = get_appointment_trends_data(db_session)
    assert at["summary"]["total"] == 0
    assert at["dates"] == []

    # 3. Department statistics
    ds = get_department_statistics_data(db_session)
    assert ds["departments"] == []

    # 4. Doctor workload
    dw = get_doctor_workload_data(db_session)
    assert dw["doctors"] == []

    # 5. Disease distribution
    dd = get_disease_distribution_data(db_session)
    assert dd["total_diagnoses"] == 0
    assert dd["labels"] == []

    # 6. Age distribution
    ad = get_age_distribution_data(db_session)
    assert ad["total"] == 0
    assert sum(ad["counts"]) == 0
    assert ad["avg_age"] == 0.0

    # 7. Gender distribution
    gd = get_gender_distribution_data(db_session)
    assert gd["total"] == 0
    assert sum(gd["counts"]) == 0

    # 8. Admission trends
    adm = get_admission_trends_data(db_session)
    assert adm["total_admissions"] == 0
    assert adm["dates"] == []

    # 9. Discharge trends
    dis = get_discharge_trends_data(db_session)
    assert dis["total_discharges"] == 0
    assert dis["avg_los_days"] == 0.0

    # 10. Bed occupancy
    bo = get_bed_occupancy_data(db_session)
    assert bo["total_beds"] == 0
    assert bo["occupancy_rate"] == 0.0
    assert bo["ward_breakdown"] == []

    # 11. Revenue trends
    rt = get_revenue_trends_data(db_session)
    assert rt["summary"]["total_billed"] == 0.0
    assert rt["summary"]["total_collected"] == 0.0
    assert rt["summary"]["total_balance"] == 0.0

    # 12. Lab test trends
    lt = get_lab_test_trends_data(db_session)
    assert lt["total_orders"] == 0
    assert lt["abnormal_rate"] == 0.0

    # 13. Pharmacy inventory
    pi = get_pharmacy_inventory_data(db_session)
    assert pi["total_skus"] == 0
    assert pi["total_valuation"] == 0.0

    # 14. Appointment cancellation
    ac = get_appointment_cancellation_data(db_session)
    assert ac["total_appointments"] == 0
    assert ac["cancellation_rate"] == 0.0

    # 15. Appointment no-show
    ans = get_appointment_no_show_data(db_session)
    assert ans["total_appointments"] == 0
    assert ans["no_show_rate"] == 0.0

    # Master summary
    summary = get_hospital_analytics_summary(db_session)
    assert summary["total_patients"] == 0
    assert summary["bed_occupancy_rate"] == 0.0
    assert summary["total_billed_revenue"] == 0.0


def test_empty_plotly_chart_builders():
    """
    Verifies that all 15 Plotly chart builders serialize valid JSON strings
    when supplied with empty data structures.
    """
    charts = [
        build_patient_growth_chart({}),
        build_appointment_trends_chart({}),
        build_department_stats_chart({}),
        build_doctor_workload_chart({}),
        build_disease_distribution_chart({}),
        build_age_distribution_chart({}),
        build_gender_distribution_chart({}),
        build_admission_trends_chart({}),
        build_discharge_trends_chart({}),
        build_bed_occupancy_gauge(0.0),
        build_ward_breakdown_bar([]),
        build_revenue_trends_chart({}),
        build_revenue_donut_chart({}),
        build_lab_trends_chart({}),
        build_pharmacy_inventory_chart({}),
        build_cancellation_chart({}),
        build_no_show_chart({}),
        build_patient_census_trend({}, {})
    ]

    for c in charts:
        assert isinstance(c, str)
        parsed = json.loads(c)
        assert "data" in parsed
        assert "layout" in parsed


# ===========================================================================
# 2. Calculation Accuracy Tests on Seeded Clinical Data
# ===========================================================================

def test_patient_demographics_and_growth_accuracy(db_session):
    """
    Tests patient growth cumulative curve, age cohort bucketing, and gender ratios.
    """
    today = date.today()
    # Create 3 patients of known ages and genders
    # Patient 1: 8 years old (Pediatric), Male
    u1 = User(email="p1@medicare.ai", password_hash="hash", role=RoleEnum.PATIENT, first_name="Child", last_name="One")
    db_session.add(u1)
    db_session.flush()
    p1 = Patient(id=u1.id, dob=today - timedelta(days=8 * 365 + 2), gender=GenderEnum.MALE)
    p1.created_at = datetime.now(timezone.utc) - timedelta(days=2)
    db_session.add(p1)

    # Patient 2: 25 years old (Young Adult), Female
    u2 = User(email="p2@medicare.ai", password_hash="hash", role=RoleEnum.PATIENT, first_name="Adult", last_name="Two")
    db_session.add(u2)
    db_session.flush()
    p2 = Patient(id=u2.id, dob=today - timedelta(days=25 * 365 + 6), gender=GenderEnum.FEMALE)
    p2.created_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.add(p2)

    # Patient 3: 70 years old (Senior), Female
    u3 = User(email="p3@medicare.ai", password_hash="hash", role=RoleEnum.PATIENT, first_name="Senior", last_name="Three")
    db_session.add(u3)
    db_session.flush()
    p3 = Patient(id=u3.id, dob=today - timedelta(days=70 * 365 + 17), gender=GenderEnum.FEMALE)
    p3.created_at = datetime.now(timezone.utc)
    db_session.add(p3)

    db_session.commit()

    # Verify Patient Growth
    growth = get_patient_growth_data(db_session, days=30)
    assert growth["total_registered"] == 3
    assert growth["cumulative_patients"][-1] == 3

    # Verify Age Distribution
    age_data = get_age_distribution_data(db_session)
    assert age_data["total"] == 3
    cohorts_map = dict(zip(age_data["cohorts"], age_data["counts"]))
    assert cohorts_map["0-12 (Pediatric)"] == 1
    assert cohorts_map["20-39 (Young Adult)"] == 1
    assert cohorts_map["60+ (Senior)"] == 1
    assert cohorts_map["40-59 (Middle Age)"] == 0
    # Average age approx (8 + 25 + 70)/3 = 34.3
    assert 33.0 <= age_data["avg_age"] <= 36.0

    # Verify Gender Distribution
    gender_data = get_gender_distribution_data(db_session)
    assert gender_data["total"] == 3
    labels_map = dict(zip(gender_data["labels"], gender_data["counts"]))
    assert labels_map["Male"] == 1
    assert labels_map["Female"] == 2
    assert labels_map["Other"] == 0
    assert gender_data["percentages"][1] == round((2 / 3) * 100, 1)  # 66.7%


def test_appointment_cancellation_and_no_show_accuracy(db_session):
    """
    Tests appointment status breakdowns, cancellation rate %, no-show rate %, and ML risk buckets.
    """
    # Create doctor and patient
    u_doc = User(email="doc@medicare.ai", password_hash="hash", role=RoleEnum.DOCTOR, first_name="Dev", last_name="Doc")
    u_pat = User(email="pat@medicare.ai", password_hash="hash", role=RoleEnum.PATIENT, first_name="Pat", last_name="One")
    db_session.add_all([u_doc, u_pat])
    db_session.flush()

    doc = Doctor(id=u_doc.id, specialization="General Medicine", license_number="LIC-AN-01", qualification="MD")
    pat = Patient(id=u_pat.id, dob=date(1990, 1, 1), gender=GenderEnum.MALE)
    db_session.add_all([doc, pat])
    db_session.flush()

    # 4 appointments:
    # 1 Completed, 1 Scheduled, 1 Cancelled, 1 No-Show
    now = datetime.now(timezone.utc)
    a1 = Appointment(patient_id=pat.id, doctor_id=doc.id, appointment_datetime=now, status=AppointmentStatusEnum.COMPLETED, no_show_probability=0.05)
    a2 = Appointment(patient_id=pat.id, doctor_id=doc.id, appointment_datetime=now, status=AppointmentStatusEnum.SCHEDULED, no_show_probability=0.25)
    a3 = Appointment(patient_id=pat.id, doctor_id=doc.id, appointment_datetime=now, status=AppointmentStatusEnum.CANCELLED, no_show_probability=0.30)
    a4 = Appointment(patient_id=pat.id, doctor_id=doc.id, appointment_datetime=now, status=AppointmentStatusEnum.NO_SHOW, no_show_probability=0.85)

    db_session.add_all([a1, a2, a3, a4])
    db_session.commit()

    # Verify Appointment Trends
    at = get_appointment_trends_data(db_session, days=30)
    assert at["summary"]["total"] == 4
    assert at["summary"]["completed"] == 1
    assert at["summary"]["scheduled"] == 1
    assert at["summary"]["cancelled"] == 1
    assert at["summary"]["no_show"] == 1

    # Verify Cancellation
    cancel_data = get_appointment_cancellation_data(db_session, days=30)
    assert cancel_data["total_appointments"] == 4
    assert cancel_data["cancelled_count"] == 1
    assert cancel_data["cancellation_rate"] == 25.0  # (1 / 4) * 100

    # Verify No-Show
    no_show_data = get_appointment_no_show_data(db_session, days=30)
    assert no_show_data["total_appointments"] == 4
    assert no_show_data["no_show_count"] == 1
    assert no_show_data["no_show_rate"] == 25.0  # (1 / 4) * 100
    # Mean risk = (0.05 + 0.25 + 0.30 + 0.85) / 4 = 1.45 / 4 = 0.3625 -> 36.2%
    assert 35.0 <= no_show_data["avg_no_show_prob"] <= 37.0
    assert no_show_data["risk_buckets"]["Low Risk (<20%)"] == 1
    assert no_show_data["risk_buckets"]["Medium Risk (20-50%)"] == 2
    assert no_show_data["risk_buckets"]["High Risk (>50%)"] == 1


def test_bed_occupancy_and_inpatient_trends_accuracy(db_session):
    """
    Tests hospital bed occupancy percentage: (occupied / total) * 100, ward breakdown,
    admission trends, and average length of stay (LOS).
    """
    # Create room and 4 beds
    room = Room(room_number="ICU-101", room_type=RoomTypeEnum.ICU, floor=1, total_beds=4, daily_rate=Decimal("2500.00"))
    db_session.add(room)
    db_session.flush()

    b1 = Bed(room_id=room.id, bed_number="ICU-101-A", status=BedStatusEnum.OCCUPIED)
    b2 = Bed(room_id=room.id, bed_number="ICU-101-B", status=BedStatusEnum.AVAILABLE)
    b3 = Bed(room_id=room.id, bed_number="ICU-101-C", status=BedStatusEnum.AVAILABLE)
    b4 = Bed(room_id=room.id, bed_number="ICU-101-D", status=BedStatusEnum.MAINTENANCE)
    db_session.add_all([b1, b2, b3, b4])
    db_session.flush()

    # Occupancy: 1 occupied out of 4 total = 25.0%
    bo = get_bed_occupancy_data(db_session)
    assert bo["total_beds"] == 4
    assert bo["occupied_beds"] == 1
    assert bo["available_beds"] == 2
    assert bo["maintenance_beds"] == 1
    assert bo["occupancy_rate"] == 25.0
    assert len(bo["ward_breakdown"]) == 1
    assert bo["ward_breakdown"][0]["occupancy_rate"] == 25.0

    # Inpatient Admissions & Discharges
    u_pat = User(email="ipd_pat@medicare.ai", password_hash="hash", role=RoleEnum.PATIENT, first_name="Inpatient", last_name="User")
    u_doc = User(email="ipd_doc@medicare.ai", password_hash="hash", role=RoleEnum.DOCTOR, first_name="Dr", last_name="Surgeon")
    db_session.add_all([u_pat, u_doc])
    db_session.flush()
    pat = Patient(id=u_pat.id, dob=date(1985, 5, 5), gender=GenderEnum.FEMALE)
    doc = Doctor(id=u_doc.id, specialization="Cardiology", license_number="LIC-SUR-01", qualification="MS")
    db_session.add_all([pat, doc])
    db_session.flush()

    now = datetime.now(timezone.utc)
    # Admission 1: admitted 5 days ago, discharged today (LOS = 5 days)
    adm1 = Admission(
        patient_id=pat.id, admitting_doctor_id=doc.id, bed_id=b1.id,
        admission_date=now - timedelta(days=5),
        discharge_date=now,
        status=AdmissionStatusEnum.DISCHARGED,
        admission_reason="Cardiac Monitoring"
    )
    # Admission 2: active admission
    adm2 = Admission(
        patient_id=pat.id, admitting_doctor_id=doc.id, bed_id=b2.id,
        admission_date=now - timedelta(days=1),
        status=AdmissionStatusEnum.ADMITTED,
        admission_reason="Post-op Recovery"
    )
    db_session.add_all([adm1, adm2])
    db_session.commit()

    adm_data = get_admission_trends_data(db_session, days=30)
    assert adm_data["total_admissions"] == 2

    dis_data = get_discharge_trends_data(db_session, days=30)
    assert dis_data["total_discharges"] == 1
    assert dis_data["avg_los_days"] == 5.0


def test_revenue_trends_and_cost_centers_accuracy(db_session):
    """
    Tests revenue metrics: total billed, cash collected, outstanding balance, and 7-component breakdown.
    """
    u_pat = User(email="rev_pat@medicare.ai", password_hash="hash", role=RoleEnum.PATIENT, first_name="Rev", last_name="Client")
    db_session.add(u_pat)
    db_session.flush()
    pat = Patient(id=u_pat.id, dob=date(1992, 1, 1), gender=GenderEnum.MALE)
    db_session.add(pat)
    db_session.flush()

    # Bill with Consultation ($500) + Medicines ($250) + Lab ($150) = Subtotal $900
    bill = Bill(
        invoice_number="INV-20260919-TEST",
        patient_id=pat.id,
        subtotal=Decimal("900.00"),
        tax=Decimal("45.00"),
        discount=Decimal("0.00"),
        total_amount=Decimal("945.00"),
        status=BillStatusEnum.PARTIAL
    )
    db_session.add(bill)
    db_session.flush()

    item1 = BillItem(bill_id=bill.id, item_type=ItemTypeEnum.CONSULTATION, description="OPD Visit", quantity=1, unit_price=Decimal("500.00"), subtotal=Decimal("500.00"))
    item2 = BillItem(bill_id=bill.id, item_type=ItemTypeEnum.MEDICINES, description="Antibiotics", quantity=1, unit_price=Decimal("250.00"), subtotal=Decimal("250.00"))
    item3 = BillItem(bill_id=bill.id, item_type=ItemTypeEnum.LABORATORY, description="Blood Profile", quantity=1, unit_price=Decimal("150.00"), subtotal=Decimal("150.00"))
    db_session.add_all([item1, item2, item3])

    # Payment 1: $500 cash collected
    p1 = Payment(bill_id=bill.id, amount=Decimal("500.00"), payment_method=PaymentMethodEnum.CASH, transaction_reference="TXN-001", is_refund=False)
    # Payment 2: $50 partial refund issued
    p2 = Payment(bill_id=bill.id, amount=Decimal("50.00"), payment_method=PaymentMethodEnum.CASH, transaction_reference="REF-001", is_refund=True)
    db_session.add_all([p1, p2])
    db_session.commit()

    rev_data = get_revenue_trends_data(db_session, days=30)
    assert rev_data["summary"]["total_billed"] == 945.00
    # Net collected = $500 - $50 = $450.00
    assert rev_data["summary"]["total_collected"] == 450.00
    assert rev_data["summary"]["total_balance"] == 495.00  # 945 - 450
    # Collection rate = (450 / 945) * 100 = 47.6%
    assert 47.0 <= rev_data["summary"]["collection_rate"] <= 48.0

    # Category breakdown verification
    assert rev_data["categories"]["Consultation"] == 500.00
    assert rev_data["categories"]["Medicines"] == 250.00
    assert rev_data["categories"]["Laboratory"] == 150.00


def test_pharmacy_and_laboratory_analytics_accuracy(db_session):
    """
    Tests pharmacy inventory valuation ($ sum of batch qty * purchase_cost),
    low stock alerts, expiring batches, and lab test abnormality rate.
    """
    # 1. Pharmacy setup
    med1 = Medicine(name="Amoxicillin 500mg", category="Antibiotic", unit="Capsule", unit_price=Decimal("10.00"), reorder_level=50)
    med2 = Medicine(name="Paracetamol 650mg", category="Analgesic", unit="Tablet", unit_price=Decimal("2.00"), reorder_level=20)
    db_session.add_all([med1, med2])
    db_session.flush()

    today = date.today()
    # Batch 1 for med1: 30 units (Low stock alert since 30 <= 50), cost $5.00 each -> $150
    b1 = MedicineInventory(
        medicine_id=med1.id, batch_number="BAT-001",
        quantity_in_stock=30, purchase_cost=Decimal("5.00"),
        expiry_date=today + timedelta(days=15)  # Expiring soon (<30 days)
    )
    # Batch 2 for med2: 100 units, cost $1.00 each -> $100
    b2 = MedicineInventory(
        medicine_id=med2.id, batch_number="BAT-002",
        quantity_in_stock=100, purchase_cost=Decimal("1.00"),
        expiry_date=today + timedelta(days=200)
    )
    db_session.add_all([b1, b2])

    # 2. Laboratory setup
    u_pat = User(email="lab_pat@medicare.ai", password_hash="hash", role=RoleEnum.PATIENT, first_name="Lab", last_name="Patient")
    u_doc = User(email="lab_doc@medicare.ai", password_hash="hash", role=RoleEnum.DOCTOR, first_name="Lab", last_name="Doctor")
    db_session.add_all([u_pat, u_doc])
    db_session.flush()
    pat = Patient(id=u_pat.id, dob=date(1990, 1, 1), gender=GenderEnum.FEMALE)
    doc = Doctor(id=u_doc.id, specialization="Pathology", license_number="LIC-LAB-01", qualification="MD")
    db_session.add_all([pat, doc])
    db_session.flush()

    test_cbc = LabTest(name="Complete Blood Count", test_code="CBC", sample_type="Blood", cost=Decimal("350.00"))
    db_session.add(test_cbc)
    db_session.flush()

    # Order 1: Normal result
    ord1 = LabOrder(patient_id=pat.id, doctor_id=doc.id, test_id=test_cbc.id, status=LabOrderStatusEnum.COMPLETED)
    db_session.add(ord1)
    db_session.flush()
    res1 = LabResult(lab_order_id=ord1.id, measured_value=14.5, unit="g/dL", is_abnormal=False)
    db_session.add(res1)

    # Order 2: Abnormal result
    ord2 = LabOrder(patient_id=pat.id, doctor_id=doc.id, test_id=test_cbc.id, status=LabOrderStatusEnum.COMPLETED)
    db_session.add(ord2)
    db_session.flush()
    res2 = LabResult(lab_order_id=ord2.id, measured_value=8.2, unit="g/dL", is_abnormal=True)
    db_session.add(res2)

    db_session.commit()

    # Verify Pharmacy
    pharm_data = get_pharmacy_inventory_data(db_session)
    assert pharm_data["total_skus"] == 2
    assert pharm_data["total_stock_units"] == 130  # 30 + 100
    assert pharm_data["total_valuation"] == 250.00  # (30 * 5) + (100 * 1) = 150 + 100
    assert pharm_data["low_stock_count"] == 1       # Med 1 is low stock
    assert pharm_data["expiring_soon_count"] == 1   # Batch 1 expires in 15 days

    # Verify Lab
    lab_data = get_lab_test_trends_data(db_session, days=30)
    assert lab_data["total_orders"] == 2
    assert lab_data["abnormal_count"] == 1
    assert lab_data["normal_count"] == 1
    assert lab_data["abnormal_rate"] == 50.0  # 1 out of 2 abnormal
    assert "Complete Blood Count" in lab_data["top_tests"]
