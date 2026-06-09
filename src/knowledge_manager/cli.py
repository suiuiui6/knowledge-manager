import asyncio
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from knowledge_manager.extractor import Extractor
from knowledge_manager.llm_clients import create_client
from knowledge_manager.schemas import (
    Config,
    ExtractionConfig,
    Index,
    LLMProviderConfig,
)
from knowledge_manager.storage import (
    approve_from_staging,
    delete_module,
    delete_staging_meta,
    list_modules,
    list_staging,
    list_staging_meta,
    load_from_staging,
    load_index,
    load_module,
    load_search_events,
    load_staging_meta,
    rebuild_index,
    sanitize_config,
    save_index,
    save_module,
    save_staging_meta,
    save_to_staging,
    search_modules,
)


console = Console()
logger = logging.getLogger("knowledge_manager")


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    root = logging.getLogger()
    root.setLevel(level)

    package_logger = logging.getLogger("knowledge_manager")
    package_logger.setLevel(level)
    package_logger.propagate = True

    if verbose and not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        root.addHandler(handler)


def _config_path(kb_path: Path) -> Path:
    return kb_path / "config.json"


def _staging_path(kb_path: Path) -> Path:
    return kb_path / ".staging"


def _load_config(kb_path: Path) -> Config:
    path = _config_path(kb_path)
    if not path.exists():
        return Config()
    return Config.model_validate_json(path.read_text(encoding="utf-8"))


def _save_config(kb_path: Path, config: Config) -> None:
    _config_path(kb_path).write_text(config.model_dump_json(indent=2), encoding="utf-8")


def _require_kb(kb_path: Path) -> None:
    if not kb_path.exists() or not (kb_path / "index.json").exists():
        click.echo(f"Error: Knowledge base not found at {kb_path}", err=True)
        raise click.Abort()


@click.group()
@click.version_option("0.5.0", prog_name="km")
@click.option(
    "--kb-path",
    type=click.Path(path_type=Path),
    default=Path.cwd(),
    help="Path to the knowledge base directory",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging output",
)
@click.pass_context
def cli(ctx: click.Context, kb_path: Path, verbose: bool) -> None:
    """Knowledge Manager — lightweight AI knowledge management."""
    ctx.ensure_object(dict)
    ctx.obj["kb_path"] = Path(kb_path)
    ctx.obj["verbose"] = verbose

    _configure_logging(verbose)
    if verbose:
        logger.debug("Verbose logging enabled")


@cli.command()
@click.argument("path", type=click.Path(path_type=Path), required=False)
def init(path: Optional[Path]) -> None:
    """Initialize a new knowledge base at PATH (or current directory)."""
    kb = Path(path) if path else Path.cwd()
    if (kb / "index.json").exists():
        click.echo(f"Error: Knowledge base already exists at {kb}", err=True)
        raise click.Abort()

    kb.mkdir(parents=True, exist_ok=True)
    _staging_path(kb).mkdir(exist_ok=True)

    # Write .gitignore template
    gitignore = kb / ".gitignore"
    gitignore.write_text(
        "# Knowledge Manager — local and sensitive files\n"
        ".staging/\n"
        ".telemetry/\n"
        "config.local.json\n",
        encoding="utf-8",
    )

    overview = (
        "A curated knowledge base of our team's technical methodology — "
        "architecture decisions, implementation patterns, operational practices, "
        "and lessons learned. Each module captures HOW we approach a topic, "
        "not just what it means. Use the index to identify relevant modules, "
        "then load the ones you need. Prefer modules with higher confidence "
        "ratings. Cross-reference related modules when topics overlap."
    )
    save_index(Index(description=overview), kb)

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
    _save_config(kb, default_config)

    click.echo(f"Initialized knowledge base at {kb}")


@cli.command("list")
@click.option("-c", "--category", default=None, help="Filter by category")
@click.pass_context
def list_cmd(ctx: click.Context, category: Optional[str]) -> None:
    """List modules in the knowledge base."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    modules = list_modules(kb)
    if category:
        modules = [m for m in modules if m.category == category]

    if not modules:
        click.echo("No modules found.")
        return

    table = Table(title="Modules")
    table.add_column("Category")
    table.add_column("ID")
    table.add_column("Title")
    for m in sorted(modules, key=lambda x: (x.category, x.id)):
        table.add_row(m.category, m.id, m.title)
    console.print(table)


@cli.command()
@click.pass_context
def stats(ctx: click.Context) -> None:
    """Show knowledge base statistics."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    index = load_index(kb) or Index()
    click.echo(f"Total modules: {index.stats.total_modules}")
    click.echo(f"Total words: {index.stats.total_words}")
    click.echo(f"Categories: {index.stats.categories}")
    for name, cat in index.categories.items():
        click.echo(f"  {name}: {len(cat.modules)} modules")


@cli.command()
@click.argument("query")
@click.option("--include-archived", is_flag=True, help="Include archived modules in search results")
@click.pass_context
def search(ctx: click.Context, query: str, include_archived: bool = False) -> None:
    """Search modules by keyword."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    results = search_modules(query, kb, include_archived=include_archived)

    if not results:
        click.echo("No matches.")
        return

    for r in results:
        conf_badge = {"high": "[high]", "medium": "[med]", "low": "[low]"}.get(
            r.module.metadata.confidence, ""
        )
        src_badge = "" if r.source == "direct" else " [related]"
        click.echo(f"{r.module.category}/{r.module.id}{src_badge} {conf_badge} — {r.module.title}")
        click.echo(f"  {r.module.summary}")


@cli.command()
@click.pass_context
def rebuild(ctx: click.Context) -> None:
    """Rebuild the index from on-disk modules."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)
    index = rebuild_index(kb)
    click.echo(f"Rebuilt index: {index.stats.total_modules} modules across {index.stats.categories} categories")


@cli.command()
@click.argument("module_id")
@click.option("-c", "--category", required=True, help="Module category")
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.pass_context
def delete(ctx: click.Context, module_id: str, category: str, yes: bool) -> None:
    """Delete a module."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    if not yes:
        if not click.confirm(f"Delete {category}/{module_id}?"):
            click.echo("Cancelled.")
            return

    if not delete_module(module_id, category, kb):
        click.echo(f"Error: module not found: {category}/{module_id}", err=True)
        raise click.Abort()

    index = load_index(kb)
    if index is not None:
        index.remove_module(module_id, category)
        save_index(index, kb)
    click.echo(f"Deleted {category}/{module_id}")


@cli.command()
@click.argument("module_id")
@click.option("-c", "--category", required=True)
@click.pass_context
def show(ctx: click.Context, module_id: str, category: str) -> None:
    """Show full module content as JSON."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)
    module = load_module(module_id, category, kb)
    if module is None:
        click.echo(f"Error: module not found: {category}/{module_id}", err=True)
        raise click.Abort()
    click.echo(module.model_dump_json(indent=2))


# --- deprecate / archive ---


@cli.command()
@click.argument("module_ref")
@click.option("--reason", default="", help="Reason for deprecation")
@click.pass_context
def deprecate(ctx: click.Context, module_ref: str, reason: str) -> None:
    """Mark a module as deprecated. Usage: km deprecate category/module-id"""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    parts = module_ref.split("/", 1)
    if len(parts) != 2:
        click.echo("Error: Use format 'category/module-id'", err=True)
        raise click.Abort()
    category, module_id = parts

    module = load_module(module_id, category, kb)
    if module is None:
        click.echo(f"Module not found: {module_ref}", err=True)
        raise click.Abort()

    module.metadata.status = "deprecated"
    save_module(module, kb)
    rebuild_index(kb)
    from knowledge_manager.webhooks import emit_event
    emit_event(kb, "module.deprecated", module_id, category, {"reason": reason})
    click.echo(f"Deprecated: {module_ref}" + (f" — {reason}" if reason else ""))


@cli.command()
@click.argument("module_ref")
@click.pass_context
def archive(ctx: click.Context, module_ref: str) -> None:
    """Archive a module (hidden from default search). Usage: km archive category/module-id"""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    parts = module_ref.split("/", 1)
    if len(parts) != 2:
        click.echo("Error: Use format 'category/module-id'", err=True)
        raise click.Abort()
    category, module_id = parts

    module = load_module(module_id, category, kb)
    if module is None:
        click.echo(f"Module not found: {module_ref}", err=True)
        raise click.Abort()

    module.metadata.status = "archived"
    save_module(module, kb)
    rebuild_index(kb)
    from knowledge_manager.webhooks import emit_event
    emit_event(kb, "module.archived", module_id, category)
    click.echo(f"Archived: {module_ref}")


# --- stale ---


@cli.command()
@click.pass_context
def stale(ctx: click.Context) -> None:
    """List modules that are expired or due for review."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    now = datetime.now(timezone.utc)
    modules = list_modules(kb)
    stale_modules: list[tuple[str, str, str, str]] = []  # (category, id, title, reason)

    for m in modules:
        reason = ""
        if m.metadata.expires_at is not None and m.metadata.expires_at < now:
            reason = f"Expired {m.metadata.expires_at.strftime('%Y-%m-%d')}"
        elif m.metadata.review_interval_days is not None:
            age = (now - m.updated_at).days
            if age > m.metadata.review_interval_days:
                reason = f"Due for review ({age}d since update, interval={m.metadata.review_interval_days}d)"
        if reason:
            stale_modules.append((m.category, m.id, m.title, reason))

    if not stale_modules:
        click.echo("No stale modules found.")
        return

    table = Table(title="Stale Modules")
    table.add_column("Category")
    table.add_column("ID")
    table.add_column("Title")
    table.add_column("Reason")
    for cat, mid, title, reason in sorted(stale_modules, key=lambda x: (x[0], x[1])):
        table.add_row(cat, mid, title, reason)
    console.print(table)


# --- config subcommands ---

@cli.group()
def config() -> None:
    """Manage configuration."""


def _set_nested(data: dict, dotted: str, value) -> None:
    keys = dotted.split(".")
    cur = data
    for k in keys[:-1]:
        cur = cur.setdefault(k, {})
    cur[keys[-1]] = value


def _get_nested(data: dict, dotted: str):
    cur = data
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


@config.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_context
def config_set(ctx: click.Context, key: str, value: str) -> None:
    """Set a config value (dotted key, e.g. extraction.provider)."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    cfg = _load_config(kb)
    data = cfg.model_dump()
    _set_nested(data, key, value)
    new_cfg = Config.model_validate(data)
    _save_config(kb, new_cfg)
    click.echo(f"Set {key} = {value}")


@config.command("get")
@click.argument("key")
@click.pass_context
def config_get(ctx: click.Context, key: str) -> None:
    """Get a config value."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)
    cfg = _load_config(kb)
    val = _get_nested(cfg.model_dump(), key)
    if val is None:
        click.echo(f"Error: key not set: {key}", err=True)
        raise click.Abort()
    click.echo(val)


@config.command("list")
@click.pass_context
def config_list(ctx: click.Context) -> None:
    """List all configuration."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)
    cfg = _load_config(kb)
    click.echo(cfg.model_dump_json(indent=2))


# --- health ---


@cli.command()
@click.option("--module", "-m", default=None, help="Show health for a specific module (category/id)")
@click.option("--category", "-c", default=None, help="Filter by category")
@click.option("--at-risk", is_flag=True, help="Only show modules needing attention")
@click.option("--format", "-f", "fmt", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def health(ctx: click.Context, module: str | None, category: str | None, at_risk: bool, fmt: str) -> None:
    """Show knowledge base health report."""
    from knowledge_manager.storage import compute_module_health, generate_health_report, load_module

    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    if module:
        # Single module detail
        parts = module.split("/", 1)
        if len(parts) != 2:
            click.echo("Error: Use format 'category/module-id'", err=True)
            raise click.Abort()
        mod = load_module(parts[1], parts[0], kb)
        if mod is None:
            click.echo(f"Module not found: {module}", err=True)
            raise click.Abort()
        h = compute_module_health(mod, kb)

        if fmt == "json":
            click.echo(h.model_dump_json(indent=2))
            return

        console.print(f"\n[bold]Module Health: {h.module_id}[/bold]")
        table = Table(title="")
        table.add_column("Dimension", style="cyan")
        table.add_column("Score", style="yellow")
        table.add_column("Detail", style="dim")
        table.add_row("Freshness", f"{h.score.freshness:.0f}", f"Updated {h.days_since_update}d ago")
        table.add_row("Usage", f"{h.score.usage:.0f}",
                      f"Loaded {h.load_count_30d}x (last: {h.last_load.strftime('%Y-%m-%d') if h.last_load else 'never'})")
        table.add_row("Completeness", f"{h.score.completeness:.0f}", "")
        issues_str = ", ".join(h.issues) if h.issues else "none"
        status_icon = "✅ Healthy" if h.score.overall >= 60 else ("⚠️ At Risk" if h.score.overall >= 30 else "❌ Critical")
        console.print(table)
        console.print(f"\n[bold]Overall: {h.score.overall:.1f}/100  {status_icon}[/bold]")
        if h.issues:
            console.print(f"[dim]Issues: {issues_str}[/dim]")
        return

    report = generate_health_report(kb)

    if fmt == "json":
        click.echo(report.model_dump_json(indent=2))
        return

    if report.total_modules == 0:
        click.echo("Knowledge base is empty. Add modules with 'km add'.")
        return

    if at_risk:
        if not report.at_risk_modules:
            click.echo("No modules at risk.")
            return
        console.print(f"\n[bold]⚠️  Modules Needing Attention[/bold]\n")
        risk_table = Table(title="")
        risk_table.add_column("Module")
        risk_table.add_column("Issue")
        risk_table.add_column("Score")
        risk_table.add_column("Action")
        for h in report.at_risk_modules:
            if category and h.category != category:
                continue
            best_action = "review"
            if "expired" in h.issues:
                best_action = "archive"
            elif "zombie" in h.issues and h.score.overall < 20:
                best_action = "archive"
            elif "stale" in h.issues:
                best_action = "deprecate"
            risk_table.add_row(
                f"{h.category}/{h.module_id}",
                h.issues[0] if h.issues else "-",
                f"{h.score.overall:.1f}",
                best_action,
            )
        console.print(risk_table)
        return

    console.print(f"\n[bold]Knowledge Base Health Report[/bold]")
    console.print(f"{report.generated_at.strftime('%Y-%m-%d')} | {report.total_modules} modules | {report.total_categories} categories\n")

    # Category breakdown
    cat_table = Table(title="")
    cat_table.add_column("Category")
    cat_table.add_column("Total")
    cat_table.add_column("Avg Score")
    cat_table.add_column("At Risk")
    for cat_name, ch in sorted(report.category_breakdown.items()):
        risk_indicator = f"{ch.at_risk_count} ⚠️" if ch.at_risk_count > 0 else "0"
        cat_table.add_row(cat_name, str(ch.total_modules), f"{ch.avg_score:.1f}", risk_indicator)
    console.print(cat_table)

    console.print(f"\n[bold]Overall Health Score: {report.overall_score:.1f}/100[/bold]")

    if report.at_risk_modules:
        console.print(f"\n[dim]{len(report.at_risk_modules)} module(s) at risk. Run [bold]km health --at-risk[/bold] for details.[/dim]")


# --- usage ---


@cli.command()
@click.option("--period", "-p", type=click.Choice(["7d", "30d", "90d"]), default="30d", help="Time period for stats")
@click.option("--format", "-f", "fmt", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def usage(ctx: click.Context, period: str, fmt: str) -> None:
    """Show knowledge base usage analytics."""
    from knowledge_manager.storage import aggregate_usage_stats

    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    days = {"7d": 7, "30d": 30, "90d": 90}[period]
    data = aggregate_usage_stats(kb, period_days=days)

    if fmt == "json":
        click.echo(data.model_dump_json(indent=2))
        return

    if data.total_searches == 0:
        click.echo(f"No usage data for the last {period}. Start searching and loading modules.")
        return

    console.print(f"\n[bold]KB Usage Analytics[/bold] (last {period})")
    console.print(f"\n Searches: {data.total_searches}   Loads: {data.total_loads}   Conversion: {data.conversion_rate}%")
    console.print(f" Sessions: {data.total_sessions}   Avg searches/session: {data.avg_searches_per_session}")

    if data.top_modules:
        console.print(f"\n[bold] Top Modules[/bold] (by loads)")
        top_table = Table(title="")
        top_table.add_column("Module")
        top_table.add_column("Loads")
        max_loads = max(m.load_count for m in data.top_modules)
        for m in data.top_modules:
            bar_len = int(m.load_count / max_loads * 10) if max_loads > 0 else 0
            spark = "█" * bar_len + "▌" if bar_len >= 1 else ""
            top_table.add_row(f"{m.category}/{m.module_id}", f"{m.load_count} {spark}")
        console.print(top_table)

    if data.unmatched_queries:
        console.print(f"\n[bold] Unmatched Queries[/bold] (top 5)")
        uq_table = Table(title="")
        uq_table.add_column("Query Theme")
        uq_table.add_column("Count")
        for uq in data.unmatched_queries:
            theme = ", ".join(uq.query_terms[:3]) if uq.query_terms else uq.query_hash[:12]
            uq_table.add_row(theme, str(uq.count))
        console.print(uq_table)
        console.print("[dim]  → These topics might need new modules.[/dim]")


# --- graph ---


@cli.command()
@click.option("--export", "-e", "export_fmt", type=click.Choice(["mermaid", "dot", "json"]), default=None, help="Export format")
@click.option("--format", "-f", "fmt", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def graph(ctx: click.Context, export_fmt: str | None, fmt: str) -> None:
    """Analyze and visualize the knowledge graph."""
    from knowledge_manager.storage import analyze_graph, detect_clusters

    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    gs = analyze_graph(kb)
    clusters = detect_clusters(kb)

    if export_fmt == "json" or fmt == "json":
        import json as _json
        output = {
            "stats": gs.model_dump(),
            "clusters": [c.model_dump() for c in clusters],
        }
        click.echo(_json.dumps(output, indent=2))
        return

    if export_fmt == "mermaid":
        lines = ["graph TD"]
        index = load_index(kb)
        if index:
            for src, targets in index.graph.items():
                src_label = src.replace("/", "_").replace("-", "_")
                for t in targets:
                    t_label = t.replace("/", "_").replace("-", "_")
                    lines.append(f"  {src_label}[\"{src}\"] --> {t_label}[\"{t}\"]")
        if len(lines) == 1:
            lines.append("  empty[\"No connections\"]")
        click.echo("\n".join(lines))
        return

    if export_fmt == "dot":
        lines = ["digraph KB {", "  rankdir=LR;"]
        index = load_index(kb)
        if index:
            for src, targets in index.graph.items():
                src_id = src.replace("/", "_").replace("-", "_")
                for t in targets:
                    t_id = t.replace("/", "_").replace("-", "_")
                    lines.append(f"  {src_id} -> {t_id};")
        lines.append("}")
        click.echo("\n".join(lines))
        return

    if gs.total_nodes == 0:
        click.echo("No modules in knowledge base. Add modules with 'km add'.")
        return

    console.print(f"\n[bold]Knowledge Graph Overview[/bold]")
    console.print(f"{gs.total_nodes} modules | {gs.total_edges} edges | density: {gs.density}")

    if gs.hub_modules:
        console.print(f"\n[bold] Top Hubs[/bold]")
        hub_table = Table(title="")
        hub_table.add_column("Module")
        hub_table.add_column("Category")
        hub_table.add_column("Inward")
        for h in gs.hub_modules:
            hub_table.add_row(h.module_id, h.category, str(h.in_degree))
        console.print(hub_table)

    if gs.orphan_modules:
        console.print(f"\n[bold] Orphan Modules[/bold] ({len(gs.orphan_modules)})")
        orphan_names = ", ".join(f"{o.category}/{o.module_id}" for o in gs.orphan_modules[:10])
        if len(gs.orphan_modules) > 10:
            orphan_names += f", ..."
        console.print(f"  {orphan_names}")

    if gs.broken_links:
        console.print(f"\n[bold] Broken Links[/bold] ({len(gs.broken_links)})")
        for bl in gs.broken_links[:10]:
            console.print(f"  {bl.source} → {bl.target} ({bl.target_status})")

    if clusters:
        console.print(f"\n[bold] Clusters[/bold] ({len(clusters)})")
        for c in clusters[:8]:
            console.print(f"  • {c.id}: {c.label}/* ({c.module_count} modules)")


# --- recommend ---


@cli.command()
@click.option("--type", "-t", "rec_type", type=click.Choice(["archive", "enrich", "links", "review"]), default=None, help="Filter by recommendation type")
@click.option("--format", "-f", "fmt", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def recommend(ctx: click.Context, rec_type: str | None, fmt: str) -> None:
    """Generate recommendations for KB improvement."""
    from knowledge_manager.storage import generate_recommendations

    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    report = generate_recommendations(kb)

    if fmt == "json":
        click.echo(report.model_dump_json(indent=2))
        return

    total = (
        len(report.archive_candidates)
        + len(report.enrichment_needed)
        + len(report.suggested_links)
        + len(report.review_reminders)
    )
    if total == 0:
        click.echo("No recommendations — your knowledge base is in great shape!")
        return

    console.print(f"\n[bold] Recommendations[/bold]")

    def _show_section(title: str, items, icon: str):
        if not items:
            return
        if rec_type and rec_type not in title.lower():
            return
        console.print(f"\n[bold]{icon} {title}[/bold] ({len(items)})")
        t = Table(title="")
        t.add_column("Module")
        t.add_column("Score")
        t.add_column("Reason")
        for r in items[:5]:
            mod_ref = f"{r.category}/{r.module_id}" if r.category else r.module_id
            t.add_row(mod_ref, f"{r.score:.2f}", r.reason)
        console.print(t)

    _show_section("Archive Candidates", report.archive_candidates, "📦")
    _show_section("Needs Enrichment", report.enrichment_needed, "✏️")
    _show_section("Suggested Links", report.suggested_links, "🔗")
    _show_section("Review Reminders", report.review_reminders, "⏰")


# --- apply ---


@cli.command()
@click.option("--type", "-t", "apply_type", type=click.Choice(["archive", "enrich", "links", "review"]), required=True, help="Type of recommendation to apply")
@click.option("--module", "-m", "module_ref", default=None, help="Apply to a specific module (category/id)")
@click.option("--dry-run", is_flag=True, help="Preview actions without executing")
@click.option("--confirm", "-y", is_flag=True, help="Confirm each action interactively")
@click.pass_context
def apply(ctx: click.Context, apply_type: str, module_ref: str | None, dry_run: bool, confirm: bool) -> None:
    """Apply recommendations in batch."""
    from knowledge_manager.storage import generate_recommendations, load_module

    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    report = generate_recommendations(kb)

    type_map = {
        "archive": report.archive_candidates,
        "enrich": report.enrichment_needed,
        "links": report.suggested_links,
        "review": report.review_reminders,
    }
    candidates = type_map.get(apply_type, [])

    if module_ref:
        candidates = [r for r in candidates if f"{r.category}/{r.module_id}" == module_ref or r.module_id == module_ref]

    if not candidates:
        click.echo(f"No {apply_type} recommendations to apply.")
        return

    for r in candidates:
        mod_ref = f"{r.category}/{r.module_id}" if r.category else r.module_id
        if apply_type == "archive":
            action = f"Archive {mod_ref}"
            if dry_run:
                click.echo(f"[DRY RUN] {action}: {r.reason}")
            else:
                if confirm:
                    ans = Prompt.ask(f"{action}?", choices=["y", "n", "s"], default="y")
                    if ans == "s":
                        break
                    elif ans == "n":
                        continue
                result = click.get_current_context().invoke(
                    archive, module_ref=mod_ref,
                )
        elif apply_type == "enrich":
            if dry_run:
                missing = r.detail.get("missing_fields", [])
                click.echo(f"[DRY RUN] Enrich {mod_ref}: add {', '.join(missing)}")
            else:
                click.echo(f"Enrich {mod_ref}: {r.reason}")
                click.echo("  (manual — edit the module file to add missing fields)")

    if dry_run:
        click.echo(f"\n[dim]{len(candidates)} action(s) previewed. Run without --dry-run to execute.[/dim]")
    else:
        rebuild_index(kb)
        click.echo(f"Applied {len(candidates)} {apply_type} action(s).")


# --- add (extract to staging) ---

@cli.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("-c", "--category", default="general", help="Category for the new modules")
@click.pass_context
def add(ctx: click.Context, file: Path, category: str) -> None:
    """Extract knowledge modules from FILE into staging."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    logger.info("Reading input file")
    text = file.read_text(encoding="utf-8")
    logger.debug("Input file size: %s characters", len(text))

    logger.info("Loading configuration")
    cfg = _load_config(kb)
    provider_name, provider_cfg = cfg.get_default_provider()
    logger.info(f"Using LLM provider: {provider_name} (model: {provider_cfg.model})")

    logger.info("Creating LLM client")
    client = create_client(provider_name, provider_cfg)
    extractor = Extractor(client, cfg.extraction)

    existing_categories = ""
    if cfg.extraction.auto_categorize:
        index = load_index(kb)
        if index is not None and index.categories:
            cat_descs = []
            for name, cat in index.categories.items():
                desc = f"  {name}"
                if cat.description:
                    desc += f": {cat.description}"
                cat_descs.append(desc)
            existing_categories = "\n".join(cat_descs)

    logger.info(f"Extracting modules (category: {category}, max: {cfg.extraction.max_modules_per_extraction})")
    modules = asyncio.run(extractor.extract(text, category, existing_categories))
    logger.debug(f"Extraction returned {len(modules)} modules")

    staging = _staging_path(kb)
    staging.mkdir(exist_ok=True)
    logger.info("Saving %s module(s) to staging", len(modules))
    from knowledge_manager.schemas import StagingMeta
    for m in modules:
        save_to_staging(m, staging)
        meta = StagingMeta(module_id=m.id, submitted_by=_git_user_name(kb))
        save_staging_meta(meta, staging)

    click.echo(f"Extracted {len(modules)} module(s) into staging")


# --- review (interactive + subcommands) ---

@cli.group(invoke_without_command=True)
@click.pass_context
def review(ctx: click.Context) -> None:
    """Review staged modules. Run without subcommand for interactive mode."""
    if ctx.invoked_subcommand is not None:
        return

    kb = ctx.obj["kb_path"]
    _require_kb(kb)
    staging = _staging_path(kb)
    from knowledge_manager.storage import save_staging_meta
    from knowledge_manager.schemas import StagingMeta

    pending = list_staging(staging)
    if not pending:
        click.echo("No staged modules to review.")
        return

    for i, module in enumerate(pending, 1):
        # Load or create metadata
        meta = load_staging_meta(module.id, staging)
        if meta is None:
            meta = StagingMeta(module_id=module.id)

        console.print(f"\n[bold cyan]Module {i}/{len(pending)}[/bold cyan]")
        if meta.status != "pending":
            console.print(f"[dim]Status: {meta.status} ({meta.approval_count()} approval(s))[/dim]")
        console.print(f"[bold]Category:[/bold] {module.category}")
        console.print(f"[bold]ID:[/bold] {module.id}")
        console.print(f"[bold]Title:[/bold] {module.title}")
        console.print(f"[bold]Summary:[/bold] {module.summary}")
        console.print(f"[bold]Tags:[/bold] {', '.join(module.metadata.tags)}")
        console.print(f"\n[bold]Overview:[/bold] {module.content.overview[:200]}")

        action = Prompt.ask("Action", choices=["a", "r", "s"], default="a")

        if action == "a":
            meta.status = "approved"
            save_staging_meta(meta, staging)
            approve_from_staging(module.id, staging, kb)
            delete_staging_meta(module.id, staging)
            console.print("[green]Approved[/green]")
        elif action == "r":
            (staging / f"{module.id}.json").unlink()
            delete_staging_meta(module.id, staging)
            console.print("[red]Rejected[/red]")
        else:
            console.print("[yellow]Skipped[/yellow]")

    rebuild_index(kb)


@review.command("list")
@click.pass_context
def review_list(ctx: click.Context) -> None:
    """List all staged modules with review status."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)
    staging = _staging_path(kb)
    pending = list_staging(staging)

    if not pending:
        click.echo("No staged modules.")
        return

    table = Table(title="Staged Modules")
    table.add_column("Module")
    table.add_column("Status")
    table.add_column("Approvals")
    table.add_column("Submitted By")
    for m in pending:
        meta = load_staging_meta(m.id, staging)
        status = meta.status if meta else "pending"
        approvals = str(meta.approval_count()) if meta else "0"
        submitted_by = meta.submitted_by if meta else "-"
        table.add_row(f"{m.category}/{m.id}", status, approvals, submitted_by)
    console.print(table)


@review.command("show")
@click.argument("module_id")
@click.pass_context
def review_show(ctx: click.Context, module_id: str) -> None:
    """Show a staged module and its review history."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)
    staging = _staging_path(kb)

    module = load_from_staging(module_id, staging)
    if module is None:
        click.echo(f"Module not found in staging: {module_id}", err=True)
        raise click.Abort()

    meta = load_staging_meta(module_id, staging)

    console.print(f"[bold]Module:[/bold] {module.category}/{module.id}")
    console.print(f"[bold]Title:[/bold] {module.title}")
    console.print(f"[bold]Summary:[/bold] {module.summary}")
    if meta:
        console.print(f"[bold]Status:[/bold] {meta.status}")
        console.print(f"[bold]Submitted by:[/bold] {meta.submitted_by or 'unknown'}")
        console.print(f"[bold]Submitted at:[/bold] {meta.submitted_at}")
        if meta.reviews:
            console.print(f"\n[bold]Reviews ({len(meta.reviews)}):[/bold]")
            for r in meta.reviews:
                action_color = "green" if r.action == "approved" else "red"
                console.print(f"  [{action_color}]{r.action}[/{action_color}] by {r.reviewer} at {r.timestamp}")
                if r.comment:
                    console.print(f"    {r.comment}")
    console.print(f"\n[bold]Content:[/bold]")
    console.print(module.model_dump_json(indent=2))


@review.command("approve")
@click.argument("module_id")
@click.option("--comment", "-m", default="", help="Approval comment")
@click.pass_context
def review_approve(ctx: click.Context, module_id: str, comment: str) -> None:
    """Approve a staged module for inclusion in the KB."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)
    staging = _staging_path(kb)
    from knowledge_manager.schemas import ReviewRecord, StagingMeta

    module = load_from_staging(module_id, staging)
    if module is None:
        click.echo(f"Module not found in staging: {module_id}", err=True)
        raise click.Abort()

    meta = load_staging_meta(module_id, staging)
    if meta is None:
        meta = StagingMeta(module_id=module_id)

    meta.reviews.append(ReviewRecord(reviewer=_git_user_name(kb), action="approved", comment=comment))
    meta.status = "approved" if meta.approval_count() >= 1 else meta.status

    cfg = _load_config(kb)
    required = cfg.review.required_approvals
    if meta.approval_count() >= required:
        approve_from_staging(module_id, staging, kb)
        delete_staging_meta(module_id, staging)
        rebuild_index(kb)
        from knowledge_manager.webhooks import emit_event
        emit_event(kb, "review.approved", module_id, module.category, {"reviewer": meta.reviews[-1].reviewer if meta.reviews else "", "approvals_count": meta.approval_count()})
        click.echo(f"Approved and merged: {module_id} ({meta.approval_count()} approval(s))")
    else:
        save_staging_meta(meta, staging)
        click.echo(f"Approved: {module_id} ({meta.approval_count()}/{required} approvals needed)")


@review.command("request-changes")
@click.argument("module_id")
@click.option("--comment", "-m", required=True, help="Reason for changes requested")
@click.pass_context
def review_request_changes(ctx: click.Context, module_id: str, comment: str) -> None:
    """Request changes on a staged module."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)
    staging = _staging_path(kb)
    from knowledge_manager.schemas import ReviewRecord, StagingMeta

    module = load_from_staging(module_id, staging)
    if module is None:
        click.echo(f"Module not found in staging: {module_id}", err=True)
        raise click.Abort()

    meta = load_staging_meta(module_id, staging)
    if meta is None:
        meta = StagingMeta(module_id=module_id)

    meta.reviews.append(ReviewRecord(reviewer=_git_user_name(kb), action="changes-requested", comment=comment))
    meta.status = "changes-requested"
    save_staging_meta(meta, staging)
    click.echo(f"Changes requested for {module_id}: {comment}")


@review.command("my-submissions")
@click.pass_context
def review_my_submissions(ctx: click.Context) -> None:
    """Show your submitted staging modules and their review status."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)
    staging = _staging_path(kb)

    metas = list_staging_meta(staging)
    if not metas:
        click.echo("No staged modules.")
        return

    table = Table(title="My Submissions")
    table.add_column("Module")
    table.add_column("Status")
    table.add_column("Approvals")
    table.add_column("Submitted At")
    for meta in sorted(metas, key=lambda m: m.submitted_at, reverse=True):
        table.add_row(
            meta.module_id,
            meta.status,
            str(meta.approval_count()),
            meta.submitted_at.strftime("%Y-%m-%d %H:%M"),
        )
    console.print(table)


# --- chat (M2) ---


@cli.command()
@click.option("--mode", type=click.Choice(["precise", "creative"]), default="precise", help="Chat mode")
@click.pass_context
def chat(ctx: click.Context, mode: str) -> None:
    """Start interactive chat with the knowledge base."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    from knowledge_manager.chat import ChatPipeline
    from knowledge_manager.llm_clients import create_client

    cfg = _load_config(kb)
    try:
        provider_name, provider_cfg = cfg.get_default_provider()
    except ValueError:
        console.print("[red]No LLM provider configured. Run 'km config set llm_providers...' first.[/red]")
        return

    llm_client = create_client(provider_name, provider_cfg)
    pipeline = ChatPipeline(kb, llm_client)

    console.print(f"[bold]KM Chat[/bold] ({mode} mode). Type /quit to exit, /clear to reset.\n")
    history: list[dict] = []

    while True:
        try:
            query = Prompt.ask("[bold]You[/bold]")
        except (KeyboardInterrupt, EOFError):
            console.print("\nGoodbye!")
            break

        if not query.strip():
            continue
        if query.strip() == "/quit":
            console.print("Goodbye!")
            break
        if query.strip() == "/clear":
            history.clear()
            console.print("[dim]History cleared.[/dim]")
            continue

        console.print()
        answer_text = ""
        sources = []
        follow_ups = []

        async def _run():
            nonlocal answer_text, sources, follow_ups
            async for event in pipeline.chat(query, history, mode):
                if event.type == "status":
                    console.print(f"[dim]{event.data.get('message', '')}[/dim]")
                elif event.type == "token":
                    answer_text += event.data["text"]
                    console.print(event.data["text"], end="", highlight=False)
                elif event.type == "citation":
                    key = event.data["key"]
                    if key not in [s["key"] for s in sources]:
                        sources.append(event.data)
                elif event.type == "done":
                    follow_ups = event.data.get("follow_ups", [])
                elif event.type == "error":
                    console.print(f"\n[red]{event.data.get('message', 'Error')}[/red]")

        asyncio.run(_run())
        console.print("\n")

        if sources:
            console.print("[dim]References:[/dim]")
            for s in sources:
                console.print(f"  [dim][ref: {s['key']}] {s['title']}[/dim]")

        if follow_ups:
            console.print("\n[dim]Follow-up questions:[/dim]")
            for i, q in enumerate(follow_ups, 1):
                console.print(f"  [dim]{i}. {q}[/dim]")

        console.print()
        history.append({"role": "user", "content": query})
        history.append({"role": "assistant", "content": answer_text})
        if len(history) > 20:
            history = history[-20:]


# --- serve (MCP) ---

@cli.command()
@click.option("--ui", is_flag=True, help="Start MCP + Web UI (FastAPI on localhost:8420)")
@click.option("--host", default="127.0.0.1", help="Host to bind the Web UI server")
@click.option("--port", default=8420, type=int, help="Port for the Web UI server")
@click.pass_context
def serve(ctx: click.Context, ui: bool, host: str, port: int) -> None:
    """Run the MCP server over stdio. Use --ui for MCP + Web UI mode."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    if ui:
        import uvicorn
        from knowledge_manager.http_server import create_app

        app = create_app(kb)
        console.print(f"[bold]Knowledge Manager Web UI[/bold]")
        console.print(f"  MCP: stdio (available)")
        console.print(f"  Web UI: http://{host}:{port}")
        console.print(f"  Fallback UI: http://{host}:{port}/ui/fallback")
        # Run MCP in background thread, FastAPI in main thread
        import threading
        from knowledge_manager.mcp_server import create_server as create_mcp

        mcp_server = create_mcp(kb)

        def run_mcp():
            asyncio.run(mcp_server.run_stdio_async())

        mcp_thread = threading.Thread(target=run_mcp, daemon=True)
        mcp_thread.start()

        uvicorn.run(app, host=host, port=port, log_level="info")
    else:
        from knowledge_manager.mcp_server import create_server

        server = create_server(kb)
        asyncio.run(server.run_stdio_async())


# --- Platform connector commands (Phase 4A) ---


@cli.command()
@click.option("--list", "-l", "list_platforms", is_flag=True, help="List available platforms")
@click.option("--print", "-p", "print_config", is_flag=True, help="Print MCP config to stdout instead of writing")
@click.option("--force", "-f", is_flag=True, help="Skip overwrite confirmation")
@click.argument("platform", required=False)
@click.pass_context
def connect(ctx: click.Context, list_platforms: bool, print_config: bool, force: bool, platform: str | None) -> None:
    """Generate MCP configuration for an Agent platform."""
    from knowledge_manager.connect import (
        PLATFORMS, build_mcp_entry, has_entry, resolve_config_path, write_mcp_config,
    )

    kb = ctx.obj["kb_path"]

    if list_platforms:
        for name, cfg in PLATFORMS.items():
            click.echo(f"  {name:<16} {cfg.description}")
        return

    if platform is None:
        click.echo("Error: specify a platform (e.g. 'claude-code') or use --list to see options.", err=True)
        raise click.Abort()

    try:
        config_path = resolve_config_path(platform, kb)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()

    entry = build_mcp_entry(kb)

    if print_config:
        config = {"mcpServers": {"knowledge-manager": entry}}
        click.echo(json.dumps(config, indent=2))
        return

    if has_entry(config_path) and not force:
        if not click.confirm(f"knowledge-manager already configured in {config_path}. Overwrite?"):
            click.echo("Cancelled.")
            return

    write_mcp_config(config_path, entry)
    click.echo(f"Connected to {platform}. Restart your Agent to activate.")


@cli.command()
@click.argument("platform")
@click.pass_context
def disconnect(ctx: click.Context, platform: str) -> None:
    """Remove knowledge-manager from a platform's MCP configuration."""
    from knowledge_manager.connect import PLATFORMS, remove_mcp_entry, resolve_config_path

    kb = ctx.obj["kb_path"]

    try:
        config_path = resolve_config_path(platform, kb)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()

    if remove_mcp_entry(config_path):
        click.echo(f"Removed knowledge-manager from {config_path}")
    else:
        click.echo(f"No knowledge-manager entry found in {config_path}")


# --- Git collaboration commands ---


def _git_user_name(kb_path: Path) -> str:
    """Get the git user.name for the KB repo. Falls back to 'unknown'."""
    result = subprocess.run(
        ["git", "-C", str(kb_path), "config", "user.name"],
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else "unknown"


def _run_git(kb_path: Path, *args: str, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a git command in the given KB directory."""
    cmd = ["git", "-C", str(kb_path)] + list(args)
    try:
        return subprocess.run(cmd, capture_output=capture, text=True, check=False)
    except FileNotFoundError:
        raise click.ClickException("Git is not installed or not on PATH. Install git to use remote KB features.")


@cli.command()
@click.argument("url")
@click.option("--path", "-p", type=click.Path(path_type=Path), default=None, help="Local path for the cloned KB")
def clone(url: str, path: Path | None) -> None:
    """Clone a remote knowledge base from a Git URL."""
    local_path = path or Path(url.rsplit("/", 1)[-1].replace(".git", ""))
    if local_path.exists():
        click.echo(f"Error: Path already exists: {local_path}", err=True)
        raise click.Abort()

    click.echo(f"Cloning {url} into {local_path}...")
    result = subprocess.run(["git", "clone", url, str(local_path)], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        click.echo(f"Error: git clone failed:\n{result.stderr.strip()}", err=True)
        raise click.Abort()

    if not (local_path / "index.json").exists():
        click.echo(f"Warning: Cloned repository does not contain index.json. It may not be a valid KM knowledge base.", err=True)

    click.echo(f"Cloned knowledge base to {local_path.absolute()}")


@cli.command()
@click.pass_context
def pull(ctx: click.Context) -> None:
    """Pull latest changes from the remote repository."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    staging = _staging_path(kb)
    if staging.exists() and list(staging.glob("*.json")):
        click.echo("Warning: You have uncommitted staged modules. Review them before pulling to avoid conflicts.", err=True)

    click.echo("Pulling latest changes...")
    result = _run_git(kb, "pull", "--rebase", "origin")
    if result.returncode != 0:
        click.echo(f"Error: pull failed:\n{result.stderr.strip()}", err=True)
        raise click.Abort()

    click.echo(result.stdout.strip() or "Already up to date.")
    rebuild_index(kb)
    from knowledge_manager.storage import generate_changelog
    generate_changelog(kb)
    click.echo("Index rebuilt.")


@cli.command()
@click.pass_context
def push(ctx: click.Context) -> None:
    """Push local changes to the remote repository."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    # Check if behind remote
    fetch_result = _run_git(kb, "fetch", "origin")
    if fetch_result.returncode != 0:
        click.echo("Warning: Could not fetch from remote. Continuing anyway...")

    behind_check = _run_git(kb, "rev-list", "--count", "HEAD..origin/main")
    if behind_check.returncode == 0:
        behind_count = behind_check.stdout.strip()
        if behind_count and behind_count != "0":
            click.echo(f"Error: Local is {behind_count} commit(s) behind remote. Run 'km pull' first.", err=True)
            raise click.Abort()

    # Sanitize config before commit
    cfg = _load_config(kb)
    sanitized = sanitize_config(cfg)
    if sanitized != cfg:
        _save_config(kb, sanitized)

    # Count module changes for commit message
    diff_stat = _run_git(kb, "diff", "--name-status", "origin/main")
    added, modified, deleted = 0, 0, 0
    for line in diff_stat.stdout.strip().split("\n"):
        if not line or not line.endswith(".json"):
            continue
        parts = line.split("\t", 1)
        status_code = parts[0] if parts else ""
        if status_code.startswith("A"):
            added += 1
        elif status_code.startswith("M"):
            modified += 1
        elif status_code.startswith("D"):
            deleted += 1

    msg_parts = []
    if modified:
        msg_parts.append(f"{modified} module(s) updated")
    if added:
        msg_parts.append(f"{added} added")
    if deleted:
        msg_parts.append(f"{deleted} deleted")
    commit_msg = ", ".join(msg_parts) if msg_parts else "km push"

    # Stage all and commit
    _run_git(kb, "add", "-A")
    _run_git(kb, "commit", "-m", commit_msg, "--allow-empty")
    click.echo("Pushing to remote...")
    result = _run_git(kb, "push", "origin")
    if result.returncode != 0:
        click.echo(f"Error: push failed:\n{result.stderr.strip()}", err=True)
        raise click.Abort()

    click.echo(result.stdout.strip() or "Push complete.")
    from knowledge_manager.storage import generate_changelog
    generate_changelog(kb)

    # Send webhook notification if configured
    notif_cfg = cfg.notifications
    if notif_cfg.webhook_url and notif_cfg.on_push:
        try:
            import httpx
            payload = {
                "text": f"KB updated by {_git_user_name(kb)}: {commit_msg}.",
            }
            httpx.post(notif_cfg.webhook_url, json=payload, timeout=10)
        except Exception:
            pass  # Webhook failures are non-critical

    # Restore config with real keys
    _save_config(kb, cfg)


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show local changes compared to the remote."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    _run_git(kb, "fetch", "origin")
    diff_result = _run_git(kb, "diff", "--name-status", "origin/main")
    if diff_result.stdout.strip():
        modules = {"added": [], "modified": [], "deleted": []}
        for line in diff_result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t", 1)
            status_code = parts[0]
            filepath = parts[1] if len(parts) > 1 else ""
            if filepath.endswith(".json") and filepath != "index.json" and filepath != "config.json":
                if status_code.startswith("A"):
                    modules["added"].append(filepath)
                elif status_code.startswith("M"):
                    modules["modified"].append(filepath)
                elif status_code.startswith("D"):
                    modules["deleted"].append(filepath)

        click.echo(f"Added: {len(modules['added'])} module(s)")
        for m in modules["added"]:
            click.echo(f"  + {m}")
        click.echo(f"Modified: {len(modules['modified'])} module(s)")
        for m in modules["modified"]:
            click.echo(f"  ~ {m}")
        click.echo(f"Deleted: {len(modules['deleted'])} module(s)")
        for m in modules["deleted"]:
            click.echo(f"  - {m}")
    else:
        click.echo("No changes compared to remote.")

    # Also show ahead/behind
    ahead = _run_git(kb, "rev-list", "--count", "origin/main..HEAD")
    behind = _run_git(kb, "rev-list", "--count", "HEAD..origin/main")
    if ahead.stdout.strip() and ahead.stdout.strip() != "0":
        click.echo(f"Local ahead by {ahead.stdout.strip()} commit(s).")
    if behind.stdout.strip() and behind.stdout.strip() != "0":
        click.echo(f"Local behind by {behind.stdout.strip()} commit(s).")


def _json_diff_sections(remote_data: dict, local_data: dict) -> list[str]:
    """Compare two module dicts and return a list of human-readable diff lines."""
    lines: list[str] = []
    sections = ["title", "summary", "category", "id", "content", "metadata"]

    for section in sections:
        remote_val = remote_data.get(section)
        local_val = local_data.get(section)

        if remote_val == local_val:
            continue

        if isinstance(remote_val, dict) and isinstance(local_val, dict):
            # Nested dict: compare field by field
            all_keys = set(remote_val.keys()) | set(local_val.keys())
            section_diffs = []
            for key in sorted(all_keys):
                rv = remote_val.get(key, "")
                lv = local_val.get(key, "")
                if rv != lv:
                    if key not in remote_val:
                        section_diffs.append(f"    + {key}: <added>")
                    elif key not in local_val:
                        section_diffs.append(f"    - {key}: <removed>")
                    else:
                        section_diffs.append(f"    ~ {key}")
                        if isinstance(rv, str) and isinstance(lv, str) and len(rv) < 200 and len(lv) < 200:
                            section_diffs.append(f"      - {rv[:100]}")
                            section_diffs.append(f"      + {lv[:100]}")
            if section_diffs:
                lines.append(f"  [{section}]")
                lines.extend(section_diffs)
        elif isinstance(remote_val, list) and isinstance(local_val, list):
            if set(remote_val) != set(local_val):
                lines.append(f"  [{section}]")
                added_items = set(local_val) - set(remote_val)
                removed_items = set(remote_val) - set(local_val)
                for item in sorted(added_items):
                    lines.append(f"    + {item}")
                for item in sorted(removed_items):
                    lines.append(f"    - {item}")
        else:
            lines.append(f"  [{section}]")
            lines.append(f"    - {remote_val}")
            lines.append(f"    + {local_val}")

    return lines


@cli.command()
@click.argument("module_ref")
@click.pass_context
def diff(ctx: click.Context, module_ref: str) -> None:
    """Show module differences between local and remote (field-level JSON diff)."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    # Parse module_ref as category/id
    parts = module_ref.split("/", 1)
    if len(parts) != 2:
        click.echo("Error: Use format 'category/module-id'", err=True)
        raise click.Abort()
    category, module_id = parts
    module_path = f"{category}/{module_id}.json"

    # Get remote version
    remote_result = _run_git(kb, "show", f"origin/main:{module_path}")
    remote_data = None
    if remote_result.returncode == 0:
        try:
            remote_data = json.loads(remote_result.stdout)
        except json.JSONDecodeError:
            click.echo("Warning: Could not parse remote JSON.")
    else:
        click.echo(f"Module not found in remote: {module_path}")

    # Get local version
    local_file = kb / module_path
    local_data = None
    if local_file.exists():
        try:
            local_data = json.loads(local_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            click.echo("Warning: Could not parse local JSON.")
    else:
        click.echo(f"Module deleted locally: {module_path}")

    if remote_data is None and local_data is None:
        return

    if remote_data is None:
        click.echo(f"Module {module_ref} is new (not in remote).")
        return

    if local_data is None:
        click.echo(f"Module {module_ref} was deleted locally.")
        return

    diffs = _json_diff_sections(remote_data, local_data)
    if not diffs:
        click.echo(f"No differences in {module_ref}.")
        return

    click.echo(f"Changes in {module_ref}:")
    for line in diffs:
        if line.startswith("  [") and line.endswith("]"):
            console.print(f"\n[bold]{line.strip()}[/bold]")
        elif line.startswith("    +"):
            console.print(f"[green]{line}[/green]")
        elif line.startswith("    -"):
            console.print(f"[red]{line}[/red]")
        elif line.startswith("    ~"):
            console.print(f"[yellow]{line}[/yellow]")
        else:
            click.echo(line)


# --- telemetry subcommands ---


@cli.group()
def telemetry() -> None:
    """Manage usage telemetry for relevance feedback."""


@telemetry.command("status")
@click.pass_context
def telemetry_status(ctx: click.Context) -> None:
    """Show telemetry status and event counts."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)
    cfg = _load_config(kb)
    enabled = cfg.telemetry.enabled
    click.echo(f"Telemetry: {'enabled' if enabled else 'disabled'}")
    events = load_search_events(kb)
    search_count = sum(1 for e in events if e.get("type") == "search")
    load_count = sum(1 for e in events if e.get("type") == "load")
    click.echo(f"Search events: {search_count}")
    click.echo(f"Load events: {load_count}")
    click.echo(f"Total events: {len(events)}")
    if search_count >= 100:
        click.echo("Ranking model: bayesian (active)")
    elif search_count > 0:
        click.echo(f"Ranking model: bayesian (warming up, {100 - search_count} searches needed)")
    else:
        click.echo("Ranking model: rule_only (no usage data yet)")


@telemetry.command("disable")
@click.pass_context
def telemetry_disable(ctx: click.Context) -> None:
    """Disable telemetry collection."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)
    cfg = _load_config(kb)
    cfg.telemetry.enabled = False
    _save_config(kb, cfg)
    click.echo("Telemetry disabled.")


@telemetry.command("enable")
@click.pass_context
def telemetry_enable(ctx: click.Context) -> None:
    """Enable telemetry collection."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)
    cfg = _load_config(kb)
    cfg.telemetry.enabled = True
    _save_config(kb, cfg)
    click.echo("Telemetry enabled.")


@telemetry.command("export")
@click.pass_context
def telemetry_export(ctx: click.Context) -> None:
    """Export anonymized telemetry data (query hashes only, no raw terms)."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)
    events = load_search_events(kb)
    # Strip query_terms for privacy; keep only query_hash
    sanitized = []
    for e in events:
        s = {
            "type": e.get("type"),
            "timestamp": e.get("timestamp"),
            "query_hash": e.get("query_hash"),
            "results_shown": e.get("results_shown"),
        }
        if e.get("type") == "load":
            s["module_id"] = e.get("module_id")
            s["category"] = e.get("category")
        sanitized.append(s)
    click.echo(json.dumps(sanitized, indent=2))


# --- rank subcommands ---


@cli.group()
def rank() -> None:
    """Inspect and manage the relevance ranking model."""


@rank.command("status")
@click.pass_context
def rank_status(ctx: click.Context) -> None:
    """Show ranking model status and feature weights."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)
    events = load_search_events(kb)
    search_count = sum(1 for e in events if e.get("type") == "search")
    load_count = sum(1 for e in events if e.get("type") == "load")
    click.echo(f"Model: {'bayesian' if search_count >= 100 else 'rule_only' if search_count == 0 else 'bayesian (warming up)'}")
    click.echo(f"Search events: {search_count}")
    click.echo(f"Load events: {load_count}")
    click.echo("Features (in order):")
    click.echo("  1. heuristic_score * confidence_weight")
    click.echo("  2. match_quality")
    click.echo("  3. bayesian_prior")
    click.echo("  4. bm25_score")


@rank.command("retrain")
@click.pass_context
def rank_retrain(ctx: click.Context) -> None:
    """Force recomputation of the Bayesian ranking model from telemetry data."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)
    import os as _os
    cache_file = kb / ".telemetry" / "rank_model.json"
    if cache_file.exists():
        cache_file.unlink()
        click.echo("Ranking model cache cleared.")
    else:
        click.echo("No cached model to clear.")
    events = load_search_events(kb)
    search_count = sum(1 for e in events if e.get("type") == "search")
    click.echo(f"Model will retrain from {search_count} search events on next query.")


# --- marketplace + install + publish (Phase 4D) ---


@cli.group()
def marketplace() -> None:
    """Browse and install modules from the knowledge marketplace."""


@marketplace.command("search")
@click.argument("query")
@click.pass_context
def marketplace_search(ctx: click.Context, query: str) -> None:
    """Search the knowledge marketplace for module templates."""
    from knowledge_manager.marketplace import fetch_marketplace_index, search_marketplace

    kb = ctx.obj["kb_path"]
    cfg = _load_config(kb)
    mp_url = cfg.marketplace.index_url

    mp_index = fetch_marketplace_index(mp_url)
    if mp_index is None:
        click.echo(f"Could not reach marketplace at {mp_url}. Check your network or config.")
        return

    results = search_marketplace(query, mp_index)
    if not results:
        click.echo(f"No marketplace modules matching '{query}'.")
        return

    click.echo(f"\nMarketplace search results for '{query}':\n")
    for mod in results[:10]:
        click.echo(f"  {mod.category}/{mod.id}")
        click.echo(f"    {mod.title}")
        click.echo(f"    {mod.summary[:120]}...")
        click.echo(f"    v{mod.version} | {mod.downloads} downloads | rating {mod.rating}/5")
        click.echo()


@marketplace.command("show")
@click.argument("module_ref")
@click.pass_context
def marketplace_show(ctx: click.Context, module_ref: str) -> None:
    """Show a marketplace module's full details."""
    from knowledge_manager.marketplace import fetch_marketplace_index

    kb = ctx.obj["kb_path"]
    cfg = _load_config(kb)
    mp_url = cfg.marketplace.index_url

    mp_index = fetch_marketplace_index(mp_url)
    if mp_index is None:
        click.echo(f"Could not reach marketplace at {mp_url}.")
        return

    if module_ref not in mp_index.modules:
        click.echo(f"Module '{module_ref}' not found in marketplace.")
        return

    mod = mp_index.modules[module_ref]
    click.echo(f"\n  ID: {mod.category}/{mod.id}")
    click.echo(f"  Title: {mod.title}")
    click.echo(f"  Summary: {mod.summary}")
    click.echo(f"  Version: {mod.version}")
    click.echo(f"  Author: {mod.author}")
    click.echo(f"  Confidence: {mod.confidence}")
    click.echo(f"  Downloads: {mod.downloads}")
    click.echo(f"  Rating: {mod.rating}/5 ({mod.ratings_count} ratings)")
    if mod.tags:
        click.echo(f"  Tags: {', '.join(mod.tags)}")
    if mod.dependencies:
        click.echo(f"  Dependencies: {', '.join(mod.dependencies)}")


@cli.command()
@click.argument("module_ref")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@click.option("--category", "-c", default=None, help="Override target category")
@click.pass_context
def install(ctx: click.Context, module_ref: str, yes: bool, category: str | None) -> None:
    """Install a module template from the knowledge marketplace into staging."""
    from knowledge_manager.marketplace import install_from_marketplace

    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    try:
        plan = install_from_marketplace(module_ref, kb)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()

    if category:
        plan.target_category = category

    click.echo(f"\nWill install {len(plan.modules)} module(s) into .staging/:\n")
    for mod in plan.modules:
        click.echo(f"  • {plan.target_category}/{mod.id} v{mod.version} — {mod.title}")
    if plan.dependencies_installed:
        click.echo(f"\n  Dependencies resolved: {', '.join(plan.dependencies_installed)}")

    if not yes:
        if not click.confirm("\nProceed with installation?"):
            click.echo("Cancelled.")
            return

    from knowledge_manager.storage import rebuild_index
    rebuild_index(kb)
    click.echo(f"\nInstalled {len(plan.modules)} module(s) into staging. Review with 'km review'.")


@cli.command()
@click.argument("module_ref")
@click.option("--dry-run", is_flag=True, help="Preview sanitized module without publishing")
@click.pass_context
def publish(ctx: click.Context, module_ref: str, dry_run: bool) -> None:
    """Publish a local module to the knowledge marketplace."""
    from knowledge_manager.marketplace import check_publish_gate, sanitize_module_text

    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    parts = module_ref.split("/", 1)
    if len(parts) != 2:
        click.echo("Error: Use format 'category/module-id'", err=True)
        raise click.Abort()
    category, module_id = parts

    from knowledge_manager.storage import load_module
    mod = load_module(module_id, category, kb)
    if mod is None:
        click.echo(f"Module not found: {module_ref}", err=True)
        raise click.Abort()

    module_json = mod.model_dump_json(indent=2)

    issues = check_publish_gate(module_json)
    if issues:
        click.echo("Publish gate checks failed:")
        for issue in issues:
            click.echo(f"  • {issue}")
        raise click.Abort()

    cfg = _load_config(kb)
    patterns = cfg.marketplace.sanitize_patterns
    if patterns:
        sanitized = sanitize_module_text(module_json, patterns)
    else:
        sanitized = module_json

    if dry_run:
        click.echo("=== Sanitized module preview ===\n")
        click.echo(sanitized)
        click.echo(f"\nSanitization rules applied: {len(patterns)}")
        return

    click.echo(f"Module {module_ref} ready for publishing.")
    click.echo("To publish, push this module to the marketplace repository.")
    click.echo(f"Marketplace index URL: {cfg.marketplace.index_url}")


# --- webhook subcommands (Phase 4C) ---


@cli.group()
def webhook() -> None:
    """Manage knowledge base webhooks for event-driven automation."""


@webhook.command("status")
@click.pass_context
def webhook_status(ctx: click.Context) -> None:
    """Show webhook configuration and delivery status."""
    from knowledge_manager.webhooks import _load_webhook_config, load_webhook_failures

    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    wc = _load_webhook_config(kb)
    if wc is None:
        click.echo("Webhooks are not configured or disabled.")
        return

    failures = load_webhook_failures(kb)
    failure_count = len(failures)

    click.echo(f"Webhooks: enabled ({len(wc.endpoints)} endpoint(s))")
    for i, ep in enumerate(wc.endpoints):
        click.echo(f"\n  Endpoint {i}: {ep.url}")
        click.echo(f"    Events: {', '.join(ep.events) if ep.events else 'all'}")
        if ep.secret:
            click.echo(f"    Signing: HMAC-SHA256 (secret configured)")
    if failure_count > 0:
        click.echo(f"\n  Failed deliveries (24h): {failure_count}")
        click.echo(f"  Run 'km webhook retry' to retry.")


@webhook.command("test")
@click.option("--endpoint", "-e", "endpoint_idx", type=int, default=0, help="Index of the endpoint to test")
@click.pass_context
def webhook_test(ctx: click.Context, endpoint_idx: int) -> None:
    """Send a test payload to a webhook endpoint."""
    from knowledge_manager.webhooks import _load_webhook_config

    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    wc = _load_webhook_config(kb)
    if wc is None or not wc.endpoints:
        click.echo("No webhook endpoints configured.")
        return

    if endpoint_idx >= len(wc.endpoints):
        click.echo(f"Error: endpoint index {endpoint_idx} out of range (0-{len(wc.endpoints) - 1})", err=True)
        raise click.Abort()

    ep = wc.endpoints[endpoint_idx]
    import json
    test_payload = json.dumps({
        "event": "test",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kb_path": str(kb),
        "message": "KM webhook test",
    })

    try:
        import httpx
        headers = dict(ep.headers)
        if ep.secret:
            from knowledge_manager.webhooks import _sign_payload
            headers["X-KM-Signature"] = f"sha256={_sign_payload(test_payload, ep.secret)}"
        resp = httpx.post(ep.url, content=test_payload, headers=headers, timeout=httpx.Timeout(10.0))
        click.echo(f"Status: {resp.status_code}")
        if resp.status_code < 400:
            click.echo("Webhook test successful.")
        else:
            click.echo(f"Response: {resp.text[:500]}")
    except ImportError:
        click.echo("Error: httpx is not installed. Install it to use webhooks.", err=True)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@webhook.command("retry")
@click.option("--since", default=None, help="Only retry failures since a date (e.g. 2026-07-14)")
@click.pass_context
def webhook_retry(ctx: click.Context, since: str | None) -> None:
    """Retry failed webhook deliveries."""
    from knowledge_manager.webhooks import retry_webhooks, load_webhook_failures

    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    failures = load_webhook_failures(kb)
    if not failures:
        click.echo("No failed webhook deliveries to retry.")
        return

    click.echo(f"Retrying {len(failures)} failed delivery(s)...")
    count = retry_webhooks(kb)
    remaining = len(load_webhook_failures(kb))
    click.echo(f"Retried successfully: {count}")
    if remaining > 0:
        click.echo(f"Still failing: {remaining} (max attempts reached or still unreachable)")


if __name__ == "__main__":
    cli()
