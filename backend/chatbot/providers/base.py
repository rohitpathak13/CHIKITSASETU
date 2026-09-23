"""
CHIKITSASETU AI Health Assistant - Base Provider Interface
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from backend.chatbot.schemas import UploadedFileMeta, LanguageEnum


class AIProviderBase(ABC):
    """Abstract interface that all multimodal and local AI providers must implement."""

    name: str = "base"

    @abstractmethod
    def generate_response(
        self,
        prompt: str,
        system_prompt: str,
        language: LanguageEnum = LanguageEnum.ENGLISH,
        file_meta: Optional[UploadedFileMeta] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generates a clinical educational response given prompt and multimodal context."""
        pass
