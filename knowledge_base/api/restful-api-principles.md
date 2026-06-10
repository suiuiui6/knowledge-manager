---
id: restful-api-principles
category: api
title: RESTful API Design Principles
summary: We design APIs following REST constraints, requiring stateless communication
  and a uniform interface where resources are identified by URIs and manipulated with
  standard HTTP methods.
tags:
- api
- rest
- stateless
- uniform-interface
confidence: high
status: published
created_at: '2026-06-05T05:05:15.010060+00:00'
updated_at: '2026-06-05T05:05:15.010061+00:00'
---

# 概述

We adhere to REST principles to create scalable, discoverable APIs. Our design mandates that every request is self-contained, and resources are exposed via URIs using standard HTTP verbs.

# 细节

Our APIs are stateless: the server stores no session state, so each request must carry all necessary authentication and context. We use a uniform interface with consistent resource naming (/users, /users/123) and standard method semantics (GET for read, POST for create, PUT for full update, DELETE for removal). This approach simplifies horizontal scaling, caching, and client consumption.

# 示例

GET /users/123 retrieves a specific user resource; POST /users with a JSON body creates a new user.

# 注意事项

Statelessness increases per-request overhead because all state (e.g., pagination cursors, filters) must be sent explicitly; session-based convenience features like 'next page' without a token are not possible.
