import json
import logging
import re
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
