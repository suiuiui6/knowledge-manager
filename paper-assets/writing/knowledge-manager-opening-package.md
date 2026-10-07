# Knowledge Manager Opening Package

## Draft:

### Polish English first

**Title options**
1. `Structured Knowledge Modules for LLM Workflows: Design and Validation of Knowledge Manager`
2. `A Git-Native MCP-Ready Knowledge System for Reviewed Team Knowledge Modules`
3. `面向小中型团队知识库的结构化知识模块管理与按需加载方法`

**One-sentence argument**
In small-to-medium team knowledge bases, we show that a git-native, reviewed knowledge-module workflow with MCP-based on-demand loading can support LLM-assisted engineering work more cleanly and more maintainably than chunk-only retrieval, supported by production-gate, retrieval, routing, and protocol evidence, with the boundary that the evidence is still strongest for `xs/s/m` scales and read/search paths.

**Abstract skeleton**
1. Team knowledge bases are increasingly used to support AI-assisted engineering, but chunk-only organization can blur semantic boundaries and make human review harder.
2. To address this, Knowledge Manager stores knowledge as structured JSON modules, adds an `extract-review-approve` workflow, and exposes index and module loading through MCP.
3. The current implementation is git-native, supports CLI and MCP access, and keeps the system readable and reviewable in ordinary version control.
4. On current checked-in evidence, MCP protocol compliance passes `14/14` tests, release-gate checks report `ready_for_production = true` at `xs/s/m`, and routing tests show `4/5` correct module-selection outcomes on a real OAuth knowledge base.
5. The results suggest that structured, human-reviewed modules are a practical fit for small-to-medium team knowledge bases, while the main boundary remains large-scale, long-document, and live conversational utility.

**Introduction outline**
1. Team knowledge reuse matters because LLM-assisted engineering needs stable, reusable project knowledge rather than one-off context stitching.
2. Chunk-only RAG is useful, but it does not always preserve semantic responsibility, review boundaries, or operational simplicity in team knowledge bases.
3. Structured modules offer a better unit of governance for small-to-medium repositories because they are inspectable, versioned, and reviewable.
4. Knowledge Manager operationalizes that idea with `extract -> review -> approve -> serve` and MCP-based on-demand loading.
5. Current evidence shows production-gate readiness, MCP protocol correctness, and bounded routing utility, but not blanket superiority over all RAG settings.
6. The paper therefore argues for a bounded, applied contribution rather than a universal replacement claim.

**Conservative contribution statements**
- We propose a git-native knowledge management workflow that organizes team knowledge into structured modules instead of raw text chunks.
- We implement an `extract-review-approve` pipeline and expose module retrieval through MCP to support selective runtime loading.
- We provide an evaluation package covering protocol compliance, retrieval quality, routing behavior, and production-gate performance on current checked-in evidence.

## Section outline:

- `Title`: keep the strongest term set in the title and avoid algorithmic overclaiming.
- `Abstract`: use a challenge-to-contribution structure; keep the boundary explicit in the final sentence.
- `Introduction`: open with team knowledge reuse, then move to the limitations of chunk-only organization, then introduce structured modules.
- `Claims`: stay on the side of architecture, workflow, and operational evidence.

## Assumptions or missing inputs:

- No fresh judged-query results on multiple real corpora are yet available in this workspace.
- Long-document and write-path evidence is still weaker than read/search/protocol evidence.
- Final journal choice is still open, so the draft stays `generic` rather than Nature-specific.

## Claim-evidence map:

- Claim: MCP protocol compliance is solid | Evidence: `test-results/mcp-protocol.md` reports `14/14` passing | Status: supported
- Claim: production-gate readiness is stronger than the old May snapshot | Evidence: `test-results/perf-run-production-gate-20260613-r16-matrix-summary.json` shows `ready_for_production = true` for `xs/s/m` | Status: supported
- Claim: routing is useful but bounded | Evidence: `test-results/llm-routing.md` reports `4/5` correct module-selection outcomes | Status: supported
- Claim: blanket superiority over chunk-only RAG | Evidence: no multi-corpus judged baseline study yet | Status: needs evidence
- Claim: large-document robustness is sufficient for universal claims | Evidence: long-doc benchmark artifacts are still incomplete | Status: needs evidence

## Why this structure:

- It keeps the paper in the applied-systems lane, which matches the current evidence.
- It gives you a clean Chinese title set plus an English-ready skeleton for later drafting.
- It makes the current boundary explicit so the paper does not overclaim.
- It separates what is already publishable from what still needs experiment support.

## 中文说明

- 这个开篇包把主线锁在“结构化知识模块 + MCP 按需加载”，比“chunk-only”更适合小中型团队知识库。
- 目前最稳的证据是协议、发布门禁、路由和提取实现，不建议现在就写成“全面优于 RAG”。
- 如果后续补上多语料、多人工作流和长文档实验，这个包可以直接升级成正式摘要和引言。
