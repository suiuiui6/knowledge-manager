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
@click.version_option("0.1.0", prog_name="km")
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
@click.pass_context
def search(ctx: click.Context, query: str) -> None:
    """Search modules by keyword."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)

    results = search_modules(query, kb)

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
    from knowledge_manager.schemas import ReviewRecord

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
    from knowledge_manager.schemas import ReviewRecord

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


# --- serve (MCP) ---

@cli.command()
@click.pass_context
def serve(ctx: click.Context) -> None:
    """Run the MCP server over stdio."""
    from knowledge_manager.mcp_server import create_server

    kb = ctx.obj["kb_path"]
    _require_kb(kb)
    server = create_server(kb)
    asyncio.run(server.run_stdio_async())


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


if __name__ == "__main__":
    cli()
