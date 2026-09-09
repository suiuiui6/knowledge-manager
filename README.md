# Knowledge Manager

[![Public surface](https://github.com/suiuiui6/knowledge-manager/actions/workflows/public-surface.yml/badge.svg)](https://github.com/suiuiui6/knowledge-manager/actions/workflows/public-surface.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Git-native knowledge modules and MCP retrieval for agentic workflows.

> 中文：Knowledge Manager 把零散笔记整理成可审阅、可版本化的知识模块，
> 并通过 CLI 与 MCP 按需提供给 AI Agent。它不是托管式 RAG 服务，也不包含生产凭据。

## Why it exists

Most small and medium knowledge bases need reviewability more than another opaque
vector pipeline. Knowledge Manager stores structured JSON modules in Git, keeps a
human review checkpoint, and exposes deterministic retrieval tools through MCP.

## Who it is for

- Teams maintaining reusable runbooks, design notes, and domain knowledge.
- Agent workflows that need selective, inspectable context.
- Projects that want Git review and atomic local writes before publishing modules.

It is not intended for tens of millions of words, hosted multi-tenant search, or
unattended production extraction.

## Quick Start

```bash
git clone https://github.com/suiuiui6/knowledge-manager.git
cd knowledge-manager
poetry install
poetry run km init ./my_kb
poetry run km --kb-path ./my_kb list
```

To use an LLM provider, set a local environment variable or configure the
generated `config.json`; never commit a real key:

```bash
$env:DEEPSEEK_API_KEY = "<your-key>"  # PowerShell
export DEEPSEEK_API_KEY="<your-key>"  # POSIX shells
poetry run km --kb-path ./my_kb add notes.txt -c engineering
poetry run km --kb-path ./my_kb review
poetry run km --kb-path ./my_kb serve
```

## Core workflow

`raw notes → extraction → staging → human review → approved JSON modules → MCP`

The `km` CLI supports initialization, listing, search, module inspection, staged
review, configuration, and an MCP server. The module schema is documented in
[`src/knowledge_manager/schemas.py`](src/knowledge_manager/schemas.py).

## Validation and evidence

```bash
poetry run pytest -q
python -B tools/check_public_surface.py
```

The public-surface workflow checks documentation, tracked paths, and credential-
like content. The repository test suite is the code-quality signal; provider live
tests are opt-in and are not run by public CI. Current test status can vary by
branch and dependency state; do not interpret this README as a production SLA.

## Project map

| Path | Purpose |
| --- | --- |
| `src/knowledge_manager/cli.py` | CLI entry point |
| `src/knowledge_manager/storage.py` | Atomic module and index storage |
| `src/knowledge_manager/llm_clients.py` | Provider adapters |
| `src/knowledge_manager/mcp_server.py` | MCP resources and tools |
| `examples/` | Safe sample knowledge base |
| `docs/` | Validation notes and design records |

## Status and limitations

This is an actively evolving open-source reference implementation. Live provider,
large-scale performance, and hosted deployment behavior are `not-run` by the
public-surface workflow. Credentials, private notes, generated logs, and uploaded
documents must remain outside Git.

## Contributing, security, and license

Read [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before opening an issue or pull request.
The project is released under the [MIT License](LICENSE).
