import re
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict

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
        logger.debug(f"DeepSeek API call: {url}")
        logger.debug(f"Model: {self.config.model}, temp: {self.config.temperature}, max_tokens: {self.config.max_tokens}")

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                    timeout=60,
                )
                resp.raise_for_status()
                result = resp.json()
                content = result["choices"][0]["message"]["content"]
                logger.debug(f"DeepSeek response: {len(content)} characters")
                return content
            except httpx.HTTPStatusError as e:
                logger.error(f"DeepSeek API error: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"DeepSeek API call failed: {e}")
                raise


class ClaudeClient(BaseLLMClient):
    async def complete(self, prompt: str) -> str:
        async with httpx.AsyncClient() as client:
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
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["content"][0]["text"]


class OpenAIClient(BaseLLMClient):
    async def complete(self, prompt: str) -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                json={
                    "model": self.config.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": self.config.temperature,
                    "max_tokens": self.config.max_tokens,
                },
                headers={"Authorization": f"Bearer {self.config.api_key}"},
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


def create_client(provider_name: str, config: LLMProviderConfig) -> BaseLLMClient:
    clients = {
        "deepseek": DeepSeekClient,
        "claude": ClaudeClient,
        "openai": OpenAIClient,
    }
    cls = clients.get(provider_name, DeepSeekClient)
    return cls(config)
