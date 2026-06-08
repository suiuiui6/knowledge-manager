import asyncio
import json
import logging
import sys
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
    list_modules,
    list_staging,
    load_index,
    load_module,
    rebuild_index,
    save_index,
    save_module,
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
    for m in modules:
        save_to_staging(m, staging)

    click.echo(f"Extracted {len(modules)} module(s) into staging")


# --- review (interactive) ---

@cli.command()
@click.pass_context
def review(ctx: click.Context) -> None:
    """Review staged modules interactively (a=approve, r=reject, s=skip)."""
    kb = ctx.obj["kb_path"]
    _require_kb(kb)
    staging = _staging_path(kb)

    pending = list_staging(staging)
    if not pending:
        click.echo("No staged modules to review.")
        return

    for i, module in enumerate(pending, 1):
        console.print(f"\n[bold cyan]Module {i}/{len(pending)}[/bold cyan]")
        console.print(f"[bold]Category:[/bold] {module.category}")
        console.print(f"[bold]ID:[/bold] {module.id}")
        console.print(f"[bold]Title:[/bold] {module.title}")
        console.print(f"[bold]Summary:[/bold] {module.summary}")
        console.print(f"[bold]Tags:[/bold] {', '.join(module.metadata.tags)}")
        console.print(f"\n[bold]Overview:[/bold] {module.content.overview[:200]}")

        action = Prompt.ask("Action", choices=["a", "r", "s"], default="a")

        if action == "a":
            approve_from_staging(module.id, staging, kb)
            console.print("[green]Approved[/green]")
        elif action == "r":
            (staging / f"{module.id}.json").unlink()
            console.print("[red]Rejected[/red]")
        else:
            console.print("[yellow]Skipped[/yellow]")

    rebuild_index(kb)


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


if __name__ == "__main__":
    cli()
