---
id: authorization-code-receipt
category: auth
title: Authorization Code Return Handling
summary: We receive the temporary authorization code appended to the redirect URI
  after user consent.
tags:
- oauth2
- callback
- authorization-code
confidence: high
status: published
created_at: '2026-06-05T05:06:32.523035+00:00'
updated_at: '2026-06-05T05:06:32.523036+00:00'
---

# 概述

The provider redirects the user agent back to our registered redirect URI with a code query parameter. We extract this short-lived code securely for token exchange.

# 细节

The redirect URI is called by the browser. Our endpoint (e.g., /callback) reads the code parameter from the query string. We also verify the state parameter to prevent CSRF attacks. The code is only used once, in a back-channel request, and should be discarded after exchange.

# 示例

Example redirect: https://our.app/callback?code=SplxlOBeZQQYbYS6WxSbIA&state=xyz123. Our handler gets 'code' from req.query.code, validates state matches session-stored state, then proceeds to token exchange.

# 注意事项

If state validation fails, abort the flow. The code is a single-use token; replay attacks are mitigated by immediate exchange.
