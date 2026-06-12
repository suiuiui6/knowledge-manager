from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc_aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


class ModuleContent(BaseModel):
    overview: str = Field(..., min_length=10)
    details: str = Field(..., min_length=20)
    examples: str = Field(default="")
    references: str = Field(default="")
    caveats: str = Field(default="")


class SourceDocumentRef(BaseModel):
    source_type: Literal["confluence", "notion"]
    source_id: str
    external_id: str
    title: str
    url: str = ""
    version: str = ""
    checksum: str = ""
    fetched_at: datetime = Field(default_factory=utc_now)

    @field_validator("fetched_at", mode="after")
    @classmethod
    def normalize_fetched_at(cls, value: datetime) -> datetime:
        normalized = ensure_utc_aware(value)
        assert normalized is not None
        return normalized


class SourceSpan(BaseModel):
    external_id: str
    heading_path: List[str] = Field(default_factory=list)
    excerpt: str = ""
    char_start: int = Field(default=0, ge=0)
    char_end: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_char_range(self) -> "SourceSpan":
        if self.char_end < self.char_start:
            raise ValueError("char_end must be greater than or equal to char_start")
        return self


class ConfluenceSourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str
    space_key: str
    email: str
    api_token_env: str
    root_page_id: str = ""
    category: str = "general"
    page_limit: int = 25


class NotionSourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_token_env: str
    database_id: str
    category: str = "general"
    page_limit: int = 25


class SourceSyncState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_cursor: str = ""
    last_synced_at: Optional[datetime] = None
    last_error: str = ""
    page_versions: Dict[str, str] = Field(default_factory=dict)

    @field_validator("last_synced_at", mode="after")
    @classmethod
    def normalize_last_synced_at(cls, value: Optional[datetime]) -> Optional[datetime]:
        return ensure_utc_aware(value)


class SourceDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["confluence", "notion"] = "confluence"
    enabled: bool = True
    confluence: Optional[ConfluenceSourceConfig] = None
    notion: Optional[NotionSourceConfig] = None
    sync: SourceSyncState = Field(default_factory=SourceSyncState)

    @model_validator(mode="after")
    def validate_source_config(self) -> "SourceDefinition":
        if self.type == "confluence":
            if self.confluence is None:
                raise ValueError("confluence config is required for confluence sources")
            if self.notion is not None:
                raise ValueError("notion config must be omitted for confluence sources")
        if self.type == "notion":
            if self.notion is None:
                raise ValueError("notion config is required for notion sources")
            if self.confluence is not None:
                raise ValueError("confluence config must be omitted for notion sources")
        return self


class SourceRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: Dict[str, SourceDefinition] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_source_keys(self) -> "SourceRegistry":
        for source_key, source in self.sources.items():
            if source_key != source.id:
                raise ValueError(
                    f"Source registry key {source_key!r} must match source id {source.id!r}"
                )
        return self


class ModuleMetadata(BaseModel):
    tags: List[str] = Field(default_factory=list)
    related_modules: List[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"
    tenant_id: str = ""
    workspace_id: str = ""
    source: str = Field(default="")
    source_documents: List[SourceDocumentRef] = Field(default_factory=list)
    source_spans: List[SourceSpan] = Field(default_factory=list)
    extraction_run_id: str = ""
    reviewed_by: str = ""
    reviewed_at: Optional[datetime] = None
    stale_due_to_source_change: bool = False
    supersedes: List[str] = Field(default_factory=list)
    derived_from: List[str] = Field(default_factory=list)
    expires_at: Optional[datetime] = None
    review_interval_days: Optional[int] = None
    status: Literal["draft", "reviewed", "published", "deprecated", "archived"] = "published"

    @field_validator("reviewed_at", mode="after")
    @classmethod
    def normalize_reviewed_at(cls, value: Optional[datetime]) -> Optional[datetime]:
        return ensure_utc_aware(value)


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
    tree: Optional[Any] = None

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


class NotificationsConfig(BaseModel):
    webhook_url: str = ""
    on_push: bool = True
    on_review_approved: bool = False


# ── M7: Lint schemas ──


class ContradictionType(str, Enum):
    FACT = "fact"
    DECISION = "decision"
    TIMELINE = "timeline"
    TERMINOLOGY = "terminology"
    STALE_REFERENCE = "stale_ref"


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ContradictionEvidence(BaseModel):
    module_key: str
    field: str = "content"
    excerpt: str = ""
    claim: str = ""


class Contradiction(BaseModel):
    id: str
    type: ContradictionType
    severity: Severity
    modules: list[str] = Field(default_factory=list)
    description: str = ""
    evidence: list[ContradictionEvidence] = Field(default_factory=list)
    suggestion: str = ""
    auto_fixable: bool = False
    auto_fix_description: str = ""


# ── M4: Research schemas ──


class ResearchSource(BaseModel):
    type: Literal["code_repo", "doc_dir", "web_search", "api"]
    path: str = ""
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    category_hint: str = ""


class ResearchConfig(BaseModel):
    enabled: bool = False
    auto_approve_threshold: float = 0.85
    sources: list[ResearchSource] = Field(default_factory=list)
    default_depth: Literal["shallow", "deep"] = "shallow"
    max_llm_calls_per_query: int = 8
    max_total_tokens_per_query: int = 32000
    auto_trigger: bool = False


class UIConfig(BaseModel):
    enabled: bool = False


class AgentRoutingPolicyConfig(BaseModel):
    category_priorities: Dict[str, List[str]] = Field(default_factory=dict)
    task_type_category_priorities: Dict[str, List[str]] = Field(default_factory=dict)
    task_type_allowed_statuses: Dict[str, List[str]] = Field(default_factory=dict)
    mandatory_companions: Dict[str, List[str]] = Field(default_factory=dict)
    risk_level_companions: Dict[str, List[str]] = Field(default_factory=dict)
    risk_level_allowed_statuses: Dict[str, List[str]] = Field(default_factory=dict)
    suppress_stale_sources: Optional[bool] = None
    suppress_expired: Optional[bool] = None


class RoutingPolicyConfig(BaseModel):
    category_priorities: Dict[str, List[str]] = Field(default_factory=dict)
    task_type_category_priorities: Dict[str, List[str]] = Field(default_factory=dict)
    task_type_allowed_statuses: Dict[str, List[str]] = Field(default_factory=dict)
    mandatory_companions: Dict[str, List[str]] = Field(default_factory=dict)
    risk_level_companions: Dict[str, List[str]] = Field(default_factory=dict)
    risk_level_allowed_statuses: Dict[str, List[str]] = Field(default_factory=dict)
    suppress_stale_sources: bool = True
    suppress_expired: bool = True
    agent_overrides: Dict[str, AgentRoutingPolicyConfig] = Field(default_factory=dict)


class Config(BaseModel):
    llm_providers: Dict[str, LLMProviderConfig] = Field(default_factory=dict)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    synonyms: Dict[str, List[str]] = Field(default_factory=dict)
    review: ReviewConfig = Field(default_factory=ReviewConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    federation: "FederationConfig" = Field(default_factory=lambda: FederationConfig())
    webhooks: "WebhookConfig" = Field(default_factory=lambda: WebhookConfig())
    marketplace: "MarketplaceConfig" = Field(default_factory=lambda: MarketplaceConfig())
    research: ResearchConfig = Field(default_factory=ResearchConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    routing_policy: RoutingPolicyConfig = Field(default_factory=RoutingPolicyConfig)

    def get_default_provider(self) -> Tuple[str, LLMProviderConfig]:
        for name, provider in self.llm_providers.items():
            if provider.default:
                return name, provider
        if self.llm_providers:
            name = next(iter(self.llm_providers))
            return name, self.llm_providers[name]
        raise ValueError("No LLM providers configured")


# ── Phase 3A: Health dashboard schemas ──


class HealthScore(BaseModel):
    freshness: float = 0.0       # 0-100
    usage: float = 0.0           # 0-100
    completeness: float = 0.0    # 0-100
    overall: float = 0.0         # weighted 0-100


class ModuleHealth(BaseModel):
    module_id: str
    category: str
    title: str
    status: str
    score: HealthScore = Field(default_factory=HealthScore)
    issues: List[str] = Field(default_factory=list)  # "zombie", "stale", "expired", "incomplete"
    last_load: Optional[datetime] = None
    load_count_30d: int = 0
    days_since_update: int = 0


class CategoryHealth(BaseModel):
    name: str
    total_modules: int
    avg_score: float = 0.0
    at_risk_count: int = 0


class KBHealthReport(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    total_modules: int = 0
    total_categories: int = 0
    overall_score: float = 0.0
    category_breakdown: Dict[str, CategoryHealth] = Field(default_factory=dict)
    at_risk_modules: List[ModuleHealth] = Field(default_factory=list)


# ── Phase 3B: Usage analytics schemas ──


class ModuleUsageEntry(BaseModel):
    module_id: str
    category: str
    title: str
    load_count: int = 0
    trend: str = "stable"  # "up", "down", "stable"


class UnmatchedQueryEntry(BaseModel):
    query_hash: str
    query_terms: List[str] = Field(default_factory=list)
    count: int = 0


class DailyActivityPoint(BaseModel):
    date: str
    searches: int = 0
    loads: int = 0


class UsageStats(BaseModel):
    period_days: int = 30
    total_searches: int = 0
    total_loads: int = 0
    conversion_rate: float = 0.0
    total_sessions: int = 0
    avg_searches_per_session: float = 0.0
    top_modules: List[ModuleUsageEntry] = Field(default_factory=list)
    unmatched_queries: List[UnmatchedQueryEntry] = Field(default_factory=list)
    daily_activity: List[DailyActivityPoint] = Field(default_factory=list)


# ── Phase 3C: Graph analysis schemas ──


class HubEntry(BaseModel):
    module_id: str
    category: str
    title: str
    in_degree: int = 0
    out_degree: int = 0


class OrphanEntry(BaseModel):
    module_id: str
    category: str
    title: str
    status: str = "published"


class BrokenLinkEntry(BaseModel):
    source: str  # "category/module_id"
    target: str  # broken reference
    target_status: str = "missing"  # "missing", "deprecated", "archived"


class ClusterEntry(BaseModel):
    id: str
    label: str = ""
    module_count: int = 0
    modules: List[str] = Field(default_factory=list)


class GraphStats(BaseModel):
    total_nodes: int = 0
    total_edges: int = 0
    density: float = 0.0
    hub_modules: List[HubEntry] = Field(default_factory=list)
    orphan_modules: List[OrphanEntry] = Field(default_factory=list)
    broken_links: List[BrokenLinkEntry] = Field(default_factory=list)
    clusters: List[ClusterEntry] = Field(default_factory=list)


# ── Phase 3D: Recommendation schemas ──


class RecommendationType(str, Enum):
    ARCHIVE = "archive"
    ENRICH = "enrich"
    LINK = "link"
    REVIEW = "review"


class Recommendation(BaseModel):
    type: RecommendationType
    module_id: str
    category: str
    title: str
    score: float = 0.0       # 0-1, higher = stronger recommendation
    reason: str = ""
    detail: Dict[str, Any] = Field(default_factory=dict)


class RecommendationReport(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    archive_candidates: List[Recommendation] = Field(default_factory=list)
    enrichment_needed: List[Recommendation] = Field(default_factory=list)
    suggested_links: List[Recommendation] = Field(default_factory=list)
    review_reminders: List[Recommendation] = Field(default_factory=list)


class SourceBacklogEntry(BaseModel):
    source_id: str
    source_type: str = ""
    last_synced_at: Optional[datetime] = None
    tracked_pages: int = 0
    stale_module_count: int = 0
    sync_error: str = ""


class LifecycleBacklog(BaseModel):
    status_counts: Dict[str, int] = Field(default_factory=dict)
    staging_status_counts: Dict[str, int] = Field(default_factory=dict)


class PolicySuppressedModule(BaseModel):
    module_id: str
    category: str
    title: str
    reasons: List[str] = Field(default_factory=list)


class OpsReport(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    source_backlog: List[SourceBacklogEntry] = Field(default_factory=list)
    lifecycle_backlog: LifecycleBacklog = Field(default_factory=LifecycleBacklog)
    policy_suppressed_modules: List[PolicySuppressedModule] = Field(default_factory=list)


# ── Phase 4A: Platform connector schemas ──


class PlatformConfig(BaseModel):
    """Mapping from platform name to its MCP config path."""
    name: str
    config_path: str  # relative to home or cwd (e.g. "~/.claude/mcp.json")
    description: str = ""


# ── Phase 4B: Federation schemas ──


class FederationNamespace(BaseModel):
    kb_path: str
    description: str = ""
    search_default: bool = True


class FederationConfig(BaseModel):
    namespaces: Dict[str, FederationNamespace] = Field(default_factory=dict)


# ── Phase 4C: Webhook schemas ──


class WebhookRetryConfig(BaseModel):
    max_attempts: int = 3
    backoff_seconds: int = 30


class WebhookEndpoint(BaseModel):
    url: str
    events: List[str] = Field(default_factory=list)  # empty = all events
    headers: Dict[str, str] = Field(default_factory=dict)
    secret: str = ""  # HMAC signing secret
    retry: WebhookRetryConfig = Field(default_factory=WebhookRetryConfig)


class WebhookEvent(BaseModel):
    event: str  # "module.created", "module.deprecated", etc.
    timestamp: datetime = Field(default_factory=utc_now)
    kb_path: str = ""
    kb_name: str = ""
    module_id: str = ""
    category: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)


class WebhookConfig(BaseModel):
    enabled: bool = False
    endpoints: List[WebhookEndpoint] = Field(default_factory=list)


# ── Phase 4D: Marketplace schemas ──


class MarketplaceModule(BaseModel):
    id: str
    category: str
    title: str
    summary: str
    tags: List[str] = Field(default_factory=list)
    confidence: str = "medium"
    author: str = "community"
    version: str = "1.0.0"
    downloads: int = 0
    rating: float = 0.0
    ratings_count: int = 0
    updated_at: datetime = Field(default_factory=utc_now)
    dependencies: List[str] = Field(default_factory=list)


class MarketplaceIndex(BaseModel):
    version: str = "1.0"
    modules: Dict[str, MarketplaceModule] = Field(default_factory=dict)
    last_updated: datetime = Field(default_factory=utc_now)


class InstallPlan(BaseModel):
    modules: List[MarketplaceModule] = Field(default_factory=list)
    target_category: str = ""
    dependencies_installed: List[str] = Field(default_factory=list)


class MarketplaceConfig(BaseModel):
    index_url: str = "https://github.com/knowledge-manager/marketplace"
    sanitize_patterns: List[str] = Field(default_factory=list)


# ── M1: Web UI + knowledge tree schemas ──


class TreeNodeType(str, Enum):
    ROOT = "root"
    CATEGORY = "category"
    MODULE = "module"
    SECTION = "section"


class TreeNode(BaseModel):
    id: str
    type: TreeNodeType
    title: str
    summary: str = ""
    path: str = ""
    page_range: Optional[tuple[int, int]] = None
    children: list["TreeNode"] = Field(default_factory=list)
    module_count: int = 0
    word_count: int = 0
    confidence: Optional[str] = None
    status: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class GraphNode(BaseModel):
    id: str
    label: str
    category: str = ""
    status: str = "published"
    in_degree: int = 0
    out_degree: int = 0


class GraphEdge(BaseModel):
    source: str
    target: str
    weight: float = 1.0


class GraphData(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    stats: Optional[dict] = None


class PaginatedResponse(BaseModel):
    items: list[dict] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    limit: int = 50
    pages: int = 0


# Resolve forward references
Config.model_rebuild()
