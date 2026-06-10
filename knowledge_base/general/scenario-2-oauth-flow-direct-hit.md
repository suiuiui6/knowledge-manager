---
id: scenario-2-oauth-flow-direct-hit
category: general
title: 'Scenario 2: OAuth Flow Direct Hit'
summary: Tests retrieval for the OAuth 2.0 server-side callback flow using the knowledge
  base.
tags:
- scenario
- oauth
- auth
- direct-hit
- retrieval
confidence: high
status: published
created_at: '2026-05-29T11:54:35.775167'
updated_at: '2026-05-29T11:54:35.775167'
---

# 概述

The user question targets the OAuth flow module; Claude must load oauth-flow/auth and answer with its content.

# 细节

User message: 'What's our OAuth 2.0 server-side callback flow? Use the knowledge base.' Pass criteria: load_module('oauth-flow/auth'), answer uses the module's content.

# 示例

load_module call with oauth-flow/auth, response describes the flow steps from the module.

# 注意事项

Ensure answer is not from general OAuth knowledge but specifically from the stored module.
