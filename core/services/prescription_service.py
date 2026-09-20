import re
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any, Union
from sqlalchemy.orm import Session
from sqlalchemy import desc

from core.models import (
    Prescription, PrescriptionItem, Medicine, MedicineBatch,
    PrescriptionStatusEnum, Patient, Doctor, MedicalRecord, User,
    AuditLog, Notification, NotificationTypeEnum, RoleEnum,
    StockTransaction, StockTransactionTypeEnum
)


# =====================================================================
# Custom Service Exceptions
# =====================================================================

class PrescriptionServiceError(Exception):
    """Base exception for prescription management errors."""
    pass


class InvalidPrescriptionDataError(PrescriptionServiceError):
    """Raised when medication, dosage, duration, or quantity fails validation."""
    pass


class PrescriptionNotFoundError(PrescriptionServiceError):
    """Raised when the requested prescription cannot be found."""
    pass


class PrescriptionPermissionError(PrescriptionServiceError):
    """Raised when a user lacks required clinical or role permissions to access/amend a prescription."""
    pass


class InventoryShortageError(PrescriptionServiceError):
    """Raised when requested medications have insufficient pharmacy inventory."""
    pass


# =====================================================================
# Validation Helpers
# =====================================================================

def validate_prescription_item(
    item_data: Dict[str, Any],
    db_session: Session
) -> Dict[str, Any]:
    """
    Validates a single medication item within a prescription order.
    Enforces non-empty strings, positive physiological durations (1-365 days),
    realistic quantities (1-1000 units), and existing medicine inventory catalog entries.
    """
    medicine_id = item_data.get("medicine_id")
    if not medicine_id:
        raise InvalidPrescriptionDataError("Each prescription item must specify a valid medication.")

    try:
        med_id_int = int(medicine_id)
    except (ValueError, TypeError):
        raise InvalidPrescriptionDataError(f"Invalid medication identifier: '{medicine_id}'. Must be an integer ID.")

    medicine = db_session.query(Medicine).filter(Medicine.id == med_id_int).first()
    if not medicine:
        raise InvalidPrescriptionDataError(f"Medication with ID #{med_id_int} does not exist in the formulary catalog.")

    # Dosage
    dosage = item_data.get("dosage")
    if not dosage or not str(dosage).strip():
        raise InvalidPrescriptionDataError(f"Dosage is required for medication '{medicine.name}' (e.g., '500 mg', '10 ml').")
    dosage_clean = str(dosage).strip()
    if len(dosage_clean) > 50:
        raise InvalidPrescriptionDataError(f"Dosage for '{medicine.name}' cannot exceed 50 characters.")

    # Frequency
    frequency = item_data.get("frequency")
    if not frequency or not str(frequency).strip():
        raise InvalidPrescriptionDataError(f"Administration frequency is required for medication '{medicine.name}' (e.g., '1-0-1 after meals', 'BID').")
    frequency_clean = str(frequency).strip()
    if len(frequency_clean) > 50:
        raise InvalidPrescriptionDataError(f"Frequency for '{medicine.name}' cannot exceed 50 characters.")

    # Duration Days
    duration_val = item_data.get("duration_days")
    if duration_val is None:
        raise InvalidPrescriptionDataError(f"Duration is required for medication '{medicine.name}'.")
    try:
        duration_days = int(duration_val)
    except (ValueError, TypeError):
        raise InvalidPrescriptionDataError(f"Duration must be an integer number of days for '{medicine.name}'. Received: '{duration_val}'.")

    if duration_days <= 0:
        raise InvalidPrescriptionDataError(f"Prescribed duration ({duration_days} days) for '{medicine.name}' must be at least 1 day.")
    if duration_days > 365:
        raise InvalidPrescriptionDataError(f"Prescribed duration ({duration_days} days) for '{medicine.name}' cannot exceed 365 days (1 year).")

    # Quantity Prescribed
    qty_val = item_data.get("quantity_prescribed")
    if qty_val is None:
        # Default or calculate if omitted
        qty_val = item_data.get("quantity")
    if qty_val is None:
        raise InvalidPrescriptionDataError(f"Quantity prescribed is required for medication '{medicine.name}'.")
    try:
        quantity_prescribed = int(qty_val)
    except (ValueError, TypeError):
        raise InvalidPrescriptionDataError(f"Quantity prescribed must be an integer for '{medicine.name}'. Received: '{qty_val}'.")

    if quantity_prescribed <= 0:
        raise InvalidPrescriptionDataError(f"Prescribed quantity ({quantity_prescribed}) for '{medicine.name}' must be at least 1 unit.")
    if quantity_prescribed > 1000:
        raise InvalidPrescriptionDataError(f"Prescribed quantity ({quantity_prescribed}) for '{medicine.name}' cannot exceed 1,000 units.")

    # Instructions
    instructions = item_data.get("instructions")
    instructions_clean = str(instructions).strip() if instructions else None
    if instructions_clean and len(instructions_clean) > 200:
        raise InvalidPrescriptionDataError(f"Instructions for '{medicine.name}' cannot exceed 200 characters.")

    return {
        "medicine_id": med_id_int,
        "medicine": medicine,
        "dosage": dosage_clean,
        "frequency": frequency_clean,
        "duration_days": duration_days,
        "quantity_prescribed": quantity_prescribed,
        "instructions": instructions_clean
    }


def validate_prescription_data(
    doctor_id: int,
    patient_id: int,
    items: List[Dict[str, Any]],
    db_session: Session,
    medical_record_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Validates complete prescription order metadata, patient, doctor,
    and individual medicine items, preventing duplicate medicines in one order.
    """
    # Validate Doctor
    doctor = db_session.query(Doctor).filter(Doctor.user_id == doctor_id).first()
    if not doctor:
        # Also check User with DOCTOR or ADMIN role
        user_doc = db_session.query(User).filter(
            User.id == doctor_id,
            User.role.in_([RoleEnum.DOCTOR, RoleEnum.ADMIN])
        ).first()
        if not user_doc:
            raise InvalidPrescriptionDataError(f"Prescribing doctor with ID #{doctor_id} not found or lacks clinical prescribing credentials.")

    # Validate Patient
    patient = db_session.query(Patient).filter(Patient.user_id == patient_id).first()
    if not patient:
        user_pat = db_session.query(User).filter(
            User.id == patient_id,
            User.role == RoleEnum.PATIENT
        ).first()
        if not user_pat:
            raise InvalidPrescriptionDataError(f"Patient with ID #{patient_id} does not exist.")

    # Validate Medical Record linkage if provided
    if medical_record_id is not None:
        rec = db_session.query(MedicalRecord).filter(MedicalRecord.id == medical_record_id).first()
        if not rec:
            raise InvalidPrescriptionDataError(f"Referenced Medical Record #{medical_record_id} does not exist.")
        if rec.patient_id != patient_id:
            raise InvalidPrescriptionDataError(
                f"Referenced Medical Record #{medical_record_id} belongs to patient #{rec.patient_id}, not patient #{patient_id}."
            )

    # Validate Items
    if not items or len(items) == 0:
        raise InvalidPrescriptionDataError("A prescription order must contain at least one medication item.")

    validated_items = []
    seen_medicine_ids = set()

    for idx, item_data in enumerate(items, 1):
        clean_item = validate_prescription_item(item_data, db_session)
        med_id = clean_item["medicine_id"]

        if med_id in seen_medicine_ids:
            med_name = clean_item["medicine"].name
            raise InvalidPrescriptionDataError(
                f"Duplicate medication '{med_name}' (ID #{med_id}) detected in prescription item #{idx}. Combine dosages into a single order line."
            )

        seen_medicine_ids.add(med_id)
        validated_items.append(clean_item)

    return validated_items


# =====================================================================
# Core Prescription Business Logic
# =====================================================================

def create_prescription(
    db_session: Session,
    doctor_id: int,
    patient_id: int,
    items: List[Dict[str, Any]],
    medical_record_id: Optional[int] = None,
    notes: Optional[str] = None,
    actor_id: Optional[int] = None,
    ip_address: Optional[str] = None
) -> Prescription:
    """
    Creates an electronic prescription containing one or more validated medications.
    Dispatches patient notification and records security audit log.
    """
    validated_items = validate_prescription_data(
        doctor_id=doctor_id,
        patient_id=patient_id,
        items=items,
        db_session=db_session,
        medical_record_id=medical_record_id
    )

    clean_notes = str(notes).strip() if notes else None

    # Instantiate Prescription
    prescription = Prescription(
        medical_record_id=medical_record_id,
        patient_id=patient_id,
        doctor_id=doctor_id,
        status=PrescriptionStatusEnum.PENDING,
        notes=clean_notes
    )
    db_session.add(prescription)
    db_session.flush()

    # Create items
    item_summaries = []
    for clean_item in validated_items:
        rx_item = PrescriptionItem(
            prescription_id=prescription.id,
            medicine_id=clean_item["medicine_id"],
            dosage=clean_item["dosage"],
            frequency=clean_item["frequency"],
            duration_days=clean_item["duration_days"],
            instructions=clean_item["instructions"],
            quantity_prescribed=clean_item["quantity_prescribed"],
            quantity_dispensed=0
        )
        db_session.add(rx_item)
        item_summaries.append({
            "medicine_id": clean_item["medicine_id"],
            "medicine_name": clean_item["medicine"].name,
            "dosage": clean_item["dosage"],
            "frequency": clean_item["frequency"],
            "duration_days": clean_item["duration_days"],
            "quantity_prescribed": clean_item["quantity_prescribed"]
        })

    # Dispatch notification to patient
    doc_user = db_session.query(User).filter(User.id == doctor_id).first()
    doctor_name = doc_user.full_name if doc_user else f"Doctor #{doctor_id}"

    notif = Notification(
        user_id=patient_id,
        title="New Prescription Issued",
        message=f"Dr. {doctor_name} has issued an electronic prescription (Rx #{prescription.id}) with {len(validated_items)} medication(s).",
        type=NotificationTypeEnum.ALERT
    )
    db_session.add(notif)

    # Record Audit Log
    current_actor = actor_id or doctor_id
    audit = AuditLog(
        user_id=current_actor,
        action="PRESCRIPTION_CREATED",
        resource_type="Prescription",
        resource_id=prescription.id,
        details={
            "prescription_id": prescription.id,
            "patient_id": patient_id,
            "doctor_id": doctor_id,
            "medical_record_id": medical_record_id,
            "item_count": len(validated_items),
            "items": item_summaries,
            "notes": clean_notes,
            "created_by": current_actor
        },
        ip_address=ip_address
    )
    db_session.add(audit)

    db_session.commit()
    return prescription


def dispense_prescription(
    db_session: Session,
    prescription_id: int,
    actor_id: int,
    ip_address: Optional[str] = None,
    item_dispensations: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Dispenses prescribed medications using First-Expiring, First-Out (FEFO)
    batch deduction logic from active, unexpired inventory.
    Updates prescription fulfillment status and logs an audit record.
    """
    rx = db_session.query(Prescription).filter(Prescription.id == prescription_id).first()
    if not rx:
        raise PrescriptionNotFoundError(f"Prescription #{prescription_id} does not exist.")

    if rx.status == PrescriptionStatusEnum.DISPENSED:
        raise PrescriptionServiceError(f"Prescription #{prescription_id} has already been completely dispensed.")

    if rx.status == PrescriptionStatusEnum.CANCELLED:
        raise PrescriptionServiceError(f"Cannot dispense cancelled Prescription #{prescription_id}.")

    # Map requested item dispensations if specified
    dispensation_map = {}
    if item_dispensations:
        for itm in item_dispensations:
            dispensation_map[itm.get("prescription_item_id")] = itm.get("quantity_dispensed")

    deducted_batches = []
    total_units_dispensed = 0

    for item in rx.items:
        needed = item.quantity_prescribed - item.quantity_dispensed
        if needed <= 0:
            continue

        if item.id in dispensation_map:
            user_requested_qty = dispensation_map[item.id]
            if user_requested_qty is not None:
                needed = min(needed, max(0, int(user_requested_qty)))

        if needed <= 0:
            continue

        # Fetch active, unexpired batches ordered by earliest expiry date (FEFO)
        batches = db_session.query(MedicineBatch).filter(
            MedicineBatch.medicine_id == item.medicine_id,
            MedicineBatch.expiry_date >= date.today(),
            MedicineBatch.quantity_in_stock > 0
        ).order_by(MedicineBatch.expiry_date.asc()).all()

        dispensed_for_this_item = 0
        remaining_needed = needed

        for b in batches:
            if b.quantity_in_stock >= remaining_needed:
                units_deducted = remaining_needed
                b.quantity_in_stock -= remaining_needed
                dispensed_for_this_item += remaining_needed
                deducted_batches.append({
                    "medicine_id": item.medicine_id,
                    "medicine_name": item.medicine.name,
                    "batch_id": b.id,
                    "batch_number": b.batch_number,
                    "units_deducted": remaining_needed,
                    "remaining_batch_stock": b.quantity_in_stock
                })
                # Record Stock Movement
                st_txn = StockTransaction(
                    medicine_id=item.medicine_id,
                    batch_id=b.id,
                    transaction_type=StockTransactionTypeEnum.DISPENSED,
                    quantity=units_deducted,
                    unit_price=b.selling_price or item.medicine.unit_price,
                    reference_type="PRESCRIPTION",
                    reference_id=rx.id,
                    performed_by_id=actor_id,
                    notes=f"Prescription #{rx.id} dispensation: {units_deducted} unit(s) of {item.medicine.name}."
                )
                db_session.add(st_txn)
                remaining_needed = 0
                break
            else:
                deducted = b.quantity_in_stock
                dispensed_for_this_item += deducted
                deducted_batches.append({
                    "medicine_id": item.medicine_id,
                    "medicine_name": item.medicine.name,
                    "batch_id": b.id,
                    "batch_number": b.batch_number,
                    "units_deducted": deducted,
                    "remaining_batch_stock": 0
                })
                # Record Stock Movement
                st_txn = StockTransaction(
                    medicine_id=item.medicine_id,
                    batch_id=b.id,
                    transaction_type=StockTransactionTypeEnum.DISPENSED,
                    quantity=deducted,
                    unit_price=b.selling_price or item.medicine.unit_price,
                    reference_type="PRESCRIPTION",
                    reference_id=rx.id,
                    performed_by_id=actor_id,
                    notes=f"Prescription #{rx.id} partial batch dispensation: {deducted} unit(s) of {item.medicine.name}."
                )
                db_session.add(st_txn)
                remaining_needed -= deducted
                b.quantity_in_stock = 0

        item.quantity_dispensed += dispensed_for_this_item
        total_units_dispensed += dispensed_for_this_item

    # Re-evaluate overall prescription fulfillment status
    all_fulfilled = all(i.quantity_dispensed >= i.quantity_prescribed for i in rx.items)
    any_fulfilled = any(i.quantity_dispensed > 0 for i in rx.items)

    old_status = rx.status.value
    if all_fulfilled:
        rx.status = PrescriptionStatusEnum.DISPENSED
    elif any_fulfilled:
        rx.status = PrescriptionStatusEnum.PARTIALLY_DISPENSED

    # Notify patient
    notif_msg = f"Prescription #{rx.id} has been processed by the pharmacy. Status: {rx.status.value}."
    notif = Notification(
        user_id=rx.patient_id,
        title="Prescription Dispensed",
        message=notif_msg,
        type=NotificationTypeEnum.ALERT
    )
    db_session.add(notif)

    # Log Audit Trail
    audit = AuditLog(
        user_id=actor_id,
        action="PRESCRIPTION_DISPENSED",
        resource_type="Prescription",
        resource_id=rx.id,
        details={
            "prescription_id": rx.id,
            "patient_id": rx.patient_id,
            "previous_status": old_status,
            "new_status": rx.status.value,
            "total_units_dispensed": total_units_dispensed,
            "deducted_batches": deducted_batches,
            "dispensed_by": actor_id
        },
        ip_address=ip_address
    )
    db_session.add(audit)

    db_session.commit()

    return {
        "prescription_id": rx.id,
        "status": rx.status.value,
        "units_dispensed": total_units_dispensed,
        "deducted_batches": deducted_batches
    }


def cancel_prescription(
    db_session: Session,
    prescription_id: int,
    actor_id: int,
    cancellation_reason: str,
    ip_address: Optional[str] = None
) -> Prescription:
    """
    Cancels an unfulfilled or pending prescription with mandatory clinical cancellation reason.
    Logs an audit trail.
    """
    rx = db_session.query(Prescription).filter(Prescription.id == prescription_id).first()
    if not rx:
        raise PrescriptionNotFoundError(f"Prescription #{prescription_id} not found.")

    if rx.status == PrescriptionStatusEnum.DISPENSED:
        raise PrescriptionServiceError("Cannot cancel a prescription that has already been completely dispensed.")

    reason_clean = str(cancellation_reason).strip() if cancellation_reason else ""
    if not reason_clean:
        raise InvalidPrescriptionDataError("A valid clinical reason is required to cancel a prescription.")

    old_status = rx.status.value
    rx.status = PrescriptionStatusEnum.CANCELLED
    append_note = f"\n[Cancelled by User #{actor_id} on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}: {reason_clean}]"
    rx.notes = (rx.notes or "") + append_note

    # Disallow further dispensing on items
    audit = AuditLog(
        user_id=actor_id,
        action="PRESCRIPTION_CANCELLED",
        resource_type="Prescription",
        resource_id=rx.id,
        details={
            "prescription_id": rx.id,
            "patient_id": rx.patient_id,
            "previous_status": old_status,
            "new_status": rx.status.value,
            "cancellation_reason": reason_clean,
            "cancelled_by": actor_id
        },
        ip_address=ip_address
    )
    db_session.add(audit)

    # Notify patient
    notif = Notification(
        user_id=rx.patient_id,
        title="Prescription Cancelled",
        message=f"Prescription #{rx.id} was cancelled. Reason: {reason_clean}",
        type=NotificationTypeEnum.ALERT
    )
    db_session.add(notif)

    db_session.commit()
    return rx


def get_prescription_detail(
    db_session: Session,
    prescription_id: int,
    requester_user_id: int,
    requester_role: str
) -> Prescription:
    """
    Retrieves a single prescription with eager-loaded items and medicines.
    Enforces strict role-based access control and patient confidentiality.
    """
    rx = db_session.query(Prescription).filter(Prescription.id == prescription_id).first()
    if not rx:
        raise PrescriptionNotFoundError(f"Prescription #{prescription_id} does not exist.")

    # Role-based confidentiality enforcement
    role_str = str(requester_role).lower()
    if role_str == "patient":
        if rx.patient_id != requester_user_id:
            raise PrescriptionPermissionError(
                f"Unauthorized access: Patient #{requester_user_id} cannot access prescription #{prescription_id} belonging to another patient."
            )
    elif role_str in ["doctor", "pharmacist", "admin", "nurse"]:
        # Authorized clinical / pharmacy roles
        pass
    else:
        raise PrescriptionPermissionError(f"Role '{requester_role}' lacks authorization to view clinical prescriptions.")

    return rx


def list_prescriptions(
    db_session: Session,
    patient_id: Optional[int] = None,
    doctor_id: Optional[int] = None,
    status: Optional[str] = None,
    search: Optional[str] = None
) -> List[Prescription]:
    """
    Lists prescriptions with optional filtering by patient, doctor, status, and text search.
    """
    query = db_session.query(Prescription)

    if patient_id is not None:
        query = query.filter(Prescription.patient_id == patient_id)

    if doctor_id is not None:
        query = query.filter(Prescription.doctor_id == doctor_id)

    if status:
        stat_lower = status.strip().lower()
        if stat_lower != "all":
            query = query.filter(Prescription.status == stat_lower)

    if search:
        s_term = f"%{search.strip()}%"
        query = query.join(Prescription.patient).join(Patient.user).filter(
            User.first_name.ilike(s_term) |
            User.last_name.ilike(s_term) |
            User.email.ilike(s_term) |
            Prescription.notes.ilike(s_term)
        )

    return query.order_by(desc(Prescription.created_at)).all()
