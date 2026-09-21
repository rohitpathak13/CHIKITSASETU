"""
FastAPI REST API Router for In-App Notifications.
Provides role-based notification lists, unread counters, single & bulk read acknowledgements,
administrative dispatches, and periodic operational event scanning.
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.user import User, RoleEnum
from backend.models.notification import (
    Notification,
    NotificationTypeEnum,
    NotificationPriorityEnum
)
from backend.services.notification_service import NotificationService
from backend.fastapi_service.dependencies import get_current_user, require_roles
from backend.fastapi_service.schemas.notification import (
    NotificationResponse,
    NotificationCreateRequest,
    NotificationListResponse,
    UnreadCountResponse,
    MarkReadResponse,
    OperationalScanResponse
)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def _to_response_dict(n: Notification) -> dict:
    """Converts a Notification SQLAlchemy instance into schema-ready dict."""
    d = n.to_dict()
    return {
        "id": d["id"],
        "user_id": d["user_id"],
        "target_role": d["target_role"],
        "title": d["title"],
        "message": d["message"],
        "type": d["type"],
        "priority": d["priority"],
        "is_read": d["is_read"],
        "read_at": d["read_at"],
        "reference_type": d["reference_type"],
        "reference_id": d["reference_id"],
        "action_url": d["action_url"],
        "metadata": d["metadata"],
        "created_at": d["created_at"],
        "updated_at": d["updated_at"]
    }


@router.get(
    "/",
    response_model=NotificationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Notifications for Current User",
    description="Retrieves paginated notifications visible to the authenticated user and their functional role."
)
def list_notifications(
    is_read: Optional[bool] = Query(None, description="Filter by read status (true or false)"),
    type: Optional[NotificationTypeEnum] = Query(None, description="Filter by notification category"),
    priority: Optional[NotificationPriorityEnum] = Query(None, description="Filter by priority urgency"),
    limit: int = Query(50, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> NotificationListResponse:
    """
    Returns personal notifications and role broadcasts tailored to the caller's role.
    """
    items, total = NotificationService.get_notification_history(
        db=db,
        user_id=current_user.id,
        role=current_user.role,
        is_read=is_read,
        type=type,
        priority=priority,
        limit=limit,
        offset=offset
    )

    unread_count = NotificationService.get_unread_count(
        db=db,
        user_id=current_user.id,
        role=current_user.role
    )

    return NotificationListResponse(
        items=[NotificationResponse(**_to_response_dict(n)) for n in items],
        total=total,
        unread_count=unread_count,
        limit=limit,
        offset=offset
    )


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Unread Notification Count",
    description="Returns the total count of unread notifications for badge counters."
)
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> UnreadCountResponse:
    """
    Calculates unread badge count visible to the caller.
    """
    count = NotificationService.get_unread_count(
        db=db,
        user_id=current_user.id,
        role=current_user.role
    )
    return UnreadCountResponse(unread_count=count)


@router.post(
    "/{id}/read",
    response_model=MarkReadResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark Specific Notification as Read"
)
def mark_notification_as_read(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> MarkReadResponse:
    """
    Updates the read status and timestamps for a specific notification.
    """
    notif = NotificationService.mark_as_read(
        db=db,
        notification_id=id,
        user_id=current_user.id,
        role=current_user.role
    )

    if not notif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification #{id} not found or not accessible to user #{current_user.id}."
        )

    return MarkReadResponse(
        success=True,
        message="Notification marked as read successfully.",
        notification_id=id,
        marked_count=1
    )


@router.post(
    "/read-all",
    response_model=MarkReadResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark All Visible Notifications as Read"
)
def mark_all_notifications_as_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> MarkReadResponse:
    """
    Batch marks all unread notifications visible to the caller as read.
    """
    count = NotificationService.mark_all_as_read(
        db=db,
        user_id=current_user.id,
        role=current_user.role
    )

    return MarkReadResponse(
        success=True,
        message=f"{count} unread notifications marked as read.",
        marked_count=count
    )


@router.post(
    "/",
    response_model=NotificationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Dispatch Custom In-App Notification"
)
def create_notification(
    payload: NotificationCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([
        RoleEnum.ADMIN,
        RoleEnum.DOCTOR,
        RoleEnum.NURSE,
        RoleEnum.RECEPTIONIST,
        RoleEnum.PHARMACIST
    ]))
) -> NotificationResponse:
    """
    Dispatches a custom clinical or administrative in-app notification.
    """
    if payload.user_id:
        target_user = db.query(User).filter(User.id == payload.user_id).first()
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Target recipient User #{payload.user_id} does not exist."
            )

    notif = NotificationService.create_notification(
        db=db,
        title=payload.title,
        message=payload.message,
        type=payload.type,
        priority=payload.priority,
        user_id=payload.user_id,
        target_role=payload.target_role,
        reference_type=payload.reference_type,
        reference_id=payload.reference_id,
        action_url=payload.action_url,
        metadata=payload.metadata
    )

    return NotificationResponse(**_to_response_dict(notif))


@router.post(
    "/scan",
    response_model=OperationalScanResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger Hospital Operational Event Scan",
    description="Evaluates outpatient appointment reminders, low inventory levels, batch expiries, and pending payments."
)
def trigger_operational_scan(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([
        RoleEnum.ADMIN,
        RoleEnum.PHARMACIST,
        RoleEnum.RECEPTIONIST,
        RoleEnum.DOCTOR
    ]))
) -> OperationalScanResponse:
    """
    Executes automated rule evaluation to identify impending operations events.
    """
    stats = NotificationService.scan_and_generate_operational_notifications(db)
    return OperationalScanResponse(
        success=True,
        message="Operational notification scanner completed successfully.",
        events_detected=stats
    )


@router.get(
    "/{id}",
    response_model=NotificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Notification Detail"
)
def get_notification_detail(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> NotificationResponse:
    """
    Fetches full metadata for an individual notification.
    """
    vis_query = NotificationService._build_visibility_query(
        db,
        user_id=current_user.id,
        role=current_user.role
    )
    notif = vis_query.filter(Notification.id == id).first()

    if not notif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification #{id} not found or not accessible."
        )

    return NotificationResponse(**_to_response_dict(notif))
