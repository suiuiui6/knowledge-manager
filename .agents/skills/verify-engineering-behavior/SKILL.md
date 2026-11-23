---
name: verify-engineering-behavior
description: Drive knowledge-manager CLI review retry, module index updates and ingestion recovery after editing module, review or job behavior.
---

# Verify engineering behavior

## Launch

From the repository root install the locked environment with `poetry install --no-interaction`. Each invocation uses isolated temporary KB directories, so no persistent service or shared user KB is required. Use the supported interpreter from that environment. A usable instance completes `km init`, then publishes and searches the fixture.

## Doctor

Run `poetry run km --version` and `poetry check --lock`. If startup fails, preserve the error and fix the environment before driving behavior. Do not drive a user's existing KB.

## Drive

```text
poetry run python scripts/verify_engineering_behavior.py --output-dir test-results/engineering-behavior
```

The helper launches real CLI processes, approves a staged fixture, retries the approval and searches the published module. It verifies disk state and graph preservation through real storage operations, then runs the existing ingestion recovery drill. That drill injects extraction failure/success at the provider boundary and exercises the real worker, persisted job, input recovery and staging APIs. It is not evidence of external provider connectivity.

For actual HTTP and MCP consumers, also run `poetry run pytest -q tests/test_http_server.py tests/test_mcp_server.py tests/test_cli.py`; raw stdio protocol behavior is exercised by existing MCP tests. Task concurrency coverage additionally requires `tests/test_reliability.py` and `tests/test_worker_service.py`.

## Evidence

`report.json` records every command, exit code, stdout/stderr and observed results. `published-module.json`, `index.json` and `recovery.json` preserve side effects. Nonzero commands, missing fixtures or failed assertions fail the run. Record HEAD plus actual working diff separately; an uncommitted snapshot is not equivalent to HEAD. The feature map defines coverage and limitations.

## Cleanup

Only subprocesses started by the helper are run; they are synchronous CLI invocations. Temporary KBs are removed on success and failure. Never kill by process name or delete output-dir evidence. Confirm evidence remains after teardown. Reuse or choose a new output directory intentionally; do not overwrite evidence from a different candidate unnoticed.

## Helpers

`scripts/verify_engineering_behavior.py` is the executable helper above. Use `$maintain-verification-skill` when commands, drive paths or expected behavior change.
