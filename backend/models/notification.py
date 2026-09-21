"""
In-App Notification Data Models and Enumerations for CHIKITSASETU.
Supports appointment reminders, lab results, low medicine stock, medicine expiry,
pending payments, admission/discharge events, and role-based visibility.
"""

import enum
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import (
    Column, Integer, String, Boolean, Enum as SQLEnum,
    ForeignKey, Text, DateTime, Index
)
from sqlalchemy.orm import relationship
from backend.database import Base
from backend.models.base import TimestampMixin
from backend.models.user import RoleEnum


class NotificationTypeEnum(str, enum.Enum):
    # Domain specific notification events
    APPOINTMENT_REMINDER = "appointment_reminder"
    LAB_RESULT = "lab_result"
    LOW_STOCK = "low_stock"
    MEDICINE_EXPIRY = "medicine_expiry"
    PENDING_PAYMENT = "pending_payment"
    ADMISSION_DISCHARGE = "admission_discharge"
    
    # Generic & Legacy notification categories
    ALERT = "alert"
    REMINDER = "reminder"
    CRITICAL = "critical"
    SYSTEM = "system"


class NotificationPriorityEnum(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class Notification(Base, TimestampMixin):
    """
    In-app notification entity supporting direct user targeting and role-based broadcasts.
    """
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Target recipient: either a specific user or a broad role group (or both)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    target_role = Column(SQLEnum(RoleEnum), nullable=True, index=True)

    title = Column(String(150), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(SQLEnum(NotificationTypeEnum), default=NotificationTypeEnum.SYSTEM, nullable=False, index=True)
    priority = Column(SQLEnum(NotificationPriorityEnum), default=NotificationPriorityEnum.NORMAL, nullable=False, index=True)

    # Read status tracking
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    read_at = Column(DateTime, nullable=True)

    # Contextual references for deep-linking
    reference_type = Column(String(60), nullable=True, index=True)  # e.g., "Appointment", "LabOrder", "Medicine", "Bill", "Admission"
    reference_id = Column(Integer, nullable=True, index=True)
    action_url = Column(String(255), nullable=True)                  # e.g., "/appointments/14", "/pharmacy/inventory"
    metadata_json = Column(Text, nullable=True)

    # Relationships
    user = relationship("User", back_populates="notifications")

    __table_args__ = (
        Index("ix_notifications_user_read", "user_id", "is_read"),
        Index("ix_notifications_role_read", "target_role", "is_read"),
    )

    def mark_read(self):
        """Marks notification as read with current UTC timestamp."""
        self.is_read = True
        self.read_at = datetime.now(timezone.utc)

    def mark_unread(self):
        """Reverts notification to unread status."""
        self.is_read = False
        self.read_at = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes notification model into dictionary representation."""
        import json
        meta = {}
        if self.metadata_json:
            try:
                meta = json.loads(self.metadata_json)
            except Exception:
                meta = {"raw": self.metadata_json}

        return {
            "id": self.id,
            "user_id": self.user_id,
            "target_role": self.target_role.value if self.target_role else None,
            "title": self.title,
            "message": self.message,
            "type": self.type.value if self.type else NotificationTypeEnum.SYSTEM.value,
            "priority": self.priority.value if self.priority else NotificationPriorityEnum.NORMAL.value,
            "is_read": self.is_read,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "reference_type": self.reference_type,
            "reference_id": self.reference_id,
            "action_url": self.action_url,
            "metadata": meta,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        recipient = f"user={self.user_id}" if self.user_id else f"role={self.target_role}"
        return f"<Notification id={self.id} {recipient} type={self.type} read={self.is_read}>"
