from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import (
    User, Patient, PatientProfile, RoleEnum,
    MedicalRecord, Prescription, Appointment, Admission, Bill
)
from backend.security import get_password_hash
from backend.fastapi_service.dependencies import get_current_user, require_roles
from backend.fastapi_service.schemas.patient import PatientCreateRequest, PatientUpdateRequest, PatientResponse
from backend.fastapi_service.schemas.appointment import AppointmentResponse
from backend.fastapi_service.schemas.medical_record import MedicalRecordResponse
from backend.fastapi_service.schemas.prescription import PrescriptionResponse
from backend.fastapi_service.schemas.admission import AdmissionResponse
from backend.fastapi_service.schemas.billing import BillDetailResponse
from backend.services import audit_service

router = APIRouter(prefix="/patients", tags=["Patients"])


@router.get("/", response_model=List[PatientResponse])
def list_patients(
    skip: int = 0,
    limit: int = 50,
    query: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List patients with optional search query by name or email."""
    q = db.query(PatientProfile).join(User)
    if query:
        search = f"%{query}%"
        q = q.filter((User.first_name.ilike(search)) | (User.last_name.ilike(search)) | (User.email.ilike(search)))
    profiles = q.offset(skip).limit(limit).all()

    results = []
    for p in profiles:
        results.append(PatientResponse(
            id=p.id,
            user_id=p.user_id,
            medical_record_number=p.medical_record_number,
            first_name=p.user.first_name,
            last_name=p.user.last_name,
            email=p.user.email,
            phone=p.user.phone,
            dob=p.dob,
            gender=p.gender,
            blood_group=p.blood_group,
            emergency_contact_name=p.emergency_contact_name,
            emergency_contact_phone=p.emergency_contact_phone,
            address=p.address,
            allergies=p.allergies,
            chronic_conditions=p.chronic_conditions
        ))
    return results


@router.post("/", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
def register_patient(
    payload: PatientCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.ADMIN, RoleEnum.RECEPTIONIST, RoleEnum.DOCTOR]))
):
    """Registers a new patient and creates their master medical profile."""
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists")

    import secrets
    raw_password = payload.password or (secrets.token_urlsafe(12) + "A1!")

    new_user = User(
        email=payload.email,
        password_hash=get_password_hash(raw_password),
        role=RoleEnum.PATIENT,
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
        is_active=True
    )
    db.add(new_user)
    db.flush()

    profile = PatientProfile(
        user_id=new_user.id,
        dob=payload.dob,
        gender=payload.gender,
        blood_group=payload.blood_group,
        emergency_contact_name=payload.emergency_contact_name,
        emergency_contact_phone=payload.emergency_contact_phone,
        address=payload.address,
        allergies=payload.allergies,
        chronic_conditions=payload.chronic_conditions
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    audit_service.log_patient_creation(
        db=db,
        patient_id=profile.id,
        user_id=new_user.id,
        actor_id=current_user.id,
        metadata={
            "medical_record_number": profile.medical_record_number,
            "email": new_user.email,
            "first_name": new_user.first_name,
            "last_name": new_user.last_name,
            "blood_group": profile.blood_group
        }
    )

    return PatientResponse(
        id=profile.id,
        user_id=new_user.id,
        medical_record_number=profile.medical_record_number,
        first_name=new_user.first_name,
        last_name=new_user.last_name,
        email=new_user.email,
        phone=new_user.phone,
        dob=profile.dob,
        gender=profile.gender,
        blood_group=profile.blood_group,
        emergency_contact_name=profile.emergency_contact_name,
        emergency_contact_phone=profile.emergency_contact_phone,
        address=profile.address,
        allergies=profile.allergies,
        chronic_conditions=profile.chronic_conditions
    )


@router.get("/{patient_id}", response_model=PatientResponse)
def get_patient(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves patient demographics and clinical baseline."""
    if current_user.role == RoleEnum.PATIENT and current_user.id != patient_id:
        raise HTTPException(status_code=403, detail="Access forbidden to other patient's record")

    p = db.query(PatientProfile).filter(PatientProfile.user_id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")

    return PatientResponse(
        id=p.id,
        user_id=p.user_id,
        medical_record_number=p.medical_record_number,
        first_name=p.user.first_name,
        last_name=p.user.last_name,
        email=p.user.email,
        phone=p.user.phone,
        dob=p.dob,
        gender=p.gender,
        blood_group=p.blood_group,
        emergency_contact_name=p.emergency_contact_name,
        emergency_contact_phone=p.emergency_contact_phone,
        address=p.address,
        allergies=p.allergies,
        chronic_conditions=p.chronic_conditions
    )


@router.put("/{patient_id}", response_model=PatientResponse)
def update_patient(
    patient_id: int,
    payload: PatientUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.ADMIN, RoleEnum.RECEPTIONIST, RoleEnum.DOCTOR]))
):
    """Updates patient demographics and contact details."""
    p = db.query(PatientProfile).filter(PatientProfile.user_id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")

    if payload.first_name is not None:
        p.user.first_name = payload.first_name
    if payload.last_name is not None:
        p.user.last_name = payload.last_name
    if payload.phone is not None:
        p.user.phone = payload.phone
    if payload.dob is not None:
        p.dob = payload.dob
    if payload.gender is not None:
        p.gender = payload.gender
    if payload.blood_group is not None:
        p.blood_group = payload.blood_group
    if payload.emergency_contact_name is not None:
        p.emergency_contact_name = payload.emergency_contact_name
    if payload.emergency_contact_phone is not None:
        p.emergency_contact_phone = payload.emergency_contact_phone
    if payload.address is not None:
        p.address = payload.address
    if payload.allergies is not None:
        p.allergies = payload.allergies
    if payload.chronic_conditions is not None:
        p.chronic_conditions = payload.chronic_conditions

    db.commit()
    db.refresh(p)

    audit_service.log_patient_update(
        db=db,
        patient_id=p.id,
        user_id=p.user_id,
        actor_id=current_user.id,
        metadata={
            "medical_record_number": p.medical_record_number,
            "patient_user_id": p.user_id,
            "updated_fields": [k for k, v in payload.dict(exclude_unset=True).items() if v is not None]
        }
    )

    return PatientResponse(
        id=p.id,
        user_id=p.user_id,
        medical_record_number=p.medical_record_number,
        first_name=p.user.first_name,
        last_name=p.user.last_name,
        email=p.user.email,
        phone=p.user.phone,
        dob=p.dob,
        gender=p.gender,
        blood_group=p.blood_group,
        emergency_contact_name=p.emergency_contact_name,
        emergency_contact_phone=p.emergency_contact_phone,
        address=p.address,
        allergies=p.allergies,
        chronic_conditions=p.chronic_conditions
    )


@router.get("/{patient_id}/medical-records", response_model=List[MedicalRecordResponse])
def get_patient_records(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves all medical records for a given patient."""
    if current_user.role == RoleEnum.PATIENT and current_user.id != patient_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return db.query(MedicalRecord).filter(MedicalRecord.patient_id == patient_id).order_by(MedicalRecord.visit_date.desc()).all()


@router.get("/{patient_id}/prescriptions", response_model=List[PrescriptionResponse])
def get_patient_prescriptions(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves all electronic prescriptions for a given patient."""
    if current_user.role == RoleEnum.PATIENT and current_user.id != patient_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return db.query(Prescription).filter(Prescription.patient_id == patient_id).order_by(Prescription.created_at.desc()).all()


@router.get("/{patient_id}/appointments", response_model=List[AppointmentResponse])
def get_patient_appointments(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves appointment history for a given patient."""
    if current_user.role == RoleEnum.PATIENT and current_user.id != patient_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return db.query(Appointment).filter(Appointment.patient_id == patient_id).order_by(Appointment.appointment_datetime.desc()).all()


@router.get("/{patient_id}/admissions", response_model=List[AdmissionResponse])
def get_patient_admissions(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves inpatient admission history for a given patient."""
    if current_user.role == RoleEnum.PATIENT and current_user.id != patient_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return db.query(Admission).filter(Admission.patient_id == patient_id).order_by(Admission.admission_date.desc()).all()


@router.get("/{patient_id}/invoices", response_model=List[BillDetailResponse])
def get_patient_invoices(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves billing ledger invoices for a given patient."""
    if current_user.role == RoleEnum.PATIENT and current_user.id != patient_id:
        raise HTTPException(status_code=403, detail="Access denied")
    bills = db.query(Bill).filter(Bill.patient_id == patient_id).order_by(Bill.created_at.desc()).all()
    results = []
    for b in bills:
        results.append(BillDetailResponse(
            id=b.id,
            invoice_number=b.invoice_number,
            patient_id=b.patient_id,
            patient_name=b.patient.user.full_name if b.patient and b.patient.user else "Unknown",
            appointment_id=b.appointment_id,
            admission_id=b.admission_id,
            subtotal=float(b.subtotal),
            discount=float(b.discount),
            tax=float(b.tax),
            insurance_covered=float(b.insurance_covered),
            final_amount=float(b.final_amount),
            amount_paid=float(b.amount_paid),
            balance=float(b.balance),
            status=b.status.value,
            notes=b.notes,
            created_at=b.created_at.isoformat() if b.created_at else None,
            due_date=b.due_date.isoformat() if b.due_date else None,
            items=[]
        ))
    return results
