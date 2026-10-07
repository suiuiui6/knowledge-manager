# Candidate Baseline Evaluation Result

Status: `candidate_not_main_result`

Results are exploratory until every query is author_labeled or double_checked.

These numbers must not be copied into the manuscript main comparison table unless the query labels are author-reviewed.

## Query Label Status

| status | count |
|---|---:|
| `candidate_needs_author_review` | 30 |

## System Summary

| system | queries | evaluable | MRR | nDCG@5 | recall@5 | precision@5 | mean latency ms | p95 latency ms | misses |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| structured_module_keyword | 30 | 28 | 0.4708 | 0.5251 | 0.6964 | 0.1714 | 0.629 | 0.848 | 8 |
| bm25_keyword_chunk_baseline | 30 | 28 | 0.4238 | 0.4957 | 0.5893 | 0.1643 | 0.804 | 1.686 | 11 |
| chunk_only_keyword_baseline | 30 | 28 | 0.4071 | 0.4685 | 0.5476 | 0.1571 | 0.248 | 0.415 | 12 |
