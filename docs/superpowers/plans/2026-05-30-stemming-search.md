# Verbose Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `--verbose` CLI mode that exposes useful debug-level progress logs while keeping normal runs quiet and avoiding sensitive payload leakage.

**Architecture:** Wire the existing `--verbose/-v` flag in `cli.py` into a consistent logging policy across `cli.py`, `extractor.py`, and `llm_clients.py`. In verbose mode, log high-level progress and sizes/counts; in non-verbose mode, keep the default warning-only output. Do not log raw prompts, raw file contents, or full LLM responses.

**Tech Stack:** Python 3.10+, `logging`, `click`, `pytest`.

---

## Background — read before starting

The repository already has a global `--verbose/-v` option in [src/knowledge_manager/cli.py](D:/tyh/knowledge-manager/src/knowledge_manager/cli.py:64), but the logging behavior is incomplete and inconsistent:

1. `cli.py` configures root logging with `logging.basicConfig(...)`, but only the `add` command actually emits operational logs.
2. `llm_clients.py` logs DeepSeek request metadata and logs full HTTP error bodies, but Claude/OpenAI paths emit no equivalent progress logs.
3. The current debug output is not tested, and there is no guard against accidentally logging full prompt/response bodies during extraction.
4. Existing CLI tests in [tests/test_cli.py](D:/tyh/knowledge-manager/tests/test_cli.py:46) do not cover `--verbose`, and client tests in [tests/test_llm.py](D:/tyh/knowledge-manager/tests/test_llm.py:34) assert request shape only.

The implementation should make verbose mode genuinely useful for `km add` while keeping the logging surface intentionally small and safe.

## File Structure

| File | Change | Responsibility |
|------|--------|----------------|
| `src/knowledge_manager/cli.py` | Modify | Centralize logging setup and make CLI-side progress logs intentional and testable |
| `src/knowledge_manager/extractor.py` | Modify | Add extraction progress logs (chunk count, per-chunk progress, parse counts) without logging content |
| `src/knowledge_manager/llm_clients.py` | Modify | Normalize provider logging, redact sensitive request/response data, keep error logs concise |
| `tests/test_cli.py` | Modify | Add `CliRunner` tests for quiet vs verbose behavior on `km add` |
| `tests/test_llm.py` | Modify | Add `caplog` tests that verify useful metadata logs and absence of raw content leakage |
| `README.md` | Modify | Document `--verbose` as a debugging aid for extraction |

No new files are needed.

---

### Task 1: Make verbose mode deterministic at the CLI boundary

**Files:**
- Modify: `src/knowledge_manager/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing CLI tests first**

Append tests to `tests/test_cli.py` that exercise the `add` command with and without `--verbose`. Reuse the existing `initialized_kb`, `cli_runner`, and patched extractor/client pattern from `test_cli_add_extracts_to_staging`.

Add two tests:

```python
def test_cli_add_is_quiet_without_verbose(cli_runner, initialized_kb, tmp_path, caplog):
    src_file = tmp_path / "notes.txt"
    src_file.write_text("Some notes about JWT authentication.")

    sample = make_module("auth-jwt", "auth")

    async def fake_extract(self, text, category):
        return [sample]

    caplog.set_level(logging.DEBUG)
    with patch("knowledge_manager.cli.Extractor.extract", new=fake_extract):
        with patch("knowledge_manager.cli.create_client") as mock_create:
            mock_create.return_value = AsyncMock()
            result = cli_runner.invoke(
                cli,
                ["--kb-path", str(initialized_kb), "add", str(src_file), "-c", "auth"],
            )

    assert result.exit_code == 0, result.output
    assert "Reading file:" not in caplog.text
    assert "Extracting modules" not in caplog.text


def test_cli_add_logs_progress_with_verbose(cli_runner, initialized_kb, tmp_path, caplog):
    src_file = tmp_path / "notes.txt"
    src_file.write_text("Some notes about JWT authentication.")

    sample = make_module("auth-jwt", "auth")

    async def fake_extract(self, text, category):
        return [sample]

    caplog.set_level(logging.DEBUG)
    with patch("knowledge_manager.cli.Extractor.extract", new=fake_extract):
        with patch("knowledge_manager.cli.create_client") as mock_create:
            mock_create.return_value = AsyncMock()
            result = cli_runner.invoke(
                cli,
                ["--verbose", "--kb-path", str(initialized_kb), "add", str(src_file), "-c", "auth"],
            )

    assert result.exit_code == 0, result.output
    assert "Verbose logging enabled" in caplog.text
    assert "Reading file:" in caplog.text
    assert "Extracting modules" in caplog.text
    assert "Saving module: auth-jwt" in caplog.text
```

These should fail initially if the root logger/caplog interplay is inconsistent.

- [ ] **Step 2: Refine CLI logging setup**

Update `cli.py` so verbose logging is predictable in tests and at runtime:

1. Keep the existing `--verbose/-v` flag.
2. Replace the current unconditional `logging.basicConfig(...)` calls with a helper such as `_configure_logging(verbose: bool) -> None`.
3. In that helper, explicitly set the `knowledge_manager` logger level to `DEBUG` when verbose and `WARNING` otherwise.
4. Only attach a stream handler if the logger has no handlers yet, so repeated `CliRunner.invoke(...)` calls do not duplicate output.
5. Use a formatter like the current `%(asctime)s [%(levelname)s] %(name)s: %(message)s` for verbose mode.
6. Set `logger.propagate = True` so `caplog` can still see records.

A concrete shape that fits this repo:

```python
def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    root = logging.getLogger()
    root.setLevel(level)

    package_logger = logging.getLogger("knowledge_manager")
    package_logger.setLevel(level)
    package_logger.propagate = True

    if verbose and not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        root.addHandler(handler)
```

Then call `_configure_logging(verbose)` from the `cli(...)` group callback and keep `logger.debug("Verbose logging enabled")`.

- [ ] **Step 3: Keep CLI-side logs operational, not content-bearing**

Retain the existing progress logs in `add(...)`, but tighten them to metadata only:

1. Keep `Reading file: {file}` and `File size: {len(text)} characters`.
2. Keep provider/model logging.
3. Keep module-count and per-module ID logging.
4. Do not add any log line that includes the raw source text.

- [ ] **Step 4: Run the CLI logging tests**

Run:

```bash
poetry run pytest tests/test_cli.py -k "verbose or quiet_without_verbose" -v
```

Expected: both tests PASS.

---

### Task 2: Add extractor and provider logs with strict redaction

**Files:**
- Modify: `src/knowledge_manager/extractor.py`
- Modify: `src/knowledge_manager/llm_clients.py`
- Test: `tests/test_llm.py`

- [ ] **Step 1: Inspect current extractor flow before editing**

Read [src/knowledge_manager/extractor.py](D:/tyh/knowledge-manager/src/knowledge_manager/extractor.py) fully and identify the exact points where these logs should go:

1. Before chunking/extraction starts.
2. After chunking decides how many chunks will be processed.
3. Before each LLM completion call.
4. After parsing each chunk response.
5. After global dedupe/capping returns the final module count.

The intent is to log counts and progress only.

- [ ] **Step 2: Add extractor progress logs**

In `extractor.py`, add a module logger (`logging.getLogger(__name__)`) if one does not exist and add `debug`/`info` logs with data like:

- `Starting extraction for category=%s`.
- `Prepared %d chunk(s) for extraction`.
- `Processing chunk %d/%d (%d chars)`.
- `Parsed %d candidate module(s) from chunk %d`.
- `Returning %d module(s) after dedupe/cap`.

Do not log:

- raw chunk text,
- full prompt text,
- raw JSON returned by the LLM,
- full module bodies.

If invalid JSON is encountered and the extractor already swallows it, the log should mention the parse failure at debug or warning level without echoing the malformed payload.

- [ ] **Step 3: Normalize client logging across providers**

Refactor `llm_clients.py` so DeepSeek, Claude, and OpenAI all emit the same safe metadata logs:

1. Before the request: provider name, destination URL/host, model, prompt length, `max_tokens`, and `temperature` if applicable.
2. After a successful response: returned text length only.
3. On HTTP errors: status code and a short, redacted body summary.
4. On non-HTTP exceptions: exception type/message only.

Implement a tiny helper for redaction/truncation instead of repeating ad hoc formatting. Example:

```python
def _summarize_error_body(text: str, limit: int = 200) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "..."
```

Use that helper only for error bodies. Do not log success response bodies at all.

- [ ] **Step 4: Add log-safety tests with `caplog`**

Append tests to `tests/test_llm.py`.

Test A: DeepSeek success logs metadata but not prompt/response bodies.

```python
@pytest.mark.asyncio
async def test_deepseek_verbose_logs_are_metadata_only(caplog):
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_OPENAI_RESPONSE
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        caplog.set_level(logging.DEBUG)
        client = DeepSeekClient(make_deepseek_config())
        result = await client.complete("secret prompt body")

    assert result == "hello"
    assert "DeepSeek API call" in caplog.text
    assert "secret prompt body" not in caplog.text
    assert "hello" not in caplog.text
```

Test B: HTTP error logging is truncated and does not dump arbitrarily large bodies.

Use a mocked `httpx.HTTPStatusError` with a long response body and assert:

- the status code is present,
- the first part of the body summary is present,
- the full oversized tail is not.

If you add a shared helper, test the observable logging behavior rather than the helper in isolation.

- [ ] **Step 5: Run the client logging tests**

Run:

```bash
poetry run pytest tests/test_llm.py -k "logs or error" -v
```

Expected: new log-focused tests PASS, existing client tests still PASS.

---

### Task 3: Document and verify the end-to-end verbose experience

**Files:**
- Modify: `README.md`
- Verify: `tests/`

- [ ] **Step 1: Add a brief README note**

Update [README.md](D:/tyh/knowledge-manager/README.md) in the CLI usage area or feature list to mention that `km add --verbose` prints extraction progress for debugging. Keep it short; one bullet or one sentence is enough. Example wording:

```markdown
- `km add --verbose` shows extraction progress, provider/model selection, and staging activity for debugging.
```

Do not promise raw prompt/response logging.

- [ ] **Step 2: Run the focused regression set**

Run:

```bash
poetry run pytest tests/test_cli.py tests/test_llm.py -v
```

Expected: CLI and LLM logging tests PASS together.

- [ ] **Step 3: Run the full suite**

Run:

```bash
poetry run pytest -q
```

Expected: no regressions outside logging-related code.

- [ ] **Step 4: Manual smoke test**

Run a real command against a disposable or existing KB and confirm the UX manually:

```bash
poetry run km --verbose --kb-path ../knowledge_base add <some-text-file> -c general
```

Check that:

1. normal command output still reports extracted module count,
2. verbose logs appear on stderr/stdout in the terminal,
3. logs mention progress and counts,
4. logs do not print raw file contents or raw model output.

If no suitable input file is available, skip this step and state that only automated verification was performed.

---

## Self-Review

**Spec coverage:** The request is specifically about “verbose logging”. This plan covers the CLI flag behavior, extraction-path observability, provider/client logging, and explicit tests for the no-leakage requirement.

**Security boundary:** The plan deliberately treats prompt text, source file contents, LLM response bodies, and oversized error payloads as sensitive/high-noise. Logs are limited to metadata, counts, IDs, and truncated error summaries.

**Testability:** The plan uses `caplog` for log assertions and `CliRunner` for end-to-end CLI coverage, so the behavior is pinned down instead of hand-checked.

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-30-stemming-search.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**