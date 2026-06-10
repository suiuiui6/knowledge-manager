---
id: query-optimization
category: database
title: Query Optimization
summary: We optimize SQL queries by leveraging indexes, avoiding SELECT *, using EXPLAIN,
  and batching operations.
tags:
- sql
- performance
- indexes
confidence: high
status: published
created_at: '2026-06-05T05:07:45.329163+00:00'
updated_at: '2026-06-05T05:07:45.329163+00:00'
---

# 概述

We analyze query execution with EXPLAIN, add indexes on high‑usage columns, avoid fetching unnecessary data, and batch writes to reduce round‑trips.

# 细节

We use the database’s EXPLAIN (or EXPLAIN ANALYZE) to inspect query plans and confirm that indexes are used appropriately. We never use SELECT * in production code to minimise bandwidth and enable index‑only scans. For multiple inserts, updates, or deletes, we batch them into a single statement or use bulk APIs. We weigh the trade‑off that indexes speed up reads at the cost of write performance and storage, so we only add indexes that match frequent query patterns.

# 示例

Analyzing a query:
EXPLAIN ANALYZE SELECT id FROM orders WHERE customer_id = 123;

Adding a supporting index:
CREATE INDEX idx_orders_customer_id ON orders(customer_id);

Batching inserts:
INSERT INTO logs (event, timestamp) VALUES (…), (…), (…);

# 参考

Connection Pooling, Transaction Management

# 注意事项

Indexes incur write overhead; over‑indexing can degrade insert/update throughput. EXPLAIN plans depend on current statistics; keep statistics updated. Avoid introducing full‑table scans under production load.
