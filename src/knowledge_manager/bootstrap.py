"""Shared helpers for creating a local knowledge base."""

from pathlib import Path

from knowledge_manager.schemas import (
    Config,
    ExtractionConfig,
    Index,
    LLMProviderConfig,
)
from knowledge_manager.storage import save_index


DEFAULT_DESCRIPTION = (
    "A curated knowledge base of our team's technical methodology: architecture "
    "decisions, implementation patterns, operational practices, and lessons "
    "learned. Each module captures how we approach a topic, not just what it "
    "means. Use the index to identify relevant modules, then load the ones you "
    "need. Prefer modules with higher confidence ratings and cross-reference "
    "related modules when topics overlap."
)


def initialize_knowledge_base(path: Path) -> Index:
    """Create a local knowledge base and return its index."""
    kb = Path(path)
    if (kb / "index.json").exists():
        raise FileExistsError(f"Knowledge base already exists at {kb}")
    if kb.exists() and not kb.is_dir():
        raise NotADirectoryError(f"Knowledge base path is not a directory: {kb}")

    kb.mkdir(parents=True, exist_ok=True)
    (kb / ".staging").mkdir(exist_ok=True)
    (kb / ".gitignore").write_text(
        "# Knowledge Manager - local and sensitive files\n"
        ".staging/\n"
        ".telemetry/\n"
        "config.local.json\n",
        encoding="utf-8",
    )

    index = Index(description=DEFAULT_DESCRIPTION)
    save_index(index, kb)

    default_config = Config(
        llm_providers={
            "deepseek": LLMProviderConfig(
                api_key="",
                model="deepseek-v4-pro",
                base_url="https://api.deepseek.com",
                default=True,
            )
        },
        extraction=ExtractionConfig(provider="deepseek", auto_categorize=True),
    )
    (kb / "config.json").write_text(
        default_config.model_dump_json(indent=2), encoding="utf-8"
    )
    return index
