import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, Enum, ForeignKey, Float, Numeric, Text, DateTime
from sqlalchemy.orm import relationship, synonym
from backend.database import Base
from backend.models.base import TimestampMixin


class LabOrderStatusEnum(str, enum.Enum):
    ORDERED = "ordered"
    SAMPLE_COLLECTED = "sample_collected"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class LabTest(Base, TimestampMixin):
    __tablename__ = "lab_tests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), unique=True, nullable=False, index=True)
    test_code = Column(String(20), unique=True, index=True, nullable=False)  # e.g., "CBC", "LFT", "LIPID"
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True, index=True)
    sample_type = Column(String(60), nullable=False)                         # e.g., Blood, Serum, Urine
    unit = Column(String(30), nullable=True)                                 # e.g., mg/dL, g/dL
    reference_range_min = Column(Float, nullable=True)
    reference_range_max = Column(Float, nullable=True)
    cost = Column(Numeric(10, 2), nullable=False, default=300.00)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Relationships
    department = relationship("Department", back_populates="lab_tests")
    orders = relationship("LabOrder", back_populates="test")

    def __repr__(self) -> str:
        return f"<LabTest id={self.id} code={self.test_code} name={self.name}>"


# Backward compatibility alias
LabTestType = LabTest


class LabOrder(Base, TimestampMixin):
    __tablename__ = "lab_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False, index=True)
    medical_record_id = Column(Integer, ForeignKey("medical_records.id"), nullable=True, index=True)
    test_id = Column(Integer, ForeignKey("lab_tests.id"), nullable=False, index=True)
    test_type_id = synonym("test_id")
    technician_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    status = Column(Enum(LabOrderStatusEnum), default=LabOrderStatusEnum.ORDERED, nullable=False, index=True)
    priority = Column(String(20), default="routine", nullable=False, index=True)  # routine, urgent, stat
    clinical_notes = Column(Text, nullable=True)

    # Lifecycle Timestamps & Actors
    ordered_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    sample_collected_at = Column(DateTime(timezone=True), nullable=True)
    sample_collected_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    processing_started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Doctor Review
    doctor_reviewed = Column(Boolean, default=False, nullable=False, index=True)
    doctor_reviewed_at = Column(DateTime(timezone=True), nullable=True)
    doctor_review_notes = Column(Text, nullable=True)

    # Cancellation
    cancellation_reason = Column(Text, nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationships
    patient = relationship("Patient")
    doctor = relationship("Doctor")
    medical_record = relationship("MedicalRecord", back_populates="lab_orders")
    test = relationship("LabTest", back_populates="orders")
    test_type = synonym("test")
    technician = relationship("User", foreign_keys=[technician_id])
    sample_collector = relationship("User", foreign_keys=[sample_collected_by_id])
    canceller = relationship("User", foreign_keys=[cancelled_by_id])
    result = relationship("LabResult", back_populates="lab_order", uselist=False, cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<LabOrder id={self.id} test={self.test_id} status={self.status}>"


class LabResult(Base, TimestampMixin):
    __tablename__ = "lab_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lab_order_id = Column(Integer, ForeignKey("lab_orders.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    measured_value = Column(Float, nullable=False)
    result_text = Column(String(200), nullable=True)
    unit = Column(String(30), nullable=False)
    is_abnormal = Column(Boolean, default=False, nullable=False, index=True)
    critical_alert = Column(Boolean, default=False, nullable=False, index=True)
    technician_notes = Column(Text, nullable=True)
    verified_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    lab_order = relationship("LabOrder", back_populates="result")

    def __repr__(self) -> str:
        return f"<LabResult id={self.id} value={self.measured_value} abnormal={self.is_abnormal}>"
