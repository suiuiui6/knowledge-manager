---
id: scenario-3-connection-pool-direct-hit
category: general
title: 'Scenario 3: Connection Pool Direct Hit'
summary: Tests retrieval of Postgres connection pool sizing guidance from the database/connection-pool
  module.
tags:
- scenario
- database
- connection-pool
- direct-hit
confidence: high
status: published
created_at: '2026-05-29T11:54:35.775172'
updated_at: '2026-05-29T11:54:35.775173'
---

# 概述

User asks about sizing the Postgres connection pool. Claude must load connection-pool/database and cite the 'small number of busy connections' guidance.

# 细节

Pass criteria: loads the module and specifically references the advice that a small number of busy connections is better.

# 示例

load_module('connection-pool/database') → answer includes 'small number of busy connections'.
