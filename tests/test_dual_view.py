from knowledge_manager.dual_view import build_dual_view
from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata, SourceDocumentRef
from knowledge_manager.storage import save_module


def test_build_dual_view_projects_sources_to_modules(tmp_path):
    from knowledge_manager.schemas import ConfluenceSourceConfig, SourceDefinition
    from knowledge_manager.source_ingestion import upsert_source

    kb = tmp_path / "kb"
    kb.mkdir()
    upsert_source(
        SourceDefinition(
            id="team-docs",
            confluence=ConfluenceSourceConfig(
                base_url="https://example.atlassian.net/wiki",
                space_key="ENG",
                email="docs@example.com",
                api_token_env="CONFLUENCE_API_TOKEN",
            ),
        ),
        kb,
    )
    save_module(
        Module(
            id="mod-1",
            category="ops",
            title="Ops Runbook",
            summary="Ops runbook for production incidents.",
            content=ModuleContent(
                overview="Ops runbook overview.",
                details="Ops runbook details with enough length for validation.",
            ),
            metadata=ModuleMetadata(
                source_documents=[
                    SourceDocumentRef(
                        source_type="confluence",
                        source_id="team-docs",
                        external_id="page-1",
                        title="Runbook",
                    )
                ]
            ),
        ),
        kb,
    )

    view = build_dual_view(kb)

    assert view["sources"][0]["module_ids"] == ["ops/mod-1"]
    assert view["modules"][0]["source_ids"] == ["team-docs"]
