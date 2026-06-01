# Knowledge Manager

Turn messy notes into structured modules that LLMs can load on demand via MCP.

Knowledge Manager is a git-native knowledge system for agentic workflows. It stores knowledge as inspectable JSON modules, maintains a lightweight index, and serves both through a CLI and MCP server.

**Who It’s For:** Teams running AI-assisted engineering workflows who want reusable, reviewable project knowledge without operating a full RAG stack.

- **Structured modules, not chunks.** Preserve intent with explicit sections (`overview`, `details`, `examples`, `references`, `caveats`).
- **Git-native JSON storage.** Plain files, atomic writes, and easy review in pull requests.
- **MCP-ready retrieval.** Expose index + module loading tools so clients can choose what to read at runtime.

## Why this approach?

For small-to-medium knowledge bases (<= 1M words), structured modules are often simpler to operate than embedding-heavy pipelines.

| Approach | Strength | Tradeoff |
|----------|----------|----------|
| Knowledge Manager | Human-readable modules + deterministic file storage | Requires a review step during ingest |
| Classic RAG | Strong semantic recall at larger scale | More moving parts (chunking, embeddings, re-indexing) |

## Quick Start

### 1. Initialize a knowledge base

```bash
km init ./my_kb
```

### 2. Configure your provider

```bash
km --kb-path ./my_kb config set llm_providers.deepseek.api_key "sk-..."
```

### 3. Extract from notes

```bash
km --kb-path ./my_kb add notes.txt -c auth
```

### 4. Review staged modules

```bash
km --kb-path ./my_kb review
```

### 5. Serve through MCP

```bash
km --kb-path ./my_kb serve
```

## Who should use this?

- Teams that want inspectable, versioned knowledge artifacts in git.
- Agent workflows that benefit from selective module loading via MCP.
- Projects where maintainability and editorial control matter more than retrieval automation at massive scale.

## Who should not use this?

- Workloads that require large-scale semantic retrieval over tens of millions of words.
- Systems already optimized around production embedding infrastructure.

## Features

- Keep knowledge Git-native and auditable: every approved module is JSON you can diff, review, and version with your repo.
- Turn unstructured docs into reusable modules with clear sections (`overview`, `details`, `examples`, `references`, `caveats`).
- Add a human checkpoint before publish: **extract → staging → review → approve**.
- Use one workflow across models with provider support for DeepSeek (default `deepseek-v4-pro`), Claude, and OpenAI.
- Reuse knowledge from editors and agents through MCP via `knowledge://index`, `load_module`, `search_modules`, and `list_categories`.
- Keep retrieval responsive for hot modules with a thread-safe LRU cache.
- Process long documents reliably with chunked extraction (`chunk_size`, `chunk_overlap`).
- Operate with visibility through verbose CLI logs for provider/model choice, chunking, and extraction progress.
- Ship with confidence: 75 tests across schema, storage, cache, LLM clients, MCP server, CLI, and integration layers.

## Typical Use Cases

- Build a shared team knowledge layer from product docs, runbooks, and incident writeups, then expose it to coding agents via MCP.
- Replace copy-pasted prompt context with reviewed, versioned modules that can be searched and loaded on demand.
- Keep architecture decisions and operational caveats close to code so AI-assisted workflows stay accurate over time.

## Installation

```bash
git clone <repo>
cd knowledge-manager
poetry install
```

The `km` command is available after install via the entry point declared in `pyproject.toml`.

## Detailed Setup

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

The LLM reads `notes.txt`, chunks it when needed, returns up to `max_modules_per_extraction` structured modules, and writes them to `.staging/`.

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
km --kb-path ./my_kb search "jwt token"      # ranked keyword search
km --kb-path ./my_kb show auth-jwt -c auth   # full module JSON
km --kb-path ./my_kb stats                   # KB statistics
```

Search ranks exact word matches first, then English stem matches, with partial matching as a fallback for short queries.

### 6. Serve as MCP

```bash
km --kb-path ./my_kb serve
```

This launches a stdio MCP server. Clients (Claude Code, etc.) see:

- Resource `knowledge://index` — full index JSON
- Tool `load_module(module_id, category)` — full module content
- Tool `search_modules(query)` — ranked keyword search with exact, stem, and short-query partial matching
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
| `cli.py` | Click CLI (10 top-level commands plus `config` subcommands) |

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

## Logging

Use `km --verbose ...` to enable operational logging during CLI runs. Verbose logs include metadata such as provider name, model, chunk counts, module counts, and payload sizes, but they intentionally exclude raw note content, full prompts, LLM responses, API keys, and local file paths.

## Development

```bash
poetry run pytest               # 75 tests
poetry run black src tests      # format
poetry run mypy src             # type check
```

Current validation artifacts are checked into [`test-results/`](test-results/) and [`docs/validation-report-2026-05-29.md`](docs/validation-report-2026-05-29.md). They cover MCP protocol compliance, retrieval behavior, and an end-to-end extract -> review -> serve run against a real sample knowledge base.

## Example knowledge base

See [`examples/sample_knowledge_base/`](examples/sample_knowledge_base/) for a small working KB you can copy as a starting point.

## License

MIT
