from core.database import Base
from core.models.base import TimestampMixin
from core.models.user import (
    Role, User, Doctor, Patient, Staff,
    DoctorProfile, PatientProfile, StaffProfile,
    RoleEnum, GenderEnum
)
from core.models.clinical import (
    Department, Appointment, MedicalRecord, Diagnosis,
    AppointmentStatusEnum
)
from core.models.pharmacy import (
    Medicine, MedicineInventory, MedicineBatch,
    Prescription, PrescriptionItem, PrescriptionStatusEnum,
    StockTransaction, StockTransactionTypeEnum
)
from core.models.laboratory import (
    LabTest, LabTestType, LabOrder, LabResult,
    LabOrderStatusEnum
)
from core.models.inpatient import (
    Room, Ward, Bed, Admission, BedTransfer,
    RoomTypeEnum, WardTypeEnum, BedStatusEnum, AdmissionStatusEnum
)
from core.models.billing import (
    Insurance, Bill, BillItem, Invoice, InvoiceItem, Payment,
    BillStatusEnum, InvoiceStatusEnum, PaymentStatusEnum, ItemTypeEnum, PaymentMethodEnum
)
from core.models.notification import (
    Notification, NotificationTypeEnum, NotificationPriorityEnum
)
from core.models.audit import (
    AuditLog
)

__all__ = [
    "Base",
    "TimestampMixin",
    # Core 25 Models
    "User",
    "Role",
    "Patient",
    "Doctor",
    "Department",
    "Staff",
    "Appointment",
    "MedicalRecord",
    "Diagnosis",
    "Prescription",
    "PrescriptionItem",
    "Medicine",
    "MedicineInventory",
    "LabTest",
    "LabOrder",
    "LabResult",
    "Admission",
    "BedTransfer",
    "Room",
    "Bed",
    "Bill",
    "BillItem",
    "Payment",
    "Insurance",
    "Notification",
    "AuditLog",
    "StockTransaction",
    # Backward-compatible aliases
    "DoctorProfile",
    "PatientProfile",
    "StaffProfile",
    "MedicineBatch",
    "LabTestType",
    "Ward",
    "Invoice",
    "InvoiceItem",
    # Enums
    "RoleEnum",
    "GenderEnum",
    "AppointmentStatusEnum",
    "PrescriptionStatusEnum",
    "StockTransactionTypeEnum",
    "LabOrderStatusEnum",
    "RoomTypeEnum",
    "WardTypeEnum",
    "BedStatusEnum",
    "AdmissionStatusEnum",
    "BillStatusEnum",
    "InvoiceStatusEnum",
    "PaymentStatusEnum",
    "ItemTypeEnum",
    "PaymentMethodEnum",
    "NotificationTypeEnum",
    "NotificationPriorityEnum",
]
