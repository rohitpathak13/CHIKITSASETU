from sqlalchemy import Column, Integer, String, ForeignKey, Text
from sqlalchemy.orm import relationship, synonym
from core.database import Base
from core.models.base import TimestampMixin
from core.models.notification import (
    Notification,
    NotificationTypeEnum,
    NotificationPriorityEnum,
)

__all__ = [
    "AuditLog",
    "Notification",
    "NotificationTypeEnum",
    "NotificationPriorityEnum",
]


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)        # e.g., "USER_LOGIN", "EMR_CREATE", "DRUG_DISPENSE"
    resource_type = Column(String(60), nullable=False, index=True)  # e.g., "Patient", "Prescription", "Bill"
    resource_id = Column(Integer, nullable=True, index=True)
    ip_address = Column(String(45), nullable=True)
    details_json = Column(Text, nullable=True)
    timestamp = synonym("created_at")

    # Relationships
    user = relationship("User", back_populates="audit_logs")

    def __init__(self, **kwargs):
        if "details" in kwargs:
            details_val = kwargs.pop("details")
            super().__init__(**kwargs)
            self.details = details_val
        else:
            super().__init__(**kwargs)

    @property
    def details(self):
        if not self.details_json:
            return {}
        try:
            import json
            return json.loads(self.details_json)
        except Exception:
            return {"raw": self.details_json}

    @details.setter
    def details(self, value):
        import json
        if isinstance(value, (dict, list)):
            self.details_json = json.dumps(value)
        elif value is None:
            self.details_json = None
        else:
            self.details_json = str(value)

    def to_dict(self):
        role_str = None
        if self.user and getattr(self.user, "role", None):
            role_str = self.user.role.value if hasattr(self.user.role, "value") else str(self.user.role)

        return {
            "id": self.id,
            "user_id": self.user_id,
            "user_email": self.user.email if self.user else None,
            "user_full_name": self.user.full_name if self.user else None,
            "user_role": role_str,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "ip_address": self.ip_address,
            "details": self.details,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "timestamp": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} user={self.user_id} action={self.action} res={self.resource_type}:{self.resource_id}>"

