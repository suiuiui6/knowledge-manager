import json
import logging
import re
from typing import List

from knowledge_manager.llm_clients import BaseLLMClient
from knowledge_manager.schemas import ExtractionConfig, Module, ModuleContent, ModuleMetadata

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """\
You are a knowledge extraction assistant. Extract structured knowledge modules from the raw text below.

Category: {category}

Raw text:
{text}

Return a JSON array (no markdown, no explanation) of up to {max_modules} modules. Each module:
{{
  "id": "kebab-case-id",
  "title": "Concise title (5+ chars)",
  "summary": "One sentence summary (10-500 chars)",
  "content": {{
    "overview": "High-level explanation (10+ chars)",
    "details": "Technical details (20+ chars)",
    "examples": "",
    "references": "",
    "caveats": ""
  }},
  "metadata": {{
    "tags": ["tag1", "tag2"],
    "confidence": "high|medium|low"
  }}
}}
"""


def _strip_markdown_json(text: str) -> str:
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    return match.group(1).strip() if match else text.strip()


class Extractor:
    def __init__(self, llm: BaseLLMClient, config: ExtractionConfig):
        self.llm = llm
        self.config = config

    async def extract(self, text: str, category: str) -> List[Module]:
        logger.debug(f"Building extraction prompt (text length: {len(text)}, category: {category})")
        prompt = EXTRACTION_PROMPT.format(
            category=category,
            text=text,
            max_modules=self.config.max_modules_per_extraction,
        )
        logger.debug(f"Prompt length: {len(prompt)} characters")

        logger.info("Calling LLM for extraction")
        try:
            raw = await self.llm.complete(prompt)
            logger.debug(f"LLM response length: {len(raw)} characters")
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return []

        raw = _strip_markdown_json(raw)
        logger.debug(f"After stripping markdown: {len(raw)} characters")

        try:
            items = json.loads(raw)
            logger.debug(f"Parsed JSON successfully, got {len(items) if isinstance(items, list) else 'non-list'} items")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode failed: {e}")
            logger.debug(f"Raw response (first 500 chars): {raw[:500]}")
            return []

        if not isinstance(items, list):
            logger.error(f"Expected list, got {type(items).__name__}")
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
                logger.debug(f"Module {i+1}/{len(items)}: {module.id} - {module.title}")
            except Exception as e:
                logger.warning(f"Failed to parse module {i+1}: {e}")
                logger.debug(f"Item data: {item}")
                continue

        logger.info(f"Successfully extracted {len(modules)} modules")
        return modules
