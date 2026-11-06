import re
from datetime import datetime, timezone
from typing import Any

import yaml

from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata

FRONTMATTER_TO_SCHEMA = {
    "id":                ("id", str),
    "category":          ("category", str),
    "title":             ("title", str),
    "summary":           ("summary", str),
    "tags":              ("metadata.tags", list),
    "confidence":        ("metadata.confidence", str),
    "status":            ("metadata.status", str),
    "source":            ("metadata.source", str),
    "expires_at":        ("metadata.expires_at", _datetime_or_none := lambda v: datetime.fromisoformat(v).replace(tzinfo=timezone.utc) if v else None),
    "review_interval_days": ("metadata.review_interval_days", lambda v: int(v) if v else None),
    "related_modules":   ("metadata.related_modules", list),
    "created_at":        ("created_at", lambda v: datetime.fromisoformat(v).replace(tzinfo=timezone.utc) if v else datetime.now(timezone.utc)),
    "updated_at":        ("updated_at", lambda v: datetime.fromisoformat(v).replace(tzinfo=timezone.utc) if v else datetime.now(timezone.utc)),
}

MD_SECTION_TO_CONTENT = {
    "概述": "overview",
    "overview": "overview",
    "细节": "details",
    "details": "details",
    "实现细节": "details",
    "示例": "examples",
    "examples": "examples",
    "参考": "references",
    "references": "references",
    "注意事项": "caveats",
    "caveats": "caveats",
    "陷阱": "caveats",
}


def parse_markdown_module(md_text: str) -> Module:
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", md_text, re.DOTALL)
    if not fm_match:
        raise ValueError("No YAML frontmatter found")

    frontmatter = yaml.safe_load(fm_match.group(1))
    body = md_text[fm_match.end():]

    module_data: dict[str, Any] = {"content": {}, "metadata": {}}
    for fm_key, (schema_path, converter) in FRONTMATTER_TO_SCHEMA.items():
        if fm_key in frontmatter and frontmatter[fm_key] is not None:
            value = frontmatter[fm_key]
            try:
                converted = converter(value)
            except Exception:
                continue
            _set_nested(module_data, schema_path, converted)

    content_fields = {"overview": "", "details": "", "examples": "", "references": "", "caveats": ""}
    current_section = "overview"
    current_lines: list[str] = []

    for line in body.split("\n"):
        h_match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if h_match:
            if current_lines:
                content_fields[current_section] = "\n".join(current_lines).strip()
                current_lines = []
            heading = h_match.group(2).strip().lower()
            matched = False
            for pattern, field in MD_SECTION_TO_CONTENT.items():
                if heading == pattern.lower():
                    current_section = field
                    matched = True
                    break
            if not matched:
                current_lines.append(line)
        else:
            current_lines.append(line)

    if current_lines:
        content_fields[current_section] = "\n".join(current_lines).strip()

    module_data["content"] = ModuleContent(
        overview=content_fields.get("overview", "") or "No overview provided yet.",
        details=content_fields.get("details", "") or "No details provided yet. Add content here.",
        examples=content_fields.get("examples", ""),
        references=content_fields.get("references", ""),
        caveats=content_fields.get("caveats", ""),
    )

    metadata = module_data.pop("metadata", {})
    module_data["metadata"] = ModuleMetadata(**metadata) if metadata else ModuleMetadata()
    return Module(**module_data)


def render_markdown_module(module: Module) -> str:
    fm = {
        "id": module.id,
        "category": module.category,
        "title": module.title,
        "summary": module.summary,
        "tags": module.metadata.tags,
        "confidence": module.metadata.confidence,
        "status": module.metadata.status,
        "source": module.metadata.source or None,
        "expires_at": module.metadata.expires_at.isoformat() if module.metadata.expires_at else None,
        "review_interval_days": module.metadata.review_interval_days,
        "related_modules": module.metadata.related_modules or None,
        "created_at": module.created_at.isoformat(),
        "updated_at": module.updated_at.isoformat(),
    }
    fm = {k: v for k, v in fm.items() if v is not None and v != [] and v != ""}

    fm_yaml = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False).strip()

    sections = []
    for heading_en, field in [("概述", "overview"), ("细节", "details"), ("示例", "examples"), ("参考", "references"), ("注意事项", "caveats")]:
        text = getattr(module.content, field, "")
        if text and text.strip():
            sections.append(f"# {heading_en}\n\n{text.strip()}\n")

    body = "\n".join(sections)
    return f"---\n{fm_yaml}\n---\n\n{body}"


def validate_frontmatter(fm: dict) -> list[str]:
    errors = []
    if not fm.get("id"):
        errors.append("Missing required field: id")
    if not fm.get("title") or len(str(fm.get("title", ""))) < 5:
        errors.append("title must be >= 5 characters")
    if fm.get("confidence") not in (None, "high", "medium", "low"):
        errors.append("confidence must be high/medium/low")
    if fm.get("status") not in (None, "draft", "reviewed", "published", "deprecated", "archived"):
        errors.append("Invalid status value")
    if fm.get("category") and not isinstance(fm.get("category"), str):
        errors.append("category must be a string")
    return errors


def _set_nested(data: dict, dotted: str, value: Any) -> None:
    keys = dotted.split(".")
    cur = data
    for k in keys[:-1]:
        cur = cur.setdefault(k, {})
    cur[keys[-1]] = value
