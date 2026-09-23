"""
CHIKITSASETU AI Health Assistant - OCR & Vision Reader
Extracts text from prescription and report images with confidence scoring and fallback disclaimers.
"""
from typing import Dict, Any, Optional
from pathlib import Path


def process_image_for_text(image_path: Path) -> Dict[str, Any]:
    """
    Attempts optical text extraction from image.
    If OCR libraries are unavailable or text is sparse/unreadable,
    returns an explicit low-confidence indicator requiring doctor confirmation.
    """
    extracted_text: Optional[str] = None
    confidence: str = "low"
    note: str = ""

    try:
        import pytesseract
        from PIL import Image
        with Image.open(str(image_path)) as img:
            extracted_text = pytesseract.image_to_string(img)
            if extracted_text and len(extracted_text.strip()) > 20:
                confidence = "medium"
            else:
                confidence = "low"
    except (ImportError, Exception):
        # Graceful fallback when local OCR binary (tesseract) is not installed
        confidence = "low"
        extracted_text = None

    if confidence == "low" or not extracted_text:
        note = (
            "I could not confidently read all text in this image directly. "
            "Please ensure the image is bright, flat, and in focus, or confirm any medical details "
            "directly with your doctor or pharmacist."
        )

    return {
        "text": extracted_text or "",
        "confidence": confidence,
        "note": note
    }
