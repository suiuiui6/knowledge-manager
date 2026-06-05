import json
import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from knowledge_manager.schemas import LLMProviderConfig, ExtractionConfig
from knowledge_manager.llm_clients import DeepSeekClient, ClaudeClient, OpenAIClient, create_client
from knowledge_manager.extractor import Extractor, _chunk_text


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


@pytest.mark.asyncio
async def test_llm_client_logs_metadata_without_prompt_leak(caplog):
    prompt = "top secret prompt body"
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
        with caplog.at_level(logging.DEBUG, logger="knowledge_manager.llm_clients"):
            result = await client.complete(prompt)

    assert result == "hello"
    assert any("request prepared" in record.getMessage() for record in caplog.records)
    assert any("response received" in record.getMessage() for record in caplog.records)
    assert prompt not in caplog.text
    assert "hello" not in caplog.text


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


# --- Chunking tests ---


def test_chunk_text_no_split_when_small():
    assert _chunk_text("short", 8000, 400) == ["short"]


def test_chunk_text_splits_with_overlap():
    text = "abcdefghij"  # 10 chars
    chunks = _chunk_text(text, chunk_size=4, overlap=1)
    assert chunks == ["abcd", "defg", "ghij"]
    # overlap: end of one chunk reappears at start of next
    assert chunks[0][-1] == chunks[1][0]


def test_chunk_text_zero_size_returns_whole():
    assert _chunk_text("anything", 0, 0) == ["anything"]


def _module_json(mod_id: str) -> dict:
    return {
        "id": mod_id,
        "title": f"Title for {mod_id}",
        "summary": f"Summary for {mod_id} which is long enough to pass validation",
        "content": {
            "overview": "Overview text that is long enough",
            "details": "Details text that is definitely long enough to pass",
        },
        "metadata": {"tags": ["t"], "confidence": "high"},
    }


@pytest.mark.asyncio
async def test_extractor_aggregates_across_chunks():
    chunk1 = json.dumps([_module_json("alpha"), _module_json("beta")])
    chunk2 = json.dumps([_module_json("gamma")])
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(side_effect=[chunk1, chunk2])

    # chunk_size=5 forces "0123456789" into multiple chunks
    cfg = ExtractionConfig(chunk_size=5, chunk_overlap=0)
    extractor = Extractor(mock_llm, cfg)
    modules = await extractor.extract("0123456789", "general")

    assert mock_llm.complete.await_count == 2
    assert [m.id for m in modules] == ["alpha", "beta", "gamma"]


@pytest.mark.asyncio
async def test_extractor_dedupes_ids_across_chunks():
    chunk1 = json.dumps([_module_json("dup"), _module_json("alpha")])
    chunk2 = json.dumps([_module_json("dup"), _module_json("beta")])
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(side_effect=[chunk1, chunk2])

    cfg = ExtractionConfig(chunk_size=5, chunk_overlap=0)
    extractor = Extractor(mock_llm, cfg)
    modules = await extractor.extract("0123456789", "general")

    assert [m.id for m in modules] == ["dup", "alpha", "beta"]


@pytest.mark.asyncio
async def test_extractor_global_cap_across_chunks():
    chunk1 = json.dumps([_module_json("a"), _module_json("b")])
    chunk2 = json.dumps([_module_json("c"), _module_json("d")])
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(side_effect=[chunk1, chunk2])

    cfg = ExtractionConfig(max_modules_per_extraction=3, chunk_size=5, chunk_overlap=0)
    extractor = Extractor(mock_llm, cfg)
    modules = await extractor.extract("0123456789", "general")

    assert len(modules) == 3
    assert [m.id for m in modules] == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_extractor_logs_metadata_without_content_leak(caplog):
    raw_text = "private source material with credentials-like text"
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=VALID_EXTRACTION_JSON)

    extractor = Extractor(mock_llm, ExtractionConfig())
    with caplog.at_level(logging.DEBUG, logger="knowledge_manager.extractor"):
        modules = await extractor.extract(raw_text, "auth")

    assert len(modules) == 1
    assert any("Extracting category=auth" in record.getMessage() for record in caplog.records)
    assert any("Prepared prompt" in record.getMessage() for record in caplog.records)
    assert raw_text not in caplog.text
    assert VALID_EXTRACTION_JSON not in caplog.text


METHODOLOGY_EXTRACTION_JSON = json.dumps([
    {
        "category": "auth",
        "id": "jwt-token-strategy",
        "title": "JWT Token Strategy",
        "summary": "We use short-lived access tokens with refresh rotation for API auth",
        "content": {
            "overview": "Our auth strategy uses RS256-signed JWTs with 15min expiry and rotating refresh tokens",
            "details": "We chose RS256 over HS256 so the API gateway can validate without shared secrets. Refresh tokens rotate on each use to limit replay window. Token blacklist is maintained in Redis.",
            "examples": "Authorization: Bearer eyJ...\n\ncurl -H 'Authorization: Bearer $TOKEN' https://api.example.com/v1/users",
            "references": "auth/oauth-2-0-framework, auth/access-token-usage",
            "caveats": "Short expiry means clients must handle 401s gracefully and retry with refresh. Redis blacklist is a SPOF — fail open if Redis is unavailable."
        },
        "metadata": {"tags": ["jwt", "auth", "tokens", "security"], "confidence": "high"},
    }
])

INVALID_THEN_VALID_JSON = [
    'not valid json at all {{{broken',
    METHODOLOGY_EXTRACTION_JSON,
]


@pytest.mark.asyncio
async def test_extractor_retries_on_json_failure():
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(side_effect=INVALID_THEN_VALID_JSON)

    extractor = Extractor(mock_llm, ExtractionConfig())
    modules = await extractor.extract("raw text about JWT", "auth")

    assert mock_llm.complete.await_count == 2
    assert len(modules) == 1
    assert modules[0].id == "jwt-token-strategy"


@pytest.mark.asyncio
async def test_extractor_handles_list_response_even_on_second_try():
    """After a non-list response on attempt 1, retry should get list on attempt 2."""
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(side_effect=[
        '{"not": "a list"}',
        METHODOLOGY_EXTRACTION_JSON,
    ])

    extractor = Extractor(mock_llm, ExtractionConfig())
    modules = await extractor.extract("raw text about JWT", "auth")

    assert len(modules) == 1
    assert modules[0].id == "jwt-token-strategy"


@pytest.mark.asyncio
async def test_extractor_methodology_prompt_includes_category_context():
    """Verify the prompt tells the LLM about existing categories."""
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=METHODOLOGY_EXTRACTION_JSON)

    extractor = Extractor(mock_llm, ExtractionConfig())
    await extractor.extract("raw text", "auth")

    call_text = mock_llm.complete.call_args[0][0]
    assert "methodology" in call_text.lower() or "how we" in call_text.lower() or "our approach" in call_text.lower()
    assert "auth" in call_text


@pytest.mark.asyncio
async def test_extractor_preserves_category_in_module():
    """Module's category field should be set from the extraction category parameter."""
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=METHODOLOGY_EXTRACTION_JSON)

    extractor = Extractor(mock_llm, ExtractionConfig())
    modules = await extractor.extract("raw text", "auth")

    assert modules[0].category == "auth"


@pytest.mark.asyncio
async def test_extractor_returns_empty_on_llm_exception():
    """LLM call failure should return empty list, not retry."""
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(side_effect=RuntimeError("API connection failed"))

    extractor = Extractor(mock_llm, ExtractionConfig())
    modules = await extractor.extract("raw text", "auth")

    assert modules == []
    assert mock_llm.complete.await_count == 1  # No retry on exception
