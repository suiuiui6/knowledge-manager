---
id: retrieval-scoring-algorithm
category: general
title: Retrieval Scoring Algorithm
summary: Describes the word-boundary regex scoring used by search_modules to rank
  candidate modules.
tags:
- retrieval
- scoring
- implementation
- search
confidence: high
status: published
created_at: '2026-05-29T11:54:35.775190'
updated_at: '2026-05-29T11:54:35.775191'
---

# 概述

search_modules uses weighted scoring across four fields: title (5), metadata.tags (3), summary (2), content.overview (1). Whole-word matching with per-term scoring summing to a module score, sorted descending; modules with zero score are dropped.

# 细节

For each query term, the module receives the weight of the highest-scoring field where the term appears as a whole word (word-boundary regex). Per-term scores are summed. Substring artifacts are filtered (auth does not match authentication or OAuth). This ensures title hits dominate, and loosely related modules sink to the bottom, providing signal to the LLM rather than a hard filter.

# 示例

Query 'jwt' appearing in a module's title yields score 5; in tags score 3; in content.overview score 1. Multiple terms like 'jwt HS256' would sum per-term scores.

# 注意事项

Intentionally allows modules that contain standalone query terms (e.g., 'auth' in 'TCP+TLS+auth handshake') to surface but below stronger matches, giving the LLM confirmation.
