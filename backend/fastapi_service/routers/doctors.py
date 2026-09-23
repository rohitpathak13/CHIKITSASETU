from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.database import get_db
from backend.models import User, Doctor, Department, Appointment, Admission, RoleEnum
from backend.security import get_password_hash
from backend.fastapi_service.dependencies import get_current_user, require_roles
from backend.fastapi_service.schemas.doctor import DoctorCreateRequest, DoctorUpdateRequest, DoctorResponse
from backend.fastapi_service.schemas.appointment import AppointmentResponse

router = APIRouter(prefix="/doctors", tags=["Doctors"])


@router.get("/", response_model=List[DoctorResponse])
def list_doctors(
    department_id: Optional[int] = None,
    specialization: Optional[str] = None,
    query: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lists hospital medical doctors with department and specialization filters."""
    q = db.query(Doctor).join(User)
    if department_id:
        q = q.filter(Doctor.department_id == department_id)
    if specialization:
        q = q.filter(Doctor.specialization.ilike(f"%{specialization}%"))
    if query:
        search = f"%{query}%"
        q = q.filter((User.first_name.ilike(search)) | (User.last_name.ilike(search)) | (Doctor.specialization.ilike(search)))

    doctors = q.offset(skip).limit(limit).all()

    results = []
    for d in doctors:
        results.append(DoctorResponse(
            id=d.id,
            user_id=d.id,
            first_name=d.user.first_name,
            last_name=d.user.last_name,
            email=d.user.email,
            phone=d.user.phone,
            department_id=d.department_id,
            department_name=d.department.name if d.department else None,
            specialization=d.specialization,
            license_number=d.license_number,
            consultation_fee=float(d.consultation_fee),
            qualification=d.qualification,
            room_number=d.room_number,
            available_days=d.available_days
        ))
    return results


@router.post("/", response_model=DoctorResponse, status_code=status.HTTP_201_CREATED)
def create_doctor(
    payload: DoctorCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.ADMIN]))
):
    """Registers a new medical doctor account and provider profile (Admin only)."""
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User with this email already exists")

    existing_lic = db.query(Doctor).filter(Doctor.license_number == payload.license_number).first()
    if existing_lic:
        raise HTTPException(status_code=400, detail="Doctor with this medical license already exists")

    if payload.department_id:
        dept = db.query(Department).filter(Department.id == payload.department_id).first()
        if not dept:
            raise HTTPException(status_code=404, detail="Department not found")

    import secrets
    raw_password = payload.password or (secrets.token_urlsafe(12) + "A1!")

    new_user = User(
        email=payload.email,
        password_hash=get_password_hash(raw_password),
        role=RoleEnum.DOCTOR,
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
        is_active=True
    )
    db.add(new_user)
    db.flush()

    new_doctor = Doctor(
        id=new_user.id,
        department_id=payload.department_id,
        specialization=payload.specialization,
        license_number=payload.license_number,
        consultation_fee=payload.consultation_fee,
        qualification=payload.qualification,
        room_number=payload.room_number,
        available_days=payload.available_days
    )
    db.add(new_doctor)
    db.commit()
    db.refresh(new_doctor)

    return DoctorResponse(
        id=new_doctor.id,
        user_id=new_doctor.id,
        first_name=new_user.first_name,
        last_name=new_user.last_name,
        email=new_user.email,
        phone=new_user.phone,
        department_id=new_doctor.department_id,
        department_name=new_doctor.department.name if new_doctor.department else None,
        specialization=new_doctor.specialization,
        license_number=new_doctor.license_number,
        consultation_fee=float(new_doctor.consultation_fee),
        qualification=new_doctor.qualification,
        room_number=new_doctor.room_number,
        available_days=new_doctor.available_days
    )


@router.get("/{doctor_id}", response_model=DoctorResponse)
def get_doctor_profile(
    doctor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves single doctor profile and credential details."""
    doc = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Doctor not found")

    return DoctorResponse(
        id=doc.id,
        user_id=doc.id,
        first_name=doc.user.first_name,
        last_name=doc.user.last_name,
        email=doc.user.email,
        phone=doc.user.phone,
        department_id=doc.department_id,
        department_name=doc.department.name if doc.department else None,
        specialization=doc.specialization,
        license_number=doc.license_number,
        consultation_fee=float(doc.consultation_fee),
        qualification=doc.qualification,
        room_number=doc.room_number,
        available_days=doc.available_days
    )


@router.put("/{doctor_id}", response_model=DoctorResponse)
def update_doctor_profile(
    doctor_id: int,
    payload: DoctorUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.ADMIN, RoleEnum.DOCTOR]))
):
    """Updates doctor details (Admin or the Doctor themselves)."""
    if current_user.role == RoleEnum.DOCTOR and current_user.id != doctor_id:
        raise HTTPException(status_code=403, detail="Not authorized to modify another physician's profile")

    doc = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Doctor not found")

    if payload.first_name is not None:
        doc.user.first_name = payload.first_name
    if payload.last_name is not None:
        doc.user.last_name = payload.last_name
    if payload.phone is not None:
        doc.user.phone = payload.phone
    if payload.department_id is not None:
        doc.department_id = payload.department_id
    if payload.specialization is not None:
        doc.specialization = payload.specialization
    if payload.consultation_fee is not None:
        doc.consultation_fee = payload.consultation_fee
    if payload.qualification is not None:
        doc.qualification = payload.qualification
    if payload.room_number is not None:
        doc.room_number = payload.room_number
    if payload.available_days is not None:
        doc.available_days = payload.available_days

    db.commit()
    db.refresh(doc)

    return DoctorResponse(
        id=doc.id,
        user_id=doc.id,
        first_name=doc.user.first_name,
        last_name=doc.user.last_name,
        email=doc.user.email,
        phone=doc.user.phone,
        department_id=doc.department_id,
        department_name=doc.department.name if doc.department else None,
        specialization=doc.specialization,
        license_number=doc.license_number,
        consultation_fee=float(doc.consultation_fee),
        qualification=doc.qualification,
        room_number=doc.room_number,
        available_days=doc.available_days
    )


@router.get("/{doctor_id}/appointments", response_model=List[AppointmentResponse])
def get_doctor_appointments(
    doctor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves all appointments scheduled with a given doctor."""
    doc = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Doctor not found")

    return db.query(Appointment).filter(Appointment.doctor_id == doctor_id).order_by(Appointment.appointment_datetime.asc()).all()


@router.get("/{doctor_id}/workload")
def get_doctor_workload_metrics(
    doctor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves operational workload metrics for a specific doctor."""
    doc = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Doctor not found")

    total_app = len(doc.appointments)
    completed_app = sum(1 for a in doc.appointments if (a.status.value if hasattr(a.status, "value") else str(a.status)) == "completed")
    admissions_count = len(doc.admissions)

    return {
        "doctor_id": doc.id,
        "name": f"Dr. {doc.user.full_name}",
        "specialization": doc.specialization,
        "total_appointments": total_app,
        "completed_consultations": completed_app,
        "admissions_managed": admissions_count
    }
