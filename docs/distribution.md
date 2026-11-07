# Distribution checklist

GitHub search alone will not create meaningful reach for a new repository. The
useful order is: make the landing page convert, make the install path short,
then distribute the project where MCP and agent users already are.

## Repository metadata

Use the following public description:

> Git-native, reviewable knowledge modules for AI agents via MCP. No vector database required.

Suggested topics:

```text
mcp
mcp-server
ai-agents
claude-code
codex
knowledge-base
knowledge-management
rag
git-native
local-first
deepseek
python
developer-tools
llm
```

The default branch must be the one that contains the tested public surface, README,
and CI workflow. Feature branches should not be the default branch.

## Submission order

Submit to the ecosystem directories before running a broad launch:

- `awesome-mcp-servers`
- `mcp.so`
- `Smithery`
- `Glama`
- `PulseMCP`
- Cline and Continue MCP directories

Then publish a reproducible walkthrough on:

- Hacker News `Show HN`
- Reddit `r/mcp`, `r/ClaudeAI`, and `r/LocalLLaMA`, following each community's
  self-promotion rules
- Dev.to and Hashnode for English readers
- Juejin, Zhihu, V2EX, and Bilibili for Chinese readers

Do not post the same generic announcement everywhere. Each channel should get a
specific angle:

1. "I gave Claude Code a memory that can be reviewed in a pull request."
2. "When a small knowledge base does not need a vector database."
3. "DeepSeek plus MCP: extract a runbook, review it, then let an agent use it."

## Launch assets

- `docs/assets/demo-terminal.svg` is the README demo image.
- `docs/assets/social-preview.png` is the 1280x640 preview to upload in the
  repository settings.
- `km demo ./km-demo` is the reproducible zero-key CTA.

## Measurement

Record the baseline before launch and update it weekly:

| Signal | Initial audit | First-month target |
| --- | ---: | ---: |
| Repository views | 12 in the last 14 days | 1,000-3,000 |
| Unique visitors | 2 in the last 14 days | 300-800 |
| Stars | 1 | 50-150 |
| External referrers | 0 | 3+ |
| External issues or PRs | 0 | 3-5 |
| Demo-to-MCP completion | not measured | 10+ |

Stars are a lagging indicator. Track whether a visitor creates a demo, installs
the tool, and connects an MCP client.

## Do not do

- Do not buy stars or use star-exchange groups.
- Do not mass-message maintainers or post unrelated links.
- Do not claim production readiness, benchmark numbers, or user adoption without
  a reproducible command and a dated evidence record.
