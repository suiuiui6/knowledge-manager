# Claude Code with a reviewable knowledge base

This walkthrough connects the demo knowledge base to Claude Code over MCP. It
does not require an API key because no extraction call is made.

## 1. Install and seed the demo

```bash
uv tool install git+https://github.com/suiuiui6/knowledge-manager.git
km demo ./km-demo
```

The demo contains four approved modules and one staged draft. The approved
modules are:

- `agent-workflows/reviewed-context`
- `agent-workflows/rollback-deployment`
- `mcp/retrieval-tools`
- `search/keyword-first`

## 2. Register the MCP server

Use an absolute path so the client does not depend on its working directory:

```bash
km --kb-path ./km-demo connect claude-code
```

The connector merges a `knowledge-manager` entry into
`~/.claude/mcp.json`. To preview the entry without writing it:

```bash
km --kb-path ./km-demo connect claude-code --print
```

If your client uses a JSON configuration instead, the expected shape is:

```json
{
  "mcpServers": {
    "knowledge-manager": {
      "command": "km",
      "args": ["--kb-path", "/absolute/path/to/km-demo", "serve"]
    }
  }
}
```

Restart the client after changing its MCP configuration.

## 3. Ask a scoped question

Use a prompt that forces discovery before loading:

```text
Use knowledge-manager to find the deployment rollback procedure.
Search first, then load only the matching module and summarize the first
three steps.
```

The expected path is:

1. The client reads the `knowledge://index` resource.
2. It calls `search_modules` with a query such as `rollback deployment`.
3. It calls `load_module` for `rollback-deployment` in `agent-workflows`.
4. It answers from that module instead of loading the whole knowledge base.

## 4. Verify the review boundary

Run the CLI directly and compare the index with the staging directory:

```bash
km --kb-path ./km-demo list
km --kb-path ./km-demo review
```

The staged draft is not part of the searchable index until you approve it. That
is the intended difference between a draft and shared context.

## Limits

This walkthrough verifies the local stdio MCP path. It does not verify hosted
multi-tenant deployment, authentication, or high-scale semantic retrieval.
