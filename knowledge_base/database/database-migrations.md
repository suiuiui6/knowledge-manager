---
id: database-migrations
category: database
title: Database Migrations
summary: We version-control schema changes using incremental, reversible migrations
  tested on staging before production deployment.
tags:
- migrations
- schema
- version-control
confidence: high
status: published
created_at: '2026-06-05T05:07:45.329156+00:00'
updated_at: '2026-06-05T05:07:45.329156+00:00'
---

# 概述

We treat database schemas as code, applying changes through versioned, incremental migration scripts that can be rolled back safely.

# 细节

We require every migration to have both upgrade and downgrade instructions so that changes are reversible. Migrations are run against a staging environment that mirrors production before going live, catching schema issues and data loss risks. We use migration tools like Alembic or Flyway to enforce version order, and we never modify an already-applied migration — new changes always become a new migration file. This ensures everyone can reproduce the exact schema state from any point in time.

# 示例

Alembic migration for adding an email column:

def upgrade():
    op.add_column('users', sa.Column('email', sa.String(), nullable=True))

def downgrade():
    op.drop_column('users', 'email')

# 参考

Query Optimization

# 注意事项

An irreversible migration prevents safe rollback. Modifying a migration that has already been applied will break synchronisation across environments. Always test downgrade paths on staging before relying on them in production.
