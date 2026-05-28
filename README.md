# Knowledge Manager

Lightweight AI knowledge management system as an alternative to traditional RAG.

## Features

- Structured knowledge modules instead of simple text chunking
- LLM-driven autonomous knowledge selection
- Multi-provider LLM support (DeepSeek, Claude, OpenAI)
- Interactive CLI for knowledge management
- MCP integration for seamless LLM access

## Installation

```bash
poetry install
```

## Quick Start

```bash
# Initialize knowledge base
km init ./my_knowledge

# Configure LLM provider
km config set llm_providers.deepseek.api_key "your-api-key"

# Add knowledge
km add notes.txt

# Review extracted modules
km review

# List modules
km list

# Search modules
km search "authentication"
```

## Development

```bash
# Run tests
poetry run pytest

# Format code
poetry run black src tests

# Type check
poetry run mypy src
```
