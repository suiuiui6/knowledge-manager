# Lightweight AI Knowledge Management System - Design Specification

**Date:** 2026-05-28  
**Status:** Approved

## Overview

A lightweight AI knowledge management system that serves as an alternative to traditional RAG. The system enables collaborative refinement of raw knowledge into structured, modular text blocks, stores them as independent JSON files, and allows LLMs to autonomously select and reference required knowledge modules based on task context.

**Target Scale:** Small-to-medium knowledge bases (up to 1 million words, ~50-200 modules)

**Key Differentiators:**
- Structured modules instead of simple text chunking
- LLM-driven autonomous knowledge selection (not rigid retrieval rules)
- Lighter and more efficient than traditional RAG or Skill-based solutions
- Collaborative human-AI knowledge refinement workflow

## System Architecture

### Core Components

1. **MCP Server** (`knowledge_mcp_server.py`)
   - Exposes MCP resources (knowledge index) and tools (module operations)
   - Manages LLM client connections for extraction (Claude, OpenAI, DeepSeek)
   - Handles all file I/O and JSON validation
   - Maintains in-memory cache of frequently accessed modules

2. **CLI** (`km` command)
   - Thin wrapper that invokes MCP tools via stdio transport
   - Commands: `init`, `add`, `extract`, `review`, `edit`, `delete`, `list`, `rebuild`
   - Configuration management for LLM providers

3. **Knowledge Base Structure:**
   ```
   knowledge_base/
   ├── config.json              # LLM provider configs, settings
   ├── index.json               # Main index with categories and module summaries
   ├── modules/
   │   ├── auth/
   │   │   ├── oauth-flow.json
   │   │   └── jwt-tokens.json
   │   ├── database/
   │   │   ├── migrations.json
   │   │   └── query-optimization.json
   │   └── deployment/
   │       └── ci-cd-pipeline.json
   ```

### Data Flow

- **Knowledge Creation:** User runs `km add raw_notes.txt` → MCP tool calls LLM to extract modules → saves JSON files → rebuilds index
- **Knowledge Retrieval:** LLM reads index resource → decides which modules needed → calls `load_module` tool → receives structured content
- **Knowledge Management:** User runs `km review` → sees extracted modules → edits/approves → updates saved

### Integration Model

**Hybrid Approach:**
- **Index as MCP Resource:** Small index with module summaries always available in LLM context
- **Modules as MCP Tools:** Full module content loaded on-demand via tool calls
- **Autonomous Selection:** LLM reads summaries and decides which modules to load based on conversation context

## JSON Schemas

### Module Schema

File: `modules/<category>/<module-id>.json`

```json
{
  "id": "oauth-flow",
  "category": "auth",
  "title": "OAuth 2.0 Authentication Flow",
  "summary": "Implementation details and best practices for OAuth 2.0 flow in our application",
  "created_at": "2026-05-28T10:30:00Z",
  "updated_at": "2026-05-28T10:30:00Z",
  "content": {
    "overview": "High-level explanation of what this knowledge covers",
    "details": "In-depth information, technical specifics, implementation notes",
    "examples": "Code snippets, usage examples, real-world scenarios",
    "references": "Links to docs, related modules, external resources",
    "caveats": "Known issues, limitations, things to watch out for"
  },
  "metadata": {
    "tags": ["authentication", "security", "api"],
    "related_modules": ["auth/jwt-tokens", "api/rate-limiting"],
    "confidence": "high",
    "source": "team documentation + code review notes"
  }
}
```

**Field Descriptions:**
- `id`: Unique identifier within category (kebab-case)
- `category`: Organizational category (e.g., auth, database, deployment)
- `title`: Human-readable title
- `summary`: 1-2 sentence overview for index
- `content.overview`: High-level explanation (2-3 sentences)
- `content.details`: Technical specifics, implementation notes
- `content.examples`: Code snippets, commands, configurations
- `content.references`: URLs, related concepts, dependencies
- `content.caveats`: Known issues, limitations, warnings
- `metadata.tags`: Searchable keywords
- `metadata.related_modules`: Cross-references to other modules
- `metadata.confidence`: high/medium/low - reliability indicator
- `metadata.source`: Where this knowledge came from

### Index Schema

File: `index.json`

```json
{
  "version": "1.0",
  "updated_at": "2026-05-28T10:30:00Z",
  "stats": {
    "total_modules": 42,
    "total_words": 125000,
    "categories": 8
  },
  "categories": {
    "auth": {
      "description": "Authentication and authorization patterns",
      "modules": [
        {
          "id": "oauth-flow",
          "title": "OAuth 2.0 Authentication Flow",
          "summary": "Implementation details and best practices for OAuth 2.0 flow",
          "tags": ["authentication", "security", "api"],
          "word_count": 850
        }
      ]
    },
    "database": {
      "description": "Database design, queries, and optimization",
      "modules": []
    }
  }
}
```

**Design Rationale:**
- Categorized organization helps LLM narrow down relevant modules quickly
- Module summaries in index allow LLM to make informed decisions without loading full content
- Stats provide context about knowledge base size and coverage

### Config Schema

File: `config.json`

```json
{
  "llm_providers": {
    "deepseek": {
      "api_key": "${DEEPSEEK_API_KEY}",
      "model": "deepseek-v4-pro",
      "base_url": "https://api.deepseek.com",
      "default": true
    },
    "claude": {
      "api_key": "${ANTHROPIC_API_KEY}",
      "model": "claude-sonnet-4-6"
    },
    "openai": {
      "api_key": "${OPENAI_API_KEY}",
      "model": "gpt-4"
    }
  },
  "extraction": {
    "provider": "deepseek",
    "max_modules_per_extraction": 10,
    "auto_categorize": true
  },
  "cache": {
    "enabled": true,
    "max_modules": 50
  }
}
```

**Configuration Features:**
- Multi-provider support (DeepSeek, Claude, OpenAI, extensible)
- Environment variable substitution for API keys
- Configurable extraction behavior
- Module caching for performance

## MCP Server Interface

### MCP Resources

**`knowledge://index`** - Main knowledge index
- Returns the full `index.json` content
- Always available in LLM context
- LLM reads this to understand available modules and decide what to load
- Updates automatically when modules are added/removed

### MCP Tools

**`load_module(category: str, module_id: str)`**
- Load a specific knowledge module
- Returns the full module JSON with all structured fields
- LLM calls this after reading the index to get detailed knowledge
- Cached for performance

**`search_modules(query: str, categories: list[str] = None)`**
- Search across modules by keyword
- Returns matching modules based on title/summary/tags
- Optional category filtering
- Useful when LLM needs to find modules by keyword

**`extract_knowledge(raw_text: str, suggested_category: str = None)`**
- Extract modules from raw input text
- Calls configured LLM to analyze text and create structured modules
- Returns list of extracted modules for user review
- Used by CLI `add` command

**`save_module(module: dict)`**
- Save a reviewed/edited module
- Validates schema and saves to appropriate category folder
- Rebuilds index automatically
- Used after user reviews extracted modules

**`delete_module(category: str, module_id: str)`**
- Remove a module
- Deletes file and updates index

**`list_categories()`**
- Get all categories with stats
- Returns category names, descriptions, module counts

## CLI Commands

### Command Reference

```bash
km init [path]                          # Initialize new knowledge base
km add <file|text> [-c category]       # Extract modules from raw input
km review                               # Review pending extracted modules
km edit <category>/<module-id>          # Edit existing module
km delete <category>/<module-id>        # Delete a module
km list [category]                      # List all modules or by category
km search <query>                       # Search modules by keyword
km rebuild                              # Rebuild index from modules
km config set <key> <value>             # Configure LLM providers
km stats                                # Show knowledge base statistics
```

### Workflow Examples

**Initial setup:**
```bash
km init ./my_knowledge
km config set llm_providers.deepseek.api_key "sk-..."
```

**Adding knowledge:**
```bash
km add notes.txt -c database
# Extracts modules, shows preview
km review
# User sees extracted modules, can edit/approve/reject
```

**Managing modules:**
```bash
km list                              # See all modules
km edit auth/oauth-flow              # Opens in $EDITOR
km search "authentication"           # Find related modules
```

### Review Interface

When user runs `km review`, they see:

```
Found 3 extracted modules:

[1] auth/oauth-flow
    Title: OAuth 2.0 Authentication Flow
    Summary: Implementation details and best practices...
    
    Actions: (a)pprove, (e)dit, (r)eject, (s)kip

[2] auth/jwt-tokens
    Title: JWT Token Management
    Summary: Best practices for JWT token generation...
    
    Actions: (a)pprove, (e)dit, (r)eject, (s)kip
```

**Actions:**
- `a` (approve): Save module to knowledge base
- `e` (edit): Open in $EDITOR, then save
- `r` (reject): Discard module
- `s` (skip): Leave in staging for later review

## LLM Integration

### System Prompt Addition

The following prompt should be added to the LLM's system context when the knowledge manager MCP server is active:

```markdown
# Knowledge Base Access

You have access to a structured knowledge base via MCP. The knowledge index is available as a resource and shows all available modules organized by category.

## How to Use:

1. **Check the index** - The `knowledge://index` resource shows all available modules with summaries
2. **Identify relevant modules** - Based on the user's question/task, determine which modules might be helpful
3. **Load modules as needed** - Use `load_module(category, module_id)` to get full details
4. **Reference appropriately** - When using knowledge from modules, mention the source naturally

## When to Load Modules:

- User asks about a topic covered in the knowledge base
- You need specific implementation details or examples
- User references "how we do X" or "our approach to Y"
- Technical decisions require context from past work

## When NOT to Load:

- General questions you can answer from training data
- User explicitly asks you NOT to use the knowledge base
- The index shows no relevant modules for the topic

## Module Content Structure:

Each module contains:
- **overview**: High-level explanation
- **details**: Technical specifics and implementation notes
- **examples**: Code snippets and usage examples
- **references**: Links and related modules
- **caveats**: Known issues and limitations

Use the appropriate section based on what the user needs.
```

### Example LLM Behavior

```
User: "How should I implement authentication in the new API?"

LLM thinks: Let me check the knowledge index...
[reads knowledge://index resource]
[sees auth category with oauth-flow and jwt-tokens modules]

LLM: I can see we have documented approaches for authentication. Let me load the relevant modules.
[calls load_module("auth", "oauth-flow")]
[calls load_module("auth", "jwt-tokens")]

LLM: Based on our authentication documentation, here's the recommended approach...
[provides answer using module content]
```

## Knowledge Extraction Process

### Extraction Prompt

When `extract_knowledge` is called, the following prompt is sent to the configured LLM:

```markdown
You are a knowledge extraction assistant. Your task is to analyze raw text and extract structured, modular knowledge blocks.

## Input:
{raw_text}

## Instructions:

1. Identify distinct knowledge topics in the text (aim for 3-10 modules depending on content)
2. For each topic, create a structured module with:
   - A clear, descriptive title
   - A 1-2 sentence summary
   - Appropriate category (suggest from: auth, database, deployment, api, frontend, backend, infrastructure, testing, or propose new)
   - Structured content fields:
     * overview: High-level explanation (2-3 sentences)
     * details: Technical specifics, implementation notes, step-by-step processes
     * examples: Code snippets, commands, configuration examples (if applicable)
     * references: URLs, related concepts, dependencies
     * caveats: Known issues, limitations, things to watch out for

3. Add relevant tags for searchability
4. Suggest related modules if connections are obvious

## Output Format:

Return a JSON array of module objects following this schema:
{schema}

## Guidelines:

- Each module should be self-contained and focused on ONE topic
- Avoid duplication - if concepts overlap, reference between modules
- Extract actual code/commands verbatim, don't paraphrase
- If information is incomplete, note it in caveats rather than inventing details
- Prioritize actionable, practical knowledge over theory
```

### Post-Extraction Workflow

1. LLM returns extracted modules as JSON array
2. System validates schema and saves to temporary staging area
3. User runs `km review` to see extracted modules
4. For each module, user can:
   - Approve (saves to knowledge base)
   - Edit (opens in editor, then saves)
   - Reject (discards)
   - Skip (leaves in staging for later)
5. After review, index is rebuilt automatically

### Error Handling

- **Invalid JSON from LLM** → Retry with error feedback
- **Schema validation fails** → Show user the issue, allow manual fix
- **Duplicate module IDs** → Auto-append suffix or prompt user to choose
- **Category doesn't exist** → Create new category or prompt user to choose existing

## Implementation Details

### Project Structure

```
knowledge-manager/
├── pyproject.toml              # Poetry/pip config
├── README.md
├── src/
│   ├── knowledge_manager/
│   │   ├── __init__.py
│   │   ├── mcp_server.py       # Main MCP server
│   │   ├── cli.py              # CLI entry point
│   │   ├── extractor.py        # LLM extraction logic
│   │   ├── storage.py          # File I/O, JSON handling
│   │   ├── schemas.py          # Pydantic models for validation
│   │   ├── cache.py            # Module caching
│   │   └── llm_clients.py      # Multi-provider LLM clients
├── tests/
│   ├── test_extraction.py
│   ├── test_storage.py
│   └── fixtures/
└── examples/
    └── sample_knowledge_base/
```

### Key Dependencies

- `mcp` - MCP SDK for Python
- `pydantic` - Schema validation
- `click` - CLI framework
- `httpx` - HTTP client for LLM APIs
- `rich` - Terminal UI for review interface

### Performance Considerations

**Index Size:**
- For 200 modules with 500-word summaries: ~100KB index
- Negligible impact on LLM context window
- Fast to parse and scan

**Module Caching:**
- LRU cache for 50 most recent modules
- ~5MB memory footprint
- Reduces file I/O for frequently accessed modules

**Lazy Loading:**
- Modules only loaded when LLM explicitly requests them
- Index provides enough information for decision-making
- Full content retrieved on-demand

**Index Updates:**
- Incremental updates when single module changes
- Full rebuild on demand via `km rebuild`
- Atomic writes to prevent corruption

### Testing Strategy

**Unit Tests:**
- Extraction logic with mock LLM responses
- Storage operations (read, write, delete)
- Schema validation with valid/invalid inputs
- Cache behavior (hits, misses, eviction)

**Integration Tests:**
- MCP server tools and resources
- CLI commands end-to-end
- Multi-provider LLM client switching

**Fixture-Based Tests:**
- Sample knowledge bases with various structures
- Edge cases (empty categories, large modules, special characters)

**Manual Testing:**
- CLI review workflow with real user interaction
- LLM integration with Claude Code
- Performance with 100+ module knowledge base

### Git Integration

**Version Control:**
- Knowledge base is a git repository
- Each module save = atomic commit with descriptive message
- User can use standard git commands for history/rollback

**Commit Messages:**
- `km add`: "Add N modules to <category>"
- `km edit`: "Update <category>/<module-id>"
- `km delete`: "Delete <category>/<module-id>"

**`.gitignore`:**
```
.cache/
*.pyc
__pycache__/
.env
config.json  # Contains API keys
```

**Best Practices:**
- Commit after each review session
- Use branches for experimental knowledge organization
- Tag stable knowledge base versions

## Success Criteria

**Functional Requirements:**
- ✓ Extract structured modules from raw text
- ✓ Store modules as independent JSON files
- ✓ Maintain categorized index
- ✓ Expose index as MCP resource
- ✓ Provide module loading via MCP tools
- ✓ CLI for knowledge management
- ✓ Multi-provider LLM support

**Performance Requirements:**
- Index loads in <100ms
- Module retrieval in <50ms (cached) / <200ms (uncached)
- Extraction processes 5000 words in <30 seconds
- Support up to 1M words across 200 modules

**Usability Requirements:**
- CLI commands are intuitive and well-documented
- Review interface is clear and efficient
- LLM integration is transparent to users
- Error messages are actionable

**Quality Requirements:**
- Schema validation prevents malformed modules
- Atomic operations prevent data corruption
- Git integration enables safe experimentation
- Tests cover core functionality

## Future Enhancements

**Not in Initial Implementation:**
- Semantic search with embeddings
- Web UI for visual module management
- Module templates for common patterns
- Automatic module merging/splitting suggestions
- Analytics on module usage patterns
- Export to other formats (Markdown, PDF)
- Multi-user collaboration features
- Module versioning within the system (beyond git)

These can be added later based on user feedback and actual usage patterns.
