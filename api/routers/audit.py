"""
FastAPI REST API Router for System Audit Logging and Administrative Compliance.
"""

from typing import Optional, List
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import User, RoleEnum, AuditLog
from api.dependencies import get_current_user, require_roles
from api.schemas.audit import (
    AuditLogResponse,
    AuditLogListResponse,
    AuditActionsListResponse,
    AuditResourceTypesResponse,
    AuditStatsResponse,
    AuditLogUserSummary
)
from core.services import audit_service

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])


def _format_audit_response(item: AuditLog) -> AuditLogResponse:
    """Helper to convert AuditLog ORM instance to Pydantic response format."""
    user_summary = None
    user_email = None
    user_name = None
    user_role = None

    if item.user:
        role_str = item.user.role.value if hasattr(item.user.role, "value") else str(item.user.role)
        user_email = item.user.email
        user_name = item.user.full_name
        user_role = role_str
        user_summary = AuditLogUserSummary(
            id=item.user.id,
            email=item.user.email,
            full_name=item.user.full_name,
            role=role_str
        )

    return AuditLogResponse(
        id=item.id,
        user_id=item.user_id,
        user_email=user_email,
        user_full_name=user_name,
        user_role=user_role,
        user=user_summary,
        action=item.action,
        resource_type=item.resource_type,
        resource_id=item.resource_id,
        ip_address=item.ip_address,
        details=item.details or {},
        timestamp=item.created_at,
        created_at=item.created_at
    )


@router.get("", response_model=AuditLogListResponse)
@router.get("/", response_model=AuditLogListResponse)
def list_audit_logs(
    user_id: Optional[int] = Query(None, description="Filter by actor user ID"),
    action: Optional[str] = Query(None, description="Filter by action name (e.g. USER_LOGIN, PATIENT_CREATE)"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type (e.g. Patient, Appointment)"),
    resource_id: Optional[int] = Query(None, description="Filter by specific entity primary key ID"),
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD) for event filter"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD) for event filter"),
    q: Optional[str] = Query(None, description="Keyword search across action, resource, metadata, and user"),
    limit: int = Query(50, ge=1, le=500, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.ADMIN]))
):
    """
    Administrative endpoint to search and filter system audit logs.
    Strictly restricted to Admin users.
    """
    items, total = audit_service.search_audit_logs(
        db=db,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        start_date=start_date,
        end_date=end_date,
        search_query=q,
        limit=limit,
        offset=offset
    )

    formatted_items = [_format_audit_response(item) for item in items]

    return AuditLogListResponse(
        items=formatted_items,
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/stats", response_model=AuditStatsResponse)
def get_audit_statistics(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.ADMIN]))
):
    """Retrieves operational summary statistics for audit and security tracking."""
    return audit_service.get_audit_stats(db)


@router.get("/actions", response_model=AuditActionsListResponse)
def get_audit_actions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.ADMIN]))
):
    """Returns list of distinct action names currently present in the audit log."""
    actions = audit_service.get_distinct_actions(db)
    return AuditActionsListResponse(actions=actions)


@router.get("/resource-types", response_model=AuditResourceTypesResponse)
def get_audit_resource_types(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.ADMIN]))
):
    """Returns list of distinct resource types currently recorded in the audit log."""
    resource_types = audit_service.get_distinct_resource_types(db)
    return AuditResourceTypesResponse(resource_types=resource_types)


@router.get("/{audit_id}", response_model=AuditLogResponse)
def get_audit_log_detail(
    audit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.ADMIN]))
):
    """Retrieves a specific audit log record by ID. Restricted to Admin."""
    log_entry = db.query(AuditLog).filter(AuditLog.id == audit_id).first()
    if not log_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit log #{audit_id} not found."
        )
    return _format_audit_response(log_entry)
