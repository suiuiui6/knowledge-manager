---
id: connection-pooling
category: database
title: Database Connection Pooling
summary: We maintain a reusable pool of database connections with specific configuration
  parameters to reduce overhead and improve performance.
tags:
- connection-pooling
- performance
confidence: high
status: published
created_at: '2026-06-05T05:07:45.329142+00:00'
updated_at: '2026-06-05T05:07:45.329145+00:00'
---

# 概述

We use connection pooling to avoid opening a new connection per request, instead borrowing from a pre-warmed pool of 10–20 connections with lifecycle limits.

# 细节

We configure a pool size of 10–20 for typical workloads, a maximum connection lifetime of 30 minutes to recycle stale connections, and a connection timeout of 5 seconds to fail fast when no connection is available. This fixed pool size balances predictable resource usage and request concurrency, avoiding the overhead of dynamic scaling. We enforce these limits at the application layer via the database driver or ORM.

# 示例

Configuration in SQLAlchemy:
engine = create_engine(
    url,
    pool_size=10,
    max_overflow=10,
    pool_timeout=5,
    pool_recycle=1800
)

# 参考

Transaction Management

# 注意事项

Setting pool size too high can exhaust database connection limits; too low causes request queuing. Monitor pool usage and tune based on workload concurrency and database capacity.
