"""Initial PostgreSQL schema with 25 core hospital domain models

Revision ID: c7363561e48f
Revises: 
Create Date: 2026-09-18 19:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7363561e48f'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. roles
    op.create_table(
        'roles',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_roles_name'), 'roles', ['name'], unique=True)
    op.create_index(op.f('ix_roles_created_at'), 'roles', ['created_at'], unique=False)

    # 2. users
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role_id', sa.Integer(), nullable=True),
        sa.Column('role', sa.Enum('ADMIN', 'DOCTOR', 'PATIENT', 'RECEPTIONIST', 'NURSE', 'PHARMACIST', 'LAB_TECH', name='roleenum'), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=False),
        sa.Column('last_name', sa.String(length=100), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_role_id'), 'users', ['role_id'], unique=False)
    op.create_index(op.f('ix_users_role'), 'users', ['role'], unique=False)
    op.create_index(op.f('ix_users_phone'), 'users', ['phone'], unique=False)
    op.create_index(op.f('ix_users_created_at'), 'users', ['created_at'], unique=False)

    # 3. departments
    op.create_table(
        'departments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('code', sa.String(length=10), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('head_doctor_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['head_doctor_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_departments_name'), 'departments', ['name'], unique=True)
    op.create_index(op.f('ix_departments_code'), 'departments', ['code'], unique=True)
    op.create_index(op.f('ix_departments_created_at'), 'departments', ['created_at'], unique=False)

    # 4. doctors
    op.create_table(
        'doctors',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=True),
        sa.Column('specialization', sa.String(length=120), nullable=False),
        sa.Column('license_number', sa.String(length=60), nullable=False),
        sa.Column('consultation_fee', sa.Numeric(precision=10, scale=2), server_default='500.00', nullable=False),
        sa.Column('qualification', sa.String(length=150), nullable=False),
        sa.Column('room_number', sa.String(length=20), nullable=True),
        sa.Column('available_days', sa.String(length=50), server_default='Mon,Tue,Wed,Thu,Fri', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id']),
        sa.ForeignKeyConstraint(['id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_doctors_department_id'), 'doctors', ['department_id'], unique=False)
    op.create_index(op.f('ix_doctors_specialization'), 'doctors', ['specialization'], unique=False)
    op.create_index(op.f('ix_doctors_license_number'), 'doctors', ['license_number'], unique=True)
    op.create_index(op.f('ix_doctors_created_at'), 'doctors', ['created_at'], unique=False)

    # 5. insurances
    op.create_table(
        'insurances',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('policy_number', sa.String(length=100), nullable=False),
        sa.Column('provider_name', sa.String(length=150), nullable=False),
        sa.Column('policy_type', sa.String(length=50), server_default='Comprehensive', nullable=False),
        sa.Column('coverage_amount', sa.Numeric(precision=12, scale=2), server_default='500000.00', nullable=False),
        sa.Column('valid_until', sa.Date(), nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=30), server_default='Active', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['patient_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_insurances_policy_number'), 'insurances', ['policy_number'], unique=True)
    op.create_index(op.f('ix_insurances_provider_name'), 'insurances', ['provider_name'], unique=False)
    op.create_index(op.f('ix_insurances_valid_until'), 'insurances', ['valid_until'], unique=False)
    op.create_index(op.f('ix_insurances_patient_id'), 'insurances', ['patient_id'], unique=False)
    op.create_index(op.f('ix_insurances_status'), 'insurances', ['status'], unique=False)
    op.create_index(op.f('ix_insurances_created_at'), 'insurances', ['created_at'], unique=False)

    # 6. patients
    op.create_table(
        'patients',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dob', sa.Date(), nullable=False),
        sa.Column('gender', sa.Enum('MALE', 'FEMALE', 'OTHER', name='genderenum'), nullable=False),
        sa.Column('blood_group', sa.String(length=5), nullable=True),
        sa.Column('emergency_contact_name', sa.String(length=120), nullable=True),
        sa.Column('emergency_contact_phone', sa.String(length=20), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('allergies', sa.Text(), nullable=True),
        sa.Column('chronic_conditions', sa.Text(), nullable=True),
        sa.Column('insurance_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['insurance_id'], ['insurances.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_patients_blood_group'), 'patients', ['blood_group'], unique=False)
    op.create_index(op.f('ix_patients_insurance_id'), 'patients', ['insurance_id'], unique=False)
    op.create_index(op.f('ix_patients_created_at'), 'patients', ['created_at'], unique=False)

    # 7. staff
    op.create_table(
        'staff',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=True),
        sa.Column('employee_id', sa.String(length=50), nullable=False),
        sa.Column('designation', sa.String(length=100), nullable=False),
        sa.Column('shift', sa.String(length=20), server_default='Morning', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id']),
        sa.ForeignKeyConstraint(['id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_staff_department_id'), 'staff', ['department_id'], unique=False)
    op.create_index(op.f('ix_staff_employee_id'), 'staff', ['employee_id'], unique=True)
    op.create_index(op.f('ix_staff_created_at'), 'staff', ['created_at'], unique=False)

    # 8. rooms
    op.create_table(
        'rooms',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('room_number', sa.String(length=80), nullable=False),
        sa.Column('room_type', sa.Enum('GENERAL', 'ICU', 'EMERGENCY', 'PEDIATRIC', 'MATERNITY', 'SURGICAL', name='roomtypeenum'), nullable=False),
        sa.Column('floor', sa.Integer(), server_default='1', nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=True),
        sa.Column('total_beds', sa.Integer(), server_default='10', nullable=False),
        sa.Column('daily_rate', sa.Numeric(precision=10, scale=2), server_default='1500.00', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_rooms_room_number'), 'rooms', ['room_number'], unique=True)
    op.create_index(op.f('ix_rooms_room_type'), 'rooms', ['room_type'], unique=False)
    op.create_index(op.f('ix_rooms_department_id'), 'rooms', ['department_id'], unique=False)
    op.create_index(op.f('ix_rooms_created_at'), 'rooms', ['created_at'], unique=False)

    # 9. beds
    op.create_table(
        'beds',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('room_id', sa.Integer(), nullable=False),
        sa.Column('bed_number', sa.String(length=30), nullable=False),
        sa.Column('status', sa.Enum('AVAILABLE', 'OCCUPIED', 'MAINTENANCE', 'RESERVED', name='bedstatusenum'), server_default='AVAILABLE', nullable=False),
        sa.Column('daily_rate', sa.Numeric(precision=10, scale=2), server_default='1500.00', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('room_id', 'bed_number', name='uq_room_bed_number')
    )
    op.create_index(op.f('ix_beds_room_id'), 'beds', ['room_id'], unique=False)
    op.create_index(op.f('ix_beds_status'), 'beds', ['status'], unique=False)
    op.create_index(op.f('ix_beds_created_at'), 'beds', ['created_at'], unique=False)

    # 10. medicines
    op.create_table(
        'medicines',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('generic_name', sa.String(length=150), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('unit', sa.String(length=30), nullable=False),
        sa.Column('unit_price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('reorder_level', sa.Integer(), server_default='20', nullable=False),
        sa.Column('manufacturer', sa.String(length=120), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_medicines_name'), 'medicines', ['name'], unique=True)
    op.create_index(op.f('ix_medicines_generic_name'), 'medicines', ['generic_name'], unique=False)
    op.create_index(op.f('ix_medicines_category'), 'medicines', ['category'], unique=False)
    op.create_index(op.f('ix_medicines_created_at'), 'medicines', ['created_at'], unique=False)

    # 11. medicine_inventory
    op.create_table(
        'medicine_inventory',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('medicine_id', sa.Integer(), nullable=False),
        sa.Column('batch_number', sa.String(length=60), nullable=False),
        sa.Column('expiry_date', sa.Date(), nullable=False),
        sa.Column('quantity_in_stock', sa.Integer(), server_default='0', nullable=False),
        sa.Column('purchase_cost', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('received_date', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['medicine_id'], ['medicines.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_medicine_inventory_medicine_id'), 'medicine_inventory', ['medicine_id'], unique=False)
    op.create_index(op.f('ix_medicine_inventory_batch_number'), 'medicine_inventory', ['batch_number'], unique=False)
    op.create_index(op.f('ix_medicine_inventory_expiry_date'), 'medicine_inventory', ['expiry_date'], unique=False)
    op.create_index(op.f('ix_medicine_inventory_created_at'), 'medicine_inventory', ['created_at'], unique=False)

    # 12. lab_tests
    op.create_table(
        'lab_tests',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('test_code', sa.String(length=20), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=True),
        sa.Column('sample_type', sa.String(length=60), nullable=False),
        sa.Column('unit', sa.String(length=30), nullable=True),
        sa.Column('reference_range_min', sa.Float(), nullable=True),
        sa.Column('reference_range_max', sa.Float(), nullable=True),
        sa.Column('cost', sa.Numeric(precision=10, scale=2), server_default='300.00', nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_lab_tests_name'), 'lab_tests', ['name'], unique=True)
    op.create_index(op.f('ix_lab_tests_test_code'), 'lab_tests', ['test_code'], unique=True)
    op.create_index(op.f('ix_lab_tests_department_id'), 'lab_tests', ['department_id'], unique=False)
    op.create_index(op.f('ix_lab_tests_created_at'), 'lab_tests', ['created_at'], unique=False)

    # 13. appointments
    op.create_table(
        'appointments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('doctor_id', sa.Integer(), nullable=False),
        sa.Column('appointment_datetime', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.Enum('SCHEDULED', 'CONFIRMED', 'COMPLETED', 'CANCELLED', 'NO_SHOW', name='appointmentstatusenum'), server_default='SCHEDULED', nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('token_number', sa.Integer(), server_default='1', nullable=False),
        sa.Column('no_show_probability', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id']),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_appointments_patient_id'), 'appointments', ['patient_id'], unique=False)
    op.create_index(op.f('ix_appointments_doctor_id'), 'appointments', ['doctor_id'], unique=False)
    op.create_index(op.f('ix_appointments_appointment_datetime'), 'appointments', ['appointment_datetime'], unique=False)
    op.create_index(op.f('ix_appointments_status'), 'appointments', ['status'], unique=False)
    op.create_index(op.f('ix_appointments_created_at'), 'appointments', ['created_at'], unique=False)

    # 14. medical_records
    op.create_table(
        'medical_records',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('doctor_id', sa.Integer(), nullable=False),
        sa.Column('appointment_id', sa.Integer(), nullable=True),
        sa.Column('visit_date', sa.Date(), nullable=False),
        sa.Column('symptoms', sa.Text(), nullable=False),
        sa.Column('diagnosis', sa.Text(), nullable=False),
        sa.Column('clinical_notes', sa.Text(), nullable=True),
        sa.Column('vitals_bp', sa.String(length=20), nullable=True),
        sa.Column('vitals_pulse', sa.Integer(), nullable=True),
        sa.Column('vitals_temp', sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column('vitals_spo2', sa.Integer(), nullable=True),
        sa.Column('follow_up_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id']),
        sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id']),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_medical_records_patient_id'), 'medical_records', ['patient_id'], unique=False)
    op.create_index(op.f('ix_medical_records_doctor_id'), 'medical_records', ['doctor_id'], unique=False)
    op.create_index(op.f('ix_medical_records_appointment_id'), 'medical_records', ['appointment_id'], unique=False)
    op.create_index(op.f('ix_medical_records_visit_date'), 'medical_records', ['visit_date'], unique=False)
    op.create_index(op.f('ix_medical_records_created_at'), 'medical_records', ['created_at'], unique=False)

    # 15. diagnoses
    op.create_table(
        'diagnoses',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('doctor_id', sa.Integer(), nullable=False),
        sa.Column('medical_record_id', sa.Integer(), nullable=True),
        sa.Column('diagnosis_code', sa.String(length=50), nullable=True),
        sa.Column('diagnosis_name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('diagnosis_type', sa.String(length=50), server_default='Primary', nullable=False),
        sa.Column('status', sa.String(length=50), server_default='Active', nullable=False),
        sa.Column('diagnosed_date', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id']),
        sa.ForeignKeyConstraint(['medical_record_id'], ['medical_records.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_diagnoses_patient_id'), 'diagnoses', ['patient_id'], unique=False)
    op.create_index(op.f('ix_diagnoses_doctor_id'), 'diagnoses', ['doctor_id'], unique=False)
    op.create_index(op.f('ix_diagnoses_medical_record_id'), 'diagnoses', ['medical_record_id'], unique=False)
    op.create_index(op.f('ix_diagnoses_diagnosis_code'), 'diagnoses', ['diagnosis_code'], unique=False)
    op.create_index(op.f('ix_diagnoses_diagnosis_name'), 'diagnoses', ['diagnosis_name'], unique=False)
    op.create_index(op.f('ix_diagnoses_diagnosed_date'), 'diagnoses', ['diagnosed_date'], unique=False)
    op.create_index(op.f('ix_diagnoses_created_at'), 'diagnoses', ['created_at'], unique=False)

    # 16. prescriptions
    op.create_table(
        'prescriptions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('medical_record_id', sa.Integer(), nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('doctor_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'DISPENSED', 'PARTIALLY_DISPENSED', 'CANCELLED', name='prescriptionstatusenum'), server_default='PENDING', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id']),
        sa.ForeignKeyConstraint(['medical_record_id'], ['medical_records.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_prescriptions_medical_record_id'), 'prescriptions', ['medical_record_id'], unique=False)
    op.create_index(op.f('ix_prescriptions_patient_id'), 'prescriptions', ['patient_id'], unique=False)
    op.create_index(op.f('ix_prescriptions_doctor_id'), 'prescriptions', ['doctor_id'], unique=False)
    op.create_index(op.f('ix_prescriptions_status'), 'prescriptions', ['status'], unique=False)
    op.create_index(op.f('ix_prescriptions_created_at'), 'prescriptions', ['created_at'], unique=False)

    # 17. prescription_items
    op.create_table(
        'prescription_items',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('prescription_id', sa.Integer(), nullable=False),
        sa.Column('medicine_id', sa.Integer(), nullable=False),
        sa.Column('dosage', sa.String(length=50), nullable=False),
        sa.Column('frequency', sa.String(length=50), nullable=False),
        sa.Column('duration_days', sa.Integer(), nullable=False),
        sa.Column('instructions', sa.String(length=200), nullable=True),
        sa.Column('quantity_prescribed', sa.Integer(), nullable=False),
        sa.Column('quantity_dispensed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['medicine_id'], ['medicines.id']),
        sa.ForeignKeyConstraint(['prescription_id'], ['prescriptions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_prescription_items_prescription_id'), 'prescription_items', ['prescription_id'], unique=False)
    op.create_index(op.f('ix_prescription_items_medicine_id'), 'prescription_items', ['medicine_id'], unique=False)
    op.create_index(op.f('ix_prescription_items_created_at'), 'prescription_items', ['created_at'], unique=False)

    # 18. lab_orders
    op.create_table(
        'lab_orders',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('doctor_id', sa.Integer(), nullable=False),
        sa.Column('medical_record_id', sa.Integer(), nullable=True),
        sa.Column('test_id', sa.Integer(), nullable=False),
        sa.Column('technician_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.Enum('ORDERED', 'SAMPLE_COLLECTED', 'PROCESSING', 'COMPLETED', 'CANCELLED', name='laborderstatusenum'), server_default='ORDERED', nullable=False),
        sa.Column('ordered_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sample_collected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id']),
        sa.ForeignKeyConstraint(['medical_record_id'], ['medical_records.id']),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id']),
        sa.ForeignKeyConstraint(['technician_id'], ['users.id']),
        sa.ForeignKeyConstraint(['test_id'], ['lab_tests.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_lab_orders_patient_id'), 'lab_orders', ['patient_id'], unique=False)
    op.create_index(op.f('ix_lab_orders_doctor_id'), 'lab_orders', ['doctor_id'], unique=False)
    op.create_index(op.f('ix_lab_orders_medical_record_id'), 'lab_orders', ['medical_record_id'], unique=False)
    op.create_index(op.f('ix_lab_orders_test_id'), 'lab_orders', ['test_id'], unique=False)
    op.create_index(op.f('ix_lab_orders_technician_id'), 'lab_orders', ['technician_id'], unique=False)
    op.create_index(op.f('ix_lab_orders_status'), 'lab_orders', ['status'], unique=False)
    op.create_index(op.f('ix_lab_orders_ordered_at'), 'lab_orders', ['ordered_at'], unique=False)
    op.create_index(op.f('ix_lab_orders_created_at'), 'lab_orders', ['created_at'], unique=False)

    # 19. lab_results
    op.create_table(
        'lab_results',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('lab_order_id', sa.Integer(), nullable=False),
        sa.Column('measured_value', sa.Float(), nullable=False),
        sa.Column('unit', sa.String(length=30), nullable=False),
        sa.Column('is_abnormal', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('critical_alert', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('technician_notes', sa.Text(), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['lab_order_id'], ['lab_orders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lab_order_id')
    )
    op.create_index(op.f('ix_lab_results_lab_order_id'), 'lab_results', ['lab_order_id'], unique=True)
    op.create_index(op.f('ix_lab_results_is_abnormal'), 'lab_results', ['is_abnormal'], unique=False)
    op.create_index(op.f('ix_lab_results_critical_alert'), 'lab_results', ['critical_alert'], unique=False)
    op.create_index(op.f('ix_lab_results_created_at'), 'lab_results', ['created_at'], unique=False)

    # 20. admissions
    op.create_table(
        'admissions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('admitting_doctor_id', sa.Integer(), nullable=False),
        sa.Column('nurse_id', sa.Integer(), nullable=True),
        sa.Column('bed_id', sa.Integer(), nullable=False),
        sa.Column('admission_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('discharge_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.Enum('ADMITTED', 'DISCHARGED', 'TRANSFERRED', name='admissionstatusenum'), server_default='ADMITTED', nullable=False),
        sa.Column('admission_reason', sa.Text(), nullable=False),
        sa.Column('discharge_summary', sa.Text(), nullable=True),
        sa.Column('readmission_risk_score', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['admitting_doctor_id'], ['doctors.id']),
        sa.ForeignKeyConstraint(['bed_id'], ['beds.id']),
        sa.ForeignKeyConstraint(['nurse_id'], ['users.id']),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_admissions_patient_id'), 'admissions', ['patient_id'], unique=False)
    op.create_index(op.f('ix_admissions_admitting_doctor_id'), 'admissions', ['admitting_doctor_id'], unique=False)
    op.create_index(op.f('ix_admissions_nurse_id'), 'admissions', ['nurse_id'], unique=False)
    op.create_index(op.f('ix_admissions_bed_id'), 'admissions', ['bed_id'], unique=False)
    op.create_index(op.f('ix_admissions_status'), 'admissions', ['status'], unique=False)
    op.create_index(op.f('ix_admissions_admission_date'), 'admissions', ['admission_date'], unique=False)
    op.create_index(op.f('ix_admissions_discharge_date'), 'admissions', ['discharge_date'], unique=False)
    op.create_index(op.f('ix_admissions_created_at'), 'admissions', ['created_at'], unique=False)

    # 21. bills
    op.create_table(
        'bills',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('bill_number', sa.String(length=50), nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('admission_id', sa.Integer(), nullable=True),
        sa.Column('appointment_id', sa.Integer(), nullable=True),
        sa.Column('insurance_id', sa.Integer(), nullable=True),
        sa.Column('subtotal', sa.Numeric(precision=10, scale=2), server_default='0.00', nullable=False),
        sa.Column('tax', sa.Numeric(precision=10, scale=2), server_default='0.00', nullable=False),
        sa.Column('discount', sa.Numeric(precision=10, scale=2), server_default='0.00', nullable=False),
        sa.Column('insurance_covered', sa.Numeric(precision=10, scale=2), server_default='0.00', nullable=False),
        sa.Column('total_amount', sa.Numeric(precision=10, scale=2), server_default='0.00', nullable=False),
        sa.Column('status', sa.Enum('UNPAID', 'PARTIALLY_PAID', 'PAID', 'CANCELLED', name='billstatusenum'), server_default='UNPAID', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['admission_id'], ['admissions.id']),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id']),
        sa.ForeignKeyConstraint(['insurance_id'], ['insurances.id']),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bills_bill_number'), 'bills', ['bill_number'], unique=True)
    op.create_index(op.f('ix_bills_patient_id'), 'bills', ['patient_id'], unique=False)
    op.create_index(op.f('ix_bills_admission_id'), 'bills', ['admission_id'], unique=False)
    op.create_index(op.f('ix_bills_appointment_id'), 'bills', ['appointment_id'], unique=False)
    op.create_index(op.f('ix_bills_insurance_id'), 'bills', ['insurance_id'], unique=False)
    op.create_index(op.f('ix_bills_status'), 'bills', ['status'], unique=False)
    op.create_index(op.f('ix_bills_created_at'), 'bills', ['created_at'], unique=False)

    # 22. bill_items
    op.create_table(
        'bill_items',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('bill_id', sa.Integer(), nullable=False),
        sa.Column('item_type', sa.Enum('CONSULTATION', 'LAB_TEST', 'PHARMACY', 'BED_CHARGE', 'PROCEDURE', name='itemtypeenum'), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('unit_price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('quantity', sa.Integer(), server_default='1', nullable=False),
        sa.Column('subtotal', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['bill_id'], ['bills.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bill_items_bill_id'), 'bill_items', ['bill_id'], unique=False)
    op.create_index(op.f('ix_bill_items_item_type'), 'bill_items', ['item_type'], unique=False)
    op.create_index(op.f('ix_bill_items_created_at'), 'bill_items', ['created_at'], unique=False)

    # 23. payments
    op.create_table(
        'payments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('bill_id', sa.Integer(), nullable=False),
        sa.Column('payment_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('payment_method', sa.Enum('CASH', 'CARD', 'UPI', 'INSURANCE', name='paymentmethodenum'), server_default='CASH', nullable=False),
        sa.Column('transaction_reference', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['bill_id'], ['bills.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_payments_bill_id'), 'payments', ['bill_id'], unique=False)
    op.create_index(op.f('ix_payments_payment_date'), 'payments', ['payment_date'], unique=False)
    op.create_index(op.f('ix_payments_payment_method'), 'payments', ['payment_method'], unique=False)
    op.create_index(op.f('ix_payments_created_at'), 'payments', ['created_at'], unique=False)

    # 24. notifications
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=150), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('type', sa.Enum('ALERT', 'REMINDER', 'CRITICAL', 'SYSTEM', name='notificationtypeenum'), server_default='SYSTEM', nullable=False),
        sa.Column('is_read', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)
    op.create_index(op.f('ix_notifications_type'), 'notifications', ['type'], unique=False)
    op.create_index(op.f('ix_notifications_is_read'), 'notifications', ['is_read'], unique=False)
    op.create_index(op.f('ix_notifications_created_at'), 'notifications', ['created_at'], unique=False)

    # 25. audit_logs
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=60), nullable=False),
        sa.Column('resource_id', sa.Integer(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('details_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_user_id'), 'audit_logs', ['user_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_resource_type'), 'audit_logs', ['resource_type'], unique=False)
    op.create_index(op.f('ix_audit_logs_resource_id'), 'audit_logs', ['resource_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('notifications')
    op.drop_table('payments')
    op.drop_table('bill_items')
    op.drop_table('bills')
    op.drop_table('admissions')
    op.drop_table('lab_results')
    op.drop_table('lab_orders')
    op.drop_table('prescription_items')
    op.drop_table('prescriptions')
    op.drop_table('diagnoses')
    op.drop_table('medical_records')
    op.drop_table('appointments')
    op.drop_table('lab_tests')
    op.drop_table('medicine_inventory')
    op.drop_table('medicines')
    op.drop_table('beds')
    op.drop_table('rooms')
    op.drop_table('staff')
    op.drop_table('patients')
    op.drop_table('insurances')
    op.drop_table('doctors')
    op.drop_table('departments')
    op.drop_table('users')
    op.drop_table('roles')
