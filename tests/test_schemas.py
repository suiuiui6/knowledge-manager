# tests/test_schemas.py
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from knowledge_manager.schemas import (
    ConfluenceSourceConfig,
    Index,
    Module,
    ModuleContent,
    ModuleMetadata,
    NotionSourceConfig,
    SourceDefinition,
    SourceDocumentRef,
    SourceRegistry,
    SourceSpan,
    SourceSyncState,
)


def test_module_content_valid():
    content = ModuleContent(
        overview="This is an overview",
        details="These are detailed technical notes"
    )
    assert content.overview == "This is an overview"
    assert content.details == "These are detailed technical notes"
    assert content.examples == ""
    assert content.references == ""
    assert content.caveats == ""


def test_module_content_with_all_fields():
    content = ModuleContent(
        overview="Overview text",
        details="Details text with more content",
        examples="Example code",
        references="https://example.com",
        caveats="Known issues"
    )
    assert content.examples == "Example code"
    assert content.references == "https://example.com"
    assert content.caveats == "Known issues"


def test_module_content_missing_required_fields():
    with pytest.raises(ValidationError):
        ModuleContent(overview="Only overview")


def test_module_content_too_short():
    with pytest.raises(ValidationError):
        ModuleContent(overview="Short", details="Also short")


def test_module_metadata_defaults():
    metadata = ModuleMetadata()
    assert metadata.tags == []
    assert metadata.related_modules == []
    assert metadata.confidence == "medium"
    assert metadata.source == ""
    assert metadata.source_documents == []
    assert metadata.source_spans == []
    assert metadata.extraction_run_id == ""
    assert metadata.reviewed_by == ""
    assert metadata.reviewed_at is None
    assert metadata.stale_due_to_source_change is False
    assert metadata.supersedes == []
    assert metadata.derived_from == []


def test_module_metadata_with_values():
    metadata = ModuleMetadata(
        tags=["auth", "security"],
        related_modules=["auth/jwt-tokens"],
        confidence="high",
        source="team documentation"
    )
    assert metadata.tags == ["auth", "security"]
    assert metadata.related_modules == ["auth/jwt-tokens"]
    assert metadata.confidence == "high"
    assert metadata.source == "team documentation"


def test_module_round_trip_with_provenance():
    module = Module(
        id="jwt-playbook",
        category="auth",
        title="JWT Playbook",
        summary="How we operate JWT auth in production.",
        content=ModuleContent(
            overview="JWT auth in production uses short-lived access tokens.",
            details="We use short-lived access tokens plus refresh rotation and Redis-backed revocation.",
        ),
        metadata=ModuleMetadata(
            source_documents=[
                SourceDocumentRef(
                    source_type="confluence",
                    source_id="team-wiki",
                    external_id="12345",
                    title="JWT Runbook",
                    version="7",
                    url="https://wiki.example/pages/12345",
                    checksum="abc123",
                )
            ],
            source_spans=[
                SourceSpan(
                    external_id="12345",
                    heading_path=["Authentication", "JWT"],
                    excerpt="Refresh tokens rotate on every successful refresh.",
                    char_start=120,
                    char_end=176,
                )
            ],
            extraction_run_id="run-1",
            reviewed_by="alice",
            stale_due_to_source_change=True,
            supersedes=["auth/jwt-playbook-v0"],
            derived_from=["12345"],
        ),
    )

    restored = Module.model_validate_json(module.model_dump_json())
    assert restored.metadata.source_documents[0].external_id == "12345"
    assert restored.metadata.source_spans[0].heading_path == ["Authentication", "JWT"]
    assert restored.metadata.reviewed_by == "alice"
    assert restored.metadata.stale_due_to_source_change is True
    assert restored.metadata.supersedes == ["auth/jwt-playbook-v0"]
    assert restored.metadata.derived_from == ["12345"]


def test_source_registry_validates_keys_and_timestamps():
    synced_at = datetime(2026, 6, 11, 14, 30)
    registry = SourceRegistry(
        sources={
            "team-docs": SourceDefinition(
                id="team-docs",
                confluence=ConfluenceSourceConfig(
                    base_url="https://example.atlassian.net/wiki",
                    space_key="ENG",
                    email="docs@example.com",
                    api_token_env="CONFLUENCE_API_TOKEN",
                ),
                sync=SourceSyncState(last_synced_at=synced_at),
            )
        }
    )

    assert registry.sources["team-docs"].sync.last_synced_at == synced_at.replace(tzinfo=timezone.utc)


def test_source_registry_rejects_key_id_mismatch():
    with pytest.raises(ValidationError):
        SourceRegistry(
            sources={
                "team-docs": SourceDefinition(
                    id="other-id",
                    confluence=ConfluenceSourceConfig(
                        base_url="https://example.atlassian.net/wiki",
                        space_key="ENG",
                        email="docs@example.com",
                        api_token_env="CONFLUENCE_API_TOKEN",
                    ),
                )
            }
        )


def test_notion_source_definition_requires_notion_config():
    source = SourceDefinition(
        id="ops-notes",
        type="notion",
        notion=NotionSourceConfig(
            api_token_env="NOTION_TOKEN",
            database_id="db-1",
            category="ops",
        ),
    )

    assert source.type == "notion"
    assert source.notion is not None
    assert source.notion.database_id == "db-1"


def test_default_timestamps_are_timezone_aware():
    module = Module(
        id="auth-jwt",
        category="auth",
        title="JWT authentication module",
        summary="Summary text that is long enough for validation.",
        content=ModuleContent(
            overview="Overview text that is long enough",
            details="Detailed notes that are definitely long enough to pass validation",
        ),
    )
    index = Index()

    assert module.created_at.tzinfo == timezone.utc
    assert module.updated_at.tzinfo == timezone.utc
    assert index.updated_at.tzinfo == timezone.utc
    assert index.stats.last_updated.tzinfo == timezone.utc


def test_extraction_config_auto_categorize_default():
    from knowledge_manager.schemas import ExtractionConfig
    cfg = ExtractionConfig()
    assert cfg.auto_categorize is False


def test_extraction_config_auto_categorize_explicit():
    from knowledge_manager.schemas import ExtractionConfig
    cfg = ExtractionConfig(auto_categorize=True)
    assert cfg.auto_categorize is True


def test_index_graph_field_defaults_empty():
    index = Index()
    assert index.graph == {}


def test_index_graph_is_built_from_related_modules():
    from knowledge_manager.schemas import ExtractionConfig
    index = Index()
    m1 = Module(
        id="jwt", category="auth",
        title="JWT Tokens Module",
        summary="Handling JSON Web Tokens for authentication",
        content=ModuleContent(overview="A JWT overview for testing", details="Detailed JWT notes for testing graph build"),
        metadata=ModuleMetadata(tags=["auth"], related_modules=["auth/oauth-flow"])
    )
    m2 = Module(
        id="oauth-flow", category="auth",
        title="OAuth 2.0 Flow Module",
        summary="Implementing OAuth 2.0 authorization flow",
        content=ModuleContent(overview="OAuth overview for testing", details="Detailed OAuth notes for testing graph build"),
        metadata=ModuleMetadata(tags=["auth"], related_modules=["auth/jwt", "api/rate-limit"])
    )
    index.add_module(m1)
    index.add_module(m2)
    assert "auth/jwt" in index.graph
    assert "auth/oauth-flow" in index.graph["auth/jwt"]
    assert "auth/jwt" in index.graph["auth/oauth-flow"]
    assert "api/rate-limit" in index.graph["auth/oauth-flow"]


def test_config_supports_agent_task_and_risk_routing_policy():
    from knowledge_manager.schemas import Config

    cfg = Config.model_validate(
        {
                "routing_policy": {
                    "task_type_category_priorities": {"incident-response": ["runbook"]},
                    "risk_level_companions": {"high": ["policy/change-approval"]},
                    "risk_level_allowed_statuses": {"high": ["reviewed", "published"]},
                    "task_type_allowed_statuses": {"production-change": ["published"]},
                    "agent_overrides": {
                        "incident-agent": {
                            "category_priorities": {"how-to": ["runbook"]},
                            "task_type_category_priorities": {"incident-response": ["policy"]},
                            "risk_level_allowed_statuses": {"high": ["published"]},
                        }
                    },
                }
        }
    )

    assert cfg.routing_policy.task_type_category_priorities["incident-response"] == ["runbook"]
    assert cfg.routing_policy.risk_level_companions["high"] == ["policy/change-approval"]
    assert cfg.routing_policy.risk_level_allowed_statuses["high"] == ["reviewed", "published"]
    assert cfg.routing_policy.task_type_allowed_statuses["production-change"] == ["published"]
    assert cfg.routing_policy.agent_overrides["incident-agent"].category_priorities["how-to"] == ["runbook"]


def test_index_graph_cleaned_on_remove_module():
    index = Index()
    m1 = Module(
        id="jwt", category="auth",
        title="JWT Tokens Module",
        summary="Handling JSON Web Tokens",
        content=ModuleContent(overview="Overview text for testing", details="Detailed notes for testing graph removal"),
        metadata=ModuleMetadata(tags=["auth"], related_modules=["auth/oauth-flow"])
    )
    index.add_module(m1)
    assert "auth/jwt" in index.graph
    index.remove_module("jwt", "auth")
    assert "auth/jwt" not in index.graph


def test_telemetry_config_defaults():
    from knowledge_manager.schemas import TelemetryConfig
    cfg = TelemetryConfig()
    assert cfg.enabled is True


def test_telemetry_config_disabled():
    from knowledge_manager.schemas import TelemetryConfig
    cfg = TelemetryConfig(enabled=False)
    assert cfg.enabled is False


def test_config_includes_telemetry():
    from knowledge_manager.schemas import Config, TelemetryConfig
    cfg = Config()
    assert cfg.telemetry is not None
    assert cfg.telemetry.enabled is True


def test_metadata_supports_expiry():
    from datetime import datetime, timezone
    from knowledge_manager.schemas import ModuleMetadata

    now = datetime.now(timezone.utc)
    meta = ModuleMetadata(expires_at=now, review_interval_days=90)
    assert meta.expires_at == now
    assert meta.review_interval_days == 90

    # Defaults
    meta2 = ModuleMetadata()
    assert meta2.expires_at is None
    assert meta2.review_interval_days is None


def test_config_supports_synonyms():
    from knowledge_manager.schemas import Config
    cfg = Config(synonyms={"token": ["jwt", "bearer"]})
    assert cfg.synonyms == {"token": ["jwt", "bearer"]}

    # Default
    cfg2 = Config()
    assert cfg2.synonyms == {}


def test_config_supports_routing_policy():
    from knowledge_manager.schemas import Config

    cfg = Config(
        routing_policy={
            "category_priorities": {"how-to": ["runbook"]},
            "mandatory_companions": {"auth": ["policy/security-baseline"]},
            "suppress_stale_sources": True,
            "suppress_expired": True,
        }
    )
    assert cfg.routing_policy.category_priorities["how-to"] == ["runbook"]
    assert cfg.routing_policy.mandatory_companions["auth"] == ["policy/security-baseline"]
    assert cfg.routing_policy.suppress_stale_sources is True


def test_ops_report_schema_defaults():
    from knowledge_manager.schemas import OpsReport

    report = OpsReport()
    assert report.source_backlog == []
    assert report.policy_suppressed_modules == []
    assert report.lifecycle_backlog.status_counts == {}
