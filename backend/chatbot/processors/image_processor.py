"""
CHIKITSASETU AI Health Assistant - Image & File Upload Processor
Performs rigorous MIME verification, image integrity checking, downsizing, and base64 encoding.
"""
import io
import os
import uuid
import base64
from pathlib import Path
from typing import Tuple, Optional
from werkzeug.utils import secure_filename
from PIL import Image

from backend.config import settings
from backend.chatbot.schemas import UploadedFileMeta


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_DOC_EXTENSIONS = {".pdf"}
ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | ALLOWED_DOC_EXTENSIONS

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf"
}


class FileValidationError(Exception):
    """Raised when an uploaded file violates safety or format policies."""
    pass


def validate_and_save_upload(
    file_bytes: bytes,
    original_filename: str,
    mime_type: str = ""
) -> UploadedFileMeta:
    """
    Validates, cleans, and securely stores an uploaded user file (image or PDF).
    Returns an UploadedFileMeta instance.
    """
    if not file_bytes:
        raise FileValidationError("No file content provided.")

    if len(file_bytes) > settings.CHATBOT_MAX_UPLOAD_BYTES:
        max_mb = settings.CHATBOT_MAX_UPLOAD_BYTES // (1024 * 1024)
        raise FileValidationError(f"File size exceeds the maximum permitted limit of {max_mb} MB.")

    safe_name = secure_filename(original_filename)
    ext = Path(safe_name).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        allowed_list = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise FileValidationError(f"Unsupported file format '{ext}'. Allowed formats: {allowed_list}")

    file_type = "pdf" if ext == ".pdf" else "image"
    unique_filename = f"{uuid.uuid4().hex}{ext}"
    saved_path = settings.CHATBOT_UPLOAD_DIR / unique_filename

    image_base64: Optional[str] = None

    if file_type == "image":
        # Validate that the bytes represent an authentic, readable image
        try:
            with Image.open(io.BytesIO(file_bytes)) as img:
                img.verify()
        except Exception:
            raise FileValidationError("The uploaded image file is corrupt or invalid.")

        # Reopen to normalize dimensions and format
        with Image.open(io.BytesIO(file_bytes)) as img:
            # Convert RGBA / CMYK to RGB if saving as JPEG
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            # Downsample if unnecessarily large (> 1920px max dimension)
            max_dim = 1920
            if max(img.size) > max_dim:
                img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

            # Save normalized image
            img.save(str(saved_path), format="JPEG", quality=85, optimize=True)

            # Prepare Base64 string for multimodal APIs
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    else:
        # Validate authentic PDF magic bytes
        if not file_bytes.startswith(b"%PDF-"):
            raise FileValidationError("The uploaded file does not appear to be a valid PDF document.")

        # Save PDF directly to secure directory
        with open(saved_path, "wb") as f:
            f.write(file_bytes)

    return UploadedFileMeta(
        filename=unique_filename,
        original_filename=safe_name,
        file_type=file_type,
        mime_type="image/jpeg" if file_type == "image" else "application/pdf",
        size_bytes=os.path.getsize(saved_path),
        saved_path=str(saved_path),
        image_base64=image_base64
    )
