import pytest
from datetime import datetime, timezone

from knowledge_manager.markdown import (
    parse_markdown_module,
    render_markdown_module,
    validate_frontmatter,
)


SAMPLE_MD = """---
id: jwt-config
category: auth
title: JWT Token Configuration
summary: We use RS256 asymmetric signing for JWT
tags: [auth, jwt, security]
confidence: high
status: published
source: internal-runbook
related_modules: [auth/oauth-flow, deployment/secrets-management]
created_at: "2026-05-28T10:00:00+00:00"
updated_at: "2026-06-01T14:30:00+00:00"
---

# 概述

We chose RS256 over HS256 for JWT signing in a microservice architecture.

# 细节

## Token Structure

```json
{"sub": "user_123", "iat": 1717200000}
```

# 示例

```python
JWT_ALGORITHM = "RS256"
```

# 注意事项

RS256 signing is ~10x slower than HS256.
"""


class TestParseMarkdown:
    def test_roundtrip(self):
        module = parse_markdown_module(SAMPLE_MD)
        assert module.id == "jwt-config"
        assert module.category == "auth"
        assert module.title == "JWT Token Configuration"
        assert module.metadata.confidence == "high"
        assert module.metadata.status == "published"
        assert "auth/oauth-flow" in module.metadata.related_modules
        assert "RS256" in module.content.overview
        assert "Token Structure" in module.content.details
        assert "JWT_ALGORITHM" in module.content.examples
        assert "10x slower" in module.content.caveats

    def test_render_then_parse(self):
        module = parse_markdown_module(SAMPLE_MD)
        rendered = render_markdown_module(module)
        reparsed = parse_markdown_module(rendered)
        assert reparsed.id == module.id
        assert reparsed.title == module.title
        assert reparsed.metadata.confidence == module.metadata.confidence
        assert "RS256" in reparsed.content.overview

    def test_no_frontmatter(self):
        with pytest.raises(ValueError, match="No YAML frontmatter"):
            parse_markdown_module("# Just a heading\nContent here")

    def test_render_module(self):
        module = parse_markdown_module(SAMPLE_MD)
        md = render_markdown_module(module)
        assert "---" in md
        assert "jwt-config" in md
        assert "# 概述" in md
        assert "# 注意事项" in md

    def test_content_sections(self):
        module = parse_markdown_module(SAMPLE_MD)
        assert len(module.content.overview) > 10
        assert len(module.content.details) > 10
        assert len(module.content.examples) > 0
        assert len(module.content.caveats) > 0


class TestValidateFrontmatter:
    def test_valid(self):
        fm = {"id": "test", "title": "Test Module Title", "confidence": "high", "status": "published"}
        assert validate_frontmatter(fm) == []

    def test_missing_id(self):
        fm = {"title": "Test Module Title"}
        errors = validate_frontmatter(fm)
        assert any("id" in e.lower() for e in errors)

    def test_short_title(self):
        fm = {"id": "test", "title": "Hi"}
        errors = validate_frontmatter(fm)
        assert any("title" in e.lower() for e in errors)

    def test_invalid_confidence(self):
        fm = {"id": "test", "title": "Test Module Title", "confidence": "unknown"}
        errors = validate_frontmatter(fm)
        assert any("confidence" in e.lower() for e in errors)

    def test_invalid_status(self):
        fm = {"id": "test", "title": "Test Module Title", "status": "deleted"}
        errors = validate_frontmatter(fm)
        assert any("status" in e.lower() for e in errors)
