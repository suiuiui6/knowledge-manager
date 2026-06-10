---
id: user-authorization-consent
category: auth
title: User Authorization Consent Flow
summary: We rely on the provider's consent screen where users explicitly approve requested
  scopes before granting access.
tags:
- oauth2
- consent
- scopes
confidence: high
status: published
created_at: '2026-06-05T05:06:32.523040+00:00'
updated_at: '2026-06-05T05:06:32.523041+00:00'
---

# 概述

We present the user with the provider's consent screen by redirecting them to the authorization endpoint. The user must explicitly allow the requested permissions for our application to proceed.

# 细节

The authorization request includes scope parameters that define the extent of access (e.g., openid, profile, email). The provider's UI shows these scopes and requires user interaction. We do not implement our own consent screen; we rely on the provider's standardized one.

# 示例

Redirect to Google: user sees list of data our app requests (basic profile, email) with Allow/Deny buttons. User selects Allow, then the flow continues.

# 注意事项

Be transparent about the scopes requested; asking for excessive scopes may lead users to deny consent. The order of parameters in the authorize URL must follow provider's specification.
