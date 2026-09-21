import enum
from datetime import datetime, date, timedelta, timezone
from sqlalchemy import Column, Integer, String, Enum, ForeignKey, Date, Numeric, Text, DateTime
from sqlalchemy.orm import relationship, synonym
from backend.database import Base
from backend.models.base import TimestampMixin


class PrescriptionStatusEnum(str, enum.Enum):
    PENDING = "pending"
    DISPENSED = "dispensed"
    PARTIALLY_DISPENSED = "partially_dispensed"
    CANCELLED = "cancelled"


class StockTransactionTypeEnum(str, enum.Enum):
    STOCK_IN = "stock_in"
    STOCK_OUT = "stock_out"
    DISPENSED = "dispensed"
    EXPIRED_DISCARD = "expired_discard"
    ADJUSTMENT = "adjustment"
    RETURNED = "returned"


class Medicine(Base, TimestampMixin):
    __tablename__ = "medicines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(150), unique=True, index=True, nullable=False)
    generic_name = Column(String(150), index=True, nullable=True)
    category = Column(String(100), nullable=False, index=True)  # e.g., Antibiotic, Analgesic, Antipyretic
    unit = Column(String(30), nullable=False)                    # e.g., Tablet, Syrup, Injection
    unit_price = Column(Numeric(10, 2), nullable=False)
    purchase_price = Column(Numeric(10, 2), default=0.00, nullable=True)
    reorder_level = Column(Integer, default=20, nullable=False)
    supplier = Column(String(150), nullable=True)
    manufacturer = Column(String(120), nullable=True)
    description = Column(Text, nullable=True)

    # Synonyms for clinical & inventory clarity
    selling_price = synonym("unit_price")
    minimum_stock = synonym("reorder_level")

    # Relationships
    inventory_items = relationship("MedicineInventory", back_populates="medicine", cascade="all, delete-orphan")
    batches = synonym("inventory_items")
    prescription_items = relationship("PrescriptionItem", back_populates="medicine")
    stock_transactions = relationship("StockTransaction", back_populates="medicine", cascade="all, delete-orphan")

    @property
    def total_stock(self) -> int:
        return sum(item.quantity_in_stock for item in self.inventory_items if item.expiry_date >= date.today())

    @property
    def expired_stock(self) -> int:
        return sum(item.quantity_in_stock for item in self.inventory_items if item.expiry_date < date.today())

    @property
    def expiring_soon_stock(self) -> int:
        today = date.today()
        cutoff = today + timedelta(days=30)
        return sum(item.quantity_in_stock for item in self.inventory_items if today <= item.expiry_date <= cutoff)

    @property
    def is_low_stock(self) -> bool:
        return self.total_stock <= self.reorder_level

    def __repr__(self) -> str:
        return f"<Medicine id={self.id} name={self.name} stock={self.total_stock}>"


class MedicineInventory(Base, TimestampMixin):
    __tablename__ = "medicine_inventory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_number = Column(String(60), nullable=False, index=True)
    expiry_date = Column(Date, nullable=False, index=True)
    quantity_in_stock = Column(Integer, nullable=False, default=0)
    initial_quantity = Column(Integer, default=0, nullable=True)
    purchase_cost = Column(Numeric(10, 2), nullable=False)
    selling_price = Column(Numeric(10, 2), nullable=True)
    supplier = Column(String(150), nullable=True)
    received_date = Column(Date, default=lambda: date.today(), nullable=False)

    # Synonyms
    purchase_price = synonym("purchase_cost")

    # Relationships
    medicine = relationship("Medicine", back_populates="inventory_items")
    stock_transactions = relationship("StockTransaction", back_populates="batch")

    @property
    def is_expired(self) -> bool:
        return self.expiry_date < date.today()

    @property
    def is_expiring_soon(self) -> bool:
        today = date.today()
        return (today <= self.expiry_date <= today + timedelta(days=30)) and self.quantity_in_stock > 0

    @property
    def days_to_expiry(self) -> int:
        return (self.expiry_date - date.today()).days

    @property
    def status_label(self) -> str:
        if self.is_expired:
            return "EXPIRED"
        elif self.is_expiring_soon:
            return "EXPIRING_SOON"
        elif self.quantity_in_stock <= 0:
            return "OUT_OF_STOCK"
        return "ACTIVE"

    def __repr__(self) -> str:
        return f"<MedicineInventory id={self.id} med_id={self.medicine_id} batch={self.batch_number} qty={self.quantity_in_stock}>"


# Backward compatibility alias
MedicineBatch = MedicineInventory


class StockTransaction(Base, TimestampMixin):
    __tablename__ = "stock_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id = Column(Integer, ForeignKey("medicine_inventory.id", ondelete="SET NULL"), nullable=True, index=True)
    transaction_type = Column(Enum(StockTransactionTypeEnum), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=True)
    supplier = Column(String(150), nullable=True)
    reference_type = Column(String(60), nullable=True)  # e.g., "PRESCRIPTION", "PURCHASE_ORDER", "MANUAL_STOCK_OUT", "EXPIRED_DISCARD"
    reference_id = Column(Integer, nullable=True)
    performed_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    notes = Column(Text, nullable=True)

    # Relationships
    medicine = relationship("Medicine", back_populates="stock_transactions")
    batch = relationship("MedicineInventory", back_populates="stock_transactions")
    performed_by = relationship("User")

    def __repr__(self) -> str:
        return f"<StockTransaction id={self.id} type={self.transaction_type} med_id={self.medicine_id} qty={self.quantity}>"



class Prescription(Base, TimestampMixin):
    __tablename__ = "prescriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    medical_record_id = Column(Integer, ForeignKey("medical_records.id", ondelete="CASCADE"), nullable=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False, index=True)
    status = Column(Enum(PrescriptionStatusEnum), default=PrescriptionStatusEnum.PENDING, nullable=False, index=True)
    notes = Column(Text, nullable=True)

    # Relationships
    medical_record = relationship("MedicalRecord", back_populates="prescriptions")
    patient = relationship("Patient")
    doctor = relationship("Doctor")
    items = relationship("PrescriptionItem", back_populates="prescription", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Prescription id={self.id} patient_id={self.patient_id} status={self.status}>"


class PrescriptionItem(Base, TimestampMixin):
    __tablename__ = "prescription_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False, index=True)
    dosage = Column(String(50), nullable=False)          # e.g., "500 mg"
    frequency = Column(String(50), nullable=False)       # e.g., "1-0-1 after meals"
    duration_days = Column(Integer, nullable=False)      # e.g., 5
    instructions = Column(String(200), nullable=True)
    quantity_prescribed = Column(Integer, nullable=False)
    quantity_dispensed = Column(Integer, default=0, nullable=False)

    # Relationships
    prescription = relationship("Prescription", back_populates="items")
    medicine = relationship("Medicine", back_populates="prescription_items")

    def __repr__(self) -> str:
        return f"<PrescriptionItem id={self.id} medicine_id={self.medicine_id} prescribed={self.quantity_prescribed}>"
