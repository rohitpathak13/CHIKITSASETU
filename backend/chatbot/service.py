"""
CHIKITSASETU AI Health Assistant - Core Orchestrator Service
Coordinates input processing, safety validation, RAG retrieval, AI inference, and response formatting.
"""
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

from backend.chatbot.schemas import (
    ChatRequest, ChatResponse, LanguageEnum, QueryCategory,
    SafetyEvaluation, SafetyLevel, DoctorRecommendation, UploadedFileMeta
)
from backend.chatbot.safety import (
    evaluate_safety,
    build_emergency_response,
    sanitize_generated_response
)
from backend.chatbot.processors import (
    detect_language,
    classify_query_category,
    sanitize_input_text,
    extract_text_from_pdf,
    process_image_for_text
)
from backend.chatbot.retrieval import (
    triage_symptoms_to_department,
    get_available_hospital_doctors,
    get_patient_authorized_context
)
from backend.chatbot.providers import get_ai_provider
from backend.chatbot.prompts import (
    CLINICAL_SYSTEM_PROMPT,
    PROMPT_MEDICINE_EXPLANATION,
    PROMPT_PRESCRIPTION_EXPLANATION,
    PROMPT_LAB_REPORT_EXPLANATION,
    PROMPT_XRAY_REPORT_EXPLANATION,
    PROMPT_HEALTH_IMAGE_OBSERVATION,
    PROMPT_SYMPTOM_UNDERSTANDING
)

logger = logging.getLogger(__name__)


class ChatbotService:
    """Enterprise clinical orchestrator for the CHIKITSASETU AI Health Assistant."""

    def __init__(self):
        self.provider = get_ai_provider()

    def process_message(self, request: ChatRequest) -> ChatResponse:
        """
        Processes an incoming user chat turn through the end-to-end clinical pipeline.
        """
        raw_text = request.message or ""
        clean_text = sanitize_input_text(raw_text)

        # 1. Detect language (English, Hindi, or Hinglish)
        lang = request.language or detect_language(clean_text)

        # 2. Extract text from uploaded document/image if present
        file_meta = request.file_meta
        if file_meta:
            if file_meta.file_type == "pdf" and not file_meta.extracted_text:
                try:
                    file_meta.extracted_text = extract_text_from_pdf(Path(file_meta.saved_path))
                except Exception as e:
                    logger.error(f"Error parsing PDF: {e}")
                    file_meta.extracted_text = "Unable to read text from uploaded PDF."
            elif file_meta.file_type == "image" and not file_meta.extracted_text:
                ocr_result = process_image_for_text(Path(file_meta.saved_path))
                file_meta.extracted_text = ocr_result.get("text")

        # 3. Detect category
        cat = request.category or classify_query_category(
            clean_text,
            has_file=bool(file_meta),
            file_type=file_meta.file_type if file_meta else ""
        )

        # 4. Mandatory Pre-Execution Safety Screen
        combined_text_for_safety = f"{clean_text} {file_meta.extracted_text if file_meta else ''}"
        safety_eval = evaluate_safety(combined_text_for_safety)

        # If a life-threatening emergency is detected, halt standard generation and return emergency guidance
        if safety_eval.is_emergency:
            emergency_reply = build_emergency_response(safety_eval, lang)
            return ChatResponse(
                reply=emergency_reply,
                language=lang,
                category=cat,
                safety=safety_eval,
                doctor_recommendations=[],
                suggested_actions=[
                    {"label": "📞 Call Emergency (108/112)", "url": "tel:108"},
                    {"label": "🏥 24x7 Casualty Ward", "url": "/ipd/dashboard"}
                ],
                provider_used="safety_guard"
            )

        # 5. Retrieve patient-authorized clinical context (RBAC-guarded)
        patient_context = get_patient_authorized_context(request.user_id, request.user_role)

        # 6. Retrieve relevant hospital doctors & department routing
        triage = triage_symptoms_to_department(combined_text_for_safety)
        dept_name = triage["department"]
        doctor_recs = get_available_hospital_doctors(dept_name, limit=2)

        # 7. Construct contextual system instructions
        system_instruction = CLINICAL_SYSTEM_PROMPT

        # 8. Query configured AI Provider
        raw_reply = self.provider.generate_response(
            prompt=clean_text or "Please explain the attached document or image.",
            system_prompt=system_instruction,
            language=lang,
            file_meta=file_meta,
            context=patient_context
        )

        # 9. Post-Execution Safety Validation
        final_reply = sanitize_generated_response(raw_reply)

        # 10. Assemble relevant suggested actions
        suggested_actions: List[Dict[str, str]] = []
        if doctor_recs:
            primary_doc = doctor_recs[0]
            suggested_actions.append({
                "label": f"📅 Book Consultation with {primary_doc.doctor_name} ({primary_doc.department})",
                "url": primary_doc.appointment_url or "/appointments/book"
            })
        else:
            suggested_actions.append({
                "label": "📅 Book OPD Appointment",
                "url": "/appointments/book"
            })

        if request.user_role == "patient":
            suggested_actions.append({
                "label": "💊 View My Prescriptions",
                "url": "/patient/prescriptions"
            })

        return ChatResponse(
            reply=final_reply,
            language=lang,
            category=cat,
            safety=safety_eval,
            doctor_recommendations=doctor_recs,
            suggested_actions=suggested_actions,
            provider_used=self.provider.name
        )


chatbot_service = ChatbotService()
