from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ModuleContent(BaseModel):
    overview: str = Field(..., min_length=10)
    details: str = Field(..., min_length=20)
    examples: str = Field(default="")
    references: str = Field(default="")
    caveats: str = Field(default="")


class ModuleMetadata(BaseModel):
    tags: List[str] = Field(default_factory=list)
    related_modules: List[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"
    source: str = Field(default="")
    expires_at: Optional[datetime] = None
    review_interval_days: Optional[int] = None
    status: Literal["draft", "reviewed", "published", "deprecated", "archived"] = "published"


class Module(BaseModel):
    id: str = Field(..., pattern=r"^[a-z0-9-]+$")
    category: str
    title: str = Field(..., min_length=5)
    summary: str = Field(..., min_length=10, max_length=500)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    content: ModuleContent
    metadata: ModuleMetadata = Field(default_factory=ModuleMetadata)

    def word_count(self) -> int:
        text = " ".join([
            self.content.overview,
            self.content.details,
            self.content.examples,
            self.content.references,
            self.content.caveats,
        ])
        return len(text.split())

    def to_file_path(self, base_path: Path) -> Path:
        return base_path / self.category / f"{self.id}.json"


class IndexModuleSummary(BaseModel):
    id: str
    category: str
    title: str
    summary: str
    tags: List[str] = Field(default_factory=list)
    word_count: int = 0


class IndexCategory(BaseModel):
    name: str
    description: str = ""
    modules: List[IndexModuleSummary] = Field(default_factory=list)


class IndexStats(BaseModel):
    total_modules: int = 0
    total_words: int = 0
    categories: int = 0
    last_updated: datetime = Field(default_factory=utc_now)


class Index(BaseModel):
    version: str = "1.0"
    description: str = ""
    categories: Dict[str, IndexCategory] = Field(default_factory=dict)
    graph: Dict[str, List[str]] = Field(default_factory=dict)
    stats: IndexStats = Field(default_factory=IndexStats)
    updated_at: datetime = Field(default_factory=utc_now)

    def add_module(self, module: Module) -> None:
        if module.category not in self.categories:
            self.categories[module.category] = IndexCategory(name=module.category)
        summary = IndexModuleSummary(
            id=module.id,
            category=module.category,
            title=module.title,
            summary=module.summary,
            tags=module.metadata.tags,
            word_count=module.word_count(),
        )
        cat = self.categories[module.category]
        existing_ids = [m.id for m in cat.modules]
        if summary.id not in existing_ids:
            cat.modules.append(summary)
        module_key = f"{module.category}/{module.id}"
        if module.metadata.related_modules:
            self.graph[module_key] = list(module.metadata.related_modules)
        elif module_key in self.graph:
            del self.graph[module_key]
        self._refresh_stats()

    def remove_module(self, module_id: str, category: str) -> bool:
        if category not in self.categories:
            return False
        cat = self.categories[category]
        original_len = len(cat.modules)
        cat.modules = [m for m in cat.modules if m.id != module_id]
        self._refresh_stats()
        removed = len(cat.modules) < original_len
        if removed:
            module_key = f"{category}/{module_id}"
            self.graph.pop(module_key, None)
            for key in self.graph:
                self.graph[key] = [r for r in self.graph[key] if r != module_key]
        return removed

    def _refresh_stats(self) -> None:
        total_modules = sum(len(c.modules) for c in self.categories.values())
        total_words = sum(m.word_count for c in self.categories.values() for m in c.modules)
        self.stats = IndexStats(
            total_modules=total_modules,
            total_words=total_words,
            categories=len(self.categories),
        )
        self.updated_at = utc_now()


class LLMProviderConfig(BaseModel):
    api_key: str
    model: str
    base_url: str = ""
    default: bool = False
    temperature: float = 0.3
    max_tokens: int = 4096


class ExtractionConfig(BaseModel):
    provider: str = "deepseek"
    max_modules_per_extraction: int = 10
    chunk_size: int = 8000
    chunk_overlap: int = 400
    auto_categorize: bool = False


class CacheConfig(BaseModel):
    enabled: bool = True
    max_modules: int = 50


class TelemetryConfig(BaseModel):
    enabled: bool = True


class ReviewRecord(BaseModel):
    reviewer: str
    action: Literal["approved", "changes-requested"]
    comment: str = ""
    timestamp: datetime = Field(default_factory=utc_now)


class StagingMeta(BaseModel):
    module_id: str
    status: Literal["pending", "approved", "changes-requested"] = "pending"
    submitted_by: str = ""
    submitted_at: datetime = Field(default_factory=utc_now)
    reviews: List[ReviewRecord] = Field(default_factory=list)

    def approval_count(self) -> int:
        return sum(1 for r in self.reviews if r.action == "approved")


class ReviewConfig(BaseModel):
    required_approvals: int = 1
    auto_approve_self_submitted: bool = False
    reviewer_whitelist: List[str] = Field(default_factory=list)


class Config(BaseModel):
    llm_providers: Dict[str, LLMProviderConfig] = Field(default_factory=dict)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    synonyms: Dict[str, List[str]] = Field(default_factory=dict)
    review: ReviewConfig = Field(default_factory=ReviewConfig)

    def get_default_provider(self) -> Tuple[str, LLMProviderConfig]:
        for name, provider in self.llm_providers.items():
            if provider.default:
                return name, provider
        if self.llm_providers:
            name = next(iter(self.llm_providers))
            return name, self.llm_providers[name]
        raise ValueError("No LLM providers configured")
