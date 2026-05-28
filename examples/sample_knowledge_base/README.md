# Sample Knowledge Base

A small example KB with three modules across two categories. Copy this directory as a starting point:

```bash
cp -r examples/sample_knowledge_base ./my_kb
km --kb-path ./my_kb stats
km --kb-path ./my_kb list
km --kb-path ./my_kb search "oauth"
km --kb-path ./my_kb serve   # expose via MCP
```

## What's included

- `auth/oauth-flow.json` — OAuth 2.0 authorization code flow
- `auth/jwt-tokens.json` — JWT signing and validation
- `database/connection-pool.json` — Connection pooling guidance
- `index.json` — auto-generated index over the above
- `config.json` — example provider config (no real API key)

You can rebuild the index any time after editing modules:

```bash
km --kb-path ./my_kb rebuild
```
