# V1 Remaining Tasks Status

Date: 2026-06-11

This note lists what is still unfinished for `docs/superpowers/plans/2026-06-11-v1-enterprise-ingestion-provenance-eval.md`.

## Current status

### Done
- Task 1: provenance metadata on modules
- Task 2: source registry schemas + persistence helpers

### In progress
- Task 2 final code-quality tail
  - `update_source_sync()` still replaces the entire `sync` object.
  - This can wipe existing `last_cursor`, `last_synced_at`, and `page_versions` if a caller only wants to update one field.
  - This is the only known remaining issue before Task 2 can be considered fully closed.

## Remaining tasks

### 1. Close Task 2 completely
- Fix `update_source_sync()` so partial sync updates do not destroy existing sync state.
- Add/adjust regression tests for partial sync updates.
- Re-run `tests/test_source_ingestion.py`.

### 2. Task 3 — Confluence connector
- Create `src/knowledge_manager/confluence.py`
- Add `tests/test_confluence.py`
- Implement read-only page listing + normalization

### 3. Task 4 — Source ingestion orchestration
- Extend `src/knowledge_manager/source_ingestion.py`
- Add ingestion summary, provenance stamping, and stale marking
- Add tests for staged module provenance and stale-source invalidation

### 4. Task 5 — Source CLI
- Modify `src/knowledge_manager/cli.py`
- Extend `tests/test_cli.py`
- Add:
  - `source add-confluence`
  - `source pull`
  - `source status`

### 5. Task 6 — Eval runner
- Create `src/knowledge_manager/eval_runner.py`
- Create `tests/test_eval_runner.py`
- Modify `src/knowledge_manager/cli.py`
- Add `eval run`

### 6. Task 7 — Final verification sweep
- Run the focused V1 test suite
- Run one CLI smoke flow
- Verify runtime artifacts such as:
  - `<kb>/.sources/registry.json`
  - `<kb>/.staging/*.json`
  - `<kb>/.staging/*.meta.json`

## Summary

If counting by plan tasks:
- Fully done: 2
- Partially done / still open: 1 (Task 2 tail)
- Not started: 5 (Tasks 3-7)

So there are **6 unfinished items remaining**:
1. Task 2 tail fix
2. Task 3
3. Task 4
4. Task 5
5. Task 6
6. Task 7
