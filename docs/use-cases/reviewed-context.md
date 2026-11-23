# Keep retrieval deterministic for a small team

The main design choice is simple: a module becomes shared context only after a
human approves it. This walkthrough shows the boundary in the demo.

## 1. Create the demo

```bash
km demo ./km-demo
km --kb-path ./km-demo list
```

You should see four approved modules. The staged draft is intentionally not in
that list.

## 2. Search approved knowledge

```bash
km --kb-path ./km-demo search "rollback deployment"
```

The result should be `agent-workflows/rollback-deployment`. Search reads modules
outside `.staging/`, so a draft cannot leak into an agent answer by accident.

## 3. Review the draft

```bash
km --kb-path ./km-demo review
```

Approve the staged on-call handoff, then rebuild and search again:

```bash
km --kb-path ./km-demo rebuild
km --kb-path ./km-demo search "on-call handoff"
```

The freshly approved module is now discoverable. This is the intended
`extract -> staging -> review -> publish -> serve` loop.

## When this is a good fit

- The team wants diffs and pull-request review for shared knowledge.
- The knowledge base is small enough that local keyword search is acceptable.
- Agents need a small, inspectable set of modules rather than an opaque context
  dump.

## When it is not

- The corpus is tens of millions of words and needs semantic recall.
- The team needs hosted multi-tenant search with a managed SLA.
- No human is available to review extracted drafts.

## Review retries and existing staging metadata

CLI `review approve` / `review request-changes` and HTTP review actions use the
same review service. Approvals count each reviewer's latest opinion on the
current content version. Repeating an approval does not increase the count;
requesting changes withdraws that reviewer's previous approval. Changing the
content requires fresh approvals. Operation timestamps and review labels do
not change the content version.

Older `.meta.json` files remain readable. Opinions without a content version
are retained as history and require a fresh review before they count. The
service retains the publication receipt in `.staging/<id>.meta.json`: retries
verify the actual published module and return the previous result. A receipt
that no longer matches the published file returns an explicit conflict.
Submitting a new draft after publication starts another review round, even
when its content is identical. Publication is retryable after a failed local
write; external webhook delivery does not carry an exactly-once guarantee.

Interactive review also binds approve/discard to the displayed content and
review round. If another writer replaces or edits the draft while the prompt
waits, the operation stops and asks the reviewer to review it again.
