---
id: api-rate-limiting
category: api
title: Rate Limiting Implementation
summary: We apply rate limiting with standard response headers and choose algorithms
  like token bucket based on burst-handling requirements to protect the API and ensure
  fair usage.
tags:
- api
- rate-limiting
- headers
confidence: high
status: published
created_at: '2026-06-05T05:05:15.010014+00:00'
updated_at: '2026-06-05T05:05:15.010015+00:00'
---

# 概述

We enforce rate limiting on our APIs to guard against abuse and guarantee equitable access. The implementation exposes standard headers and selects an algorithm that fits burst tolerance needs.

# 细节

We evaluate token bucket, fixed window, and sliding window log algorithms. Token bucket is preferred when we need to allow bursts while maintaining an average rate; fixed window is simpler but can suffer from boundary double-spend issues. Whichever algorithm is used, our responses always include X-RateLimit-Limit, X-RateLimit-Remaining, and X-RateLimit-Reset headers so clients can adapt their request pacing.

# 示例

Response header example: X-RateLimit-Limit: 100, X-RateLimit-Remaining: 45, X-RateLimit-Reset: 1620000000.

# 注意事项

Fixed window counters are susceptible to boundary problems where clients send requests at the edge of two windows; choose token bucket or sliding logs when this is unacceptable.
