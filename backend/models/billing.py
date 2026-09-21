import enum
from datetime import datetime, date, timezone
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import Column, Integer, String, Enum, ForeignKey, Numeric, DateTime, Date, Boolean, Text
from sqlalchemy.orm import relationship, synonym
from backend.database import Base
from backend.models.base import TimestampMixin


class BillStatusEnum(str, enum.Enum):
    PENDING = "pending"
    PARTIAL = "partial"
    PAID = "paid"
    REFUNDED = "refunded"

    # Backward compatibility aliases
    UNPAID = "unpaid"
    PARTIALLY_PAID = "partially_paid"
    CANCELLED = "cancelled"


# Aliases
PaymentStatusEnum = BillStatusEnum
InvoiceStatusEnum = BillStatusEnum


class ItemTypeEnum(str, enum.Enum):
    # Canonical 7 Bill Components
    CONSULTATION = "consultation"
    LABORATORY = "laboratory"
    MEDICINES = "medicines"
    ROOM = "room"
    BED = "bed"
    PROCEDURES = "procedures"
    OTHER_SERVICES = "other_services"

    # Backward compatibility aliases
    LAB_TEST = "lab_test"
    PHARMACY = "pharmacy"
    BED_CHARGE = "bed_charge"
    PROCEDURE = "procedure"


class PaymentMethodEnum(str, enum.Enum):
    CASH = "cash"
    CARD = "card"
    UPI = "upi"
    INSURANCE = "insurance"
    NET_BANKING = "net_banking"
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    CHEQUE = "cheque"
    ONLINE = "online"


class Insurance(Base, TimestampMixin):
    __tablename__ = "insurances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    policy_number = Column(String(100), unique=True, index=True, nullable=False)
    provider_name = Column(String(150), nullable=False, index=True)
    policy_type = Column(String(50), default="Comprehensive", nullable=False)
    coverage_amount = Column(Numeric(12, 2), default=500000.00, nullable=False)
    valid_until = Column(Date, nullable=False, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True, index=True)
    status = Column(String(30), default="Active", nullable=False, index=True)

    # Relationships
    patient = relationship("Patient", foreign_keys=[patient_id])
    patients = synonym("patient")
    bills = relationship("Bill", back_populates="insurance")

    def __repr__(self) -> str:
        return f"<Insurance id={self.id} provider={self.provider_name} policy={self.policy_number}>"


class Bill(Base, TimestampMixin):
    __tablename__ = "bills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bill_number = Column(String(50), unique=True, index=True, nullable=False)
    invoice_number = synonym("bill_number")
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=True, index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True, index=True)
    insurance_id = Column(Integer, ForeignKey("insurances.id"), nullable=True, index=True)
    
    subtotal = Column(Numeric(10, 2), default=0.00, nullable=False)
    tax = Column(Numeric(10, 2), default=0.00, nullable=False)
    discount = Column(Numeric(10, 2), default=0.00, nullable=False)
    insurance_covered = Column(Numeric(10, 2), default=0.00, nullable=False)
    total_amount = Column(Numeric(10, 2), default=0.00, nullable=False)
    final_amount = synonym("total_amount")
    status = Column(Enum(BillStatusEnum), default=BillStatusEnum.PENDING, nullable=False, index=True)
    due_date = Column(Date, nullable=True, index=True)
    notes = Column(String(500), nullable=True)

    # Relationships
    patient = relationship("Patient", back_populates="bills")
    admission = relationship("Admission", back_populates="bill")
    appointment = relationship("Appointment", back_populates="bill")
    insurance = relationship("Insurance", back_populates="bills")
    items = relationship("BillItem", back_populates="bill", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="bill", cascade="all, delete-orphan")

    @property
    def amount_paid(self) -> float:
        all_pmts = []
        seen_ids = set()
        if self.payments:
            for p in self.payments:
                all_pmts.append(p)
                if p.id:
                    seen_ids.add(p.id)

        from sqlalchemy.orm import object_session
        sess = object_session(self)
        if sess is not None and self.id is not None:
            db_pmts = sess.query(Payment).filter(Payment.bill_id == self.id).all()
            for p in db_pmts:
                if p.id not in seen_ids:
                    all_pmts.append(p)
                    seen_ids.add(p.id)

        total_paid = Decimal("0.00")
        for p in all_pmts:
            amt = Decimal(str(p.amount or "0.00"))
            if getattr(p, "is_refund", False):
                total_paid -= amt
            else:
                total_paid += amt
        return float(max(Decimal("0.00"), total_paid))

    @property
    def balance_due(self) -> float:
        tot = Decimal(str(self.total_amount or "0.00"))
        paid = Decimal(str(self.amount_paid))
        diff = tot - paid
        return float(max(Decimal("0.00"), diff))

    @property
    def balance(self) -> float:
        return self.balance_due

    @property
    def payment_status(self) -> BillStatusEnum:
        if self.status in (BillStatusEnum.UNPAID, BillStatusEnum.PENDING):
            return BillStatusEnum.PENDING
        if self.status in (BillStatusEnum.PARTIALLY_PAID, BillStatusEnum.PARTIAL):
            return BillStatusEnum.PARTIAL
        if self.status == BillStatusEnum.REFUNDED:
            return BillStatusEnum.REFUNDED
        return self.status

    def recalculate(self):
        if self.items:
            items_subtotal = sum(Decimal(str(item.subtotal)) for item in self.items)
            self.subtotal = items_subtotal
            tax_amt = Decimal(str(self.tax or "0.00"))
            disc_amt = Decimal(str(self.discount or "0.00"))
            ins_amt = Decimal(str(self.insurance_covered or "0.00"))
            computed = items_subtotal + tax_amt - disc_amt - ins_amt
            self.total_amount = max(Decimal("0.00"), computed)

        if self.status == BillStatusEnum.REFUNDED:
            return

        paid = Decimal(str(self.amount_paid))
        tot = Decimal(str(self.total_amount or "0.00"))

        if paid >= tot and tot > 0:
            self.status = BillStatusEnum.PAID
        elif paid > 0:
            if self.status in (BillStatusEnum.UNPAID, BillStatusEnum.PARTIALLY_PAID):
                self.status = BillStatusEnum.PARTIALLY_PAID
            else:
                self.status = BillStatusEnum.PARTIAL
        else:
            if self.status == BillStatusEnum.UNPAID:
                self.status = BillStatusEnum.UNPAID
            else:
                self.status = BillStatusEnum.PENDING

    def __repr__(self) -> str:
        return f"<Bill id={self.id} num={self.bill_number} total={self.total_amount} status={self.status}>"


# Backward compatibility alias
Invoice = Bill


class BillItem(Base, TimestampMixin):
    __tablename__ = "bill_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bill_id = Column(Integer, ForeignKey("bills.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_id = synonym("bill_id")
    item_type = Column(Enum(ItemTypeEnum), nullable=False, index=True)
    description = Column(String(255), nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)

    # Relationships
    bill = relationship("Bill", back_populates="items")
    invoice = synonym("bill")

    @property
    def category_display(self) -> str:
        mapping = {
            ItemTypeEnum.CONSULTATION: "Consultation",
            ItemTypeEnum.LABORATORY: "Laboratory",
            ItemTypeEnum.MEDICINES: "Medicines",
            ItemTypeEnum.ROOM: "Room",
            ItemTypeEnum.BED: "Bed",
            ItemTypeEnum.PROCEDURES: "Procedures",
            ItemTypeEnum.OTHER_SERVICES: "Other Services",
            ItemTypeEnum.LAB_TEST: "Laboratory",
            ItemTypeEnum.PHARMACY: "Medicines",
            ItemTypeEnum.BED_CHARGE: "Bed",
            ItemTypeEnum.PROCEDURE: "Procedures",
        }
        return mapping.get(self.item_type, str(self.item_type.value).capitalize())

    def __repr__(self) -> str:
        return f"<BillItem id={self.id} type={self.item_type} subtotal={self.subtotal}>"


# Backward compatibility alias
InvoiceItem = BillItem


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bill_id = Column(Integer, ForeignKey("bills.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_id = synonym("bill_id")
    payment_date = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    payment_method = Column(Enum(PaymentMethodEnum), default=PaymentMethodEnum.CASH, nullable=False, index=True)
    transaction_reference = Column(String(100), nullable=True)
    is_refund = Column(Boolean, default=False, nullable=False, index=True)
    notes = Column(String(255), nullable=True)

    # Relationships
    bill = relationship("Bill", back_populates="payments")
    invoice = synonym("bill")

    def __repr__(self) -> str:
        return f"<Payment id={self.id} amount={self.amount} method={self.payment_method} refund={self.is_refund}>"
