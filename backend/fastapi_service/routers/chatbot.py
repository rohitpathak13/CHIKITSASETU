import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from pydantic import BaseModel, Field

from backend.models.user import User
from backend.fastapi_service.dependencies import get_current_user
from backend.chatbot.schemas import ChatRequest, UploadedFileMeta, LanguageEnum, QueryCategory
from backend.chatbot.service import chatbot_service
from backend.chatbot.processors import validate_and_save_upload, FileValidationError
from backend.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chatbot", tags=["AI Health Assistant"])

_FASTAPI_UPLOADS: Dict[str, UploadedFileMeta] = {}


class ChatMessageRequest(BaseModel):
    message: str = Field(..., description="User question, symptom description, or medicine name")
    category: Optional[str] = Field(None, description="Query category (e.g. medicine, prescription, symptoms)")
    language: Optional[str] = Field(None, description="Language code: en, hi, or hinglish")
    file_id: Optional[str] = Field(None, description="Optional file ID returned from prior /upload endpoint")


@router.post("/chat", summary="Process Chat Turn with AI Health Assistant")
async def chat_endpoint(
    payload: ChatMessageRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Sends a query to the AI Health Assistant. Supports symptoms, medicine inquiries,
    prescription explanations, and document analysis.
    Requires an authenticated user session/token.
    """
    file_meta: Optional[UploadedFileMeta] = None
    if payload.file_id and payload.file_id in _FASTAPI_UPLOADS:
        file_meta = _FASTAPI_UPLOADS[payload.file_id]

    cat_enum = None
    if payload.category:
        try:
            cat_enum = QueryCategory(payload.category)
        except ValueError:
            pass

    lang_enum = None
    if payload.language:
        try:
            lang_enum = LanguageEnum(payload.language)
        except ValueError:
            pass

    user_id = current_user.id
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role)

    req = ChatRequest(
        message=payload.message,
        language=lang_enum,
        category=cat_enum,
        file_meta=file_meta,
        user_id=user_id,
        user_role=user_role
    )

    try:
        resp = chatbot_service.process_message(req)
        return {"success": True, "data": resp.to_dict()}
    except Exception as e:
        logger.error("FastAPI Chatbot turn failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="The AI Health Assistant encountered an unexpected error. Please try again."
        )


@router.post("/upload", summary="Upload Health Document or Condition Image")
async def upload_document_or_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    Uploads an X-ray report PDF, lab report PDF, prescription image, or visible skin condition photo.
    Validates file formats (PDF, JPG, PNG, WEBP) and stores securely for processing.
    Requires an authenticated user session/token.
    """
    try:
        content = await file.read()
        file_meta = validate_and_save_upload(
            file_bytes=content,
            original_filename=file.filename or "upload",
            mime_type=file.content_type or ""
        )
        _FASTAPI_UPLOADS[file_meta.filename] = file_meta

        return {
            "success": True,
            "data": {
                "file_id": file_meta.filename,
                "original_filename": file_meta.original_filename,
                "file_type": file_meta.file_type,
                "mime_type": file_meta.mime_type,
                "size_bytes": file_meta.size_bytes
            }
        }
    except FileValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("FastAPI Chatbot upload failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Upload processing failed due to an internal server error. Please try again."
        )


@router.get("/quick-actions", summary="List Available Clinical Quick Actions")
async def list_quick_actions():
    """Returns curated starter prompts for medicines, reports, and symptoms."""
    actions = [
        {"id": "explain_medicine", "icon": "💊", "label": "Explain My Medicine", "category": "medicine"},
        {"id": "explain_prescription", "icon": "🧾", "label": "Explain Prescription", "category": "prescription"},
        {"id": "explain_xray", "icon": "🩻", "label": "Explain X-Ray Report", "category": "xray_report"},
        {"id": "explain_lab", "icon": "🧪", "label": "Explain Lab Report", "category": "lab_report"},
        {"id": "summarize_report", "icon": "📄", "label": "Summarize Medical Report", "category": "document_summary"},
        {"id": "analyze_image", "icon": "🖼️", "label": "Analyze Health Image", "category": "health_image"},
        {"id": "understand_symptoms", "icon": "🩺", "label": "Understand Symptoms", "category": "symptoms"},
        {"id": "find_doctor", "icon": "👨‍⚕️", "label": "Find Appropriate Doctor", "category": "doctor_recommendation"},
        {"id": "appointment_help", "icon": "📅", "label": "Appointment Help", "category": "appointment_help"},
    ]
    return {"success": True, "actions": actions}


@router.get("/health", summary="AI Health Assistant Service Status")
async def assistant_health():
    """Checks the status and active provider of the AI Health Assistant."""
    return {
        "status": "operational",
        "service": "CHIKITSASETU AI Health Assistant",
        "provider": chatbot_service.provider.name,
        "max_upload_bytes": settings.CHATBOT_MAX_UPLOAD_BYTES,
        "supported_languages": ["en", "hi", "hinglish"],
        "version": settings.PROJECT_VERSION
    }
