# Large Document Extraction Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `km add` reliably extract useful modules from long specs and reports without regressing the current small-document workflow.

**Architecture:** Keep the existing extractor pipeline in [src/knowledge_manager/extractor.py](D:/tyh/knowledge-manager/src/knowledge_manager/extractor.py:58), but strengthen the weak points that still hurt large documents: naive character slicing, chunk prompts that lack context, and a global cap that can let early chunks starve later sections. This is an incremental improvement to the current one-pass chunked extraction path, not a rewrite to full RAG or a new storage model.

**Tech Stack:** Python 3.10+, `httpx`, `pydantic`, `click`, `pytest`.

---

## Background - read before starting

The strongest evidence for this task is the large-document testing report in [test-results/scalability.md](D:/tyh/knowledge-manager/test-results/scalability.md:378):

1. The report marks large document extraction as a high-severity issue: current behavior fails on comprehensive specs/reports and is called out as the top scalability bottleneck.
2. The report recommends chunking or multi-pass extraction, but the repo has already moved partway there: [src/knowledge_manager/extractor.py](D:/tyh/knowledge-manager/src/knowledge_manager/extractor.py:44) now includes `_chunk_text(...)`, and the LLM clients already use a 60 second timeout in [src/knowledge_manager/llm_clients.py](D:/tyh/knowledge-manager/src/knowledge_manager/llm_clients.py:33) and [src/knowledge_manager/llm_clients.py](D:/tyh/knowledge-manager/src/knowledge_manager/llm_clients.py:61).
3. That means the remaining gap is not "add chunking from scratch." The real issue is extraction quality and coverage on long documents:
   - chunks are still split on raw character count rather than document boundaries,
   - the prompt does not tell the LLM where the chunk sits in the larger document,
   - [Extractor.extract](D:/tyh/knowledge-manager/src/knowledge_manager/extractor.py:78) enforces the global module cap while walking chunks in order, so early chunks can consume the whole budget before later sections are seen.
4. Configuration already exposes `chunk_size`, `chunk_overlap`, and `max_modules_per_extraction` in [src/knowledge_manager/schemas.py](D:/tyh/knowledge-manager/src/knowledge_manager/schemas.py:122), and `km add` already routes through the extractor in [src/knowledge_manager/cli.py](D:/tyh/knowledge-manager/src/knowledge_manager/cli.py:322). The implementation should build on those hooks rather than inventing a second ingestion path.

The plan below is therefore scoped to making the current chunked extractor good enough for long-form design docs, not to building a full outline-first system unless the improved one-pass path still fails validation.

## File Structure

| File | Change | Responsibility |
|------|--------|----------------|
| `src/knowledge_manager/extractor.py` | Modify | Improve chunking, chunk prompt context, and cross-chunk aggregation |
| `src/knowledge_manager/schemas.py` | Optional modify | Only if a new extraction tuning field is truly needed |
| `tests/test_llm.py` | Modify | Add extractor-focused tests for boundary-aware chunking and fair aggregation |
| `tests/test_integration.py` | Modify | Add end-to-end coverage for a large synthetic source document |
| `README.md` | Optional modify | Document any user-visible extraction behavior or config changes |

No new runtime modules should be added unless the extractor becomes unmanageably complex. Keep the work inside the existing ingestion path.

---

### Task 1: Replace naive character slicing with boundary-aware chunk preparation

**Files:**
- Modify: `src/knowledge_manager/extractor.py`
- Test: `tests/test_llm.py`

- [ ] **Step 1: Write splitter tests first**

Add unit tests around `_chunk_text(...)` in [tests/test_llm.py](D:/tyh/knowledge-manager/tests/test_llm.py:221) that capture the behavior we actually want for long documentation:

1. Prefer splitting at section boundaries when the text contains Markdown headings.
2. Otherwise prefer paragraph boundaries (`\n\n`) before falling back to raw character slicing.
3. Preserve the existing overlap behavior when a hard split is unavoidable.
4. Keep the current small-text behavior unchanged.

Use synthetic Markdown-like text rather than fixtures so the tests stay focused on chunking behavior.

- [ ] **Step 2: Refactor `_chunk_text(...)` into a boundary-aware splitter**

Update [src/knowledge_manager/extractor.py](D:/tyh/knowledge-manager/src/knowledge_manager/extractor.py:44) so chunking tries increasingly weaker boundaries in this order:

1. Markdown headings such as `#`, `##`, `###`.
2. Blank-line paragraph breaks.
3. Sentence/newline boundaries near the chunk edge.
4. Raw character slicing as the final fallback.

Implementation constraints:

1. Keep the public helper name `_chunk_text(...)` so existing tests and call sites remain simple.
2. Keep `chunk_size` and `chunk_overlap` semantics intact.
3. Do not introduce tokenization dependencies; stay character-based for now.
4. Do not produce empty chunks.

The point is not perfect semantic segmentation. The point is to stop cutting specs mid-heading or mid-paragraph whenever an obvious boundary exists.

- [ ] **Step 3: Keep logs aligned with the stronger splitter**

Update extractor logs in [src/knowledge_manager/extractor.py](D:/tyh/knowledge-manager/src/knowledge_manager/extractor.py:66) so verbose runs can show how many chunks were prepared and, if useful, whether fallback splitting was needed. Keep this metadata-only and avoid logging chunk bodies.

- [ ] **Step 4: Run the chunking unit tests**

Run:

```bash
poetry run pytest tests/test_llm.py -k "chunk_text" -v
```

Expected: existing chunk tests still pass, and the new boundary-aware tests pass.

---

### Task 2: Make chunk extraction context-aware and fair across the whole document

**Files:**
- Modify: `src/knowledge_manager/extractor.py`
- Test: `tests/test_llm.py`

- [ ] **Step 1: Add tests that expose current coverage bias**

Append extractor tests that fail under the current implementation:

1. A multi-chunk document where each chunk returns distinct modules, but later chunks should still contribute when `max_modules_per_extraction` is smaller than the total candidate count.
2. A case where the first chunk returns many modules and the last chunk returns a critical distinct module; the final output should not always be only the earliest chunk’s modules.
3. A case where chunk prompts need chunk position metadata, asserted by inspecting the prompt passed to the mocked LLM.

The current `test_extractor_global_cap_across_chunks` in [tests/test_llm.py](D:/tyh/knowledge-manager/tests/test_llm.py:281) encodes the existing early-chunk bias. Replace that expectation with the desired fair-coverage behavior instead of preserving a bad invariant.

- [ ] **Step 2: Enrich the extraction prompt with chunk context**

Modify `EXTRACTION_PROMPT` and `_extract_chunk(...)` in [src/knowledge_manager/extractor.py](D:/tyh/knowledge-manager/src/knowledge_manager/extractor.py:11) so each chunked request includes:

1. `Chunk: X of Y` metadata.
2. A short instruction that this is only part of a larger document.
3. A request to extract only concepts grounded in the current chunk.
4. A request to keep module IDs/title choices stable and specific, not generic placeholders.

Do not add unrelated schema changes here. This prompt change is about reducing duplicate or contextless modules, not about broadening the module format.

- [ ] **Step 3: Stop letting early chunks consume the entire global budget**

Refactor [Extractor.extract](D:/tyh/knowledge-manager/src/knowledge_manager/extractor.py:63) so cross-chunk aggregation is document-wide and deterministic:

1. Process all prepared chunks unless an individual LLM call fails.
2. Collect chunk-local module lists first instead of trimming the final answer while still iterating.
3. Dedupe by module ID across chunks.
4. Apply the global `max_modules_per_extraction` only after all chunk candidates are collected.
5. Select the final modules using a simple fair strategy, such as round-robin across chunk result lists, so later sections have a chance to surface.

This is the most important behavioral change in the plan. Without it, large specs remain biased toward the first few sections even if chunking itself improves.

- [ ] **Step 4: Add a small per-chunk candidate budget if needed**

If processing all chunks with the full global cap per chunk produces too many noisy candidates, add an internal per-chunk cap derived from document size, for example a small oversampling budget rather than the full global cap. If you do this:

1. Keep it internal to the extractor first; do not add CLI surface area unless tests show it needs tuning.
2. Document the derivation in code with one short comment if the formula is non-obvious.
3. Keep the final user-visible cap governed only by `max_modules_per_extraction`.

This step is optional because fair final aggregation may already be enough.

- [ ] **Step 5: Run targeted extractor tests**

Run:

```bash
poetry run pytest tests/test_llm.py -k "extractor and chunk" -v
```

Expected: prompt-context tests, fair-aggregation tests, and legacy extractor tests all pass.

---

### Task 3: Add one integration test for a synthetic large document

**Files:**
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Add a realistic long-document ingest test**

Append an integration test to [tests/test_integration.py](D:/tyh/knowledge-manager/tests/test_integration.py:150) that simulates a long Markdown source file with several sections, for example auth, storage, deployment, and observability.

Patch `Extractor.extract` only if necessary to keep this test scoped to the CLI workflow. If you want to validate the real extractor behavior instead, prefer patching the LLM client response sequence rather than bypassing extraction entirely.

The test should assert at least one of these:

1. Modules from a later section are not dropped purely because earlier sections already produced candidates.
2. The staged output contains a spread of modules that reflects multiple sections.
3. The CLI still writes staged files and reports the extracted module count correctly.

- [ ] **Step 2: Keep the fixture synthetic and deterministic**

Do not depend on a real external design spec for this test. Build the source text inline so the test remains stable, fast, and easy to reason about.

- [ ] **Step 3: Run the integration coverage**

Run:

```bash
poetry run pytest tests/test_integration.py -k "extract" -v
```

Expected: existing extract/review integration tests still pass, plus the new large-document case.

---

### Task 4: Reassess whether a second pass is still necessary

**Files:**
- Review only unless changes are required: `src/knowledge_manager/extractor.py`, `README.md`

- [ ] **Step 1: Validate the improved one-pass flow against the original failure mode**

Use the same class of input described in [test-results/scalability.md](D:/tyh/knowledge-manager/test-results/scalability.md:380): a long spec/report rather than a short note file. The question is whether boundary-aware chunking plus fair aggregation fixes the practical problem.

- [ ] **Step 2: Only add multi-pass extraction if the improved one-pass path still fails**

If the new behavior still produces empty or obviously fragmented output for long docs, then and only then plan a second increment:

1. Pass 1: extract per-section summaries or candidate concepts.
2. Pass 2: normalize or consolidate those candidates into final modules.

Do not implement that second pass pre-emptively in this change. The current repo is small and the simpler path is easier to test and maintain.

- [ ] **Step 3: Document user-visible changes if any config or behavior changed**

If you introduce a new config field or materially change how chunking behaves, add one short note to [README.md](D:/tyh/knowledge-manager/README.md:71) in the extraction/config section. If there is no user-visible change, skip the README edit.

---

## Validation Checklist

- [ ] Boundary-aware chunking prefers headings/paragraphs before raw slicing.
- [ ] Chunk prompts include `chunk_index/total_chunks` context.
- [ ] Later document sections can contribute final modules even when the global cap is small.
- [ ] Existing extractor tests still pass.
- [ ] Existing integration ingest/review tests still pass.
- [ ] No raw document text, prompts, or full LLM responses are added to logs.

## Acceptance Criteria

This work is complete when all of the following are true:

1. A synthetic multi-section long document can be processed without the final result collapsing to only the earliest chunk.
2. Chunk boundaries no longer routinely split obvious Markdown headings or paragraphs when a nearby safe boundary exists.
3. The implementation stays inside the current `km add -> Extractor -> staging` path, with no new ingestion mode.
4. Tests cover both the splitter behavior and the cross-chunk aggregation behavior that previously made long documents unreliable.

## Out of Scope

- Embedding-based retrieval or vector storage.
- Tokenizer-based chunk sizing.
- A full outline-first multi-pass extraction system in this increment.
- Broad schema changes unrelated to large-document coverage.
