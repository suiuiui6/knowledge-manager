import logging
from abc import ABC, abstractmethod
from typing import Any, cast

import httpx

from knowledge_manager.schemas import LLMProviderConfig


logger = logging.getLogger(__name__)


class BaseLLMClient(ABC):
    def __init__(self, config: LLMProviderConfig):
        self.config = config

    @abstractmethod
    async def complete(self, prompt: str) -> str:
        ...


class DeepSeekClient(BaseLLMClient):
    async def complete(self, prompt: str) -> str:
        url = f"{self.config.base_url or 'https://api.deepseek.com'}/v1/chat/completions"
        payload = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        logger.debug("DeepSeek request prepared for model=%s max_tokens=%s", self.config.model, self.config.max_tokens)

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                    timeout=120,
                )
                resp.raise_for_status()
                result = cast(dict[str, Any], resp.json())
                content = cast(str, result["choices"][0]["message"]["content"])
                logger.debug("DeepSeek response received (%s characters)", len(content))
                return content
            except httpx.HTTPStatusError as e:
                logger.error("DeepSeek API error: %s", e.response.status_code)
                raise
            except Exception:
                logger.exception("DeepSeek API call failed")
                raise


class ClaudeClient(BaseLLMClient):
    async def complete(self, prompt: str) -> str:
        logger.debug(
            "Claude request prepared for model=%s max_tokens=%s",
            self.config.model,
            self.config.max_tokens,
        )
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    json={
                        "model": self.config.model,
                        "max_tokens": self.config.max_tokens,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                    headers={
                        "x-api-key": self.config.api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    timeout=120,
                )
                resp.raise_for_status()
                result = cast(dict[str, Any], resp.json())
                content = cast(str, result["content"][0]["text"])
                logger.debug("Claude response received (%s characters)", len(content))
                return content
            except httpx.HTTPStatusError as e:
                logger.error("Claude API error: %s", e.response.status_code)
                raise
            except Exception:
                logger.exception("Claude API call failed")
                raise


class OpenAIClient(BaseLLMClient):
    async def complete(self, prompt: str) -> str:
        logger.debug(
            "OpenAI request prepared for model=%s max_tokens=%s",
            self.config.model,
            self.config.max_tokens,
        )
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    json={
                        "model": self.config.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": self.config.temperature,
                        "max_tokens": self.config.max_tokens,
                    },
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                    timeout=120,
                )
                resp.raise_for_status()
                result = cast(dict[str, Any], resp.json())
                content = cast(str, result["choices"][0]["message"]["content"])
                logger.debug("OpenAI response received (%s characters)", len(content))
                return content
            except httpx.HTTPStatusError as e:
                logger.error("OpenAI API error: %s", e.response.status_code)
                raise
            except Exception:
                logger.exception("OpenAI API call failed")
                raise


def create_client(provider_name: str, config: LLMProviderConfig) -> BaseLLMClient:
    if provider_name == "claude":
        return ClaudeClient(config)
    if provider_name == "openai":
        return OpenAIClient(config)
    return DeepSeekClient(config)
