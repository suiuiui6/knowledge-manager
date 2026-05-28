import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from knowledge_manager.schemas import LLMProviderConfig, ExtractionConfig
from knowledge_manager.llm_clients import DeepSeekClient, ClaudeClient, OpenAIClient, create_client
from knowledge_manager.extractor import Extractor


def make_deepseek_config(**kwargs) -> LLMProviderConfig:
    return LLMProviderConfig(
        api_key="sk-test",
        model="deepseek-v4-pro",
        base_url="https://api.deepseek.com",
        **kwargs,
    )


def make_claude_config() -> LLMProviderConfig:
    return LLMProviderConfig(api_key="sk-ant-test", model="claude-sonnet-4-6")


def make_openai_config() -> LLMProviderConfig:
    return LLMProviderConfig(api_key="sk-openai-test", model="gpt-4")


MOCK_OPENAI_RESPONSE = {
    "choices": [{"message": {"content": "hello"}}]
}

MOCK_CLAUDE_RESPONSE = {
    "content": [{"text": "hello"}]
}


@pytest.mark.asyncio
async def test_deepseek_calls_correct_endpoint():
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_OPENAI_RESPONSE
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        client = DeepSeekClient(make_deepseek_config())
        result = await client.complete("test prompt")

        assert result == "hello"
        call_kwargs = mock_client.post.call_args
        assert "api.deepseek.com" in call_kwargs[0][0]
        assert call_kwargs[1]["headers"]["Authorization"] == "Bearer sk-test"


@pytest.mark.asyncio
async def test_claude_calls_correct_endpoint():
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_CLAUDE_RESPONSE
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        client = ClaudeClient(make_claude_config())
        result = await client.complete("test prompt")

        assert result == "hello"
        call_kwargs = mock_client.post.call_args
        assert "anthropic.com" in call_kwargs[0][0]
        assert call_kwargs[1]["headers"]["x-api-key"] == "sk-ant-test"


@pytest.mark.asyncio
async def test_openai_calls_correct_endpoint():
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_OPENAI_RESPONSE
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        client = OpenAIClient(make_openai_config())
        result = await client.complete("test prompt")

        assert result == "hello"
        call_kwargs = mock_client.post.call_args
        assert "openai.com" in call_kwargs[0][0]


def test_create_client_deepseek():
    client = create_client("deepseek", make_deepseek_config())
    assert isinstance(client, DeepSeekClient)


def test_create_client_claude():
    client = create_client("claude", make_claude_config())
    assert isinstance(client, ClaudeClient)


def test_create_client_openai():
    client = create_client("openai", make_openai_config())
    assert isinstance(client, OpenAIClient)


# --- Extractor tests ---

VALID_EXTRACTION_JSON = json.dumps([
    {
        "id": "auth-jwt",
        "title": "JWT Authentication",
        "summary": "How JWT tokens work in our system for authentication purposes",
        "content": {
            "overview": "JWT tokens are used for stateless authentication",
            "details": "Tokens are signed with RS256 and expire after 24 hours",
            "examples": "",
            "references": "",
            "caveats": "",
        },
        "metadata": {"tags": ["auth", "jwt"], "confidence": "high"},
    }
])


@pytest.mark.asyncio
async def test_extractor_returns_modules():
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=VALID_EXTRACTION_JSON)

    extractor = Extractor(mock_llm, ExtractionConfig())
    modules = await extractor.extract("Some raw text about JWT auth", "auth")

    assert len(modules) == 1
    assert modules[0].id == "auth-jwt"
    assert modules[0].category == "auth"
    assert modules[0].metadata.tags == ["auth", "jwt"]


@pytest.mark.asyncio
async def test_extractor_handles_json_in_markdown():
    wrapped = f"```json\n{VALID_EXTRACTION_JSON}\n```"
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=wrapped)

    extractor = Extractor(mock_llm, ExtractionConfig())
    modules = await extractor.extract("raw text", "auth")
    assert len(modules) == 1


@pytest.mark.asyncio
async def test_extractor_returns_empty_on_invalid_json():
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value="not valid json at all")

    extractor = Extractor(mock_llm, ExtractionConfig())
    modules = await extractor.extract("raw text", "general")
    assert modules == []


@pytest.mark.asyncio
async def test_extractor_respects_max_modules():
    many = json.dumps([
        {
            "id": f"mod-{i}",
            "title": f"Module {i} Title",
            "summary": f"Summary for module {i} which is long enough to pass validation",
            "content": {
                "overview": "Overview text that is long enough",
                "details": "Details text that is definitely long enough to pass",
            },
            "metadata": {},
        }
        for i in range(15)
    ])
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=many)

    extractor = Extractor(mock_llm, ExtractionConfig(max_modules_per_extraction=5))
    modules = await extractor.extract("raw text", "general")
    assert len(modules) <= 5
