---
id: access-token-presentation
category: auth
title: API Access Token Usage
summary: We pass the access token in the Authorization header as a Bearer token for
  all protected API requests.
tags:
- api
- access-token
- bearer
confidence: high
status: published
created_at: '2026-06-05T05:06:32.523022+00:00'
updated_at: '2026-06-05T05:06:32.523022+00:00'
---

# 概述

When making requests to our resource server on behalf of the user, the client includes the access token as a Bearer token in the HTTP Authorization header. The resource server validates the token before returning the requested data.

# 细节

We follow the RFC 6750 Bearer Token Usage. The token is obtained from the authorization server after the code exchange. The client adds header: Authorization: Bearer <access_token>. This approach keeps tokens out of URLs and request bodies, reducing exposure in logs.

# 示例

GET /api/userinfo HTTP/1.1
Host: api.example.com
Authorization: Bearer ya29.a0AfH6S...

The server validates the token's signature, expiry, and scopes before responding.

# 注意事项

Protect the token in transit with TLS. Token must not be exposed to client-side JavaScript; keep it server-side or in secure storage.
