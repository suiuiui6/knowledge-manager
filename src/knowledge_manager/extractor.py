import json
import re
from typing import List

from knowledge_manager.llm_clients import BaseLLMClient
from knowledge_manager.schemas import ExtractionConfig, Module, ModuleContent, ModuleMetadata

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
        prompt = EXTRACTION_PROMPT.format(
            category=category,
            text=text,
            max_modules=self.config.max_modules_per_extraction,
        )
        raw = await self.llm.complete(prompt)
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
            except Exception:
                continue

        return modules
