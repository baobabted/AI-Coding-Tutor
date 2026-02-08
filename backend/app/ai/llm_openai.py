import asyncio
import json
import logging
from typing import AsyncIterator

import httpx

from app.ai.llm_base import LLMProvider, LLMError

logger = logging.getLogger(__name__)

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-5.2"


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def generate_stream(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 8192,
    ) -> AsyncIterator[str]:
        """Stream tokens from the OpenAI Chat Completions API.

        Request format (POST /v1/chat/completions):
          {
            "model": "gpt-5.2",
            "stream": true,
            "max_tokens": 8192,
            "messages": [
              {"role": "system", "content": "..."},
              {"role": "user", "content": "..."},
              {"role": "assistant", "content": "..."}
            ]
          }

        SSE stream chunks:
          data: {"choices":[{"delta":{"content":"Hello"},...}]}
          ...
          data: [DONE]
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # OpenAI uses a "system" role message for system prompts
        api_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            api_messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        payload = {
            "model": OPENAI_MODEL,
            "max_tokens": max_tokens,
            "messages": api_messages,
            "stream": True,
        }

        retries = 3
        backoff = 1

        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    async with client.stream(
                        "POST", OPENAI_API_URL, json=payload, headers=headers
                    ) as response:
                        if response.status_code == 429 or response.status_code >= 500:
                            if attempt < retries - 1:
                                logger.warning(
                                    "OpenAI API returned %d, retrying in %ds",
                                    response.status_code,
                                    backoff,
                                )
                                await asyncio.sleep(backoff)
                                backoff *= 2
                                continue
                            raise LLMError(
                                f"OpenAI API error {response.status_code} after {retries} retries"
                            )

                        if response.status_code != 200:
                            body = await response.aread()
                            raise LLMError(
                                f"OpenAI API error {response.status_code}: {body.decode()}"
                            )

                        async for line in response.aiter_lines():
                            if not line.startswith("data: "):
                                continue
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                break
                            try:
                                event = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue

                            choices = event.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                text = delta.get("content", "")
                                if text:
                                    yield text
                        return

            except httpx.TimeoutException:
                if attempt < retries - 1:
                    logger.warning("OpenAI API timeout, retrying in %ds", backoff)
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                raise LLMError("OpenAI API timeout after retries")
            except LLMError:
                raise
            except Exception as e:
                raise LLMError(f"OpenAI API unexpected error: {e}")

    def count_tokens(self, text: str) -> int:
        """Approximate token count using character heuristic."""
        return max(1, len(text) // 4)
