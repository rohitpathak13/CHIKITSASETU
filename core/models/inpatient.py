import enum
from datetime import datetime, timezone, date
from sqlalchemy import Column, Integer, String, Enum, ForeignKey, Numeric, Text, DateTime, Float, UniqueConstraint, desc
from sqlalchemy.orm import relationship, synonym
from core.database import Base
from core.models.base import TimestampMixin


class RoomTypeEnum(str, enum.Enum):
    GENERAL = "general"
    ICU = "icu"
    EMERGENCY = "emergency"
    PEDIATRIC = "pediatric"
    MATERNITY = "maternity"
    SURGICAL = "surgical"


# Backward compatibility alias
WardTypeEnum = RoomTypeEnum


class BedStatusEnum(str, enum.Enum):
    AVAILABLE = "available"
    OCCUPIED = "occupied"
    MAINTENANCE = "maintenance"
    RESERVED = "reserved"


class AdmissionStatusEnum(str, enum.Enum):
    ADMITTED = "admitted"
    DISCHARGED = "discharged"
    TRANSFERRED = "transferred"


class Room(Base, TimestampMixin):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    room_number = Column(String(80), unique=True, nullable=False, index=True)
    name = synonym("room_number")
    room_type = Column(Enum(RoomTypeEnum), nullable=False, index=True)
    ward_type = synonym("room_type")
    floor = Column(Integer, nullable=False, default=1)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True, index=True)
    total_beds = Column(Integer, nullable=False, default=10)
    daily_rate = Column(Numeric(10, 2), default=1500.00, nullable=False)

    # Relationships
    department = relationship("Department", back_populates="rooms")
    beds = relationship("Bed", back_populates="room", cascade="all, delete-orphan")

    @property
    def available_beds_count(self) -> int:
        return sum(1 for b in self.beds if b.status == BedStatusEnum.AVAILABLE)

    @property
    def occupied_beds_count(self) -> int:
        return sum(1 for b in self.beds if b.status == BedStatusEnum.OCCUPIED)

    def __repr__(self) -> str:
        return f"<Room id={self.id} num={self.room_number} type={self.room_type}>"


# Backward compatibility alias
Ward = Room


class Bed(Base, TimestampMixin):
    __tablename__ = "beds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    ward_id = synonym("room_id")
    bed_number = Column(String(30), nullable=False)
    status = Column(Enum(BedStatusEnum), default=BedStatusEnum.AVAILABLE, nullable=False, index=True)
    daily_rate = Column(Numeric(10, 2), default=1500.00, nullable=False)

    __table_args__ = (
        UniqueConstraint("room_id", "bed_number", name="uq_room_bed_number"),
    )

    # Relationships
    room = relationship("Room", back_populates="beds")
    ward = synonym("room")
    admissions = relationship("Admission", back_populates="bed")

    @property
    def is_available(self) -> bool:
        return self.status == BedStatusEnum.AVAILABLE

    @property
    def current_admission(self):
        return next((a for a in self.admissions if a.status == AdmissionStatusEnum.ADMITTED), None)

    def __repr__(self) -> str:
        return f"<Bed id={self.id} room={self.room_id} num={self.bed_number} status={self.status}>"


class Admission(Base, TimestampMixin):
    __tablename__ = "admissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    admitting_doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False, index=True)
    doctor_id = synonym("admitting_doctor_id")
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True, index=True)
    nurse_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    bed_id = Column(Integer, ForeignKey("beds.id"), nullable=False, index=True)
    
    admission_date = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    discharge_date = Column(DateTime(timezone=True), nullable=True, index=True)
    status = Column(Enum(AdmissionStatusEnum), default=AdmissionStatusEnum.ADMITTED, nullable=False, index=True)
    
    admission_reason = Column(Text, nullable=False)
    notes = Column(Text, nullable=True)
    discharge_summary = Column(Text, nullable=True)
    readmission_risk_score = Column(Float, nullable=True)  # Populated via ML model

    # Relationships
    patient = relationship("Patient", back_populates="admissions")
    doctor = relationship("Doctor", back_populates="admissions")
    department = relationship("Department")
    nurse = relationship("User", foreign_keys=[nurse_id])
    bed = relationship("Bed", back_populates="admissions")
    transfers = relationship("BedTransfer", back_populates="admission", cascade="all, delete-orphan", foreign_keys="[BedTransfer.admission_id]", order_by=lambda: desc(BedTransfer.transferred_at))
    bill = relationship("Bill", back_populates="admission", uselist=False)
    invoice = synonym("bill")
    invoices = synonym("bill")

    @property
    def length_of_stay_days(self) -> int:
        start = self.admission_date.date() if hasattr(self.admission_date, "date") else self.admission_date
        if self.discharge_date:
            end = self.discharge_date.date() if hasattr(self.discharge_date, "date") else self.discharge_date
        else:
            end = datetime.now(timezone.utc).date()
        return max(1, (end - start).days)

    def __repr__(self) -> str:
        return f"<Admission id={self.id} patient={self.patient_id} status={self.status}>"


class BedTransfer(Base, TimestampMixin):
    __tablename__ = "bed_transfers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    admission_id = Column(Integer, ForeignKey("admissions.id", ondelete="CASCADE"), nullable=False, index=True)
    from_bed_id = Column(Integer, ForeignKey("beds.id"), nullable=False, index=True)
    to_bed_id = Column(Integer, ForeignKey("beds.id"), nullable=False, index=True)
    transferred_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    transferred_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reason = Column(Text, nullable=False)
    notes = Column(Text, nullable=True)

    # Relationships
    admission = relationship("Admission", back_populates="transfers")
    from_bed = relationship("Bed", foreign_keys=[from_bed_id])
    to_bed = relationship("Bed", foreign_keys=[to_bed_id])
    transferred_by = relationship("User", foreign_keys=[transferred_by_id])

    def __repr__(self) -> str:
        return f"<BedTransfer id={self.id} adm={self.admission_id} from={self.from_bed_id} to={self.to_bed_id}>"

