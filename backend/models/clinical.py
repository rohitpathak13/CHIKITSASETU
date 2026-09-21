import enum
from datetime import datetime, date, timezone
from sqlalchemy import Column, Integer, String, Boolean, Enum, ForeignKey, Date, DateTime, Numeric, Text, Float, Index
from sqlalchemy.orm import relationship, synonym
from backend.database import Base
from backend.models.base import TimestampMixin


class AppointmentStatusEnum(str, enum.Enum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class Department(Base, TimestampMixin):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    code = Column(String(10), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    head_doctor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    doctors = relationship("Doctor", back_populates="department", foreign_keys="Doctor.department_id")
    rooms = relationship("Room", back_populates="department")
    wards = synonym("rooms")
    lab_tests = relationship("LabTest", back_populates="department")
    lab_test_types = synonym("lab_tests")

    def __repr__(self) -> str:
        return f"<Department id={self.id} code={self.code} name={self.name}>"


class Appointment(Base, TimestampMixin):
    __tablename__ = "appointments"
    __table_args__ = (
        Index("ix_appointments_doctor_datetime", "doctor_id", "appointment_datetime"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False, index=True)
    appointment_datetime = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(Enum(AppointmentStatusEnum), default=AppointmentStatusEnum.SCHEDULED, nullable=False, index=True)
    reason = Column(Text, nullable=True)
    token_number = Column(Integer, nullable=False, default=1)
    no_show_probability = Column(Float, nullable=True)  # Populated via ML scoring

    # Relationships
    patient = relationship("Patient", back_populates="appointments")
    doctor = relationship("Doctor", back_populates="appointments")
    medical_record = relationship("MedicalRecord", back_populates="appointment", uselist=False)
    bill = relationship("Bill", back_populates="appointment", uselist=False)
    invoice = synonym("bill")

    def __repr__(self) -> str:
        return f"<Appointment id={self.id} patient_id={self.patient_id} doctor_id={self.doctor_id} status={self.status}>"


class MedicalRecord(Base, TimestampMixin):
    __tablename__ = "medical_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False, index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True, index=True)
    visit_date = Column(Date, default=lambda: date.today(), nullable=False, index=True)
    symptoms = Column(Text, nullable=False)
    diagnosis = Column(Text, nullable=False)
    clinical_notes = Column(Text, nullable=True)
    
    # Vital signs
    vitals_bp = Column(String(20), nullable=True)       # e.g., "120/80"
    vitals_pulse = Column(Integer, nullable=True)       # bpm
    vitals_temp = Column(Numeric(4, 1), nullable=True)   # Celsius / Fahrenheit
    vitals_spo2 = Column(Integer, nullable=True)        # %
    vitals_weight = Column(Numeric(5, 2), nullable=True) # kg
    vitals_height = Column(Numeric(5, 2), nullable=True) # cm
    vitals_respiratory_rate = Column(Integer, nullable=True) # breaths/min
    
    # Clinical management & encounter findings
    allergies = Column(Text, nullable=True)             # Encounter-noted allergies / adverse reactions
    treatment_plan = Column(Text, nullable=True)        # Non-pharmacological plan, diet, therapy, lifestyle
    follow_up_date = Column(Date, nullable=True)

    # Relationships
    patient = relationship("Patient", back_populates="medical_records")
    doctor = relationship("Doctor", back_populates="medical_records")
    appointment = relationship("Appointment", back_populates="medical_record")
    diagnoses = relationship("Diagnosis", back_populates="medical_record", cascade="all, delete-orphan")
    prescriptions = relationship("Prescription", back_populates="medical_record", cascade="all, delete-orphan")
    lab_orders = relationship("LabOrder", back_populates="medical_record", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<MedicalRecord id={self.id} patient_id={self.patient_id} diagnosis={self.diagnosis[:20]}>"


class Diagnosis(Base, TimestampMixin):
    __tablename__ = "diagnoses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False, index=True)
    medical_record_id = Column(Integer, ForeignKey("medical_records.id", ondelete="CASCADE"), nullable=True, index=True)
    diagnosis_code = Column(String(50), nullable=True, index=True)   # ICD-10 e.g. "I10", "E11.9"
    diagnosis_name = Column(String(255), nullable=False, index=True) # e.g. "Essential Hypertension"
    description = Column(Text, nullable=True)
    diagnosis_type = Column(String(50), default="Primary", nullable=False)  # Primary, Secondary, Differential
    status = Column(String(50), default="Active", nullable=False)           # Active, Resolved, Chronic
    diagnosed_date = Column(Date, default=lambda: date.today(), nullable=False, index=True)

    # Relationships
    patient = relationship("Patient", back_populates="diagnoses")
    doctor = relationship("Doctor", back_populates="diagnoses")
    medical_record = relationship("MedicalRecord", back_populates="diagnoses")

    def __repr__(self) -> str:
        return f"<Diagnosis id={self.id} code={self.diagnosis_code} name={self.diagnosis_name}>"
