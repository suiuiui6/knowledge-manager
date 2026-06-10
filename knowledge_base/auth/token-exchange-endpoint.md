---
id: token-exchange-endpoint
category: auth
title: Token Exchange for Access Token
summary: We exchange the authorization code for an access token by making a server-to-server
  POST to the provider's token endpoint.
tags:
- oauth2
- token-exchange
- server-to-server
confidence: high
status: published
created_at: '2026-06-05T05:06:32.523028+00:00'
updated_at: '2026-06-05T05:06:32.523029+00:00'
---

# 概述

After receiving the authorization code via redirect, our backend server directly POSTs to the provider's token endpoint with required parameters to obtain tokens.

# 细节

We use the code, client_id, client_secret, redirect_uri, and grant_type=authorization_code. This server-to-server communication ensures client secrets are kept confidential. The response contains access_token and optionally refresh_token, id_token, token_type, expires_in. We store the tokens securely server-side.

# 示例

POST /token HTTP/1.1
Host: oauth2.googleapis.com
Content-Type: application/x-www-form-urlencoded

code=AUTH_CODE&client_id=CLIENT_ID&client_secret=CLIENT_SECRET&redirect_uri=https://our.app/callback&grant_type=authorization_code

Response: { "access_token": "...", "token_type": "Bearer", "expires_in": 3600, "refresh_token": "..." }

# 注意事项

Ensure that redirect_uri exactly matches the one used in the authorization request. Many providers require client_secret for confidential clients. Rate limits may apply.
