import re
from datetime import datetime, date, time, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union
from sqlalchemy import or_, desc, func
from sqlalchemy.orm import Session, joinedload

from backend.models.audit import AuditLog
from backend.models.user import User


# Sensitive fields regex pattern (case-insensitive substring match)
SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|hash|token|secret|authorization|bearer|credit_?card|card_?num|cvv|cvc|ssn|aadhaar|pan(_number)?|api_?key|private_?key|pin)",
    re.IGNORECASE
)


def sanitize_metadata(data: Any) -> Any:
    """
    Recursively scrubs sensitive keys and values from dictionary/list structures
    and converts non-serializable objects (Decimal, datetime, date, enum) to JSON-friendly primitives.
    """
    if data is None:
        return {}

    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            key_str = str(key)
            if SENSITIVE_KEY_PATTERN.search(key_str):
                sanitized[key_str] = "[REDACTED]"
            else:
                sanitized[key_str] = sanitize_metadata(value)
        return sanitized

    if isinstance(data, (list, tuple, set)):
        return [sanitize_metadata(item) for item in data]

    if isinstance(data, (datetime, date)):
        return data.isoformat()

    if isinstance(data, Decimal):
        return float(data)

    if hasattr(data, "value"):
        # Enum value
        return data.value

    return data


# Canonical Action Constants
class AuditActions:
    LOGIN = "USER_LOGIN"
    LOGIN_FAILED = "USER_LOGIN_FAILED"
    LOGOUT = "USER_LOGOUT"
    PATIENT_CREATE = "PATIENT_CREATE"
    PATIENT_UPDATE = "PATIENT_UPDATE"
    APPOINTMENT_CREATE = "APPOINTMENT_CREATE"
    APPOINTMENT_UPDATE = "APPOINTMENT_UPDATE"
    APPOINTMENT_CANCEL = "APPOINTMENT_CANCEL"
    MEDICAL_RECORD_CREATE = "MEDICAL_RECORD_CREATE"
    MEDICAL_RECORD_UPDATE = "MEDICAL_RECORD_UPDATE"
    PRESCRIPTION_CREATE = "PRESCRIPTION_CREATE"
    PRESCRIPTION_UPDATE = "PRESCRIPTION_UPDATE"
    PRESCRIPTION_DISPENSE = "PRESCRIPTION_DISPENSE"
    BILLING_CREATE = "BILLING_CREATE"
    BILLING_UPDATE = "BILLING_UPDATE"
    PAYMENT_RECORDED = "PAYMENT_RECORDED"
    INVENTORY_CREATE = "INVENTORY_CREATE"
    INVENTORY_UPDATE = "INVENTORY_UPDATE"
    STOCK_IN = "STOCK_IN"
    STOCK_OUT = "STOCK_OUT"
    ADMISSION_CREATE = "ADMISSION_CREATE"
    ADMISSION_DISCHARGE = "ADMISSION_DISCHARGE"
    ADMISSION_TRANSFER = "ADMISSION_TRANSFER"


def log_action(
    db: Session,
    action: str,
    resource_type: str,
    resource_id: Optional[int] = None,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    commit: bool = True
) -> AuditLog:
    """
    Creates and records a sanitized AuditLog entry.
    """
    clean_metadata = sanitize_metadata(metadata or {})

    audit = AuditLog(
        user_id=user_id,
        action=action.strip(),
        resource_type=resource_type.strip(),
        resource_id=resource_id,
        ip_address=ip_address,
        details=clean_metadata
    )

    db.add(audit)
    if commit:
        try:
            db.commit()
            db.refresh(audit)
        except Exception:
            db.rollback()
            raise
    else:
        db.flush()

    return audit


# ---------------------------------------------------------------------
# Specialized Action Loggers for Hospital Operations
# ---------------------------------------------------------------------

def log_login(
    db: Session,
    user_id: Optional[int],
    ip_address: Optional[str] = None,
    success: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
    commit: bool = True
) -> AuditLog:
    action = AuditActions.LOGIN if success else AuditActions.LOGIN_FAILED
    details = metadata or {}
    if not success and "reason" not in details:
        details["reason"] = "Invalid authentication credentials"
    return log_action(
        db=db,
        action=action,
        resource_type="User",
        resource_id=user_id,
        user_id=user_id,
        ip_address=ip_address,
        metadata=details,
        commit=commit
    )


def log_logout(
    db: Session,
    user_id: int,
    ip_address: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    commit: bool = True
) -> AuditLog:
    details = metadata or {"status": "User logged out securely"}
    return log_action(
        db=db,
        action=AuditActions.LOGOUT,
        resource_type="User",
        resource_id=user_id,
        user_id=user_id,
        ip_address=ip_address,
        metadata=details,
        commit=commit
    )


def log_patient_creation(
    db: Session,
    patient_id: int,
    user_id: int,
    actor_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    commit: bool = True
) -> AuditLog:
    return log_action(
        db=db,
        action=AuditActions.PATIENT_CREATE,
        resource_type="Patient",
        resource_id=patient_id,
        user_id=actor_id or user_id,
        ip_address=ip_address,
        metadata=metadata or {},
        commit=commit
    )


def log_patient_update(
    db: Session,
    patient_id: int,
    user_id: int,
    actor_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    commit: bool = True
) -> AuditLog:
    return log_action(
        db=db,
        action=AuditActions.PATIENT_UPDATE,
        resource_type="Patient",
        resource_id=patient_id,
        user_id=actor_id or user_id,
        ip_address=ip_address,
        metadata=metadata or {},
        commit=commit
    )


def log_appointment_change(
    db: Session,
    appointment_id: int,
    action: str,
    actor_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    commit: bool = True
) -> AuditLog:
    return log_action(
        db=db,
        action=action,
        resource_type="Appointment",
        resource_id=appointment_id,
        user_id=actor_id,
        ip_address=ip_address,
        metadata=metadata or {},
        commit=commit
    )


def log_medical_record_change(
    db: Session,
    record_id: int,
    action: str,
    actor_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    commit: bool = True
) -> AuditLog:
    return log_action(
        db=db,
        action=action,
        resource_type="MedicalRecord",
        resource_id=record_id,
        user_id=actor_id,
        ip_address=ip_address,
        metadata=metadata or {},
        commit=commit
    )


def log_prescription_change(
    db: Session,
    prescription_id: int,
    action: str,
    actor_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    commit: bool = True
) -> AuditLog:
    return log_action(
        db=db,
        action=action,
        resource_type="Prescription",
        resource_id=prescription_id,
        user_id=actor_id,
        ip_address=ip_address,
        metadata=metadata or {},
        commit=commit
    )


def log_billing_change(
    db: Session,
    bill_id: int,
    action: str,
    actor_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    commit: bool = True
) -> AuditLog:
    return log_action(
        db=db,
        action=action,
        resource_type="Bill",
        resource_id=bill_id,
        user_id=actor_id,
        ip_address=ip_address,
        metadata=metadata or {},
        commit=commit
    )


def log_inventory_change(
    db: Session,
    resource_id: int,
    action: str,
    resource_type: str = "Medicine",
    actor_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    commit: bool = True
) -> AuditLog:
    return log_action(
        db=db,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=actor_id,
        ip_address=ip_address,
        metadata=metadata or {},
        commit=commit
    )


def log_admission_discharge(
    db: Session,
    admission_id: int,
    action: str,
    actor_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    commit: bool = True
) -> AuditLog:
    return log_action(
        db=db,
        action=action,
        resource_type="Admission",
        resource_id=admission_id,
        user_id=actor_id,
        ip_address=ip_address,
        metadata=metadata or {},
        commit=commit
    )


# ---------------------------------------------------------------------
# Search and Filtering Engine
# ---------------------------------------------------------------------

def search_audit_logs(
    db: Session,
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    start_date: Optional[Union[datetime, date, str]] = None,
    end_date: Optional[Union[datetime, date, str]] = None,
    search_query: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> Tuple[List[AuditLog], int]:
    """
    Searches and filters audit logs with comprehensive parameters and pagination.
    Returns (items, total_count).
    """
    query = db.query(AuditLog).outerjoin(AuditLog.user).options(joinedload(AuditLog.user))

    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)

    if action:
        # Match action exact or partial
        query = query.filter(AuditLog.action.ilike(f"%{action.strip()}%"))

    if resource_type:
        query = query.filter(AuditLog.resource_type.ilike(f"%{resource_type.strip()}%"))

    if resource_id is not None:
        query = query.filter(AuditLog.resource_id == resource_id)

    # Date handling
    if start_date:
        if isinstance(start_date, str):
            start_dt = datetime.fromisoformat(start_date)
        elif isinstance(start_date, date) and not isinstance(start_date, datetime):
            start_dt = datetime.combine(start_date, time.min)
        else:
            start_dt = start_date
        query = query.filter(AuditLog.created_at >= start_dt)

    if end_date:
        if isinstance(end_date, str):
            end_dt = datetime.fromisoformat(end_date)
        elif isinstance(end_date, date) and not isinstance(end_date, datetime):
            end_dt = datetime.combine(end_date, time.max)
        else:
            end_dt = end_date
        query = query.filter(AuditLog.created_at <= end_dt)

    if search_query and search_query.strip():
        term = f"%{search_query.strip()}%"
        query = query.filter(
            or_(
                AuditLog.action.ilike(term),
                AuditLog.resource_type.ilike(term),
                AuditLog.details_json.ilike(term),
                AuditLog.ip_address.ilike(term),
                User.first_name.ilike(term),
                User.last_name.ilike(term),
                User.email.ilike(term),
            )
        )

    total_count = query.count()
    items = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()

    return items, total_count


def get_distinct_actions(db: Session) -> List[str]:
    """Retrieves list of distinct action types stored in the database."""
    results = db.query(AuditLog.action).distinct().order_by(AuditLog.action).all()
    return [r[0] for r in results if r[0]]


def get_distinct_resource_types(db: Session) -> List[str]:
    """Retrieves list of distinct resource types stored in the database."""
    results = db.query(AuditLog.resource_type).distinct().order_by(AuditLog.resource_type).all()
    return [r[0] for r in results if r[0]]


def get_audit_stats(db: Session) -> Dict[str, Any]:
    """Computes summary statistics for audit activity."""
    total_logs = db.query(func.count(AuditLog.id)).scalar() or 0
    total_logins = db.query(func.count(AuditLog.id)).filter(
        AuditLog.action.in_([AuditActions.LOGIN, "USER_LOGIN"])
    ).scalar() or 0
    total_security_events = db.query(func.count(AuditLog.id)).filter(
        AuditLog.action.ilike("%failed%")
    ).scalar() or 0

    top_actions = db.query(
        AuditLog.action, func.count(AuditLog.id)
    ).group_by(AuditLog.action).order_by(desc(func.count(AuditLog.id))).limit(5).all()

    top_resources = db.query(
        AuditLog.resource_type, func.count(AuditLog.id)
    ).group_by(AuditLog.resource_type).order_by(desc(func.count(AuditLog.id))).limit(5).all()

    return {
        "total_logs": total_logs,
        "total_logins": total_logins,
        "total_security_events": total_security_events,
        "top_actions": [{"action": act, "count": cnt} for act, cnt in top_actions],
        "top_resources": [{"resource_type": res, "count": cnt} for res, cnt in top_resources]
    }
