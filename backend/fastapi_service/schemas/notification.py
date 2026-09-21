"""
Pydantic Validation Schemas for the FastAPI Notifications REST Module.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from backend.models.user import RoleEnum
from backend.models.notification import NotificationTypeEnum, NotificationPriorityEnum


class NotificationResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    target_role: Optional[str] = None
    title: str
    message: str
    type: str
    priority: str
    is_read: bool
    read_at: Optional[datetime] = None
    reference_type: Optional[str] = None
    reference_id: Optional[int] = None
    action_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class NotificationCreateRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=150, description="Short summary title")
    message: str = Field(..., min_length=2, description="Detailed notification message text")
    type: NotificationTypeEnum = Field(default=NotificationTypeEnum.SYSTEM, description="Category/event type")
    priority: NotificationPriorityEnum = Field(default=NotificationPriorityEnum.NORMAL, description="Alert urgency level")
    user_id: Optional[int] = Field(default=None, description="Direct target user ID")
    target_role: Optional[RoleEnum] = Field(default=None, description="Broadcast target role")
    reference_type: Optional[str] = Field(default=None, max_length=60, description="Linked entity type (e.g. Appointment, Medicine)")
    reference_id: Optional[int] = Field(default=None, description="Linked entity primary key")
    action_url: Optional[str] = Field(default=None, max_length=255, description="Client deep-link URI")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional contextual JSON key-values")


class NotificationListResponse(BaseModel):
    items: List[NotificationResponse]
    total: int
    unread_count: int
    limit: int
    offset: int


class UnreadCountResponse(BaseModel):
    unread_count: int


class MarkReadResponse(BaseModel):
    success: bool
    message: str
    notification_id: Optional[int] = None
    marked_count: Optional[int] = None


class OperationalScanResponse(BaseModel):
    success: bool
    message: str
    events_detected: Dict[str, int]
