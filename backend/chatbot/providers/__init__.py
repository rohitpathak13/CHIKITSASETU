"""
CHIKITSASETU AI Health Assistant - AI Providers Factory
"""
from backend.config import settings
from backend.chatbot.providers.base import AIProviderBase
from backend.chatbot.providers.local_provider import LocalBuiltinProvider
from backend.chatbot.providers.gemini_provider import GeminiProvider
from backend.chatbot.providers.openai_provider import OpenAIProvider


def get_ai_provider() -> AIProviderBase:
    """
    Factory creating the configured AI provider.
    Defaults to the local clinical knowledge engine when no external API key is set.
    """
    provider_type = (settings.CHATBOT_PROVIDER or "auto").lower().strip()
    api_key = settings.CHATBOT_API_KEY

    if provider_type == "gemini":
        return GeminiProvider()
    elif provider_type == "openai":
        return OpenAIProvider()
    elif provider_type == "local":
        return LocalBuiltinProvider()

    # "auto" resolution
    if api_key:
        if api_key.startswith("AIzaSy") or "gemini" in (settings.CHATBOT_MODEL or "").lower():
            return GeminiProvider()
        return OpenAIProvider()

    return LocalBuiltinProvider()


__all__ = [
    "AIProviderBase",
    "LocalBuiltinProvider",
    "GeminiProvider",
    "OpenAIProvider",
    "get_ai_provider",
]
