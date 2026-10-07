from __future__ import annotations

from knowledge_manager.schemas import (
    GraphData,
    GraphEdge,
    GraphNode,
    Index,
    IndexCategory,
    IndexModuleSummary,
    IndexStats,
    OpsReport,
    RecommendationReport,
    TreeNode,
    TreeNodeType,
)
from knowledge_manager.source_ingestion import load_source_registry
from knowledge_manager.storage import (
    generate_ops_report,
    generate_recommendations,
    list_modules,
    list_staging,
    list_staging_meta,
    load_module,
)
from knowledge_manager.tenancy import TenantContext, module_visible_to_tenant


def build_tenant_index(kb_path, tenant: TenantContext | None) -> Index:
    modules = list_modules(kb_path, tenant=tenant)
    categories: dict[str, IndexCategory] = {}
    graph: dict[str, list[str]] = {}

    for module in modules:
        category = categories.setdefault(module.category, IndexCategory(name=module.category))
        category.modules.append(
            IndexModuleSummary(
                id=module.id,
                category=module.category,
                title=module.title,
                summary=module.summary,
                tags=module.metadata.tags,
                word_count=module.word_count(),
            )
        )

    visible_keys = {f"{module.category}/{module.id}" for module in modules}
    for module in modules:
        key = f"{module.category}/{module.id}"
        related = [ref for ref in module.metadata.related_modules if ref in visible_keys]
        if related:
            graph[key] = related

    total_words = sum(module.word_count() for module in modules)
    return Index(
        description="",
        categories=categories,
        graph=graph,
        stats=IndexStats(
            total_modules=len(modules),
            total_words=total_words,
            categories=len(categories),
        ),
    )


def build_tenant_tree(kb_path, tenant: TenantContext | None) -> TreeNode:
    modules = list_modules(kb_path, tenant=tenant)
    root = TreeNode(
        id="root",
        type=TreeNodeType.ROOT,
        title="Knowledge Base",
        module_count=len(modules),
        word_count=sum(module.word_count() for module in modules),
    )
    by_category: dict[str, list] = {}
    for module in modules:
        by_category.setdefault(module.category, []).append(module)

    for category_name, category_modules in sorted(by_category.items()):
        category_node = TreeNode(
            id=category_name,
            type=TreeNodeType.CATEGORY,
            title=category_name,
            module_count=len(category_modules),
            word_count=sum(module.word_count() for module in category_modules),
        )
        for module in sorted(category_modules, key=lambda item: item.id):
            category_node.children.append(
                TreeNode(
                    id=f"{module.category}/{module.id}",
                    type=TreeNodeType.MODULE,
                    title=module.title,
                    summary=module.summary,
                    path=f"{module.category}/{module.id}",
                    confidence=module.metadata.confidence,
                    status=module.metadata.status,
                    tags=module.metadata.tags,
                )
            )
        root.children.append(category_node)
    return root


def build_tenant_subtree(cat: str, mod_id: str, kb_path, tenant: TenantContext | None) -> TreeNode | None:
    module = load_module(mod_id, cat, kb_path)
    if module is None or not module_visible_to_tenant(module, tenant):
        return None
    node = TreeNode(
        id=f"{cat}/{mod_id}",
        type=TreeNodeType.MODULE,
        title=module.title,
        summary=module.summary,
        path=f"{cat}/{mod_id}",
        confidence=module.metadata.confidence,
        status=module.metadata.status,
        tags=module.metadata.tags,
    )
    for ref in module.metadata.related_modules:
        parts = ref.split("/", 1)
        if len(parts) != 2:
            continue
        related = load_module(parts[1], parts[0], kb_path)
        if related is None or not module_visible_to_tenant(related, tenant):
            continue
        node.children.append(
            TreeNode(
                id=ref,
                type=TreeNodeType.MODULE,
                title=related.title,
                summary=related.summary,
                path=ref,
                confidence=related.metadata.confidence,
                status=related.metadata.status,
                tags=related.metadata.tags,
            )
        )
    return node


def build_tenant_graph(kb_path, tenant: TenantContext | None) -> GraphData:
    index = build_tenant_index(kb_path, tenant)
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    reverse_degree: dict[str, int] = {key: 0 for key in index.graph}
    for key in [f"{cat.name}/{module.id}" for cat in index.categories.values() for module in cat.modules]:
        reverse_degree.setdefault(key, 0)
    for src, targets in index.graph.items():
        for target in targets:
            reverse_degree[target] = reverse_degree.get(target, 0) + 1
            edges.append(GraphEdge(source=src, target=target, weight=1.0))

    for category_name, category in index.categories.items():
        for module in category.modules:
            key = f"{category_name}/{module.id}"
            nodes.append(
                GraphNode(
                    id=key,
                    label=module.title,
                    category=category_name,
                    in_degree=reverse_degree.get(key, 0),
                    out_degree=len(index.graph.get(key, [])),
                )
            )
    density = 0.0
    total_nodes = len(nodes)
    if total_nodes > 1:
        density = len(edges) / (total_nodes * (total_nodes - 1))
    return GraphData(
        nodes=nodes,
        edges=edges,
        stats={"total_nodes": total_nodes, "total_edges": len(edges), "density": density},
    )


def build_tenant_subgraph(cat: str, mod_id: str, kb_path, tenant: TenantContext | None) -> GraphData | None:
    module = load_module(mod_id, cat, kb_path)
    if module is None or not module_visible_to_tenant(module, tenant):
        return None
    center_key = f"{cat}/{mod_id}"
    related = {center_key, *module.metadata.related_modules}
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    visible_refs: set[str] = set()

    for ref in related:
        parts = ref.split("/", 1)
        if len(parts) != 2:
            continue
        related_module = load_module(parts[1], parts[0], kb_path)
        if related_module is None or not module_visible_to_tenant(related_module, tenant):
            continue
        visible_refs.add(ref)
        nodes.append(
            GraphNode(
                id=ref,
                label=related_module.title,
                category=parts[0],
                status=related_module.metadata.status,
            )
        )
    for ref in module.metadata.related_modules:
        if ref in visible_refs:
            edges.append(GraphEdge(source=center_key, target=ref, weight=1.0))
    return GraphData(nodes=nodes, edges=edges, stats={"center": center_key, "depth": 1})


def build_tenant_recommendations(kb_path, tenant: TenantContext | None) -> RecommendationReport:
    report = generate_recommendations(kb_path)

    def _visible(items):
        visible = []
        for item in items:
            module = load_module(item.module_id, item.category, kb_path)
            if module is not None and module_visible_to_tenant(module, tenant):
                visible.append(item)
        return visible

    return RecommendationReport(
        generated_at=report.generated_at,
        archive_candidates=_visible(report.archive_candidates),
        enrichment_needed=_visible(report.enrichment_needed),
        suggested_links=_visible(report.suggested_links),
        review_reminders=_visible(report.review_reminders),
    )


def build_tenant_ops_report(kb_path, tenant: TenantContext | None) -> OpsReport:
    if tenant is None:
        return generate_ops_report(kb_path)

    staging_modules = list_staging(kb_path / ".staging")
    visible_staging_ids = {
        module.id for module in staging_modules if module_visible_to_tenant(module, tenant)
    }
    visible_staging_meta = [
        meta for meta in list_staging_meta(kb_path / ".staging") if meta.module_id in visible_staging_ids
    ]
    report = generate_ops_report(kb_path, staging_meta=visible_staging_meta)
    visible_module_keys = {
        f"{module.category}/{module.id}" for module in list_modules(kb_path, tenant=tenant)
    }
    registry = load_source_registry(kb_path)
    visible_source_ids = {
        source_id
        for source_id, source in registry.sources.items()
        if (
            (not source.tenant_id and tenant.allow_global_reads)
            or source.tenant_id == tenant.tenant_id
        ) and (
            not tenant.workspace_id or not source.workspace_id or source.workspace_id == tenant.workspace_id
        )
    }
    filtered_policy = [
        item
        for item in report.policy_suppressed_modules
        if f"{item.category}/{item.module_id}" in visible_module_keys
    ]
    filtered_source_backlog = [
        item for item in report.source_backlog if item.source_id in visible_source_ids
    ]
    return OpsReport(
        generated_at=report.generated_at,
        source_backlog=filtered_source_backlog,
        lifecycle_backlog=report.lifecycle_backlog,
        policy_suppressed_modules=filtered_policy,
    )


def filter_review_backlog_export(kb_path, tenant: TenantContext | None, export: dict) -> dict:
    if tenant is None:
        return export
    visible_staging_ids = {
        module.id
        for module in list_staging(kb_path / ".staging")
        if module_visible_to_tenant(module, tenant)
    }
    items = [item for item in export.get("items", []) if item.get("module_id", "") in visible_staging_ids]
    stale_sources = filter_source_backlog_items(kb_path, tenant, export.get("stale_sources", []))
    return {
        **export,
        "total": len(items),
        "items": items,
        "stale_sources": stale_sources,
    }


def filter_source_backlog_items(kb_path, tenant: TenantContext | None, items: list[dict]) -> list[dict]:
    if tenant is None:
        return items
    registry = load_source_registry(kb_path)
    visible_source_ids = {
        source_id
        for source_id, source in registry.sources.items()
        if (
            (not source.tenant_id and tenant.allow_global_reads)
            or source.tenant_id == tenant.tenant_id
        ) and (
            not tenant.workspace_id or not source.workspace_id or source.workspace_id == tenant.workspace_id
        )
    }
    return [item for item in items if item.get("source_id", "") in visible_source_ids]
