import enum
import re
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, Enum, ForeignKey, Date, Numeric, Text
from sqlalchemy.orm import relationship, synonym, validates
from core.database import Base
from core.models.base import TimestampMixin
from core.security import verify_password, get_password_hash


class RoleEnum(str, enum.Enum):
    ADMIN = "admin"
    DOCTOR = "doctor"
    PATIENT = "patient"
    RECEPTIONIST = "receptionist"
    NURSE = "nurse"
    PHARMACIST = "pharmacist"
    LAB_TECH = "lab_tech"
    LAB_TECHNICIAN = "lab_tech"


class GenderEnum(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(String(255), nullable=True)

    # Relationships
    users = relationship("User", back_populates="role_rel")

    def __repr__(self) -> str:
        return f"<Role id={self.id} name={self.name}>"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=True, index=True)
    role = Column(Enum(RoleEnum), nullable=False, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    role_rel = relationship("Role", back_populates="users")
    doctor_profile = relationship("Doctor", back_populates="user", uselist=False, cascade="all, delete-orphan")
    patient_profile = relationship("Patient", back_populates="user", uselist=False, cascade="all, delete-orphan")
    staff_profile = relationship("Staff", back_populates="user", uselist=False, cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user")

    # Canonical aliases
    doctor = synonym("doctor_profile")
    patient = synonym("patient_profile")
    staff = synonym("staff_profile")

    @validates("email")
    def validate_email(self, key, address):
        if not address or "@" not in address:
            raise ValueError(f"Invalid email address provided: {address}")
        return address.lower().strip()

    @validates("phone")
    def validate_phone(self, key, value):
        if value:
            clean = value.strip()
            if len(clean) > 20:
                raise ValueError("Phone number exceeds maximum length of 20 characters.")
            return clean
        return value

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def set_password(self, password: str):
        self.password_hash = get_password_hash(password)

    def check_password(self, password: str) -> bool:
        return verify_password(password, self.password_hash)

    # Flask-Login integration compatibility properties
    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return str(self.id)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"


class Doctor(Base, TimestampMixin):
    __tablename__ = "doctors"

    id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    user_id = synonym("id")
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True, index=True)
    specialization = Column(String(120), nullable=False, index=True)
    license_number = Column(String(60), unique=True, nullable=False, index=True)
    consultation_fee = Column(Numeric(10, 2), default=500.00, nullable=False)
    qualification = Column(String(150), nullable=False)
    room_number = Column(String(20), nullable=True)
    available_days = Column(String(50), default="Mon,Tue,Wed,Thu,Fri")

    # Relationships
    user = relationship("User", back_populates="doctor_profile")
    department = relationship("Department", back_populates="doctors", foreign_keys=[department_id])
    appointments = relationship("Appointment", back_populates="doctor")
    medical_records = relationship("MedicalRecord", back_populates="doctor")
    admissions = relationship("Admission", back_populates="doctor")
    diagnoses = relationship("Diagnosis", back_populates="doctor")

    def __repr__(self) -> str:
        return f"<Doctor id={self.id} spec={self.specialization}>"


# Backward compatibility alias
DoctorProfile = Doctor


class Patient(Base, TimestampMixin):
    __tablename__ = "patients"

    id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    user_id = synonym("id")
    dob = Column(Date, nullable=False)
    gender = Column(Enum(GenderEnum), nullable=False)
    blood_group = Column(String(5), nullable=True, index=True)
    emergency_contact_name = Column(String(120), nullable=True)
    emergency_contact_phone = Column(String(20), nullable=True)
    address = Column(Text, nullable=True)
    allergies = Column(Text, nullable=True)
    chronic_conditions = Column(Text, nullable=True)
    insurance_id = Column(Integer, ForeignKey("insurances.id", use_alter=True), nullable=True, index=True)

    # Relationships
    user = relationship("User", back_populates="patient_profile")
    insurance = relationship("Insurance", foreign_keys=[insurance_id])
    appointments = relationship("Appointment", back_populates="patient")
    medical_records = relationship("MedicalRecord", back_populates="patient")
    admissions = relationship("Admission", back_populates="patient")
    bills = relationship("Bill", back_populates="patient")
    invoices = synonym("bills")
    diagnoses = relationship("Diagnosis", back_populates="patient")

    @property
    def medical_record_number(self) -> str:
        return f"MRN-{self.id:06d}"

    def __repr__(self) -> str:
        return f"<Patient id={self.id} gender={self.gender}>"


# Backward compatibility alias
PatientProfile = Patient


class Staff(Base, TimestampMixin):
    __tablename__ = "staff"

    id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    user_id = synonym("id")
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True, index=True)
    employee_id = Column(String(50), unique=True, nullable=False, index=True)
    designation = Column(String(100), nullable=False)
    shift = Column(String(20), default="Morning")

    # Relationships
    user = relationship("User", back_populates="staff_profile")
    department = relationship("Department", foreign_keys=[department_id])

    def __repr__(self) -> str:
        return f"<Staff id={self.id} employee_id={self.employee_id}>"


# Backward compatibility alias
StaffProfile = Staff
