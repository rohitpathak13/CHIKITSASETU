"""
CHIKITSASETU AI Health Assistant - Text & Language Processor
Handles user query sanitization, language detection (EN / HI / Hinglish), and query categorization.
"""
import re
from typing import Tuple
from backend.chatbot.schemas import LanguageEnum, QueryCategory


# Common Hinglish conversational and clinical vocabulary
HINGLISH_KEYWORDS = {
    "kya", "hai", "hain", "mujhe", "dawai", "dawakhana", "dard", "kaise", "karein",
    "bukhar", "khansi", "ye", "meri", "report", "batayein", "kisliye", "hota", "hoti",
    "pet", "sar", "gala", "chhati", "dawa", "peena", "khana", "khanae", "se", "pehle",
    "baad", "subah", "shaam", "raat", "doctor", "dikhao", "ilaj", "kripya", "batao",
    "ka", "ki", "ke", "ko", "par", "mein", "aur", "toh", "kyun", "kab", "kahan"
}


def detect_language(text: str) -> LanguageEnum:
    """
    Detects whether the input is predominantly English, Hindi (Devanagari), or Hinglish (Roman Hindi).
    """
    if not text:
        return LanguageEnum.ENGLISH

    # 1. Check for Devanagari Unicode Block (\u0900 - \u097F)
    devanagari_count = len(re.findall(r"[\u0900-\u097F]", text))
    if devanagari_count > 3 or (len(text.strip()) > 0 and devanagari_count / len(text.strip()) > 0.25):
        return LanguageEnum.HINDI

    # 2. Check for Hinglish lexical patterns in Roman script
    words = re.findall(r"\b[A-Za-z]+\b", text.lower())
    if words:
        hinglish_matches = sum(1 for w in words if w in HINGLISH_KEYWORDS)
        if hinglish_matches >= 2 or (len(words) <= 4 and hinglish_matches >= 1):
            return LanguageEnum.HINGLISH

    return LanguageEnum.ENGLISH


def classify_query_category(text: str, has_file: bool = False, file_type: str = "") -> QueryCategory:
    """
    Categorizes the incoming user query to guide knowledge retrieval and prompt selection.
    """
    t = text.lower()

    if "prescription" in t or "parcha" in t or "rx" in t:
        return QueryCategory.PRESCRIPTION

    if "x-ray" in t or "xray" in t or "radiology" in t or "scan" in t:
        if has_file and file_type == "image":
            return QueryCategory.XRAY_IMAGE
        return QueryCategory.XRAY_REPORT

    if any(k in t for k in ["lab report", "blood test", "cbc", "glucose", "sugar", "lipid", "creatinine", "lft", "kft", "thyroid", "urine report"]):
        return QueryCategory.LAB_REPORT

    if any(k in t for k in ["medicine", "tablet", "capsule", "syrup", "dawai", "dose", "paracetamol", "antibiotic", "metformin", "side effect"]):
        return QueryCategory.MEDICINE

    if any(k in t for k in ["rash", "redness", "swelling", "wound", "skin", "mole", "infection", "boil", "chhale"]):
        if has_file:
            return QueryCategory.HEALTH_IMAGE
        return QueryCategory.SYMPTOMS

    if any(k in t for k in ["symptom", "fever", "cough", "pain", "headache", "vomiting", "diarrhea", "bukhar", "dard", "chhati"]):
        return QueryCategory.SYMPTOMS

    if any(k in t for k in ["doctor", "specialist", "department", "physician", "cardiologist", "dermatologist"]):
        return QueryCategory.DOCTOR_RECOMMENDATION

    if any(k in t for k in ["appointment", "booking", "slot", "schedule", "token"]):
        return QueryCategory.APPOINTMENT_HELP

    if any(k in t for k in ["summary", "summarize", "discharge", "medical report"]):
        return QueryCategory.DOCUMENT_SUMMARY

    return QueryCategory.GENERAL


def sanitize_input_text(text: str, max_chars: int = 4000) -> str:
    """
    Trims excessive whitespace and bounds input length to prevent denial-of-service or token bloat.
    """
    if not text:
        return ""
    # Strip dangerous control characters while preserving standard whitespace
    cleaned = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
    return cleaned.strip()[:max_chars]
