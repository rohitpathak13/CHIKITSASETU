"""
CHIKITSASETU AI Health Assistant - Document & PDF Processor
Extracts textual content, structured test sections, and medical findings from uploaded PDFs using pypdf.
"""
import io
import re
from typing import Optional, Dict, Any, List
from pathlib import Path


class DocumentProcessingError(Exception):
    """Raised when a document cannot be parsed or is corrupted."""
    pass


def extract_text_from_pdf(file_path: Path, max_pages: int = 15) -> str:
    """
    Safely reads text content from a PDF document using pypdf.
    Bounds total pages and extracted characters to protect system memory.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise DocumentProcessingError("pypdf is required for PDF parsing.")

    if not file_path.exists():
        raise DocumentProcessingError(f"PDF file does not exist at {file_path}")

    extracted_pages: List[str] = []
    try:
        reader = PdfReader(str(file_path))
        num_pages = len(reader.pages)

        for i in range(min(num_pages, max_pages)):
            page = reader.pages[i]
            text = page.extract_text() or ""
            # Clean up whitespace
            cleaned_page = re.sub(r"[ \t]+", " ", text).strip()
            if cleaned_page:
                extracted_pages.append(f"--- Page {i + 1} ---\n{cleaned_page}")

        full_text = "\n\n".join(extracted_pages)
        if not full_text.strip():
            return "Note: The PDF did not contain selectable digital text (it may be a scanned document image)."

        return full_text[:12000]  # Cap at 12,000 characters to prevent token bloat
    except Exception as e:
        raise DocumentProcessingError(f"Failed to parse PDF document: {str(e)}")


def parse_lab_report_text(report_text: str) -> Dict[str, Any]:
    """
    Heuristically extracts key test names, values, and reference flags from text.
    """
    results: List[Dict[str, str]] = []
    lines = report_text.splitlines()

    # Pattern: Test Name ... Value ... Unit ... Reference Range
    # e.g., "Hemoglobin 13.5 g/dL (12.0 - 15.5)" or "Glucose (Fasting): 110 mg/dL"
    value_pattern = re.compile(
        r"([A-Za-z0-9\s\-\(\)\/]{3,35})\s*[:\t=]\s*([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z\/\%\^]+)?(?:\s*[\(\[]?([0-9\.\-\s]+)[\)\]]?)?"
    )

    for line in lines:
        line_clean = line.strip()
        match = value_pattern.search(line_clean)
        if match:
            param = match.group(1).strip()
            val = match.group(2).strip()
            unit = match.group(3).strip() if match.group(3) else ""
            ref = match.group(4).strip() if match.group(4) else ""
            if len(param) > 2 and not param.lower().startswith(("date", "page", "time", "ref", "dr")):
                results.append({
                    "parameter": param,
                    "value": val,
                    "unit": unit,
                    "reference_range": ref
                })

    return {
        "raw_text": report_text,
        "parsed_items": results[:25]
    }
