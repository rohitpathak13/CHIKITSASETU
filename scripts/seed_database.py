import os
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal

# Ensure database models are registered
from core.database import init_db, SessionLocal
from core.models import (
    Role, User, Doctor, Patient, Staff,
    DoctorProfile, PatientProfile, StaffProfile,
    RoleEnum, GenderEnum,
    Department, Appointment, MedicalRecord, Diagnosis, AppointmentStatusEnum,
    Medicine, MedicineInventory, MedicineBatch, Prescription, PrescriptionItem, PrescriptionStatusEnum,
    LabTest, LabTestType, LabOrder, LabResult, LabOrderStatusEnum,
    Room, Ward, Bed, Admission, RoomTypeEnum, WardTypeEnum, BedStatusEnum, AdmissionStatusEnum,
    Insurance, Bill, BillItem, Invoice, InvoiceItem, Payment,
    BillStatusEnum, InvoiceStatusEnum, ItemTypeEnum, PaymentMethodEnum,
    AuditLog, Notification, NotificationTypeEnum
)
from core.security import get_password_hash


def seed():
    print("[*] Initializing database tables...")
    init_db()
    db = SessionLocal()

    # Clear existing records in reverse dependency order
    print("[*] Cleaning previous data...")
    for model in [
        AuditLog, Notification, Payment, BillItem, Bill,
        Admission, LabResult, LabOrder, PrescriptionItem, Prescription,
        Diagnosis, MedicalRecord, Appointment,
        Bed, Room, MedicineInventory, Medicine, LabTest,
        Staff, Patient, Doctor, Insurance, Department,
        User, Role
    ]:
        try:
            db.query(model).delete()
        except Exception:
            pass
    db.commit()

    print("[*] Seeding System Roles...")
    roles_data = [
        (RoleEnum.ADMIN.value, "Administrator with complete system, user, and configuration access."),
        (RoleEnum.DOCTOR.value, "Licensed physician responsible for consultations, EMR, prescriptions, and diagnostics."),
        (RoleEnum.PATIENT.value, "Healthcare recipient accessing appointments, medical records, and invoices."),
        (RoleEnum.RECEPTIONIST.value, "Front-desk personnel managing outpatient registrations and bed inquiries."),
        (RoleEnum.NURSE.value, "Registered nurse charting vitals, bed assignments, and patient care rounds."),
        (RoleEnum.PHARMACIST.value, "Pharmacy specialist dispensing medications and managing batch stock."),
        (RoleEnum.LAB_TECH.value, "Laboratory pathologist processing clinical specimens and diagnostic orders.")
    ]
    role_map = {}
    for r_name, r_desc in roles_data:
        r_obj = Role(name=r_name, description=r_desc)
        db.add(r_obj)
        db.flush()
        role_map[r_name] = r_obj

    print("[*] Seeding System Users & Profiles...")
    password_hash = get_password_hash("Password123!")

    # 1. Admin
    admin_user = User(
        email="admin@medicare.ai",
        password_hash=password_hash,
        role=RoleEnum.ADMIN,
        role_id=role_map[RoleEnum.ADMIN.value].id,
        first_name="Arthur",
        last_name="Vance",
        phone="+1-555-0100",
        is_active=True
    )
    db.add(admin_user)
    db.flush()

    # 2. Clinical Departments
    dept_cardio = Department(name="Cardiology", code="CARD", description="Comprehensive cardiovascular clinical services.")
    dept_neuro = Department(name="Neurology", code="NEUR", description="Advanced neurological and spine disorders.")
    dept_peds = Department(name="Pediatrics", code="PED", description="Child health and pediatric intensive care.")
    dept_ortho = Department(name="Orthopedics", code="ORTH", description="Musculoskeletal surgery, trauma, and joint replacement.")
    dept_gen = Department(name="General Medicine", code="GEN", description="Internal medicine and acute outpatient consultations.")
    db.add_all([dept_cardio, dept_neuro, dept_peds, dept_ortho, dept_gen])
    db.flush()

    # 3. Doctors
    doctors_data = [
        ("dr.sharma@medicare.ai", "Rajesh", "Sharma", dept_cardio.id, "Interventional Cardiology", "MD, DM (Cardio)", "LIC-CARD-9081", "Room 101", 800.00),
        ("dr.chen@medicare.ai", "Mei", "Chen", dept_neuro.id, "Neurology & Stroke", "MD, DNB (Neuro)", "LIC-NEUR-4421", "Room 102", 900.00),
        ("dr.patel@medicare.ai", "Ananya", "Patel", dept_peds.id, "Pediatric Critical Care", "MBBS, MD (Peds)", "LIC-PEDS-3129", "Room 103", 600.00),
        ("dr.adams@medicare.ai", "Robert", "Adams", dept_ortho.id, "Orthopedic & Trauma Surgery", "MS (Ortho), FRCS", "LIC-ORTH-7712", "Room 104", 750.00),
        ("dr.smith@medicare.ai", "Emily", "Smith", dept_gen.id, "Internal Medicine", "MD (Internal Med)", "LIC-GEN-1029", "Room 105", 500.00),
    ]

    doctor_objs = []
    for email, fn, ln, dept_id, spec, qual, lic, room, fee in doctors_data:
        doc_user = User(
            email=email,
            password_hash=password_hash,
            role=RoleEnum.DOCTOR,
            role_id=role_map[RoleEnum.DOCTOR.value].id,
            first_name=fn,
            last_name=ln,
            phone="+1-555-020" + str(len(doctor_objs)),
            is_active=True
        )
        db.add(doc_user)
        db.flush()

        doc_profile = Doctor(
            id=doc_user.id,
            department_id=dept_id,
            specialization=spec,
            qualification=qual,
            license_number=lic,
            room_number=room,
            consultation_fee=Decimal(str(fee))
        )
        db.add(doc_profile)
        doctor_objs.append((doc_user, doc_profile))
    db.flush()

    # Set Head of Departments
    dept_cardio.head_doctor_id = doctor_objs[0][0].id
    dept_neuro.head_doctor_id = doctor_objs[1][0].id
    dept_peds.head_doctor_id = doctor_objs[2][0].id
    dept_ortho.head_doctor_id = doctor_objs[3][0].id
    dept_gen.head_doctor_id = doctor_objs[4][0].id
    db.flush()

    # 4. Staff (Receptionist, Nurses, Pharmacist, Lab Tech)
    staff_data = [
        ("reception@medicare.ai", "Elena", "Rostova", RoleEnum.RECEPTIONIST, "EMP-REC-01", "Chief Receptionist & Registrar", dept_gen.id),
        ("nurse.mary@medicare.ai", "Mary", "Watson", RoleEnum.NURSE, "EMP-NUR-01", "ICU Charge Nurse", dept_cardio.id),
        ("nurse.david@medicare.ai", "David", "Kim", RoleEnum.NURSE, "EMP-NUR-02", "Inpatient Floor Nurse", dept_gen.id),
        ("pharmacy@medicare.ai", "James", "Wilson", RoleEnum.PHARMACIST, "EMP-PHAR-01", "Supervising Hospital Pharmacist", None),
        ("lab@medicare.ai", "Rachel", "Green", RoleEnum.LAB_TECH, "EMP-LAB-01", "Chief Diagnostic Pathologist", None),
    ]

    staff_objs = {}
    for email, fn, ln, role, emp_id, desig, d_id in staff_data:
        s_user = User(
            email=email,
            password_hash=password_hash,
            role=role,
            role_id=role_map[role.value].id,
            first_name=fn,
            last_name=ln,
            phone="+1-555-030" + str(len(staff_objs)),
            is_active=True
        )
        db.add(s_user)
        db.flush()

        s_profile = Staff(
            id=s_user.id,
            department_id=d_id,
            employee_id=emp_id,
            designation=desig,
            shift="Rotating"
        )
        db.add(s_profile)
        staff_objs[role] = s_user
    db.flush()

    # 5. Patients & Insurances
    patients_raw = [
        ("john.doe@example.com", "John", "Doe", date(1968, 5, 14), GenderEnum.MALE, "O+", "Jane Doe", "+1-555-9011", "42 Elm St, Springfield", "Penicillin", "Type 2 Diabetes, Hypertension"),
        ("sarah.jenkins@example.com", "Sarah", "Jenkins", date(1985, 11, 23), GenderEnum.FEMALE, "A+", "Tom Jenkins", "+1-555-9012", "18 Maple Ave, Springfield", "Sulfa drugs", "Mild Asthma"),
        ("raj.kumar@example.com", "Raj", "Kumar", date(1974, 3, 8), GenderEnum.MALE, "B+", "Priya Kumar", "+1-555-9013", "73 Pine St, Springfield", None, "Coronary Artery Disease"),
        ("emily.clark@example.com", "Emily", "Clark", date(2002, 8, 30), GenderEnum.FEMALE, "AB+", "Laura Clark", "+1-555-9014", "92 Oak Lane, Springfield", "Aspirin", None),
        ("michael.brown@example.com", "Michael", "Brown", date(1955, 1, 19), GenderEnum.MALE, "O-", "Grace Brown", "+1-555-9015", "101 Cedar Blvd, Springfield", None, "Congestive Heart Failure, CKD"),
    ]

    patient_objs = []
    for email, fn, ln, dob, gender, blood, ec_name, ec_phone, addr, allergies, chronic in patients_raw:
        p_user = User(
            email=email,
            password_hash=password_hash,
            role=RoleEnum.PATIENT,
            role_id=role_map[RoleEnum.PATIENT.value].id,
            first_name=fn,
            last_name=ln,
            phone="+1-555-040" + str(len(patient_objs)),
            is_active=True
        )
        db.add(p_user)
        db.flush()

        p_profile = Patient(
            id=p_user.id,
            dob=dob,
            gender=gender,
            blood_group=blood,
            emergency_contact_name=ec_name,
            emergency_contact_phone=ec_phone,
            address=addr,
            allergies=allergies,
            chronic_conditions=chronic
        )
        db.add(p_profile)
        patient_objs.append((p_user, p_profile))
    db.flush()

    # Seed Health Insurance Policies
    ins1 = Insurance(
        policy_number="POL-STAR-782109",
        provider_name="Star Health Allied Insurance",
        policy_type="Comprehensive Health Shield",
        coverage_amount=Decimal("500000.00"),
        valid_until=date.today() + timedelta(days=365),
        patient_id=patient_objs[0][0].id,
        status="Active"
    )
    ins2 = Insurance(
        policy_number="POL-BLUE-441920",
        provider_name="Blue Cross Senior Platinum",
        policy_type="Critical Illness & Senior Care",
        coverage_amount=Decimal("1000000.00"),
        valid_until=date.today() + timedelta(days=280),
        patient_id=patient_objs[4][0].id,
        status="Active"
    )
    ins3 = Insurance(
        policy_number="POL-NAT-990142",
        provider_name="National Health Care Corp",
        policy_type="Standard Family Floater",
        coverage_amount=Decimal("300000.00"),
        valid_until=date.today() + timedelta(days=190),
        patient_id=patient_objs[1][0].id,
        status="Active"
    )
    db.add_all([ins1, ins2, ins3])
    db.flush()

    # Link insurance back to patients
    patient_objs[0][1].insurance_id = ins1.id
    patient_objs[4][1].insurance_id = ins2.id
    patient_objs[1][1].insurance_id = ins3.id
    db.flush()

    # 6. Inpatient Rooms and Beds
    rooms_data = [
        ("Intensive Care Unit (ICU)", RoomTypeEnum.ICU, 3, dept_cardio.id, 6, Decimal("4500.00"), "ICU-"),
        ("General Ward - Male", RoomTypeEnum.GENERAL, 1, dept_gen.id, 8, Decimal("1200.00"), "GWM-"),
        ("General Ward - Female", RoomTypeEnum.GENERAL, 1, dept_gen.id, 8, Decimal("1200.00"), "GWF-"),
        ("Pediatric Care Unit", RoomTypeEnum.PEDIATRIC, 2, dept_peds.id, 6, Decimal("1800.00"), "PED-"),
        ("Emergency Trauma Ward", RoomTypeEnum.EMERGENCY, 0, dept_ortho.id, 4, Decimal("3000.00"), "ER-"),
    ]

    all_beds = []
    for r_name, r_type, floor, d_id, bed_count, rate, prefix in rooms_data:
        room = Room(
            room_number=r_name,
            room_type=r_type,
            floor=floor,
            department_id=d_id,
            total_beds=bed_count,
            daily_rate=rate
        )
        db.add(room)
        db.flush()

        for i in range(1, bed_count + 1):
            bed = Bed(
                room_id=room.id,
                bed_number=f"{prefix}{100 + i}",
                status=BedStatusEnum.AVAILABLE,
                daily_rate=rate
            )
            db.add(bed)
            all_beds.append(bed)
    db.flush()

    # 7. Pharmacy Formulary & Batch Inventory (FEFO)
    meds_data = [
        ("Amoxicillin 500mg", "Amoxicillin", "Antibiotic", "Capsule", Decimal("15.00"), 50, "Pfizer Labs"),
        ("Paracetamol 650mg", "Acetaminophen", "Antipyretic", "Tablet", Decimal("5.00"), 100, "GlaxoSmithKline"),
        ("Atorvastatin 20mg", "Atorvastatin", "Lipid-lowering", "Tablet", Decimal("22.50"), 30, "Sun Pharma"),
        ("Metformin 500mg", "Metformin HCl", "Antidiabetic", "Tablet", Decimal("8.00"), 40, "Cipla Healthcare"),
        ("Pantoprazole 40mg", "Pantoprazole", "Proton Pump Inhibitor", "Tablet", Decimal("12.00"), 40, "Dr. Reddy's"),
        ("Azithromycin 500mg", "Azithromycin", "Antibiotic", "Tablet", Decimal("35.00"), 25, "Lupin Ltd"),
        ("Ceftriaxone 1g Injection", "Ceftriaxone", "Cephalosporin", "Vial", Decimal("120.00"), 15, "Novartis"),
        ("Salbutamol Inhaler 100mcg", "Albuterol", "Bronchodilator", "Inhaler", Decimal("180.00"), 10, "Cipla"),
    ]

    med_objs = []
    for name, gen, cat, unit, price, reorder, mfr in meds_data:
        med = Medicine(
            name=name,
            generic_name=gen,
            category=cat,
            unit=unit,
            unit_price=price,
            reorder_level=reorder,
            manufacturer=mfr,
            description=f"Standard pharmaceutical grade {name}"
        )
        db.add(med)
        db.flush()

        batch1 = MedicineInventory(
            medicine_id=med.id,
            batch_number=f"BAT-2026-{med.id}01",
            expiry_date=date.today() + timedelta(days=365),
            quantity_in_stock=150,
            purchase_cost=price * Decimal("0.6")
        )
        batch2 = MedicineInventory(
            medicine_id=med.id,
            batch_number=f"BAT-2026-{med.id}02",
            expiry_date=date.today() + timedelta(days=180),
            quantity_in_stock=60,
            purchase_cost=price * Decimal("0.55")
        )
        db.add_all([batch1, batch2])
        med_objs.append(med)
    db.flush()

    # 8. Diagnostic Lab Tests
    lab_tests_data = [
        ("Complete Blood Count (CBC)", "CBC", dept_gen.id, "Whole Blood", "count/uL", 4.0, 11.0, Decimal("400.00")),
        ("Liver Function Test (LFT)", "LFT", dept_gen.id, "Serum", "U/L", 10.0, 45.0, Decimal("750.00")),
        ("Kidney Function Test (KFT)", "KFT", dept_gen.id, "Serum", "mg/dL", 0.6, 1.3, Decimal("650.00")),
        ("Fasting Blood Sugar (FBS)", "FBS", dept_gen.id, "Plasma", "mg/dL", 70.0, 100.0, Decimal("150.00")),
        ("Lipid Profile", "LIPID", dept_cardio.id, "Serum", "mg/dL", 125.0, 200.0, Decimal("850.00")),
        ("Troponin I (High Sensitivity)", "TROP-I", dept_cardio.id, "Serum", "ng/mL", 0.0, 0.04, Decimal("1200.00")),
    ]

    lab_test_objs = []
    for name, code, d_id, sample, unit, r_min, r_max, cost in lab_tests_data:
        test = LabTest(
            name=name,
            test_code=code,
            department_id=d_id,
            sample_type=sample,
            unit=unit,
            reference_range_min=r_min,
            reference_range_max=r_max,
            cost=cost
        )
        db.add(test)
        lab_test_objs.append(test)
    db.flush()

    # 9. Appointments, Consultations & EMR Records
    # Patient 0 (John Doe) with Doctor 0 (Dr. Sharma - Cardio)
    app1 = Appointment(
        patient_id=patient_objs[0][0].id,
        doctor_id=doctor_objs[0][0].id,
        appointment_datetime=datetime.now(timezone.utc) - timedelta(days=2),
        status=AppointmentStatusEnum.COMPLETED,
        reason="Follow-up check for hypertension and recurrent exertional chest discomfort.",
        token_number=1,
        no_show_probability=0.12
    )
    # Patient 1 (Sarah Jenkins) with Doctor 4 (Dr. Smith - Gen Med)
    app2 = Appointment(
        patient_id=patient_objs[1][0].id,
        doctor_id=doctor_objs[4][0].id,
        appointment_datetime=datetime.now(timezone.utc) + timedelta(days=1, hours=2),
        status=AppointmentStatusEnum.CONFIRMED,
        reason="Seasonal cough and wheezing exacerbation.",
        token_number=2,
        no_show_probability=0.28
    )
    # Patient 2 (Raj Kumar) with Doctor 3 (Dr. Adams - Ortho)
    app3 = Appointment(
        patient_id=patient_objs[2][0].id,
        doctor_id=doctor_objs[3][0].id,
        appointment_datetime=datetime.now(timezone.utc) + timedelta(hours=3),
        status=AppointmentStatusEnum.SCHEDULED,
        reason="Post-fall severe knee swelling and restricted mobility.",
        token_number=3,
        no_show_probability=0.45
    )
    db.add_all([app1, app2, app3])
    db.flush()

    # 10. Clinical EMR Record & Diagnoses for App 1
    rec1 = MedicalRecord(
        patient_id=patient_objs[0][0].id,
        doctor_id=doctor_objs[0][0].id,
        appointment_id=app1.id,
        visit_date=date.today() - timedelta(days=2),
        symptoms="Exertional retrosternal heaviness, shortness of breath on climbing stairs.",
        diagnosis="Coronary Artery Disease - Angina Pectoris; Essential Hypertension",
        clinical_notes="Advised strict sodium restriction, continue antiplatelet therapy, ordered Troponin I and Lipid Profile.",
        vitals_bp="142/92",
        vitals_pulse=84,
        vitals_temp=Decimal("36.8"),
        vitals_spo2=97,
        follow_up_date=date.today() + timedelta(days=14)
    )
    db.add(rec1)
    db.flush()

    # Formal Clinical Diagnoses with ICD-10 codes
    diag1 = Diagnosis(
        patient_id=patient_objs[0][0].id,
        doctor_id=doctor_objs[0][0].id,
        medical_record_id=rec1.id,
        diagnosis_code="I10",
        diagnosis_name="Essential (Primary) Hypertension",
        description="Persistent Stage 2 hypertension. BP 142/92.",
        diagnosis_type="Primary",
        status="Active",
        diagnosed_date=date.today() - timedelta(days=2)
    )
    diag2 = Diagnosis(
        patient_id=patient_objs[0][0].id,
        doctor_id=doctor_objs[0][0].id,
        medical_record_id=rec1.id,
        diagnosis_code="I25.10",
        diagnosis_name="Atherosclerotic heart disease of native coronary artery",
        description="Exertional angina pectoris confirmed via clinical evaluation.",
        diagnosis_type="Secondary",
        status="Active",
        diagnosed_date=date.today() - timedelta(days=2)
    )
    diag3 = Diagnosis(
        patient_id=patient_objs[1][0].id,
        doctor_id=doctor_objs[4][0].id,
        medical_record_id=None,
        diagnosis_code="J45.909",
        diagnosis_name="Unspecified asthma, uncomplicated",
        description="Mild intermittent bronchial asthma.",
        diagnosis_type="Primary",
        status="Active",
        diagnosed_date=date.today() - timedelta(days=5)
    )
    db.add_all([diag1, diag2, diag3])
    db.flush()

    # 11. Prescription for Record 1
    rx1 = Prescription(
        medical_record_id=rec1.id,
        patient_id=patient_objs[0][0].id,
        doctor_id=doctor_objs[0][0].id,
        status=PrescriptionStatusEnum.DISPENSED,
        notes="Take Atorvastatin at bedtime. Monitor morning fasting glucose."
    )
    db.add(rx1)
    db.flush()

    rx_item1 = PrescriptionItem(
        prescription_id=rx1.id,
        medicine_id=med_objs[2].id, # Atorvastatin
        dosage="20mg",
        frequency="0-0-1 (Night)",
        duration_days=30,
        instructions="After dinner with water",
        quantity_prescribed=30,
        quantity_dispensed=30
    )
    rx_item2 = PrescriptionItem(
        prescription_id=rx1.id,
        medicine_id=med_objs[3].id, # Metformin
        dosage="500mg",
        frequency="1-0-1 (Twice daily)",
        duration_days=30,
        instructions="With meals",
        quantity_prescribed=60,
        quantity_dispensed=60
    )
    db.add_all([rx_item1, rx_item2])
    db.flush()

    # 12. Lab Order & Verified Result for Record 1
    lab_order1 = LabOrder(
        patient_id=patient_objs[0][0].id,
        doctor_id=doctor_objs[0][0].id,
        medical_record_id=rec1.id,
        test_id=lab_test_objs[5].id, # Troponin I
        technician_id=staff_objs[RoleEnum.LAB_TECH].id,
        status=LabOrderStatusEnum.COMPLETED,
        ordered_at=datetime.now(timezone.utc) - timedelta(days=2),
        completed_at=datetime.now(timezone.utc) - timedelta(days=2, hours=-2)
    )
    db.add(lab_order1)
    db.flush()

    lab_result1 = LabResult(
        lab_order_id=lab_order1.id,
        measured_value=0.025,
        unit="ng/mL",
        is_abnormal=False,
        critical_alert=False,
        technician_notes="Serum Troponin I within normal limits; borderline low ischemic risk.",
        verified_at=datetime.now(timezone.utc) - timedelta(days=2, hours=-2)
    )
    db.add(lab_result1)
    db.flush()

    # 13. Inpatient Admission (Michael Brown in ICU)
    occupied_bed = all_beds[0]  # ICU-101
    occupied_bed.status = BedStatusEnum.OCCUPIED

    admission1 = Admission(
        patient_id=patient_objs[4][0].id, # Michael Brown
        admitting_doctor_id=doctor_objs[0][0].id, # Dr. Sharma
        nurse_id=staff_objs[RoleEnum.NURSE].id, # Nurse Mary
        bed_id=occupied_bed.id,
        admission_date=datetime.now(timezone.utc) - timedelta(days=3),
        status=AdmissionStatusEnum.ADMITTED,
        admission_reason="Acute exacerbation of congestive heart failure with pulmonary congestion.",
        discharge_summary=None,
        readmission_risk_score=0.74  # High risk
    )
    db.add(admission1)
    db.flush()

    # 14. Itemized Consolidated Billing & Payments
    bill1 = Bill(
        bill_number="BILL-2026-0001",
        patient_id=patient_objs[0][0].id,
        appointment_id=app1.id,
        insurance_id=ins1.id,
        subtotal=Decimal("2075.00"),
        tax=Decimal("103.75"),
        discount=Decimal("0.00"),
        insurance_covered=Decimal("1500.00"),
        total_amount=Decimal("678.75"),
        status=BillStatusEnum.PAID
    )
    db.add(bill1)
    db.flush()

    bill_items = [
        BillItem(bill_id=bill1.id, item_type=ItemTypeEnum.CONSULTATION, description="Cardiology Consultation - Dr. Rajesh Sharma", unit_price=Decimal("800.00"), quantity=1, subtotal=Decimal("800.00")),
        BillItem(bill_id=bill1.id, item_type=ItemTypeEnum.LAB_TEST, description="Troponin I Quantitative Assay", unit_price=Decimal("1200.00"), quantity=1, subtotal=Decimal("1200.00")),
        BillItem(bill_id=bill1.id, item_type=ItemTypeEnum.PHARMACY, description="Atorvastatin 20mg (30 Tablets)", unit_price=Decimal("2.50"), quantity=30, subtotal=Decimal("75.00")),
    ]
    db.add_all(bill_items)
    db.flush()

    payment1 = Payment(
        bill_id=bill1.id,
        amount=Decimal("678.75"),
        payment_method=PaymentMethodEnum.CARD,
        transaction_reference="TXN-CARD-9921471"
    )
    db.add(payment1)
    db.flush()

    # 15. Real-Time Clinical Notifications
    seed_notifs = [
        Notification(
            user_id=doctor_objs[0][0].id,
            title="CRITICAL: Abnormal Troponin Level",
            message="Patient Michael Brown (ICU-101) has elevated cardiac markers requiring urgent review.",
            type=NotificationTypeEnum.CRITICAL,
            is_read=False
        ),
        Notification(
            user_id=doctor_objs[0][0].id,
            title="Inpatient Admitted",
            message="Michael Brown admitted to ICU Bed ICU-101. Deterioration hazard evaluated at 74%.",
            type=NotificationTypeEnum.ALERT,
            is_read=False
        ),
        Notification(
            user_id=doctor_objs[0][0].id,
            title="Lab Results Ready",
            message="Lab Results for Patient John Doe (Troponin I) have been verified and uploaded.",
            type=NotificationTypeEnum.SYSTEM,
            is_read=True
        ),
        Notification(
            user_id=staff_objs[RoleEnum.NURSE].id,
            title="Bed Sanitization Required",
            message="Bed GEN-102 vacated. Terminal cleaning and sanitization required before next admission.",
            type=NotificationTypeEnum.ALERT,
            is_read=False
        ),
        Notification(
            user_id=staff_objs[RoleEnum.NURSE].id,
            title="Routine Vitals Check Due",
            message="ICU vitals round scheduled for 20:00. Please chart SPO2 and blood pressure.",
            type=NotificationTypeEnum.REMINDER,
            is_read=False
        ),
        Notification(
            user_id=staff_objs[RoleEnum.PHARMACIST].id,
            title="Low Stock Warning: Amoxicillin",
            message="Amoxicillin 500mg has reached safety reorder buffer (Current: 50 units). Restock recommended.",
            type=NotificationTypeEnum.ALERT,
            is_read=False
        ),
        Notification(
            user_id=staff_objs[RoleEnum.PHARMACIST].id,
            title="Electronic Rx Dispensed",
            message="Prescription #1 for John Doe fulfilled via FEFO batch allocation.",
            type=NotificationTypeEnum.SYSTEM,
            is_read=True
        ),
        Notification(
            user_id=staff_objs[RoleEnum.RECEPTIONIST].id,
            title="High OPD Volume Expected",
            message="Cardiology department has 8 bookings scheduled today. Peak arrival expected at 11:00 AM.",
            type=NotificationTypeEnum.REMINDER,
            is_read=False
        ),
        Notification(
            user_id=patient_objs[0][0].id,
            title="Consultation Completed",
            message="Your consultation summary and lab reports are ready in your patient portal.",
            type=NotificationTypeEnum.SYSTEM,
            is_read=False
        ),
        Notification(
            user_id=patient_objs[0][0].id,
            title="Payment Receipt Confirmed",
            message="Bill BILL-2026-0001 ($678.75 after insurance) settled via Card. Thank you.",
            type=NotificationTypeEnum.SYSTEM,
            is_read=True
        ),
        Notification(
            user_id=admin_user.id,
            title="System Security Audit Completed",
            message="Daily automated RBAC access and HIPAA compliance audit executed with zero violations.",
            type=NotificationTypeEnum.SYSTEM,
            is_read=False
        )
    ]
    db.add_all(seed_notifs)

    # 16. Audit Log Records
    audit1 = AuditLog(
        user_id=admin_user.id,
        action="SYSTEM_INIT_SEED",
        resource_type="System",
        resource_id=1,
        ip_address="127.0.0.1",
        details_json='{"status": "Database seeded with 25 core hospital domain models"}'
    )
    audit2 = AuditLog(
        user_id=doctor_objs[0][0].id,
        action="EMR_RECORD_CREATE",
        resource_type="MedicalRecord",
        resource_id=rec1.id,
        ip_address="192.168.1.101",
        details_json=f'{{"patient_id": {patient_objs[0][0].id}, "diagnosis": "Coronary Artery Disease"}}'
    )
    db.add_all([audit1, audit2])

    db.commit()
    print("[+] Database seeding complete! Summary of records across all 25 models:")
    print(f"    - Roles: {db.query(Role).count()}")
    print(f"    - Users: {db.query(User).count()}")
    print(f"    - Departments: {db.query(Department).count()}")
    print(f"    - Doctors: {db.query(Doctor).count()}")
    print(f"    - Patients: {db.query(Patient).count()}")
    print(f"    - Staff: {db.query(Staff).count()}")
    print(f"    - Insurances: {db.query(Insurance).count()}")
    print(f"    - Rooms: {db.query(Room).count()} | Beds: {db.query(Bed).count()}")
    print(f"    - Medicines: {db.query(Medicine).count()} | Inventory Batches: {db.query(MedicineInventory).count()}")
    print(f"    - Lab Tests: {db.query(LabTest).count()}")
    print(f"    - Appointments: {db.query(Appointment).count()}")
    print(f"    - Medical Records: {db.query(MedicalRecord).count()}")
    print(f"    - Diagnoses: {db.query(Diagnosis).count()}")
    print(f"    - Prescriptions: {db.query(Prescription).count()} | Items: {db.query(PrescriptionItem).count()}")
    print(f"    - Lab Orders: {db.query(LabOrder).count()} | Results: {db.query(LabResult).count()}")
    print(f"    - Admissions: {db.query(Admission).count()}")
    print(f"    - Bills: {db.query(Bill).count()} | Items: {db.query(BillItem).count()}")
    print(f"    - Payments: {db.query(Payment).count()}")
    print(f"    - Notifications: {db.query(Notification).count()}")
    print(f"    - Audit Logs: {db.query(AuditLog).count()}")
    db.close()


if __name__ == "__main__":
    seed()
