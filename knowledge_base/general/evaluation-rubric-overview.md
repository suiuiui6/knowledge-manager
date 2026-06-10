---
id: evaluation-rubric-overview
category: general
title: Retrieval Evaluation Rubric Overview
summary: Defines a live test for the knowledge-manager MCP server retrieval using
  fresh Claude Code sessions and five scenarios.
tags:
- retrieval
- evaluation
- mcp
- knowledge-manager
- rubric
confidence: high
status: published
created_at: '2026-05-29T11:54:35.775145'
updated_at: '2026-05-29T11:54:35.775147'
---

# 概述

The rubric verifies that the knowledge-manager MCP server retrieves correct knowledge modules during real Claude tool-use loops. A fresh session is started, /mcp confirms server connectivity, then each scenario question is pasted without additional context to observe whether Claude autonomously consults the KB.

# 细节

Setup: run /mcp to confirm tools load_module, search_modules, list_categories are available. Each scenario tests a different retrieval behavior: direct hits, indirect cross-content matches, and out-of-scope abstention. Passing means answers come from the correct module with no hallucination from unrelated content.

# 示例

User message: 'How do we validate JWT tokens at the API gateway? Please check the project knowledge base before answering.' Expected: Claude calls search_modules (JWT-related), then load_module for jwt-tokens/auth, answer cites RS256, JWKS, kid rotation.

# 参考

MCP server: knowledge-manager; Tools: load_module, search_modules, list_categories.

# 注意事项

The system's safety relies on Claude's judgment about what to load; search precision is secondary. The rubric must be run in a completely fresh Claude Code session to avoid caching effects.
