# Methodology Knowledge Modules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the knowledge manager from extracting encyclopedia-style definitions to producing methodology-rich modules, with a curated global overview that lets strong LLMs (Opus 4.7+) autonomously navigate and apply project knowledge like a senior engineer.

**Architecture:** Redesign the extraction prompt and pipeline to produce "how we work" modules instead of "what is X" definitions. Build a meaningful knowledge base overview (index description + category descriptions) as the model's entry point. Add JSON retry, auto-categorize, cache wiring, and category-filtered search as supporting infrastructure.

**Tech Stack:** Python, Pydantic, httpx, pytest + unittest.mock (AsyncMock), snowballstemmer, FastMCP

---

### Task 1: Add `auto_categorize` and `existing_categories` fields to ExtractionConfig

**Files:**
- Modify: `knowledge-manager/src/knowledge_manager/schemas.py:127-131` (ExtractionConfig)
- Test: `knowledge-manager/tests/test_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to knowledge-manager/tests/test_schemas.py

def test_extraction_config_auto_categorize_default():
    from knowledge_manager.schemas import ExtractionConfig
    cfg = ExtractionConfig()
    assert cfg.auto_categorize is False

def test_extraction_config_auto_categorize_explicit():
    from knowledge_manager.schemas import ExtractionConfig
    cfg = ExtractionConfig(auto_categorize=True)
    assert cfg.auto_categorize is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest knowledge-manager/tests/test_schemas.py::test_extraction_config_auto_categorize_default -v`
Expected: FAIL with "type object 'ExtractionConfig' has no attribute 'auto_categorize'"

- [ ] **Step 3: Add the field to ExtractionConfig**

In `knowledge-manager/src/knowledge_manager/schemas.py:126-131`, replace the class:

```python
class ExtractionConfig(BaseModel):
    provider: str = "deepseek"
    max_modules_per_extraction: int = 10
    chunk_size: int = 8000
    chunk_overlap: int = 400
    auto_categorize: bool = False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest knowledge-manager/tests/test_schemas.py::test_extraction_config_auto_categorize_default knowledge-manager/tests/test_schemas.py::test_extraction_config_auto_categorize_explicit -v`
Expected: both PASS

- [ ] **Step 5: Commit**

```bash
git add knowledge-manager/src/knowledge_manager/schemas.py knowledge-manager/tests/test_schemas.py
git commit -m "feat: add auto_categorize field to ExtractionConfig"
```

---

### Task 2: Redesign extraction prompt for methodology + JSON retry

**Files:**
- Modify: `knowledge-manager/src/knowledge_manager/extractor.py:11-36` (prompt), `:64-156` (extract flow)
- Test: `knowledge-manager/tests/test_llm.py`

- [ ] **Step 1: Write failing tests for retry and methodology prompt**

```python
# Append to knowledge-manager/tests/test_llm.py

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest knowledge-manager/tests/test_llm.py::test_extractor_retries_on_json_failure knowledge-manager/tests/test_llm.py::test_extractor_handles_list_response_even_on_second_try knowledge-manager/tests/test_llm.py::test_extractor_methodology_prompt_includes_category_context knowledge-manager/tests/test_llm.py::test_extractor_preserves_category_in_module -v`
Expected: pytest collects all 4 but at least one FAILS (retry test fails because current code returns [] on first failure)

- [ ] **Step 3: Replace extraction prompt and add retry logic in extractor.py**

Replace the prompt constant at `knowledge-manager/src/knowledge_manager/extractor.py:11-36`:

```python
EXTRACTION_PROMPT = """\
You are a knowledge extraction assistant. Extract structured, methodology-focused knowledge modules from the raw text below.

This knowledge base captures HOW we work — our approaches, decisions, patterns, tradeoffs, and lessons learned. It is NOT an encyclopedia of definitions. Write as if onboarding a senior engineer: assume they know the core concepts, but need to understand OUR specific approach to each topic.

Category: {category}

Existing categories: {existing_categories}

Raw text:
{text}

Return a JSON array (no markdown, no explanation) of up to {max_modules} modules. Each module:
{{
  "category": "existing-or-new-kebab-case-category-name",
  "id": "kebab-case-id",
  "title": "Concise title (5+ chars)",
  "summary": "One sentence capturing our approach or decision (10-500 chars)",
  "content": {{
    "overview": "Our approach to this topic — what we do and why. Not a textbook definition. (10+ chars)",
    "details": "Specific decisions, tradeoffs, implementation patterns, and reasoning. Why we chose X over Y. (20+ chars)",
    "examples": "Real code, configs, commands, or patterns we actually use. Omit if the source provides none. (0+ chars)",
    "references": "Names of related modules, external docs, or internal links. Omit if none. (0+ chars)",
    "caveats": "Known pitfalls, sharp edges, limitations of our approach. Omit if none. (0+ chars)"
  }},
  "metadata": {{
    "tags": ["tag1", "tag2"],
    "confidence": "high|medium|low"
  }}
}}

Guidelines:
- Each module covers ONE topic, decision, or pattern. Don't cram.
- Prefer OUR specific way over general theory. "We use RS256 because..." not "JWT is a standard that..."
- Fill examples, references, caveats when the source provides real content. Don't invent.
- If the source is thin, extract the best actionable knowledge you can — don't pad.
"""
```

Replace the `Extractor` class (entire class, `knowledge-manager/src/knowledge_manager/extractor.py:58-203`):

```python
class Extractor:
    def __init__(self, llm: BaseLLMClient, config: ExtractionConfig):
        self.llm = llm
        self.config = config

    async def extract(self, text: str, category: str, existing_categories: str = "") -> List[Module]:
        max_modules = self.config.max_modules_per_extraction
        chunks = _chunk_text(text, self.config.chunk_size, self.config.chunk_overlap)
        logger.info(
            "Extracting category=%s from %s characters in %s chunk(s) "
            "(chunk_size=%s, overlap=%s)",
            category,
            len(text),
            len(chunks),
            self.config.chunk_size,
            self.config.chunk_overlap,
        )

        modules: List[Module] = []
        seen_ids: set[str] = set()
        for ci, chunk in enumerate(chunks, 1):
            if len(modules) >= max_modules:
                logger.info(
                    "Reached global cap of %s modules; stopping at chunk %s/%s",
                    max_modules,
                    ci - 1,
                    len(chunks),
                )
                break
            logger.debug("Processing chunk %s/%s (%s characters)", ci, len(chunks), len(chunk))
            chunk_modules = await self._extract_chunk(chunk, category, existing_categories, ci, len(chunks))
            for module in chunk_modules:
                if len(modules) >= max_modules:
                    break
                if module.id in seen_ids:
                    logger.debug("Skipping duplicate module id across chunks: %s", module.id)
                    continue
                seen_ids.add(module.id)
                modules.append(module)

        logger.info("Successfully extracted %s modules across %s chunk(s)", len(modules), len(chunks))
        return modules

    async def _extract_chunk(
        self, text: str, category: str, existing_categories: str, chunk_index: int, total_chunks: int
    ) -> List[Module]:
        prompt = EXTRACTION_PROMPT.format(
            category=category,
            existing_categories=existing_categories,
            text=text,
            max_modules=self.config.max_modules_per_extraction,
        )
        logger.debug(
            "Prepared prompt for chunk %s/%s (%s characters, category=%s, max_modules=%s)",
            chunk_index,
            total_chunks,
            len(prompt),
            category,
            self.config.max_modules_per_extraction,
        )

        items = await self._call_llm_with_retry(prompt, chunk_index, total_chunks)
        if not items:
            return []

        modules = []
        for i, item in enumerate(items[: self.config.max_modules_per_extraction]):
            try:
                content_data = item.get("content", {})
                meta_data = item.get("metadata", {})
                module = Module(
                    id=item["id"],
                    category=category,
                    title=item["title"],
                    summary=item["summary"],
                    content=ModuleContent(**content_data),
                    metadata=ModuleMetadata(**meta_data),
                )
                modules.append(module)
                logger.debug(
                    "Parsed module %s/%s from chunk %s/%s (id=%s, title_length=%s)",
                    i + 1,
                    min(len(items), self.config.max_modules_per_extraction),
                    chunk_index,
                    total_chunks,
                    module.id,
                    len(module.title),
                )
            except Exception as e:
                item_keys = sorted(item.keys()) if isinstance(item, dict) else None
                logger.warning(
                    "Failed to parse module %s for chunk %s/%s: %s (item_type=%s, keys=%s)",
                    i + 1,
                    chunk_index,
                    total_chunks,
                    e,
                    type(item).__name__,
                    item_keys,
                )
                continue

        return modules

    async def _call_llm_with_retry(
        self, prompt: str, chunk_index: int, total_chunks: int, max_retries: int = 2
    ) -> list | None:
        for attempt in range(max_retries + 1):
            logger.info(
                "Calling LLM for chunk %s/%s (attempt %s/%s)",
                chunk_index, total_chunks, attempt + 1, max_retries + 1,
            )
            try:
                raw = await self.llm.complete(prompt)
                logger.debug(
                    "Received LLM response for chunk %s/%s attempt %s (%s characters)",
                    chunk_index, total_chunks, attempt + 1, len(raw),
                )
            except Exception:
                logger.exception(
                    "LLM call failed for chunk %s/%s attempt %s",
                    chunk_index, total_chunks, attempt + 1,
                )
                return None

            raw = _strip_markdown_json(raw)
            logger.debug(
                "Normalized LLM response for chunk %s/%s attempt %s to %s characters",
                chunk_index, total_chunks, attempt + 1, len(raw),
            )

            try:
                items = json.loads(raw)
                logger.debug(
                    "Parsed JSON for chunk %s/%s attempt %s into %s item(s)",
                    chunk_index, total_chunks, attempt + 1,
                    len(items) if isinstance(items, list) else "non-list",
                )
            except json.JSONDecodeError as e:
                logger.error(
                    "JSON decode failed for chunk %s/%s attempt %s at position %s: %s (response_length=%s)",
                    chunk_index, total_chunks, attempt + 1, e.pos, e.msg, len(raw),
                )
                if attempt < max_retries:
                    prompt = (
                        f"Your previous response was not valid JSON. Error: {e}\n\n"
                        f"Return ONLY a JSON array, no markdown wrapping, no explanation.\n\n"
                        f"Original instructions:\n{prompt}"
                    )
                    continue
                return None

            if not isinstance(items, list):
                logger.error(
                    "Expected list response for chunk %s/%s attempt %s, got %s",
                    chunk_index, total_chunks, attempt + 1, type(items).__name__,
                )
                if attempt < max_retries:
                    prompt = (
                        f"Your previous response was a JSON object, but a JSON array is required.\n\n"
                        f"Return ONLY a JSON array of module objects, no markdown wrapping, no explanation.\n\n"
                        f"Original instructions:\n{prompt}"
                    )
                    continue
                return None

            return items

        return None
```

- [ ] **Step 4: Run all extractor-related tests to verify**

Run: `pytest knowledge-manager/tests/test_llm.py -v -k "extract"`

Expected: all 8 extraction tests PASS (4 new + migration test, dedup, cap, chunks, max_modules, no content leak)

Run: `pytest knowledge-manager/tests/test_llm.py -v`

Expected: all tests PASS (extraction + LLM client tests)

- [ ] **Step 5: Commit**

```bash
git add knowledge-manager/src/knowledge_manager/extractor.py knowledge-manager/tests/test_llm.py
git commit -m "feat: methodology-focused extraction prompt with JSON retry"
```

---

### Task 3: Auto-categorize — LLM assigns category per module

**Files:**
- Modify: `knowledge-manager/src/knowledge_manager/extractor.py:63-66` (`extract` method signature and logic)
- Modify: `knowledge-manager/src/knowledge_manager/cli.py:318-351` (`add` command)
- Test: `knowledge-manager/tests/test_llm.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to knowledge-manager/tests/test_llm.py

AUTO_CATEGORIZE_JSON = json.dumps([
    {
        "category": "auth",
        "id": "jwt-token-strategy",
        "title": "JWT Token Strategy",
        "summary": "We use short-lived access tokens with refresh rotation for API auth",
        "content": {
            "overview": "Our auth strategy uses RS256-signed JWTs with 15min expiry",
            "details": "We chose RS256 over HS256 so the API gateway can validate without shared secrets.",
            "examples": "",
            "references": "",
            "caveats": "",
        },
        "metadata": {"tags": ["jwt", "auth"], "confidence": "high"},
    },
    {
        "category": "database",
        "id": "connection-pool-sizing",
        "title": "Connection Pool Sizing",
        "summary": "Postgres connection pool sizing for our workload pattern",
        "content": {
            "overview": "We size pools based on active query count, not connection count",
            "details": "Our workload is read-heavy with occasional writes. We use PgBouncer in transaction mode.",
            "examples": "",
            "references": "",
            "caveats": "",
        },
        "metadata": {"tags": ["database", "performance"], "confidence": "high"},
    },
])


@pytest.mark.asyncio
async def test_auto_categorize_uses_llm_category_field():
    """When auto_categorize is True, use category from LLM response, not the parameter."""
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=AUTO_CATEGORIZE_JSON)

    cfg = ExtractionConfig(auto_categorize=True)
    extractor = Extractor(mock_llm, cfg)
    modules = await extractor.extract("raw text", "general")

    assert len(modules) == 2
    assert modules[0].category == "auth"
    assert modules[1].category == "database"


@pytest.mark.asyncio
async def test_auto_categorize_fallback_when_no_category_in_response():
    """When LLM doesn't include category in a module, fall back to the parameter."""
    no_cat = json.dumps([{
        "id": "some-module",
        "title": "Some Module Title",
        "summary": "A summary that is long enough",
        "content": {
            "overview": "Overview text that is long enough",
            "details": "Details text that is definitely long enough to pass validation",
        },
        "metadata": {"tags": ["test"], "confidence": "high"},
    }])
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=no_cat)

    cfg = ExtractionConfig(auto_categorize=True)
    extractor = Extractor(mock_llm, cfg)
    modules = await extractor.extract("raw text", "general")

    assert len(modules) == 1
    assert modules[0].category == "general"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest knowledge-manager/tests/test_llm.py::test_auto_categorize_uses_llm_category_field knowledge-manager/tests/test_llm.py::test_auto_categorize_fallback_when_no_category_in_response -v`
Expected: FAIL — modules get category from the `category` parameter, not from LLM response

- [ ] **Step 3: Update Extractor.extract to support auto_categorize**

In `knowledge-manager/src/knowledge_manager/extractor.py`, in the `extract` method and the `_extract_chunk` method's module parsing:

The `extract` method gains `existing_categories: str = ""` parameter (already added in Task 2).

In `_extract_chunk`, change the module parsing loop (where `content_data` and `meta_data` are extracted) to optionally read category from the LLM response:

```python
# In _extract_chunk, replace the module parsing section:
        modules = []
        for i, item in enumerate(items[: self.config.max_modules_per_extraction]):
            try:
                content_data = item.get("content", {})
                meta_data = item.get("metadata", {})
                llm_category = item.get("category") if self.config.auto_categorize else None
                module_category = (llm_category or category)
                module = Module(
                    id=item["id"],
                    category=module_category,
                    title=item["title"],
                    summary=item["summary"],
                    content=ModuleContent(**content_data),
                    metadata=ModuleMetadata(**meta_data),
                )
                modules.append(module)
```

And update `cli.py` `add` command to pass `existing_categories` when auto_categorize is enabled. In `knowledge-manager/src/knowledge_manager/cli.py:340-341`, replace:

```python
    modules = asyncio.run(extractor.extract(text, category))
```

with:

```python
    existing_categories = ""
    if cfg.extraction.auto_categorize:
        index = load_index(kb)
        if index is not None and index.categories:
            cat_descs = []
            for name, cat in index.categories.items():
                desc = f"  {name}"
                if cat.description:
                    desc += f": {cat.description}"
                cat_descs.append(desc)
            existing_categories = "\n".join(cat_descs)
    modules = asyncio.run(extractor.extract(text, category, existing_categories))
```

- [ ] **Step 4: Run tests**

Run: `pytest knowledge-manager/tests/test_llm.py -v -k "categorize or extract"`

Expected: all category + extract tests PASS

- [ ] **Step 5: Verify CLI backward compatibility — `km add` with explicit `-c` still works**

Run existing extract tests to ensure no regression:

Run: `pytest knowledge-manager/tests/test_llm.py -v`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add knowledge-manager/src/knowledge_manager/extractor.py knowledge-manager/src/knowledge_manager/cli.py knowledge-manager/tests/test_llm.py
git commit -m "feat: auto-categorize support in extraction pipeline"
```

---

### Task 4: Knowledge base overview — meaningful init + category descriptions

**Files:**
- Modify: `knowledge-manager/src/knowledge_manager/cli.py:111-137` (`init` command)
- Modify: `knowledge-manager/src/knowledge_manager/cli.py:356-388` (`review` command)
- Test: `knowledge-manager/tests/test_cli.py`

- [ ] **Step 1: Write a failing test for init overview**

```python
# Create knowledge-manager/tests/test_cli.py

from click.testing import CliRunner
from knowledge_manager.cli import cli
from pathlib import Path
from knowledge_manager.storage import load_index


def test_init_creates_meaningful_description():
    runner = CliRunner()
    with runner.isolated_filesystem():
        kb = Path("test_kb")
        result = runner.invoke(cli, ["--kb-path", str(kb), "init"])
        assert result.exit_code == 0

        index = load_index(kb)
        assert index is not None
        assert len(index.description) > 20, "Description should be more than just 'Knowledge base'"
        assert "methodology" in index.description.lower() or "knowledge" in index.description.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest knowledge-manager/tests/test_cli.py::test_init_creates_meaningful_description -v`
Expected: FAIL — current description is "Knowledge base" (too short)

- [ ] **Step 3: Update `km init` in cli.py**

In `knowledge-manager/src/knowledge_manager/cli.py:122`, replace:

```python
    save_index(Index(description="Knowledge base"), kb)
```

with:

```python
    overview = (
        "A curated knowledge base of our team's technical methodology — "
        "architecture decisions, implementation patterns, operational practices, "
        "and lessons learned. Each module captures HOW we approach a topic, "
        "not just what it means. Use the index to identify relevant modules, "
        "then load the ones you need. Prefer modules with higher confidence "
        "ratings. Cross-reference related modules when topics overlap."
    )
    save_index(Index(description=overview), kb)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest knowledge-manager/tests/test_cli.py::test_init_creates_meaningful_description -v`
Expected: PASS

- [ ] **Step 5: Also update the default init config to enable auto_categorize**

In `knowledge-manager/src/knowledge_manager/cli.py:133`, change:

```python
        extraction=ExtractionConfig(provider="deepseek"),
```

to:

```python
        extraction=ExtractionConfig(provider="deepseek", auto_categorize=True),
```

- [ ] **Step 6: Commit**

```bash
git add knowledge-manager/src/knowledge_manager/cli.py knowledge-manager/tests/test_cli.py
git commit -m "feat: meaningful knowledge base overview on init"
```

---

### Task 5: Wire ModuleCache into MCP server

**Files:**
- Modify: `knowledge-manager/src/knowledge_manager/mcp_server.py:9-55` (create_server)
- Create: `knowledge-manager/tests/test_cache.py` (already exists, append)

- [ ] **Step 1: Write failing test for cached module loading**

```python
# Append to knowledge-manager/tests/test_mcp_server.py

def test_load_module_uses_cache(kb_path):
    """load_module should hit cache on second call for the same module."""
    import time
    from knowledge_manager.mcp_server import create_server
    from knowledge_manager.schemas import Module, ModuleContent
    from knowledge_manager.storage import save_module

    save_module(make_module("auth-jwt", "auth"), kb_path)

    server = create_server(kb_path)

    import asyncio
    async def measure():
        result1 = await server.call_tool("load_module", {"module_id": "auth-jwt", "category": "auth"})
        t1 = asyncio.get_event_loop().time()

        result2 = await server.call_tool("load_module", {"module_id": "auth-jwt", "category": "auth"})
        t2 = asyncio.get_event_loop().time()

        content1 = result1[0].text if hasattr(result1[0], "text") else str(result1[0])
        content2 = result2[0].text if hasattr(result2[0], "text") else str(result2[0])
        assert "JWT" in content1
        assert "JWT" in content2

    asyncio.run(measure())
```

- [ ] **Step 2: Run test to verify current behavior**

Run: `pytest knowledge-manager/tests/test_mcp_server.py::test_load_module_uses_cache -v`
Expected: PASS (the test validates load_module still works, which confirms our setup)

Note: this test verifies functionality, not cache hit rate — cache miss vs hit is hard to observe externally. The structural change (below) is what matters.

- [ ] **Step 3: Wire cache into create_server**

In `knowledge-manager/src/knowledge_manager/mcp_server.py:9-55`, replace the entire file:

```python
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from knowledge_manager.cache import ModuleCache
from knowledge_manager.storage import load_index, load_module, search_modules


def create_server(kb_path: Path, cache: ModuleCache | None = None) -> FastMCP:
    if cache is None:
        cache = ModuleCache()

    mcp = FastMCP("knowledge-manager")

    @mcp.resource("knowledge://index")
    def get_index() -> str:
        index = load_index(kb_path)
        if index is None:
            return json.dumps({
                "version": "1.0",
                "description": "Empty knowledge base — use `km add` to populate",
                "categories": {},
                "stats": {},
            })
        return index.model_dump_json()

    @mcp.tool(name="load_module")
    def load_module_tool(module_id: str, category: str) -> str:
        """Load a full knowledge module by ID and category."""
        cached = cache.get(module_id)
        if cached is not None:
            return cached.model_dump_json(indent=2)

        module = load_module(module_id, category, kb_path)
        if module is None:
            return f"Module not found: {module_id} in category {category}"

        cache.put(module)
        return module.model_dump_json(indent=2)

    @mcp.tool(name="search_modules")
    def search_modules_tool(query: str, category: str = "") -> str:
        """Search modules by keyword. Word-boundary matching across title, tags,
        summary, and overview; results scored and sorted by relevance.
        Optionally filter by category."""
        results = [
            {
                "id": m.id,
                "category": m.category,
                "title": m.title,
                "summary": m.summary,
                "tags": m.metadata.tags,
            }
            for m in search_modules(query, kb_path, category if category else None)
        ]
        return json.dumps(results, indent=2)

    @mcp.tool(name="list_categories")
    def list_categories_tool() -> str:
        """List all categories and their module counts."""
        index = load_index(kb_path)
        if index is None:
            return json.dumps([])
        result = [
            {
                "category": name,
                "module_count": len(cat.modules),
                "description": cat.description,
            }
            for name, cat in index.categories.items()
        ]
        return json.dumps(result, indent=2)

    return mcp
```

- [ ] **Step 4: Run MCP server tests**

Run: `pytest knowledge-manager/tests/test_mcp_server.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add knowledge-manager/src/knowledge_manager/mcp_server.py knowledge-manager/tests/test_mcp_server.py
git commit -m "feat: wire module cache into MCP server, add category filter to search"
```

---

### Task 6: Category-filtered search in storage layer

**Files:**
- Modify: `knowledge-manager/src/knowledge_manager/storage.py:71-135` (`search_modules` signature and body)
- Test: `knowledge-manager/tests/test_storage.py`

- [ ] **Step 1: Write failing test**

```python
# Append to knowledge-manager/tests/test_storage.py

def test_search_modules_with_category_filter(kb_path):
    _kb_with_signals(kb_path)
    results = search_modules("auth", kb_path, category="auth")
    ids = [m.id for m in results]
    assert "jwt" in ids
    assert "conn-pool" not in ids, "conn-pool is in database category, should be filtered out"


def test_search_modules_with_nonexistent_category(kb_path):
    _kb_with_signals(kb_path)
    results = search_modules("auth", kb_path, category="nonexistent")
    assert results == []


def test_search_modules_without_category_filter_returns_all(kb_path):
    _kb_with_signals(kb_path)
    results = search_modules("auth", kb_path)
    ids = [m.id for m in results]
    assert "jwt" in ids
    assert "conn-pool" in ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest knowledge-manager/tests/test_storage.py::test_search_modules_with_category_filter -v`
Expected: FAIL — `search_modules() got an unexpected keyword argument 'category'`

- [ ] **Step 3: Update search_modules signature and filter logic**

In `knowledge-manager/src/knowledge_manager/storage.py:71`, change the function signature:

```python
def search_modules(query: str, kb_path: Path, category: str | None = None) -> List[Module]:
```

And add the filter right after the scored list is built (after line 132, before the sort):

```python
    # Filter by category if specified
    if category is not None:
        scored = [(s, q, m) for s, q, m in scored if m.category == category]
```

- [ ] **Step 4: Run tests**

Run: `pytest knowledge-manager/tests/test_storage.py -v -k "search"`

Expected: all search tests PASS (3 new + all existing)

Run: `pytest knowledge-manager/tests/test_storage.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add knowledge-manager/src/knowledge_manager/storage.py knowledge-manager/tests/test_storage.py
git commit -m "feat: category-filtered search in storage layer"
```

---

### Task 7: Full integration smoke test

**Files:**
- Modify: None (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `pytest knowledge-manager/tests/ -v`
Expected: all tests PASS (~40+ tests across test_llm.py, test_storage.py, test_schemas.py, test_mcp_server.py, test_cli.py, test_cache.py)

- [ ] **Step 2: Verify `km init` creates the new overview**

Run: `km --kb-path /tmp/test_kb_methodology init && cat /tmp/test_kb_methodology/index.json | python -m json.tool | head -10`
Expected: description field contains "methodology" / "curated knowledge base"

- [ ] **Step 3: Verify extraction with new prompt works end-to-end**

Run with a real LLM (requires API key):
```bash
echo "We use RS256 JWT tokens with 15-minute expiry. Tokens are validated at the API gateway using a JWKS endpoint. We chose RS256 over HS256 so validation can happen without a shared secret. The main pitfall is that short-lived tokens mean clients must handle 401 responses gracefully." > /tmp/test_jwt.txt
km --kb-path /tmp/test_kb_methodology add /tmp/test_jwt.txt -c auth
km --kb-path /tmp/test_kb_methodology review
```
Expected: extracted module(s) in staging with methodology-level content (approach decisions, tradeoffs, caveats filled)

- [ ] **Step 4: Commit final state if any changes remain**

```bash
git status
```

---
