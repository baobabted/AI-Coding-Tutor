from abc import ABC, abstractmethod
from typing import AsyncIterator

LLMContentPart = dict[str, str]
LLMMessage = dict[str, str | list[LLMContentPart]]


class LLMError(Exception):
    """Raised when an LLM provider fails unrecoverably."""
    pass


class LLMProvider(ABC):
    @abstractmethod
    async def generate_stream(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        max_tokens: int = 8192,
    ) -> AsyncIterator[str]:
        """Yield response tokens one at a time."""
        ...

    async def generate(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        max_tokens: int = 30,
    ) -> str:
        """Non-streaming generation. Collects output from generate_stream."""
        parts: list[str] = []
        async for chunk in self.generate_stream(system_prompt, messages, max_tokens):
            parts.append(chunk)
        return "".join(parts)

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Return approximate token count for the given text."""
        ...
