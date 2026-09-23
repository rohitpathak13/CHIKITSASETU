"""
CHIKITSASETU AI Health Assistant - Comprehensive Unit Tests
Validates safety screening, language identification, medicine explanations, doctor specialty recommendations,
multimodal file validation, and RBAC patient context isolation.
"""
import pytest
import io
from pathlib import Path
from PIL import Image

from backend.chatbot.schemas import (
    ChatRequest, ChatResponse, LanguageEnum, QueryCategory, SafetyLevel
)
from backend.chatbot.safety import evaluate_safety, build_emergency_response, sanitize_generated_response
from backend.chatbot.processors import (
    detect_language,
    classify_query_category,
    sanitize_input_text,
    validate_and_save_upload,
    FileValidationError
)
from backend.chatbot.retrieval import (
    find_medicine_knowledge,
    find_lab_param_knowledge,
    find_radiology_term_explanation,
    triage_symptoms_to_department,
    get_available_hospital_doctors,
    get_patient_authorized_context
)
from backend.chatbot.service import chatbot_service
from backend.models import User, Role, RoleEnum


# ==============================================================================
# 1. Safety Layer & Emergency Detection Tests
# ==============================================================================

def test_emergency_chest_pain_detection():
    query = "I have severe crushing chest pain radiating to my left arm and jaw"
    safety = evaluate_safety(query)
    assert safety.is_emergency is True
    assert safety.level == SafetyLevel.EMERGENCY
    assert safety.emergency_type == "cardiovascular_emergency"


def test_emergency_respiratory_detection():
    query = "Help I cannot breathe and my lips are turning blue"
    safety = evaluate_safety(query)
    assert safety.is_emergency is True
    assert safety.emergency_type == "respiratory_emergency"


def test_emergency_stroke_detection():
    query = "Sudden facial drooping with slurred speech and weakness in right arm"
    safety = evaluate_safety(query)
    assert safety.is_emergency is True
    assert safety.emergency_type == "neurological_stroke"


def test_emergency_response_builder_english():
    safety = evaluate_safety("Severe chest pain radiating to left arm")
    response_text = build_emergency_response(safety, LanguageEnum.ENGLISH)
    assert "MEDICAL EMERGENCY ALERT" in response_text
    assert "108" in response_text or "112" in response_text
    assert "Do not drive yourself" in response_text


def test_emergency_response_builder_hinglish():
    safety = evaluate_safety("Chhati mein tez dard hai aur saans nahi aa rahi")
    response_text = build_emergency_response(safety, LanguageEnum.HINGLISH)
    assert "EMERGENCY" in response_text
    assert "108" in response_text or "112" in response_text
    assert "Emergency Room" in response_text or "hospital" in response_text.lower()


def test_safe_query_not_flagged():
    query = "What is the common use of Paracetamol 500mg tablet?"
    safety = evaluate_safety(query)
    assert safety.is_emergency is False
    assert safety.level == SafetyLevel.SAFE


def test_post_response_sanitization():
    # Enforces non-definitive diagnosis guardrails
    bad_output = "Based on this, you have acute bronchitis and you are diagnosed with infection."
    sanitized = sanitize_generated_response(bad_output)
    assert "you have" not in sanitized.lower()
    assert "may be consistent with" in sanitized.lower()
    assert "Disclaimer" in sanitized or "educational" in sanitized.lower()


# ==============================================================================
# 2. Language Detection & Sanitization Tests
# ==============================================================================

def test_detect_english():
    lang = detect_language("Can you explain my blood test report?")
    assert lang == LanguageEnum.ENGLISH


def test_detect_hindi():
    lang = detect_language("इस दवा का उपयोग क्या है और इसे कैसे लें?")
    assert lang == LanguageEnum.HINDI


def test_detect_hinglish():
    lang = detect_language("Ye medicine kisliye hai aur iske side effects kya hain?")
    assert lang == LanguageEnum.HINGLISH


def test_sanitize_input():
    dirty = "   Hello Doctor \x00\x08 test query \n\n   "
    clean = sanitize_input_text(dirty)
    assert clean == "Hello Doctor  test query"


# ==============================================================================
# 3. Knowledge Retrieval & Medicine Tests
# ==============================================================================

def test_find_medicine_paracetamol():
    med = find_medicine_knowledge("What is paracetamol used for?")
    assert med is not None
    assert "Paracetamol" in med["generic"]
    assert "Analgesic" in med["category"]
    assert "4000mg" in med["precautions"]


def test_find_medicine_metformin():
    med = find_medicine_knowledge("Tell me about metformin hydrochloride")
    assert med is not None
    assert "Metformin" in med["generic"]
    assert "Diabetes" in med["common_uses"]


def test_find_lab_param_hemoglobin():
    info = find_lab_param_knowledge("Hemoglobin")
    assert info is not None
    assert "Hemoglobin" in info["test_name"]
    assert "g/dL" in info["unit"]


def test_find_radiology_term():
    explanation = find_radiology_term_explanation("degenerative changes in spine")
    assert explanation is not None
    assert "wear-and-tear" in explanation.lower() or "aging" in explanation.lower()


# ==============================================================================
# 4. Specialty Triage & Doctor Routing Tests
# ==============================================================================

def test_symptom_triage_cardiology():
    triage = triage_symptoms_to_department("I have frequent palpitations and chest pressure on exertion")
    assert triage["department"] == "Cardiology"


def test_symptom_triage_dermatology():
    triage = triage_symptoms_to_department("Red itchy rash and dry eczema on my skin")
    assert triage["department"] == "Dermatology"


def test_symptom_triage_orthopedics():
    triage = triage_symptoms_to_department("Severe knee joint pain and back pain after walking")
    assert triage["department"] == "Orthopedics"


def test_symptom_triage_general_medicine():
    triage = triage_symptoms_to_department("Mild fever and general body weakness for 2 days")
    assert triage["department"] == "General Medicine"


def test_get_available_hospital_doctors():
    # Verifies querying database for actual CHIKITSASETU doctors
    doctors = get_available_hospital_doctors("Cardiology", limit=2)
    assert len(doctors) > 0
    assert doctors[0].doctor_name is not None
    assert doctors[0].appointment_url is not None


# ==============================================================================
# 5. Multimodal File Validation Tests
# ==============================================================================

def test_file_validation_disallowed_extension():
    with pytest.raises(FileValidationError) as exc:
        validate_and_save_upload(
            file_bytes=b"malicious script",
            original_filename="malware.exe",
            mime_type="application/x-msdownload"
        )
    assert "Unsupported file format" in str(exc.value)


def test_file_validation_oversized_payload(monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "CHATBOT_MAX_UPLOAD_BYTES", 100)
    with pytest.raises(FileValidationError) as exc:
        validate_and_save_upload(
            file_bytes=b"x" * 200,
            original_filename="report.pdf",
            mime_type="application/pdf"
        )
    assert "exceeds" in str(exc.value)


def test_valid_image_upload_processing():
    # Create valid synthetic RGB image in memory
    img = Image.new("RGB", (200, 200), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    img_bytes = buf.getvalue()

    meta = validate_and_save_upload(
        file_bytes=img_bytes,
        original_filename="skin_rash.jpg",
        mime_type="image/jpeg"
    )
    assert meta.file_type == "image"
    assert meta.image_base64 is not None
    assert Path(meta.saved_path).exists()

    # Clean up test file
    Path(meta.saved_path).unlink(missing_ok=True)


# ==============================================================================
# 6. End-to-End Chatbot Service Processing Tests
# ==============================================================================

def test_chatbot_service_emergency_pipeline():
    req = ChatRequest(message="Crushing chest pain radiating to left arm")
    resp = chatbot_service.process_message(req)
    assert resp.safety.is_emergency is True
    assert "CRITICAL MEDICAL EMERGENCY ALERT" in resp.reply
    assert len(resp.suggested_actions) > 0
    assert "108" in resp.suggested_actions[0]["label"]


def test_chatbot_service_medicine_query():
    req = ChatRequest(message="What is Metformin used for?")
    resp = chatbot_service.process_message(req)
    assert resp.safety.is_emergency is False
    assert "Metformin" in resp.reply
    assert "Diabetes" in resp.reply
    assert len(resp.doctor_recommendations) > 0


def test_chatbot_service_hinglish_response():
    req = ChatRequest(message="Ye paracetamol tablet kisliye use hoti hai?")
    resp = chatbot_service.process_message(req)
    assert resp.language == LanguageEnum.HINGLISH
    assert "Medicine" in resp.reply or "Dawa" in resp.reply or "Paracetamol" in resp.reply
    assert resp.safety.is_emergency is False


def test_patient_rbac_context_isolation():
    # Unauthenticated context should return empty clinical data
    anon_context = get_patient_authorized_context(user_id=None, user_role=None)
    assert anon_context["authorized"] is False
    assert len(anon_context["prescriptions"]) == 0

    # Non-patient (e.g. doctor) querying patient records directly via helper
    doc_context = get_patient_authorized_context(user_id=1, user_role=RoleEnum.DOCTOR.value)
    assert doc_context["authorized"] is False


def test_flask_chatbot_routes(flask_client, db_session):
    from backend.models import User, RoleEnum
    from backend.security import get_password_hash

    # Create active user for session authentication test
    user = User(
        email="chatbot_test_doc@chikitsasetu.ai",
        password_hash=get_password_hash("Password123!"),
        role=RoleEnum.DOCTOR,
        first_name="Chat",
        last_name="Doctor",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()

    # Test Quick Actions endpoint
    resp = flask_client.get("/chatbot/api/quick-actions")
    assert resp.status_code == 200
    json_data = resp.get_json()
    assert json_data["success"] is True
    assert len(json_data["actions"]) >= 8

    # Test Message endpoint requires authentication
    unauth_resp = flask_client.post(
        "/chatbot/api/message",
        json={"message": "What is Cetirizine used for?"}
    )
    assert unauth_resp.status_code == 401

    # Authenticate session
    with flask_client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["user_role"] = user.role.value

    msg_resp = flask_client.post(
        "/chatbot/api/message",
        json={"message": "What is Cetirizine used for?"}
    )
    assert msg_resp.status_code == 200
    msg_json = msg_resp.get_json()
    assert msg_json["success"] is True
    assert "reply" in msg_json["data"]
    assert "Cetirizine" in msg_json["data"]["reply"]

