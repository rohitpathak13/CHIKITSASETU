"""
CHIKITSASETU AI Health Assistant - Data Schemas & Types
Defines structured request, response, safety evaluation, and file payload contracts.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class LanguageEnum(str, Enum):
    ENGLISH = "en"
    HINDI = "hi"
    HINGLISH = "hinglish"


class QueryCategory(str, Enum):
    GENERAL = "general"
    MEDICINE = "medicine"
    PRESCRIPTION = "prescription"
    XRAY_REPORT = "xray_report"
    XRAY_IMAGE = "xray_image"
    LAB_REPORT = "lab_report"
    DOCUMENT_SUMMARY = "document_summary"
    HEALTH_IMAGE = "health_image"
    SYMPTOMS = "symptoms"
    DOCTOR_RECOMMENDATION = "doctor_recommendation"
    APPOINTMENT_HELP = "appointment_help"


class SafetyLevel(str, Enum):
    SAFE = "safe"
    CAUTION = "caution"
    EMERGENCY = "emergency"


@dataclass
class UploadedFileMeta:
    filename: str
    original_filename: str
    file_type: str  # "image" or "pdf"
    mime_type: str
    size_bytes: int
    saved_path: str
    extracted_text: Optional[str] = None
    image_base64: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SafetyEvaluation:
    level: SafetyLevel
    is_emergency: bool = False
    emergency_type: Optional[str] = None
    warning_message: Optional[str] = None
    trigger_phrases: List[str] = field(default_factory=list)


@dataclass
class DoctorRecommendation:
    department: str
    specialization: str
    doctor_name: Optional[str] = None
    doctor_id: Optional[int] = None
    available_days: Optional[str] = None
    consultation_fee: Optional[float] = None
    appointment_url: Optional[str] = None


@dataclass
class ChatRequest:
    message: str
    language: Optional[LanguageEnum] = None
    category: Optional[QueryCategory] = None
    file_meta: Optional[UploadedFileMeta] = None
    user_id: Optional[int] = None
    user_role: Optional[str] = None
    conversation_history: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class ChatResponse:
    reply: str
    language: LanguageEnum
    category: QueryCategory
    safety: SafetyEvaluation
    doctor_recommendations: List[DoctorRecommendation] = field(default_factory=list)
    suggested_actions: List[Dict[str, str]] = field(default_factory=list)
    provider_used: str = "local"
    disclaimer: str = (
        "Educational AI health assistant. Not a substitute for professional clinical diagnosis, "
        "prescription, or medical advice. Always confirm with a qualified healthcare professional."
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reply": self.reply,
            "language": self.language.value,
            "category": self.category.value,
            "safety": {
                "level": self.safety.level.value,
                "is_emergency": self.safety.is_emergency,
                "emergency_type": self.safety.emergency_type,
                "warning_message": self.safety.warning_message,
            },
            "doctor_recommendations": [
                {
                    "department": d.department,
                    "specialization": d.specialization,
                    "doctor_name": d.doctor_name,
                    "doctor_id": d.doctor_id,
                    "available_days": d.available_days,
                    "consultation_fee": d.consultation_fee,
                    "appointment_url": d.appointment_url,
                }
                for d in self.doctor_recommendations
            ],
            "suggested_actions": self.suggested_actions,
            "provider_used": self.provider_used,
            "disclaimer": self.disclaimer,
        }
