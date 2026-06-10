import json
import logging
import re
from pathlib import Path
from typing import List

from knowledge_manager.llm_clients import BaseLLMClient
from knowledge_manager.schemas import ExtractionConfig, Module, ModuleContent, ModuleMetadata

logger = logging.getLogger(__name__)

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

IMAGE_PROMPT = """\
Analyze this image and extract structured, methodology-focused knowledge modules.

Treat the image as a source of architecture/design/process knowledge. For diagrams: identify components, data flows, technology choices, and architectural decisions. For screenshots: extract the workflow or pattern shown. For other images: describe what methodology or decision is captured.

Category: {category}

Return a JSON array (no markdown, no explanation) of up to {max_modules} modules in the same format as standard extraction:
{{
  "category": "kebab-case-category-name",
  "id": "kebab-case-id",
  "title": "Concise title (5+ chars)",
  "summary": "One sentence capturing the insight (10-500 chars)",
  "content": {{
    "overview": "What this image shows and why it matters. (10+ chars)",
    "details": "Specific components, flows, technologies, or decisions visible. (20+ chars)",
    "examples": "Notable details: labels, annotations, version numbers. Omit if none. (0+ chars)",
    "references": "Related systems or docs this connects to. Omit if none. (0+ chars)",
    "caveats": "Ambiguities or context missing from the image. Omit if none. (0+ chars)"
  }},
  "metadata": {{
    "tags": ["tag1", "tag2"],
    "confidence": "high|medium|low"
  }}
}}
"""

REPO_PROMPT = """\
Analyze this code repository structure and extract structured knowledge modules about its architecture, patterns, and decisions.

Repository: {repo_name}
Directory structure:
```
{dir_tree}
```

Key files:
{key_files}

Category: {category}

Return a JSON array (no markdown, no explanation) of up to {max_modules} modules covering:
- Architecture overview (component structure, tech stack)
- Key design patterns and decisions
- Data flow or API structure
- Infrastructure and deployment approach
- Notable tooling or conventions

Each module follows the standard format. Extract actionable methodology, not code dumps.
"""

MEETING_PROMPT = """\
Analyze these meeting notes and extract structured knowledge modules. Focus on:

1. **Architecture decisions** — record as decision-record type with rationale
2. **Action items** — extract as draft modules with clear owners
3. **Risks identified** — update relevant modules' caveats with these risks
4. **Technical insights** — any methodology or pattern discussed

Category: {category}

Raw notes:
{text}

Return a JSON array (no markdown, no explanation) of up to {max_modules} modules in the standard extraction format.
"""


def _strip_markdown_json(text: str) -> str:
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    return match.group(1).strip() if match else text.strip()


def _chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    if chunk_size <= 0 or len(text) <= chunk_size:
        return [text]
    step = max(1, chunk_size - overlap)
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + chunk_size])
        if start + chunk_size >= len(text):
            break
        start += step
    return chunks


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
                for key in content_data:
                    val = content_data[key]
                    if val is None:
                        content_data[key] = ""
                    elif isinstance(val, list):
                        content_data[key] = ", ".join(str(v) for v in val)
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
        original_prompt = prompt
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
                        f"Original instructions:\n{original_prompt}"
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
                        f"Original instructions:\n{original_prompt}"
                    )
                    continue
                return None

            return items

        return None

    async def extract_from_image(self, image_path: str, category: str, existing_categories: str = "") -> list:
        max_modules = self.config.max_modules_per_extraction
        prompt = IMAGE_PROMPT.format(category=category, max_modules=max_modules)

        try:
            raw = await self.llm.complete_vision(prompt, image_path)
        except NotImplementedError:
            logger.warning("Vision not supported by current LLM provider; falling back to filename-only extraction")
            text = f"Image file: {Path(image_path).name}\nPath: {image_path}"
            return await self.extract(text, category, existing_categories)
        except Exception:
            logger.exception("Vision extraction failed for %s", image_path)
            return []

        return self._parse_modules(raw, category)

    def extract_from_repo(self, repo_path: str, category: str, existing_categories: str = "") -> list:
        import asyncio as _asyncio
        return _asyncio.run(self._extract_from_repo_async(repo_path, category, existing_categories))

    async def _extract_from_repo_async(self, repo_path: str, category: str, existing_categories: str = "") -> list:
        root = Path(repo_path)
        if not root.exists():
            logger.warning("Repo path does not exist: %s", repo_path)
            return []

        max_modules = self.config.max_modules_per_extraction
        dir_tree = self._render_dir_tree(root)
        key_files = self._read_key_files(root)

        prompt = REPO_PROMPT.format(
            repo_name=root.name,
            dir_tree=dir_tree,
            key_files=key_files,
            category=category,
            max_modules=max_modules,
        )

        raw = await self.llm.complete(prompt)
        return self._parse_modules(raw, category)

    def extract_from_meeting(self, text: str, category: str, existing_categories: str = "") -> list:
        import asyncio as _asyncio
        return _asyncio.run(self._extract_from_meeting_async(text, category, existing_categories))

    async def _extract_from_meeting_async(self, text: str, category: str, existing_categories: str = "") -> list:
        max_modules = self.config.max_modules_per_extraction
        prompt = MEETING_PROMPT.format(category=category, text=text, max_modules=max_modules)

        raw = await self.llm.complete(prompt)
        modules = self._parse_modules(raw, category)

        for m in modules:
            if "decision" in prompt.lower() or "决定" in text:
                m.metadata.tags.append("decision-record")
                if m.metadata.confidence == "medium":
                    m.metadata.confidence = "high"

        return modules

    def _parse_modules(self, raw: str, category: str) -> list:
        raw = _strip_markdown_json(raw)
        try:
            items = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(items, list):
            return []

        modules = []
        for item in items[: self.config.max_modules_per_extraction]:
            try:
                content_data = item.get("content", {})
                for key in content_data:
                    val = content_data[key]
                    if val is None:
                        content_data[key] = ""
                    elif isinstance(val, list):
                        content_data[key] = ", ".join(str(v) for v in val)
                meta_data = item.get("metadata", {})
                llm_category = item.get("category") if self.config.auto_categorize else None
                m = Module(
                    id=item["id"],
                    category=llm_category or category,
                    title=item["title"],
                    summary=item["summary"],
                    content=ModuleContent(**content_data),
                    metadata=ModuleMetadata(**meta_data),
                )
                modules.append(m)
            except Exception:
                logger.warning("Failed to parse multimodal module item", exc_info=True)
        return modules

    @staticmethod
    def _render_dir_tree(root: Path, max_depth: int = 3, max_files: int = 80) -> str:
        lines = []
        count = 0
        for path in sorted(root.rglob("*")):
            if count >= max_files:
                lines.append("... (truncated)")
                break
            if path.name.startswith(".") and path.name not in (".git", ".github", ".env.example"):
                continue
            if any(p.startswith(".") for p in path.parts):
                if ".git" not in path.parts and ".github" not in path.parts:
                    continue
            rel = path.relative_to(root)
            depth = len(rel.parts)
            if depth > max_depth:
                continue
            prefix = "  " * (depth - 1) + ("├── " if depth > 0 else "")
            name = rel.name + ("/" if path.is_dir() else "")
            lines.append(f"{prefix}{name}")
            count += 1
        return "\n".join(lines)

    @staticmethod
    def _read_key_files(root: Path, max_bytes: int = 6000) -> str:
        key_patterns = [
            "README*", "ARCHITECTURE*", "ARCH*", "CONTRIBUTING*",
            "pyproject.toml", "Cargo.toml", "package.json", "go.mod",
            "Makefile", "docker-compose*", "Dockerfile*",
            "config*", "*.yaml", "*.yml",
        ]
        import fnmatch
        parts = []
        total = 0
        for pattern in key_patterns:
            for f in sorted(root.rglob(pattern)):
                if f.is_dir() or f.suffix in (".pyc", ".lock", ".svg", ".png"):
                    continue
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")[:2000]
                    rel = f.relative_to(root)
                    parts.append(f"\n=== {rel} ===\n{content}")
                    total += len(content)
                    if total >= max_bytes:
                        return "\n".join(parts)
                except Exception:
                    pass
        return "\n".join(parts)
