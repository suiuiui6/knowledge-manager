---
id: scenario-1-jwt-tokens-direct-hit
category: general
title: 'Scenario 1: JWT Tokens Direct Hit'
summary: Tests retrieval when the query directly matches the module id auth/jwt-tokens.
tags:
- scenario
- jwt
- auth
- direct-hit
- retrieval
confidence: high
status: published
created_at: '2026-05-29T11:54:35.775160'
updated_at: '2026-05-29T11:54:35.775161'
---

# 概述

User asks about JWT token validation at the API gateway and explicitly requests KB check. Claude should retrieve and cite the module covering RS256, JWKS, and kid rotation flow.

# 细节

The module loaded is jwt-tokens/auth from category auth. The answer must include RS256 algorithm, JWKS endpoint, and the kid rotation flow as described in the module body. Tool use: search_modules with a JWT query then load_module.

# 示例

Expected tool sequence: search_modules(query='JWT validation') → load_module('jwt-tokens/auth'). Answer mentions RS256, JWKS, kid rotation.

# 注意事项

No other modules should be consulted. Answer must be based on the loaded module content, not general knowledge.
