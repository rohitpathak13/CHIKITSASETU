"""
Pydantic Validation Schemas for the FastAPI Audit Logs REST Module.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class AuditLogUserSummary(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    role: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AuditLogResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    user_email: Optional[str] = None
    user_full_name: Optional[str] = None
    user_role: Optional[str] = None
    user: Optional[AuditLogUserSummary] = None
    action: str
    resource_type: str
    resource_id: Optional[int] = None
    ip_address: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    items: List[AuditLogResponse]
    total: int
    limit: int
    offset: int


class AuditActionsListResponse(BaseModel):
    actions: List[str]


class AuditResourceTypesResponse(BaseModel):
    resource_types: List[str]


class ActionCountItem(BaseModel):
    action: str
    count: int


class ResourceCountItem(BaseModel):
    resource_type: str
    count: int


class AuditStatsResponse(BaseModel):
    total_logs: int
    total_logins: int
    total_security_events: int
    top_actions: List[ActionCountItem]
    top_resources: List[ResourceCountItem]
