"""
CHIKITSASETU AI Health Assistant - OpenAI / Standard REST Provider
Communicates with OpenAI-compatible multimodal APIs (OpenAI, Groq, Ollama) via REST using httpx.
"""
import logging
from typing import Optional, Dict, Any, List
import httpx

from backend.config import settings
from backend.chatbot.providers.base import AIProviderBase
from backend.chatbot.providers.local_provider import LocalBuiltinProvider
from backend.chatbot.schemas import UploadedFileMeta, LanguageEnum

logger = logging.getLogger(__name__)


class OpenAIProvider(AIProviderBase):
    """OpenAI-compatible multimodal provider (GPT-4o, Groq, Ollama)."""

    name: str = "openai"

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini", api_base: Optional[str] = None):
        self.api_key = api_key or settings.CHATBOT_API_KEY
        self.model = model or settings.CHATBOT_MODEL or "gpt-4o-mini"
        self.api_base = (api_base or settings.CHATBOT_API_BASE or "https://api.openai.com/v1").rstrip("/")
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
            logger.warning("OpenAI API key is not configured. Falling back to local clinical engine.")
            return self.fallback.generate_response(prompt, system_prompt, language, file_meta, context)

        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        user_content: List[Dict[str, Any]] = []

        full_prompt = prompt
        if file_meta and file_meta.extracted_text:
            full_prompt += f"\n\n[Extracted Document Text]:\n{file_meta.extracted_text}"

        user_content.append({"type": "text", "text": full_prompt})

        if file_meta and file_meta.image_base64:
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{file_meta.mime_type or 'image/jpeg'};base64,{file_meta.image_base64}"
                }
            })

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 1024
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "").strip()
                logger.error(f"OpenAI API returned error {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.exception(f"Network error communicating with OpenAI API: {e}")

        # Fallback to local clinical engine
        return self.fallback.generate_response(prompt, system_prompt, language, file_meta, context)
