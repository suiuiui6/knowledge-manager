# Knowledge Manager

Lightweight AI knowledge management system — an alternative to traditional RAG. Instead of chunking text and relying on vector similarity, you collaborate with an LLM to refine raw notes into **structured knowledge modules** (JSON files) that the LLM autonomously selects from at runtime via MCP.

## Why?

Traditional RAG has well-known weaknesses for small-to-medium knowledge bases (≤ 1M words):

- Chunking destroys structure and intent.
- Vector retrieval is rigid and brittle to phrasing.
- Re-indexing is expensive and opaque.

Knowledge Manager takes a different path:

- **Modules, not chunks.** Each piece of knowledge is a self-contained JSON file with `overview`, `details`, `examples`, `references`, and `caveats`.
- **Index, not embeddings.** A single `index.json` describes every module with title, summary, tags, and category — enough for an LLM to decide what to load.
- **LLM-driven navigation.** The MCP server exposes the index as a resource; the model picks modules to load on demand via tools.
- **Git-friendly storage.** Plain JSON, atomic writes, no databases.

## Features

- Structured `Module` schema (Pydantic v2): `id`, `category`, `title`, `summary`, `content.{overview,details,examples,references,caveats}`, `metadata.{tags,confidence,...}`
- Multi-provider LLM support: DeepSeek (default, `deepseek-v4-pro`), Claude, OpenAI
- Two-phase ingest: **extract → staging → human review → approve**
- Interactive Rich-powered review UI
- Thread-safe LRU cache for hot modules
- MCP server with `knowledge://index` resource and `load_module` / `search_modules` / `list_categories` tools
- 71 tests across schemas, storage, cache, LLM clients, MCP server, CLI, and integration

## Installation

```bash
git clone <repo>
cd knowledge-manager
poetry install
```

The `km` command is available after install via the entry point declared in `pyproject.toml`.

## Quick Start

### 1. Initialize a knowledge base

```bash
km init ./my_kb
```

This creates:

```
my_kb/
├── index.json        # auto-maintained module index
├── config.json       # LLM provider + extraction config
└── .staging/         # pending modules awaiting review
```

### 2. Configure your LLM

Edit `my_kb/config.json` or use the CLI:

```bash
km --kb-path ./my_kb config set llm_providers.deepseek.api_key "sk-..."
```

The default provider is `deepseek` with model `deepseek-v4-pro`. Switch providers with:

```bash
km --kb-path ./my_kb config set extraction.provider claude
```

### 3. Extract modules from raw notes

```bash
km --kb-path ./my_kb add notes.txt -c auth
```

The LLM reads `notes.txt`, returns up to N structured modules, and writes them to `.staging/`.

### 4. Review staged modules

```bash
km --kb-path ./my_kb review
```

For each staged module:
- `a` — approve (move to KB and update index)
- `r` — reject (delete from staging)
- `s` — skip (leave in staging for later)

### 5. Browse and search

```bash
km --kb-path ./my_kb list                    # all modules
km --kb-path ./my_kb list -c auth            # filter by category
km --kb-path ./my_kb search "jwt token"      # keyword search
km --kb-path ./my_kb show auth-jwt -c auth   # full module JSON
km --kb-path ./my_kb stats                   # KB statistics
```

### 6. Serve as MCP

```bash
km --kb-path ./my_kb serve
```

This launches a stdio MCP server. Clients (Claude Code, etc.) see:

- Resource `knowledge://index` — full index JSON
- Tool `load_module(module_id, category)` — full module content
- Tool `search_modules(query)` — keyword OR-match
- Tool `list_categories()` — categories with counts

## Module schema

```json
{
  "id": "auth-jwt",
  "category": "auth",
  "title": "JWT authentication in our API",
  "summary": "How JWT tokens are issued, signed (RS256), and validated.",
  "created_at": "2026-05-28T10:00:00Z",
  "updated_at": "2026-05-28T10:00:00Z",
  "content": {
    "overview": "...",
    "details": "...",
    "examples": "...",
    "references": "...",
    "caveats": "..."
  },
  "metadata": {
    "tags": ["auth", "jwt", "security"],
    "related_modules": ["auth/oauth-flow"],
    "confidence": "high",
    "source": "internal-runbook"
  }
}
```

`id` must match `^[a-z0-9-]+$`. The full schema is in [`src/knowledge_manager/schemas.py`](src/knowledge_manager/schemas.py).

## Architecture

```
┌────────────┐      ┌──────────────┐
│  raw text  │─────▶│  Extractor   │  (LLM call)
└────────────┘      └───────┬──────┘
                            ▼
                       .staging/*.json
                            │
                       human review
                            ▼
            ┌────────────────────────────┐
            │   <category>/<id>.json     │
            │   index.json (auto)        │
            └──────────────┬─────────────┘
                           │
                  ┌────────┴────────┐
                  │                 │
                  ▼                 ▼
              CLI (km)         MCP server
                                 │
                      Claude Code / clients
```

| Module | Responsibility |
|--------|----------------|
| `schemas.py` | Pydantic models (Module, Index, Config, ...) |
| `storage.py` | Atomic file I/O, CRUD, staging, index rebuild |
| `cache.py` | Thread-safe LRU module cache |
| `llm_clients.py` | DeepSeek / Claude / OpenAI async clients |
| `extractor.py` | LLM-powered raw-text → module extraction |
| `mcp_server.py` | FastMCP server (resource + 3 tools) |
| `cli.py` | Click CLI (10 commands) |

## CLI reference

| Command | Description |
|---------|-------------|
| `km init [PATH]` | Initialize a knowledge base |
| `km list [-c CAT]` | List modules (optionally by category) |
| `km stats` | Show KB statistics |
| `km search QUERY` | Keyword search across modules |
| `km show ID -c CAT` | Show full module JSON |
| `km add FILE [-c CAT]` | Extract modules from FILE into staging |
| `km review` | Interactive review of staged modules |
| `km delete ID -c CAT [--yes]` | Delete a module |
| `km rebuild` | Rebuild `index.json` from on-disk modules |
| `km config {set,get,list}` | Manage `config.json` |
| `km serve` | Run MCP server over stdio |

All commands accept a global `--kb-path PATH` (default: cwd).

## Configuration

`config.json` example:

```json
{
  "llm_providers": {
    "deepseek": {
      "api_key": "sk-...",
      "model": "deepseek-v4-pro",
      "base_url": "https://api.deepseek.com",
      "default": true,
      "temperature": 0.3,
      "max_tokens": 4096
    },
    "claude": {
      "api_key": "sk-ant-...",
      "model": "claude-sonnet-4-6",
      "default": false
    }
  },
  "extraction": {
    "provider": "deepseek",
    "max_modules_per_extraction": 10
  },
  "cache": {
    "enabled": true,
    "max_modules": 50
  }
}
```

`config.json` is gitignored — never commit API keys.

## Development

```bash
poetry run pytest               # 71 tests
poetry run black src tests      # format
poetry run mypy src             # type check
```

## Example knowledge base

See [`examples/sample_knowledge_base/`](examples/sample_knowledge_base/) for a small working KB you can copy as a starting point.

## License

MIT
