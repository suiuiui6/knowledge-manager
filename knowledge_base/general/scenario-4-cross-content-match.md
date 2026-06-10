---
id: scenario-4-cross-content-match
category: general
title: 'Scenario 4: Indirect Cross-Content Match'
summary: Tests retrieval when the relevant information is in the caveats field of
  a module, not in its title or summary.
tags:
- scenario
- cross-content
- caveats
- jwt
- retrieval
confidence: high
status: published
created_at: '2026-05-29T11:54:35.775177'
updated_at: '2026-05-29T11:54:35.775178'
---

# 概述

User asks why HS256 tokens are rejected at the gateway. The answer is in the caveats field of jwt-tokens/auth (algorithm confusion), requiring search to index content.overview and Claude to load a module with low-summary match.

# 细节

search_modules must match the term 'HS256' inside content.overview (weight 1). Claude must still load jwt-tokens/auth even though its summary doesn't highlight HS256. Answer should explain algorithm confusion attack.

# 示例

search_modules(query='HS256 reject') likely returns jwt-tokens/auth due to content.overview match. Then load_module and answer citing the algorithm confusion caveat.

# 注意事项

This scenario verifies that search reaches into content.overview, that low-weight matches are surfaced, and that the LLM does not skip the module due to an imperfect summary match.
