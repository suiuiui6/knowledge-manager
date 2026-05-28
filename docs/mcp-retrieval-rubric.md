# MCP Live Test — Retrieval Evaluation Rubric

The `knowledge-manager` MCP server is registered locally for this project. To verify retrieval works against the real Claude Code tool-use loop, open a **fresh Claude Code session in this directory** and paste each scenario below as a separate user message. Grade Claude's behavior using the rubric.

## Setup verification

In the new session, first confirm the server is reachable:

```
/mcp
```

You should see `knowledge-manager` listed as connected with tools `load_module`, `search_modules`, `list_categories`.

## Scenarios

For each one, paste the question verbatim. Do not give Claude any other context — the whole point is to see whether it autonomously consults the KB.

### Scenario 1 — direct hit (auth/jwt-tokens)
> How do we validate JWT tokens at the API gateway? Please check the project knowledge base before answering.

**Pass criteria:** Claude calls `search_modules` (with a JWT-related query) then `load_module` for `jwt-tokens/auth`, and its answer cites RS256 / JWKS / the kid rotation flow from the module body.

### Scenario 2 — direct hit (auth/oauth-flow)
> What's our OAuth 2.0 server-side callback flow? Use the knowledge base.

**Pass criteria:** Claude loads `oauth-flow/auth` and answers using its content.

### Scenario 3 — direct hit (database/connection-pool)
> How should I size the Postgres connection pool for our workload?

**Pass criteria:** Claude loads `connection-pool/database` and cites the "small number of busy connections" guidance.

### Scenario 4 — indirect / cross-content match
> Why do we reject HS256 tokens at the gateway? Check the KB.

**Pass criteria:** Claude finds and loads `jwt-tokens/auth` (the algorithm-confusion caveat lives in the `caveats` field, not the title/summary). This tests whether `search_modules` reaches into `content.overview` and whether Claude is willing to load a module whose summary doesn't perfectly match.

### Scenario 5 — abstention / out-of-scope
> Help me set up a Kubernetes ingress controller.

**Pass criteria:** Either:
- Claude calls `search_modules` (or reads the index), sees nothing relevant, and answers from general knowledge while noting the KB has nothing on this; OR
- Claude doesn't call the KB at all because the question is obviously outside its scope.

**Fail criteria:** Claude loads an unrelated module and tries to bend its content to fit (this is the hallucination-from-RAG failure mode this system is meant to avoid).

## Retrieval implementation notes

`search_modules` uses word-boundary regex matching with weighted scoring:

| Field | Weight |
|-------|--------|
| `title` | 5 |
| `metadata.tags` | 3 |
| `summary` | 2 |
| `content.overview` | 1 |

For each query term, the module gets the weight of the highest-scoring field where the term appears as a whole word. Per-term scores sum to a module score; modules with score 0 are dropped; results are sorted by score descending.

Consequences:
- Substring artifacts are filtered: `auth` does not match `authentication` or `OAuth`.
- Title hits dominate overview hits, so loosely-related modules sink to the bottom rather than competing with the right answer.
- Modules that *legitimately* contain a query term (e.g. `auth` as a standalone word in "TCP+TLS+auth handshake") still surface — they just rank below stronger matches. This is intentional: the LLM gets the signal to confirm, not a hard filter.

## What "good" looks like

A passing run of all 5 scenarios with no fabricated content from unrelated modules. The system's safety net is Claude's judgment about what to load — search precision is secondary.
