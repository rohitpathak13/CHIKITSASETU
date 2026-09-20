import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any, Union, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, func, or_

from core.models import (
    Admission, Bed, Room, Ward, BedTransfer, Department,
    User, Patient, Doctor, Staff, AuditLog, Notification,
    BedStatusEnum, AdmissionStatusEnum, RoomTypeEnum, NotificationTypeEnum,
    Invoice
)
from core.services.discharge_billing import process_inpatient_discharge_and_billing

logger = logging.getLogger(__name__)


# =====================================================================
# Service Exceptions
# =====================================================================

class InpatientServiceError(Exception):
    """Base exception for IPD admission and bed management operations."""
    pass


class AdmissionNotFoundError(InpatientServiceError):
    """Raised when an admission record cannot be found."""
    pass


class BedNotFoundError(InpatientServiceError):
    """Raised when a bed cannot be found."""
    pass


class BedUnavailableError(InpatientServiceError):
    """Raised when an operation attempts to allocate an occupied, reserved, or maintenance bed."""
    pass


class PatientAlreadyAdmittedError(InpatientServiceError):
    """Raised when attempting to admit a patient who already has an active admission."""
    pass


class InvalidAdmissionDataError(InpatientServiceError):
    """Raised when admission or transfer parameters are invalid."""
    pass


# =====================================================================
# Patient Admission Management
# =====================================================================

def admit_patient(
    db_session: Session,
    patient_id: int,
    bed_id: int,
    admitting_doctor_id: int,
    admission_reason: str,
    department_id: Optional[int] = None,
    nurse_id: Optional[int] = None,
    notes: Optional[str] = None,
    actor_id: Optional[int] = None,
    ip_address: Optional[str] = None
) -> Admission:
    """
    Admits a patient to an IPD bed:
    1. Verifies patient exists.
    2. Checks patient does not already have an active ADMITTED status admission.
    3. Verifies bed exists and has BedStatusEnum.AVAILABLE status (strictly preventing occupied beds).
    4. Auto-detects department from bed's room if not explicitly provided.
    5. Sets bed status to OCCUPIED.
    6. Creates Admission record.
    7. Creates AuditLog entry and Notification.
    """
    if not admission_reason or not admission_reason.strip():
        raise InvalidAdmissionDataError("Admission reason is required.")

    # 1. Patient validation
    patient = db_session.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        patient_user = db_session.query(User).filter(User.id == patient_id).first()
        if not patient_user:
            raise InvalidAdmissionDataError(f"Patient with ID #{patient_id} not found.")

    # 2. Check for active admission
    active_admission = db_session.query(Admission).filter(
        Admission.patient_id == patient_id,
        Admission.status == AdmissionStatusEnum.ADMITTED
    ).first()
    if active_admission:
        raise PatientAlreadyAdmittedError(
            f"Patient #{patient_id} is already actively admitted in Admission #{active_admission.id} "
            f"(Bed: {active_admission.bed.bed_number if active_admission.bed else 'N/A'})."
        )

    # 3. Doctor validation
    doctor = db_session.query(Doctor).filter(Doctor.id == admitting_doctor_id).first()
    if not doctor:
        doc_user = db_session.query(User).filter(User.id == admitting_doctor_id).first()
        if not doc_user:
            raise InvalidAdmissionDataError(f"Admitting doctor with ID #{admitting_doctor_id} not found.")

    # 4. Bed validation & availability check
    bed = db_session.query(Bed).filter(Bed.id == bed_id).first()
    if not bed:
        raise BedNotFoundError(f"Bed with ID #{bed_id} does not exist.")

    if bed.status != BedStatusEnum.AVAILABLE:
        raise BedUnavailableError(
            f"Cannot assign Bed '{bed.bed_number}'! Current status is '{bed.status.value.upper()}'. "
            f"Only AVAILABLE beds can be assigned."
        )

    # 5. Determine department
    resolved_department_id = department_id
    if resolved_department_id is None and bed.room and bed.room.department_id:
        resolved_department_id = bed.room.department_id

    # 6. Update bed status to OCCUPIED
    bed.status = BedStatusEnum.OCCUPIED

    # 7. Create Admission
    admission = Admission(
        patient_id=patient_id,
        bed_id=bed_id,
        admitting_doctor_id=admitting_doctor_id,
        nurse_id=nurse_id,
        department_id=resolved_department_id,
        admission_date=datetime.now(timezone.utc),
        admission_reason=admission_reason.strip(),
        notes=notes.strip() if notes else None,
        status=AdmissionStatusEnum.ADMITTED
    )
    db_session.add(admission)
    db_session.flush()

    # 8. Audit Log
    actor = actor_id or admitting_doctor_id
    audit = AuditLog(
        user_id=actor,
        action="IPD_PATIENT_ADMISSION",
        resource_type="Admission",
        resource_id=admission.id,
        details={
            "admission_id": admission.id,
            "patient_id": patient_id,
            "bed_id": bed_id,
            "bed_number": bed.bed_number,
            "doctor_id": admitting_doctor_id,
            "department_id": resolved_department_id,
            "admission_date": admission.admission_date.isoformat(),
            "reason": admission_reason
        },
        ip_address=ip_address
    )
    db_session.add(audit)

    # 9. In-app Notification
    notif = Notification(
        user_id=patient_id,
        title="Inpatient Admission Confirmed",
        message=f"You have been admitted to Bed {bed.bed_number} in Room {bed.room.room_number if bed.room else 'N/A'}.",
        type=NotificationTypeEnum.SYSTEM
    )
    db_session.add(notif)
    db_session.flush()

    return admission


# =====================================================================
# Bed Transfer Management
# =====================================================================

def transfer_bed(
    db_session: Session,
    admission_id: int,
    to_bed_id: int,
    reason: str,
    transferred_by_id: Optional[int] = None,
    notes: Optional[str] = None,
    release_previous_as: BedStatusEnum = BedStatusEnum.MAINTENANCE,
    ip_address: Optional[str] = None
) -> BedTransfer:
    """
    Transfers an admitted patient to another bed:
    1. Verifies admission is currently active (ADMITTED).
    2. Verifies destination bed exists and is AVAILABLE (prevents assigning occupied bed).
    3. Releases origin bed to specified status (defaults to MAINTENANCE for cleaning/sanitizing).
    4. Sets destination bed to OCCUPIED.
    5. Records BedTransfer history log.
    6. Updates admission.bed_id and admission.department_id if department changed.
    7. Logs AuditLog.
    """
    if not reason or not reason.strip():
        raise InvalidAdmissionDataError("Transfer reason is required.")

    admission = db_session.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise AdmissionNotFoundError(f"Admission #{admission_id} not found.")

    if admission.status != AdmissionStatusEnum.ADMITTED:
        raise InvalidAdmissionDataError(
            f"Cannot transfer patient in admission #{admission_id}. Current status is '{admission.status.value}'."
        )

    if admission.bed_id == to_bed_id:
        raise InvalidAdmissionDataError("Destination bed must be different from the patient's current bed.")

    destination_bed = db_session.query(Bed).filter(Bed.id == to_bed_id).first()
    if not destination_bed:
        raise BedNotFoundError(f"Destination bed #{to_bed_id} not found.")

    if destination_bed.status != BedStatusEnum.AVAILABLE:
        raise BedUnavailableError(
            f"Cannot transfer to Bed '{destination_bed.bed_number}'! Current status is "
            f"'{destination_bed.status.value.upper()}'. Only AVAILABLE beds can be assigned."
        )

    from_bed = admission.bed
    from_bed_id = from_bed.id if from_bed else None
    from_bed_num = from_bed.bed_number if from_bed else "None"

    # Release origin bed
    if from_bed:
        from_bed.status = release_previous_as

    # Occupy destination bed
    destination_bed.status = BedStatusEnum.OCCUPIED

    # Create transfer record
    transfer = BedTransfer(
        admission_id=admission.id,
        from_bed_id=from_bed_id,
        to_bed_id=destination_bed.id,
        transferred_at=datetime.now(timezone.utc),
        transferred_by_id=transferred_by_id,
        reason=reason.strip(),
        notes=notes.strip() if notes else None
    )
    db_session.add(transfer)

    # Update admission pointer
    admission.bed_id = destination_bed.id
    if destination_bed.room and destination_bed.room.department_id:
        admission.department_id = destination_bed.room.department_id

    db_session.flush()

    # Audit Log
    audit = AuditLog(
        user_id=transferred_by_id,
        action="IPD_BED_TRANSFER",
        resource_type="BedTransfer",
        resource_id=transfer.id,
        details={
            "admission_id": admission.id,
            "patient_id": admission.patient_id,
            "from_bed": from_bed_num,
            "to_bed": destination_bed.bed_number,
            "reason": reason,
            "previous_bed_status": release_previous_as.value
        },
        ip_address=ip_address
    )
    db_session.add(audit)

    # Notification to patient
    notif = Notification(
        user_id=admission.patient_id,
        title="Bed Transfer Completed",
        message=f"You have been transferred from Bed {from_bed_num} to Bed {destination_bed.bed_number} (Reason: {reason}).",
        type=NotificationTypeEnum.SYSTEM
    )
    db_session.add(notif)
    db_session.flush()

    return transfer


# =====================================================================
# Discharge Management
# =====================================================================

def discharge_patient(
    db_session: Session,
    admission_id: int,
    discharge_summary: str,
    actor_id: Optional[int] = None,
    ip_address: Optional[str] = None
) -> Tuple[Admission, Invoice]:
    """
    Executes discharge of an inpatient:
    1. Validates admission is active.
    2. Calculates length of stay (minimum 1 day).
    3. Aggregates bed accommodation fees, pharmacy medications, diagnostic lab orders.
    4. Auto-generates itemized hospital invoice with standard 5% tax.
    5. Sets admission status to DISCHARGED and sets discharge_date and discharge_summary.
    6. Sets bed status to MAINTENANCE for sanitization.
    7. Dispatches notifications and audit logs.
    """
    if not discharge_summary or not discharge_summary.strip():
        raise InvalidAdmissionDataError("Discharge summary notes are required.")

    return process_inpatient_discharge_and_billing(
        admission_id=admission_id,
        discharge_summary=discharge_summary.strip(),
        db=db_session,
        actor_id=actor_id,
        ip_address=ip_address
    )


# =====================================================================
# Bed Status Maintenance & Allocation
# =====================================================================

def update_bed_status(
    db_session: Session,
    bed_id: int,
    new_status: Union[BedStatusEnum, str],
    actor_id: Optional[int] = None,
    notes: Optional[str] = None,
    ip_address: Optional[str] = None
) -> Bed:
    """
    Updates the operational status of a bed (e.g. from MAINTENANCE to AVAILABLE after sanitization).
    Cannot manually set a bed to OCCUPIED if there is no active admission for it.
    """
    bed = db_session.query(Bed).filter(Bed.id == bed_id).first()
    if not bed:
        raise BedNotFoundError(f"Bed #{bed_id} not found.")

    if isinstance(new_status, str):
        try:
            target_status = BedStatusEnum(new_status.lower())
        except ValueError:
            raise InvalidAdmissionDataError(f"Invalid bed status '{new_status}'. Allowed: AVAILABLE, OCCUPIED, RESERVED, MAINTENANCE.")
    else:
        target_status = new_status

    old_status = bed.status

    if target_status == BedStatusEnum.OCCUPIED and not bed.current_admission:
        raise InvalidAdmissionDataError("Cannot manually mark a bed as OCCUPIED without an active patient admission.")

    if old_status == BedStatusEnum.OCCUPIED and target_status != BedStatusEnum.OCCUPIED:
        # Check if there is an active admission
        active_adm = bed.current_admission
        if active_adm:
            raise InvalidAdmissionDataError(
                f"Bed '{bed.bed_number}' has active admission #{active_adm.id}. "
                f"Patient must be transferred or discharged first."
            )

    bed.status = target_status
    db_session.flush()

    # Audit log
    audit = AuditLog(
        user_id=actor_id,
        action="IPD_BED_STATUS_UPDATE",
        resource_type="Bed",
        resource_id=bed.id,
        details={"status": target_status.value, "old_status": old_status.value, "notes": notes},
        ip_address=ip_address
    )
    db_session.add(audit)
    db_session.flush()

    return bed


# =====================================================================
# Bed Availability & Department / Room Queries
# =====================================================================

def get_bed_availability(
    db_session: Session,
    department_id: Optional[int] = None,
    room_id: Optional[int] = None,
    room_type: Optional[RoomTypeEnum] = None,
    status: Optional[BedStatusEnum] = None
) -> List[Bed]:
    """
    Returns beds filtered by optional department, room, room type, and status.
    """
    query = db_session.query(Bed).options(
        joinedload(Bed.room).joinedload(Room.department),
        joinedload(Bed.admissions)
    )

    if room_id:
        query = query.filter(Bed.room_id == room_id)

    if department_id:
        query = query.join(Bed.room).filter(Room.department_id == department_id)

    if room_type:
        if not department_id:
            query = query.join(Bed.room)
        query = query.filter(Room.room_type == room_type)

    if status:
        query = query.filter(Bed.status == status)

    return query.order_by(Bed.room_id, Bed.bed_number).all()


def get_all_rooms_with_beds(db_session: Session) -> List[Room]:
    """Returns all rooms with pre-loaded department and beds for matrix rendering."""
    return db_session.query(Room).options(
        joinedload(Room.department),
        joinedload(Room.beds).joinedload(Bed.admissions)
    ).order_by(Room.room_number).all()


# =====================================================================
# Dashboard Statistics
# =====================================================================

def get_ipd_dashboard_stats(db_session: Session) -> Dict[str, Any]:
    """
    Computes key IPD statistics:
    - Total beds
    - Occupied beds
    - Available beds
    - Reserved beds
    - Maintenance beds
    - Occupancy percentage ((Occupied / Total) * 100)
    - Additional operational metrics (rooms, active admissions, breakdown by room type).
    """
    total_beds = db_session.query(func.count(Bed.id)).scalar() or 0
    occupied_beds = db_session.query(func.count(Bed.id)).filter(Bed.status == BedStatusEnum.OCCUPIED).scalar() or 0
    available_beds = db_session.query(func.count(Bed.id)).filter(Bed.status == BedStatusEnum.AVAILABLE).scalar() or 0
    reserved_beds = db_session.query(func.count(Bed.id)).filter(Bed.status == BedStatusEnum.RESERVED).scalar() or 0
    maintenance_beds = db_session.query(func.count(Bed.id)).filter(Bed.status == BedStatusEnum.MAINTENANCE).scalar() or 0

    occupancy_percentage = round((occupied_beds / total_beds * 100.0), 2) if total_beds > 0 else 0.0

    total_rooms = db_session.query(func.count(Room.id)).scalar() or 0
    active_admissions_count = db_session.query(func.count(Admission.id)).filter(
        Admission.status == AdmissionStatusEnum.ADMITTED
    ).scalar() or 0
    total_admissions_historical = db_session.query(func.count(Admission.id)).scalar() or 0

    # Room type distribution
    room_types_data = []
    rooms = db_session.query(Room).options(joinedload(Room.beds)).all()
    type_counts = {}
    for r in rooms:
        rtype = r.room_type.value if hasattr(r.room_type, "value") else str(r.room_type)
        if rtype not in type_counts:
            type_counts[rtype] = {"total_beds": 0, "occupied_beds": 0, "available_beds": 0}
        for b in r.beds:
            type_counts[rtype]["total_beds"] += 1
            if b.status == BedStatusEnum.OCCUPIED:
                type_counts[rtype]["occupied_beds"] += 1
            elif b.status == BedStatusEnum.AVAILABLE:
                type_counts[rtype]["available_beds"] += 1

    for rtype, data in type_counts.items():
        occ = round((data["occupied_beds"] / data["total_beds"] * 100), 1) if data["total_beds"] > 0 else 0.0
        room_types_data.append({
            "room_type": rtype,
            "total_beds": data["total_beds"],
            "occupied_beds": data["occupied_beds"],
            "available_beds": data["available_beds"],
            "occupancy_rate": occ
        })

    # Recent transfers
    recent_transfers = db_session.query(BedTransfer).options(
        joinedload(BedTransfer.admission).joinedload(Admission.patient).joinedload(Patient.user),
        joinedload(BedTransfer.from_bed),
        joinedload(BedTransfer.to_bed),
        joinedload(BedTransfer.transferred_by)
    ).order_by(BedTransfer.transferred_at.desc()).limit(5).all()

    # Recent admissions
    recent_admissions = db_session.query(Admission).options(
        joinedload(Admission.patient).joinedload(Patient.user),
        joinedload(Admission.doctor).joinedload(Doctor.user),
        joinedload(Admission.bed).joinedload(Bed.room),
        joinedload(Admission.department)
    ).order_by(Admission.admission_date.desc()).limit(5).all()

    return {
        "total_beds": total_beds,
        "occupied_beds": occupied_beds,
        "available_beds": available_beds,
        "reserved_beds": reserved_beds,
        "maintenance_beds": maintenance_beds,
        "occupancy_percentage": occupancy_percentage,
        "total_rooms": total_rooms,
        "active_admissions_count": active_admissions_count,
        "total_admissions_historical": total_admissions_historical,
        "room_types_breakdown": room_types_data,
        "recent_transfers": recent_transfers,
        "recent_admissions": recent_admissions
    }


# =====================================================================
# Admission Records & History Queries
# =====================================================================

def get_admission_detail(db_session: Session, admission_id: int) -> Admission:
    """Returns detailed admission record with eager loaded relationships."""
    adm = db_session.query(Admission).options(
        joinedload(Admission.patient).joinedload(Patient.user),
        joinedload(Admission.doctor).joinedload(Doctor.user),
        joinedload(Admission.nurse),
        joinedload(Admission.bed).joinedload(Bed.room).joinedload(Room.department),
        joinedload(Admission.department),
        joinedload(Admission.transfers).joinedload(BedTransfer.from_bed),
        joinedload(Admission.transfers).joinedload(BedTransfer.to_bed),
        joinedload(Admission.transfers).joinedload(BedTransfer.transferred_by),
        joinedload(Admission.bill)
    ).filter(Admission.id == admission_id).first()

    if not adm:
        raise AdmissionNotFoundError(f"Admission #{admission_id} not found.")

    return adm


def get_patient_admission_history(db_session: Session, patient_id: int) -> List[Admission]:
    """Returns chronological admission history for a patient."""
    return db_session.query(Admission).options(
        joinedload(Admission.bed).joinedload(Bed.room),
        joinedload(Admission.doctor).joinedload(Doctor.user),
        joinedload(Admission.department),
        joinedload(Admission.transfers)
    ).filter(
        Admission.patient_id == patient_id
    ).order_by(Admission.admission_date.desc()).all()


def list_admissions(
    db_session: Session,
    status: Optional[AdmissionStatusEnum] = None,
    patient_id: Optional[int] = None,
    doctor_id: Optional[int] = None,
    department_id: Optional[int] = None,
    search: Optional[str] = None
) -> List[Admission]:
    """
    Lists admissions with flexible filtering and patient/bed text search.
    """
    query = db_session.query(Admission).options(
        joinedload(Admission.patient).joinedload(Patient.user),
        joinedload(Admission.doctor).joinedload(Doctor.user),
        joinedload(Admission.bed).joinedload(Bed.room),
        joinedload(Admission.department)
    )

    if status:
        query = query.filter(Admission.status == status)

    if patient_id:
        query = query.filter(Admission.patient_id == patient_id)

    if doctor_id:
        query = query.filter(Admission.admitting_doctor_id == doctor_id)

    if department_id:
        query = query.filter(Admission.department_id == department_id)

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.join(Admission.patient).join(Patient.user).join(Admission.bed).filter(
            or_(
                User.first_name.ilike(term),
                User.last_name.ilike(term),
                Bed.bed_number.ilike(term),
                Admission.admission_reason.ilike(term)
            )
        )

    return query.order_by(Admission.admission_date.desc()).all()
