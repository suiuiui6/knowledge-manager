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
