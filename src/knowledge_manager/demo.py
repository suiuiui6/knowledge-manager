"""A deterministic demo knowledge base that needs no API key."""

from dataclasses import dataclass
from pathlib import Path

from knowledge_manager.bootstrap import initialize_knowledge_base
from knowledge_manager.schemas import Index, Module, ModuleContent, ModuleMetadata
from knowledge_manager.storage import rebuild_index, save_module, save_to_staging


DEMO_DESCRIPTION = (
    "A small demo knowledge base showing how reviewed modules are searched, "
    "loaded, and served to AI agents through MCP."
)
DEMO_QUERY = "rollback deployment"


@dataclass(frozen=True)
class DemoSeed:
    """Summary of the files created by the demo command."""

    index: Index
    modules: tuple[Module, ...]
    staged: Module


def demo_modules() -> tuple[Module, ...]:
    """Return the approved modules used by the demo."""
    return (
        Module(
            id="reviewed-context",
            category="agent-workflows",
            title="Give agents reviewed context instead of a context dump",
            summary="Load only approved knowledge modules when an agent needs them.",
            content=ModuleContent(
                overview=(
                    "Agents work better when context is selected, scoped, and "
                    "reviewed. Knowledge Manager keeps the reviewed source of truth "
                    "in Git and lets an MCP client request only the module it needs."
                ),
                details=(
                    "Raw notes are extracted into a staging directory first. A human "
                    "reviews each draft before it is promoted into the knowledge base. "
                    "The MCP client can read the index, search for a topic, and then "
                    "load the matching module without injecting the whole repository."
                ),
                examples=(
                    'Ask the agent: "Search knowledge-manager for the deployment '
                    'rollback procedure, then load only the matching module."'
                ),
                references="docs/use-cases/claude-code.md",
                caveats=(
                    "This workflow targets small and medium knowledge bases. It is not "
                    "a replacement for high-scale semantic retrieval over tens of "
                    "millions of words."
                ),
            ),
            metadata=ModuleMetadata(
                tags=["mcp", "context", "review"],
                related_modules=["mcp/retrieval-tools"],
                confidence="high",
                source="demo",
            ),
        ),
        Module(
            id="rollback-deployment",
            category="agent-workflows",
            title="Roll back a failed deployment safely",
            summary="A short runbook for detecting, containing, and reverting a failed release.",
            content=ModuleContent(
                overview=(
                    "Use this runbook when a new release increases errors or breaks "
                    "a critical path. The goal is to restore service first, then "
                    "preserve evidence for the follow-up investigation."
                ),
                details=(
                    "1. Confirm the failure with the release marker and error-rate "
                    "dashboard. 2. Stop further rollout. 3. Revert to the last known "
                    "good version. 4. Verify health checks and the critical user path. "
                    "5. Record the incident timeline and link it from the release."
                ),
                examples=(
                    "If the error rate doubles within five minutes of a release, stop "
                    "the rollout and revert before debugging the new code in production."
                ),
                references="docs/use-cases/deepseek-runbooks.md",
                caveats=(
                    "Database migrations may not be safely reversible. Check the "
                    "rollback compatibility notes before reverting an application "
                    "version that changed persistent data."
                ),
            ),
            metadata=ModuleMetadata(
                tags=["runbook", "deployment", "operations"],
                related_modules=["mcp/retrieval-tools"],
                confidence="high",
                source="demo",
            ),
        ),
        Module(
            id="retrieval-tools",
            category="mcp",
            title="Expose knowledge through MCP resources and tools",
            summary="Use an index resource plus search and load tools so clients fetch only what they need.",
            content=ModuleContent(
                overview=(
                    "The MCP surface keeps discovery cheap. The index resource shows "
                    "available modules, while search and load tools operate on the "
                    "same reviewed files that a developer can inspect in Git."
                ),
                details=(
                    "Start with the knowledge://index resource. Use search_modules "
                    "for a ranked keyword lookup, load_module for the selected file, "
                    "and list_categories for a compact inventory. The server uses "
                    "stdio, so no hosted service is required for local workflows."
                ),
                examples=(
                    '{"mcpServers":{"knowledge-manager":{"command":"km",'
                    '"args":["--kb-path","<absolute-path>","serve"]}}}'
                ),
                references="src/knowledge_manager/mcp_server.py",
                caveats=(
                    "The client must be restarted after changing the MCP server "
                    "configuration. Absolute paths are more reliable than relative "
                    "paths in editor integrations."
                ),
            ),
            metadata=ModuleMetadata(
                tags=["mcp", "tools", "retrieval"],
                related_modules=["agent-workflows/reviewed-context"],
                confidence="high",
                source="demo",
            ),
        ),
        Module(
            id="keyword-first",
            category="search",
            title="Start with deterministic keyword retrieval",
            summary="Use exact and stemmed keyword search before adding embedding infrastructure.",
            content=ModuleContent(
                overview=(
                    "A small reviewed knowledge base often gets more value from a "
                    "transparent search function than from another opaque vector "
                    "pipeline. Results can be inspected and the ranking is easy to "
                    "explain during review."
                ),
                details=(
                    "Knowledge Manager ranks title, tag, summary, and overview fields. "
                    "It checks exact word boundaries first, then English stems, and "
                    "uses partial matches for short queries. The implementation is "
                    "deterministic and operates on local JSON modules."
                ),
                examples='km --kb-path ./km-demo search "rollback deployment"',
                references="src/knowledge_manager/storage.py",
                caveats=(
                    "Keyword retrieval does not understand arbitrary paraphrases as "
                    "well as embeddings. Add semantic retrieval only after measuring "
                    "real misses and the operational cost of another dependency."
                ),
            ),
            metadata=ModuleMetadata(
                tags=["search", "keywords", "local-first"],
                related_modules=["agent-workflows/reviewed-context"],
                confidence="high",
                source="demo",
            ),
        ),
    )


def staged_demo_module() -> Module:
    """Return a draft module so the review checkpoint is visible immediately."""
    return Module(
        id="staged-oncall-handoff",
        category="agent-workflows",
        title="Draft an on-call handoff agents can reuse",
        summary="A staging example: review this draft before it becomes shared context.",
        content=ModuleContent(
            overview=(
                "An on-call handoff should state what changed, what is still risky, "
                "and which checks the next engineer should run first."
            ),
            details=(
                "Include the current incident state, recent changes, known noisy "
                "alerts, open mitigations, and links to the source systems. Remove "
                "names and private data before publishing the module."
            ),
            examples="Next shift: check the queue backlog, then the release marker.",
            references="docs/use-cases/claude-code.md",
            caveats="This is intentionally staged so the demo can show the human review step.",
        ),
        metadata=ModuleMetadata(
            tags=["on-call", "handoff", "staging"],
            confidence="medium",
            source="demo-staging",
            status="draft",
        ),
    )


def seed_demo_kb(path: Path) -> DemoSeed:
    """Create a demo knowledge base at an empty path."""
    kb = Path(path)
    if kb.exists() and not kb.is_dir():
        raise FileExistsError(f"Demo path is not an empty directory: {kb}")
    if kb.exists() and any(kb.iterdir()):
        raise FileExistsError(
            f"Demo path is not empty: {kb}. Choose a new path or remove it first."
        )

    initialize_knowledge_base(kb)
    modules = demo_modules()
    for module in modules:
        save_module(module, kb)
    index = rebuild_index(kb)
    staged = staged_demo_module()
    save_to_staging(staged, kb / ".staging")
    return DemoSeed(index=index, modules=modules, staged=staged)
