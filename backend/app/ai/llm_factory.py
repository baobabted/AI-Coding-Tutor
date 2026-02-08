import logging

from app.ai.llm_base import LLMProvider, LLMError
from app.ai.llm_anthropic import AnthropicProvider
from app.ai.llm_openai import OpenAIProvider
from app.ai.llm_google import GoogleGeminiProvider

logger = logging.getLogger(__name__)


def get_llm_provider(settings) -> LLMProvider:
    """Return the configured primary LLM provider."""
    provider = settings.llm_provider.lower()

    if provider == "anthropic" and settings.anthropic_api_key:
        return AnthropicProvider(settings.anthropic_api_key)
    if provider == "openai" and settings.openai_api_key:
        return OpenAIProvider(settings.openai_api_key)
    if provider == "google" and settings.google_api_key:
        return GoogleGeminiProvider(settings.google_api_key)

    # Fall back to any available provider
    if settings.anthropic_api_key:
        return AnthropicProvider(settings.anthropic_api_key)
    if settings.openai_api_key:
        return OpenAIProvider(settings.openai_api_key)
    if settings.google_api_key:
        return GoogleGeminiProvider(settings.google_api_key)

    raise LLMError(
        "No LLM provider configured. "
        "Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or GOOGLE_API_KEY in .env"
    )


async def get_llm_with_fallback(settings) -> LLMProvider:
    """Return an available LLM provider, trying fallbacks if needed.

    Priority chain: Anthropic -> OpenAI -> Google Gemini.
    """
    providers: list[tuple[str, LLMProvider]] = []

    if settings.anthropic_api_key:
        providers.append(("Anthropic", AnthropicProvider(settings.anthropic_api_key)))
    if settings.openai_api_key:
        providers.append(("OpenAI", OpenAIProvider(settings.openai_api_key)))
    if settings.google_api_key:
        providers.append(("Google Gemini", GoogleGeminiProvider(settings.google_api_key)))

    if not providers:
        raise LLMError(
            "No LLM provider configured. "
            "Set at least ANTHROPIC_API_KEY, OPENAI_API_KEY, or GOOGLE_API_KEY."
        )

    return providers[0][1]
