"""
CHIKITSASETU AI Health Assistant - Google Gemini Multimodal Provider
Communicates with Google Gemini 1.5 Flash/Pro via REST using httpx.
Supports inline text, image base64, and document payloads with seamless fallback.
"""
import logging
from typing import Optional, Dict, Any, List
import httpx

from backend.config import settings
from backend.chatbot.providers.base import AIProviderBase
from backend.chatbot.providers.local_provider import LocalBuiltinProvider
from backend.chatbot.schemas import UploadedFileMeta, LanguageEnum

logger = logging.getLogger(__name__)


class GeminiProvider(AIProviderBase):
    """Multimodal Gemini 1.5 provider communicating via Google Generative Language REST API."""

    name: str = "gemini"

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-1.5-flash"):
        self.api_key = api_key or settings.CHATBOT_API_KEY
        self.model = model or settings.CHATBOT_MODEL or "gemini-1.5-flash"
        self.fallback = LocalBuiltinProvider()

    def generate_response(
        self,
        prompt: str,
        system_prompt: str,
        language: LanguageEnum = LanguageEnum.ENGLISH,
        file_meta: Optional[UploadedFileMeta] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        if not self.api_key:
            logger.warning("Gemini API key is not configured. Falling back to local clinical engine.")
            return self.fallback.generate_response(prompt, system_prompt, language, file_meta, context)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        # Construct Gemini contents structure
        parts: List[Dict[str, Any]] = []

        # Add image or document if present
        if file_meta and file_meta.image_base64:
            parts.append({
                "inline_data": {
                    "mime_type": file_meta.mime_type or "image/jpeg",
                    "data": file_meta.image_base64
                }
            })

        # Add contextual information (prescriptions, labs, extracted text)
        full_user_prompt = prompt
        if file_meta and file_meta.extracted_text:
            full_user_prompt += f"\n\n[Extracted Document Text]:\n{file_meta.extracted_text}"

        if context and context.get("authorized"):
            rx_count = len(context.get("prescriptions", []))
            lab_count = len(context.get("recent_labs", []))
            full_user_prompt += f"\n\n[Patient Clinical Context]: Verified patient with {rx_count} prescriptions and {lab_count} recent lab reports."

        parts.append({"text": full_user_prompt})

        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": parts
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "topP": 0.8,
                "maxOutputTokens": 1024
            }
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        content_parts = candidates[0].get("content", {}).get("parts", [])
                        if content_parts:
                            return content_parts[0].get("text", "").strip()
                logger.error(f"Gemini API returned error {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.exception(f"Network error communicating with Gemini API: {e}")

        # Fallback to local clinical engine on any API failure
        return self.fallback.generate_response(prompt, system_prompt, language, file_meta, context)
