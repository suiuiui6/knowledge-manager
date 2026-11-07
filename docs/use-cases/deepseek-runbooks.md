# Extract a runbook with DeepSeek, then review it

This walkthrough uses a provider for the extraction step. The review, search,
and MCP steps remain local.

## 1. Initialize a knowledge base

```bash
km init ./my-kb
```

## 2. Configure the provider

Prefer an environment variable over writing a key into a file:

```bash
export DEEPSEEK_API_KEY="<your-key>"
```

PowerShell:

```powershell
$env:DEEPSEEK_API_KEY = "<your-key>"
```

The generated `config.json` is ignored by Git. Do not commit a real key.

## 3. Add a runbook

Create a small note:

```markdown
# Release rollback

If a release doubles the error rate, stop the rollout, revert to the last known
good version, verify the health check, and record the incident timeline.
```

Then extract it:

```bash
km --kb-path ./my-kb add notes.md -c operations
```

The provider returns draft modules in `.staging/`. No draft is published
automatically.

## 4. Review and publish

```bash
km --kb-path ./my-kb review
```

For each draft:

- `a` approves it and moves it into the knowledge base.
- `r` rejects it.
- `s` leaves it staged for later.

After approval, rebuild and search:

```bash
km --kb-path ./my-kb rebuild
km --kb-path ./my-kb search "release rollback"
```

The approved module is now available through the same MCP surface as the demo.

## What this verifies

- The CLI can initialize a knowledge base without a provider key.
- Extraction writes to staging instead of publishing directly.
- Review is a real checkpoint, not a documentation-only claim.
- Search sees approved modules only.

Live provider behavior depends on the provider account, model, and network. The
public CI does not run live provider calls.
