from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any, Union
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc

from core.models import (
    LabOrder, LabResult, LabTest, LabTestType,
    Patient, Doctor, MedicalRecord, User,
    AuditLog, Notification, NotificationTypeEnum,
    RoleEnum, LabOrderStatusEnum
)


# =====================================================================
# Custom Service Exceptions
# =====================================================================

class LaboratoryServiceError(Exception):
    """Base exception for laboratory service errors."""
    pass


class InvalidLabDataError(LaboratoryServiceError):
    """Raised when submitted lab order or result data fails validation."""
    pass


class LabOrderNotFoundError(LaboratoryServiceError):
    """Raised when the requested lab order is not found."""
    pass


class LabPermissionError(LaboratoryServiceError):
    """Raised when a user attempts an unauthorized lab operation."""
    pass


class LabInvalidStateTransitionError(LaboratoryServiceError):
    """Raised when an order status transition is invalid according to clinical workflow."""
    pass


# =====================================================================
# Service Functions
# =====================================================================

def order_lab_tests(
    db_session: Session,
    patient_id: int,
    doctor_id: int,
    test_ids: List[int],
    medical_record_id: Optional[int] = None,
    priority: str = "routine",
    clinical_notes: Optional[str] = None,
    ordering_user_id: Optional[int] = None,
    user_role: Optional[str] = None
) -> List[LabOrder]:
    """
    Step 1 of Workflow: Doctor orders test(s).
    Validates patient, doctor, and test catalog items.
    Creates LabOrder instances with status ORDERED.
    """
    if user_role:
        norm_role = str(user_role).lower().replace("roleenum.", "")
        if norm_role not in ["doctor", "admin"]:
            raise LabPermissionError("Only authorized medical doctors or administrators can order diagnostic laboratory tests.")

    if not patient_id:
        raise InvalidLabDataError("A valid patient identifier is required to order laboratory tests.")

    patient = db_session.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise InvalidLabDataError(f"Patient #{patient_id} does not exist in the hospital registry.")

    if not doctor_id:
        raise InvalidLabDataError("A valid ordering physician identifier is required.")

    doctor = db_session.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise InvalidLabDataError(f"Doctor #{doctor_id} does not exist in the medical staff directory.")

    if not test_ids or not isinstance(test_ids, (list, tuple)):
        raise InvalidLabDataError("At least one diagnostic laboratory test must be selected.")

    valid_priorities = ["routine", "urgent", "stat"]
    clean_priority = str(priority).strip().lower() if priority else "routine"
    if clean_priority not in valid_priorities:
        raise InvalidLabDataError(f"Invalid priority '{priority}'. Must be one of: {', '.join(valid_priorities)}.")

    created_orders: List[LabOrder] = []
    now = datetime.now(timezone.utc)

    for tid in test_ids:
        try:
            tid_int = int(tid)
        except (ValueError, TypeError):
            raise InvalidLabDataError(f"Invalid test ID '{tid}'. Must be an integer identifier.")

        lab_test = db_session.query(LabTest).filter(LabTest.id == tid_int).first()
        if not lab_test:
            raise InvalidLabDataError(f"Diagnostic test ID #{tid_int} was not found in the test formulary catalog.")

        order = LabOrder(
            patient_id=patient.id,
            doctor_id=doctor.id,
            medical_record_id=medical_record_id,
            test_id=lab_test.id,
            status=LabOrderStatusEnum.ORDERED,
            priority=clean_priority,
            clinical_notes=str(clinical_notes).strip() if clinical_notes else None,
            ordered_at=now
        )
        db_session.add(order)
        created_orders.append(order)

    db_session.flush()

    # Dispatched Audit Log
    actor_id = ordering_user_id or doctor_id
    audit = AuditLog(
        user_id=actor_id,
        action="LAB_TESTS_ORDERED",
        resource_type="LabOrder",
        resource_id=created_orders[0].id if created_orders else None,
        ip_address=None,
        details_json=f'{{"patient_id": {patient.id}, "doctor_id": {doctor.id}, "order_count": {len(created_orders)}, "priority": "{clean_priority}"}}'
    )
    db_session.add(audit)

    # If urgent or stat, alert the laboratory team
    if clean_priority in ["urgent", "stat"]:
        lab_techs = db_session.query(User).filter(User.role == RoleEnum.LAB_TECH).all()
        for tech in lab_techs:
            notif = Notification(
                user_id=tech.id,
                title=f"🚨 {clean_priority.upper()} Lab Order: {patient.user.full_name}",
                message=f"Urgent diagnostic investigation ordered by Dr. {doctor.user.last_name} for patient {patient.user.full_name}.",
                type=NotificationTypeEnum.CRITICAL if clean_priority == "stat" else NotificationTypeEnum.ALERT
            )
            db_session.add(notif)

    db_session.commit()
    return created_orders


def receive_and_collect_sample(
    db_session: Session,
    order_id: int,
    technician_id: int,
    notes: Optional[str] = None,
    user_role: Optional[str] = None
) -> LabOrder:
    """
    Step 2 & 3 of Workflow: Lab technician receives order & sample collected.
    Transitions ORDERED → SAMPLE_COLLECTED.
    """
    if user_role:
        norm_role = str(user_role).lower().replace("roleenum.", "")
        if norm_role not in ["lab_tech", "admin", "nurse", "doctor"]:
            raise LabPermissionError("Only laboratory technicians, nurses, or administrators can log sample collections.")

    order = db_session.query(LabOrder).filter(LabOrder.id == order_id).first()
    if not order:
        raise LabOrderNotFoundError(f"Lab Order #{order_id} does not exist.")

    if order.status == LabOrderStatusEnum.CANCELLED:
        raise LabInvalidStateTransitionError("Cannot collect specimen for a cancelled laboratory order.")
    if order.status == LabOrderStatusEnum.COMPLETED:
        raise LabInvalidStateTransitionError("Order has already been completed and verified.")
    if order.status in [LabOrderStatusEnum.SAMPLE_COLLECTED, LabOrderStatusEnum.PROCESSING]:
        raise LabInvalidStateTransitionError(f"Specimen for Order #{order_id} has already been collected (status: {order.status.value}).")

    order.status = LabOrderStatusEnum.SAMPLE_COLLECTED
    order.sample_collected_at = datetime.now(timezone.utc)
    order.sample_collected_by_id = technician_id

    if notes:
        existing_notes = order.clinical_notes or ""
        order.clinical_notes = f"{existing_notes}\n[Sample Log]: {notes.strip()}".strip()

    audit = AuditLog(
        user_id=technician_id,
        action="LAB_SAMPLE_COLLECTED",
        resource_type="LabOrder",
        resource_id=order.id,
        ip_address=None,
        details_json=f'{{"order_id": {order.id}, "technician_id": {technician_id}, "test_code": "{order.test.test_code}"}}'
    )
    db_session.add(audit)
    db_session.commit()
    return order


def start_processing_order(
    db_session: Session,
    order_id: int,
    technician_id: int,
    user_role: Optional[str] = None
) -> LabOrder:
    """
    Step 4 of Workflow: Processing.
    Transitions SAMPLE_COLLECTED → PROCESSING.
    """
    if user_role:
        norm_role = str(user_role).lower().replace("roleenum.", "")
        if norm_role not in ["lab_tech", "admin"]:
            raise LabPermissionError("Only laboratory technicians or administrators can start test processing.")

    order = db_session.query(LabOrder).filter(LabOrder.id == order_id).first()
    if not order:
        raise LabOrderNotFoundError(f"Lab Order #{order_id} does not exist.")

    if order.status == LabOrderStatusEnum.CANCELLED:
        raise LabInvalidStateTransitionError("Cannot process a cancelled laboratory order.")
    if order.status == LabOrderStatusEnum.COMPLETED:
        raise LabInvalidStateTransitionError("Order has already been completed.")
    if order.status == LabOrderStatusEnum.ORDERED:
        raise LabInvalidStateTransitionError("Specimen must be collected before processing can begin.")
    if order.status == LabOrderStatusEnum.PROCESSING:
        return order  # Already in processing

    order.status = LabOrderStatusEnum.PROCESSING
    order.processing_started_at = datetime.now(timezone.utc)
    order.technician_id = technician_id

    audit = AuditLog(
        user_id=technician_id,
        action="LAB_PROCESSING_STARTED",
        resource_type="LabOrder",
        resource_id=order.id,
        ip_address=None,
        details_json=f'{{"order_id": {order.id}, "technician_id": {technician_id}}}'
    )
    db_session.add(audit)
    db_session.commit()
    return order


def enter_lab_result(
    db_session: Session,
    order_id: int,
    measured_value: Union[float, int, str],
    technician_id: int,
    technician_notes: Optional[str] = None,
    result_text: Optional[str] = None,
    user_role: Optional[str] = None
) -> LabOrder:
    """
    Step 5 of Workflow: Result entered.
    Calculates reference range thresholds (is_abnormal, critical_alert).
    Transitions PROCESSING (or SAMPLE_COLLECTED) → COMPLETED.
    Dispatches notifications to the ordering physician.
    """
    if user_role:
        norm_role = str(user_role).lower().replace("roleenum.", "")
        if norm_role not in ["lab_tech", "admin"]:
            raise LabPermissionError("Only certified laboratory technicians or administrators can enter diagnostic findings.")

    order = db_session.query(LabOrder).filter(LabOrder.id == order_id).first()
    if not order:
        raise LabOrderNotFoundError(f"Lab Order #{order_id} does not exist.")

    if order.status == LabOrderStatusEnum.CANCELLED:
        raise LabInvalidStateTransitionError("Cannot record results for a cancelled order.")
    if order.status == LabOrderStatusEnum.ORDERED:
        raise LabInvalidStateTransitionError("Specimen must be collected and processed before entering results.")

    # Validate measured value
    try:
        val_float = float(measured_value)
    except (ValueError, TypeError):
        raise InvalidLabDataError(f"Invalid measured numeric value: '{measured_value}'. Must be a valid number.")

    test = order.test
    is_abnormal = False
    critical_alert = False

    # Reference interval checking
    if test.reference_range_min is not None and val_float < test.reference_range_min:
        is_abnormal = True
        if val_float < test.reference_range_min * 0.7:
            critical_alert = True
    elif test.reference_range_max is not None and val_float > test.reference_range_max:
        is_abnormal = True
        if val_float > test.reference_range_max * 1.4:
            critical_alert = True

    now = datetime.now(timezone.utc)

    # Check if result already exists for this order
    result = order.result
    if not result:
        result = LabResult(
            lab_order=order,
            lab_order_id=order.id,
            measured_value=val_float,
            result_text=result_text.strip() if result_text else None,
            unit=test.unit or "",
            is_abnormal=is_abnormal,
            critical_alert=critical_alert,
            technician_notes=technician_notes.strip() if technician_notes else None,
            verified_at=now
        )
        order.result = result
        db_session.add(result)
    else:
        result.measured_value = val_float
        result.result_text = result_text.strip() if result_text else None
        result.unit = test.unit or ""
        result.is_abnormal = is_abnormal
        result.critical_alert = critical_alert
        result.technician_notes = technician_notes.strip() if technician_notes else None
        result.verified_at = now

    order.status = LabOrderStatusEnum.COMPLETED
    order.technician_id = technician_id
    order.completed_at = now

    # Notification to ordering doctor
    alert_tag = "CRITICAL FINDING" if critical_alert else ("Abnormal Result" if is_abnormal else "Normal Result")
    notif = Notification(
        user_id=order.doctor_id,
        title=f"Lab Results: {test.name} [{alert_tag}]",
        message=f"Results for {order.patient.user.full_name}: {val_float} {test.unit}. Notes: {technician_notes or 'Technician verified.'}",
        type=NotificationTypeEnum.CRITICAL if critical_alert else (NotificationTypeEnum.ALERT if is_abnormal else NotificationTypeEnum.SYSTEM)
    )
    db_session.add(notif)

    # Audit log
    audit = AuditLog(
        user_id=technician_id,
        action="LAB_RESULT_ENTERED",
        resource_type="LabOrder",
        resource_id=order.id,
        ip_address=None,
        details_json=f'{{"order_id": {order.id}, "measured_value": {val_float}, "is_abnormal": {is_abnormal}, "critical_alert": {critical_alert}}}'
    )
    db_session.add(audit)
    db_session.commit()
    db_session.refresh(order)
    return order



def doctor_review_lab_result(
    db_session: Session,
    order_id: int,
    doctor_id: int,
    review_notes: Optional[str] = None,
    user_role: Optional[str] = None
) -> LabOrder:
    """
    Step 6 of Workflow: Doctor reviews result.
    Allows ordering physician (or authorized doctor/admin) to review,
    document clinical remarks, and sign off on completed lab investigations.
    Notifies the patient that report is reviewed.
    """
    if user_role:
        norm_role = str(user_role).lower().replace("roleenum.", "")
        if norm_role not in ["doctor", "admin"]:
            raise LabPermissionError("Only medical doctors or hospital administrators can review diagnostic pathology reports.")

    order = db_session.query(LabOrder).filter(LabOrder.id == order_id).first()
    if not order:
        raise LabOrderNotFoundError(f"Lab Order #{order_id} does not exist.")

    if order.status != LabOrderStatusEnum.COMPLETED:
        raise LabInvalidStateTransitionError(f"Cannot perform clinical review: Order is in status '{order.status.value}', not COMPLETED.")

    order.doctor_reviewed = True
    order.doctor_reviewed_at = datetime.now(timezone.utc)
    order.doctor_review_notes = review_notes.strip() if review_notes else "Reviewed and acknowledged by attending physician."

    # Notify patient that doctor has reviewed their results
    notif = Notification(
        user_id=order.patient_id,
        title=f"Lab Results Reviewed: {order.test.name}",
        message=f"Dr. {order.doctor.user.last_name} has reviewed your {order.test.name} laboratory investigation report.",
        type=NotificationTypeEnum.SYSTEM
    )
    db_session.add(notif)

    audit = AuditLog(
        user_id=doctor_id,
        action="LAB_RESULT_DOCTOR_REVIEWED",
        resource_type="LabOrder",
        resource_id=order.id,
        ip_address=None,
        details_json=f'{{"order_id": {order.id}, "reviewed_by_doctor_id": {doctor_id}}}'
    )
    db_session.add(audit)
    db_session.commit()
    return order


def cancel_lab_order(
    db_session: Session,
    order_id: int,
    user_id: int,
    reason: str,
    user_role: Optional[str] = None
) -> LabOrder:
    """
    Cancels a pending or processing lab order with a mandatory clinical reason.
    Cannot cancel an order that is already COMPLETED.
    """
    if user_role:
        norm_role = str(user_role).lower().replace("roleenum.", "")
        if norm_role not in ["doctor", "lab_tech", "admin"]:
            raise LabPermissionError("You do not have authorization to cancel laboratory orders.")

    if not reason or not str(reason).strip():
        raise InvalidLabDataError("A clinical or operational justification reason is mandatory to cancel a lab order.")

    order = db_session.query(LabOrder).filter(LabOrder.id == order_id).first()
    if not order:
        raise LabOrderNotFoundError(f"Lab Order #{order_id} does not exist.")

    if order.status == LabOrderStatusEnum.COMPLETED:
        raise LabInvalidStateTransitionError("Completed laboratory orders cannot be cancelled once results are verified.")
    if order.status == LabOrderStatusEnum.CANCELLED:
        return order

    order.status = LabOrderStatusEnum.CANCELLED
    order.cancelled_at = datetime.now(timezone.utc)
    order.cancelled_by_id = user_id
    order.cancellation_reason = str(reason).strip()

    audit = AuditLog(
        user_id=user_id,
        action="LAB_ORDER_CANCELLED",
        resource_type="LabOrder",
        resource_id=order.id,
        ip_address=None,
        details_json=f'{{"order_id": {order.id}, "reason": "{order.cancellation_reason}"}}'
    )
    db_session.add(audit)
    db_session.commit()
    return order


def get_lab_order_detail(
    db_session: Session,
    order_id: int,
    requester_user_id: int,
    requester_role: str
) -> LabOrder:
    """
    Step 7 of Workflow & General RBAC: Patient can view result.
    Enforces that patients can ONLY access their own orders.
    Doctors, Lab Techs, Nurses, and Admins can access clinical orders.
    """
    order = db_session.query(LabOrder).filter(LabOrder.id == order_id).first()
    if not order:
        raise LabOrderNotFoundError(f"Lab Order #{order_id} was not found.")

    norm_role = str(requester_role).lower().replace("roleenum.", "")
    if norm_role == "patient":
        if order.patient_id != requester_user_id:
            raise LabPermissionError("Access denied: You are not authorized to view this patient's confidential laboratory report.")

    return order


def list_lab_orders(
    db_session: Session,
    status_filter: Optional[str] = None,
    patient_id: Optional[int] = None,
    doctor_id: Optional[int] = None,
    search_query: Optional[str] = None,
    priority: Optional[str] = None,
    unreviewed_only: bool = False,
    limit: int = 100,
    offset: int = 0
) -> List[LabOrder]:
    """
    Lists lab orders with versatile filters and search criteria.
    """
    query = db_session.query(LabOrder).join(LabOrder.patient).join(Patient.user).join(LabOrder.test)

    if status_filter and status_filter.lower() != "all":
        try:
            status_enum = LabOrderStatusEnum(status_filter.lower())
            query = query.filter(LabOrder.status == status_enum)
        except ValueError:
            pass

    if patient_id:
        query = query.filter(LabOrder.patient_id == patient_id)

    if doctor_id:
        query = query.filter(LabOrder.doctor_id == doctor_id)

    if priority and priority.lower() != "all":
        query = query.filter(LabOrder.priority == priority.lower())

    if unreviewed_only:
        query = query.filter(
            LabOrder.status == LabOrderStatusEnum.COMPLETED,
            LabOrder.doctor_reviewed.is_(False)
        )

    if search_query:
        sq = f"%{search_query.strip()}%"
        # Support numeric order ID search
        clean_num = search_query.strip().replace("#", "")
        order_id_filter = int(clean_num) if clean_num.isdigit() else -1

        query = query.filter(
            or_(
                LabOrder.id == order_id_filter,
                User.first_name.ilike(sq),
                User.last_name.ilike(sq),
                User.email.ilike(sq),
                User.phone.ilike(sq),
                LabTest.name.ilike(sq),
                LabTest.test_code.ilike(sq)
            )
        )

    return query.order_by(desc(LabOrder.ordered_at)).offset(offset).limit(limit).all()


def get_patient_lab_history(
    db_session: Session,
    patient_id: int,
    test_id: Optional[int] = None
) -> List[LabOrder]:
    """
    Retrieves complete lab history for a patient to track longitudinal trends.
    """
    query = db_session.query(LabOrder).filter(LabOrder.patient_id == patient_id)
    if test_id:
        query = query.filter(LabOrder.test_id == test_id)
    return query.order_by(desc(LabOrder.ordered_at)).all()


def create_or_update_lab_test(
    db_session: Session,
    name: str,
    test_code: str,
    sample_type: str,
    cost: Union[float, int, Decimal],
    unit: Optional[str] = None,
    reference_range_min: Optional[float] = None,
    reference_range_max: Optional[float] = None,
    description: Optional[str] = None,
    department_id: Optional[int] = None,
    test_id: Optional[int] = None,
    user_role: Optional[str] = None
) -> LabTest:
    """
    Test Formulary Catalog Management: Add or update diagnostic tests.
    """
    if user_role:
        norm_role = str(user_role).lower().replace("roleenum.", "")
        if norm_role not in ["lab_tech", "admin"]:
            raise LabPermissionError("Only laboratory personnel or administrators can modify the test formulary catalog.")

    if not name or not str(name).strip():
        raise InvalidLabDataError("Diagnostic test name is mandatory.")
    if not test_code or not str(test_code).strip():
        raise InvalidLabDataError("Test code identifier is mandatory (e.g., 'CBC', 'LFT').")
    if not sample_type or not str(sample_type).strip():
        raise InvalidLabDataError("Specimen sample type is mandatory (e.g., 'Blood', 'Serum', 'Urine').")

    try:
        cost_dec = Decimal(str(cost))
        if cost_dec < 0:
            raise ValueError()
    except Exception:
        raise InvalidLabDataError("Cost fee must be a positive numeric value.")

    min_f = float(reference_range_min) if reference_range_min is not None and str(reference_range_min).strip() != "" else None
    max_f = float(reference_range_max) if reference_range_max is not None and str(reference_range_max).strip() != "" else None

    if min_f is not None and max_f is not None and min_f > max_f:
        raise InvalidLabDataError("Reference range minimum cannot exceed reference range maximum.")

    clean_code = str(test_code).strip().upper()
    clean_name = str(name).strip()

    if test_id:
        test = db_session.query(LabTest).filter(LabTest.id == test_id).first()
        if not test:
            raise InvalidLabDataError(f"Lab Test #{test_id} not found.")
        # Check uniqueness of test_code and name if changed
        existing = db_session.query(LabTest).filter(
            or_(LabTest.test_code == clean_code, LabTest.name == clean_name),
            LabTest.id != test_id
        ).first()
        if existing:
            raise InvalidLabDataError(f"Another test with code '{clean_code}' or name '{clean_name}' already exists.")
    else:
        existing = db_session.query(LabTest).filter(
            or_(LabTest.test_code == clean_code, LabTest.name == clean_name)
        ).first()
        if existing:
            raise InvalidLabDataError(f"Test with code '{clean_code}' or name '{clean_name}' already exists.")
        test = LabTest()
        db_session.add(test)

    test.name = clean_name
    test.test_code = clean_code
    test.sample_type = str(sample_type).strip()
    test.unit = str(unit).strip() if unit else None
    test.reference_range_min = min_f
    test.reference_range_max = max_f
    test.cost = cost_dec
    test.description = str(description).strip() if description else None
    test.department_id = department_id
    test.is_active = True

    db_session.commit()
    return test
