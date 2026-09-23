"""
CHIKITSASETU AI Health Assistant - Flask Web Routes & API
Handles user interaction, file uploads, quick actions, and session authentication.
"""
import logging
from pathlib import Path
from flask import Blueprint, request, jsonify, session
from backend.chatbot.schemas import ChatRequest, UploadedFileMeta, LanguageEnum, QueryCategory
from backend.chatbot.service import chatbot_service
from backend.chatbot.processors import validate_and_save_upload, FileValidationError
from backend.config import settings
from backend.utils.decorators import login_required

logger = logging.getLogger(__name__)

chatbot_bp = Blueprint("chatbot", __name__, url_prefix="/chatbot/api")

# In-memory session upload tracker for temporary file correlation
_TEMP_UPLOADS: dict = {}


@chatbot_bp.route("/message", methods=["POST"])
@login_required
def post_message():
    """
    Main conversational endpoint for the AI Health Assistant.
    Receives user query, optional file_id, and session metadata.
    Requires an authenticated user session.
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    message_text = data.get("message", "").strip()
    category_str = data.get("category")
    language_str = data.get("language")
    file_id = data.get("file_id")

    file_meta: UploadedFileMeta = None
    if file_id and file_id in _TEMP_UPLOADS:
        file_meta = _TEMP_UPLOADS[file_id]

    # Map category enum if provided
    category = None
    if category_str:
        try:
            category = QueryCategory(category_str)
        except ValueError:
            category = None

    # Map language enum if provided
    language = None
    if language_str:
        try:
            language = LanguageEnum(language_str)
        except ValueError:
            language = None

    # Strictly bind to authenticated session
    user_id = session.get("user_id")
    user_role = session.get("user_role")

    req = ChatRequest(
        message=message_text,
        language=language,
        category=category,
        file_meta=file_meta,
        user_id=user_id,
        user_role=user_role
    )

    try:
        resp = chatbot_service.process_message(req)
        return jsonify({
            "success": True,
            "data": resp.to_dict()
        })
    except Exception as e:
        logger.error("Chatbot message processing encountered an internal error: %s", e, exc_info=True)
        return jsonify({
            "success": False,
            "error": "The AI Health Assistant encountered an unexpected error. Please try again."
        }), 500


@chatbot_bp.route("/upload", methods=["POST"])
@login_required
def upload_file():
    """
    Secure file upload endpoint. Accepts medical documents (.pdf) or images (.jpg, .jpeg, .png, .webp).
    Requires an authenticated user session.
    """
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file part in upload request."}), 400

    uploaded_file = request.files["file"]
    if not uploaded_file.filename:
        return jsonify({"success": False, "error": "No file selected."}), 400

    try:
        file_bytes = uploaded_file.read()
        file_meta = validate_and_save_upload(
            file_bytes=file_bytes,
            original_filename=uploaded_file.filename,
            mime_type=uploaded_file.mimetype or ""
        )

        # Store in transient upload cache
        _TEMP_UPLOADS[file_meta.filename] = file_meta

        return jsonify({
            "success": True,
            "data": {
                "file_id": file_meta.filename,
                "original_filename": file_meta.original_filename,
                "file_type": file_meta.file_type,
                "mime_type": file_meta.mime_type,
                "size_bytes": file_meta.size_bytes
            }
        })
    except FileValidationError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("Chatbot upload processing failed: %s", e, exc_info=True)
        return jsonify({
            "success": False,
            "error": "Upload processing failed due to an internal server error. Please try again."
        }), 500


@chatbot_bp.route("/quick-actions", methods=["GET"])
def get_quick_actions():
    """Returns curated initial quick actions for the floating widget."""
    actions = [
        {"id": "explain_medicine", "icon": "💊", "label": "Explain My Medicine", "prompt": "Please explain my medicine and what it is used for.", "category": "medicine"},
        {"id": "explain_prescription", "icon": "🧾", "label": "Explain Prescription", "prompt": "Can you explain this prescription and how to take these medicines safely?", "category": "prescription"},
        {"id": "explain_xray", "icon": "🩻", "label": "Explain X-Ray Report", "prompt": "Help me understand my X-ray report and technical terminology.", "category": "xray_report"},
        {"id": "explain_lab", "icon": "🧪", "label": "Explain Lab Report", "prompt": "Please explain the test results and reference ranges in my blood report.", "category": "lab_report"},
        {"id": "summarize_report", "icon": "📄", "label": "Summarize Medical Report", "prompt": "Please summarize my medical report or discharge summary in simple terms.", "category": "document_summary"},
        {"id": "analyze_image", "icon": "🖼️", "label": "Analyze Health Image", "prompt": "I have uploaded a photo of a visible skin condition. What could this be?", "category": "health_image"},
        {"id": "understand_symptoms", "icon": "🩺", "label": "Understand Symptoms", "prompt": "I have some symptoms I would like to understand better.", "category": "symptoms"},
        {"id": "find_doctor", "icon": "👨‍⚕️", "label": "Find Appropriate Doctor", "prompt": "Which doctor specialty should I visit for my health issue?", "category": "doctor_recommendation"},
        {"id": "appointment_help", "icon": "📅", "label": "Appointment Help", "prompt": "How can I book an appointment with a doctor at CHIKITSASETU?", "category": "appointment_help"},
    ]
    return jsonify({"success": True, "actions": actions})


@chatbot_bp.route("/my-health-summary", methods=["GET"])
@login_required
def get_health_summary():
    """Returns basic patient record statistics for authenticated users."""
    user_id = session.get("user_id")
    user_role = session.get("user_role")

    from backend.chatbot.retrieval import get_patient_authorized_context
    context = get_patient_authorized_context(user_id, user_role)
    return jsonify({
        "authenticated": True,
        "user_id": user_id,
        "role": user_role,
        "has_prescriptions": len(context.get("prescriptions", [])) > 0,
        "has_labs": len(context.get("recent_labs", [])) > 0,
        "has_appointments": len(context.get("appointments", [])) > 0
    })
