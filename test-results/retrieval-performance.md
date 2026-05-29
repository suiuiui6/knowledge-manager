# Knowledge Manager - Retrieval Performance Report

**Test Date:** 2026-05-29 19:53:11  
**Knowledge Base:** `D:\tyh\knowledge_base`  
**Total Modules:** 8  
**Categories:** auth

---

## Test 1: Single Query Latency

Measured latency for queries of different lengths (10 iterations each):

| Query | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | StdDev (ms) | Results |
|-------|-----------|-------------|----------|----------|-------------|---------|
| OAuth | 3.16 | 3.08 | 2.99 | 3.64 | 0.19 | 8 |
| OAuth authorization | 3.14 | 3.09 | 3.04 | 3.44 | 0.13 | 8 |
| OAuth authorization framework | 3.16 | 3.12 | 2.98 | 3.53 | 0.16 | 8 |
| OAuth 2.0 authorization code flow | 3.12 | 3.11 | 2.95 | 3.38 | 0.12 | 8 |

## Test 2: Batch Query Throughput

- **Total Queries:** 100
- **Total Time:** 0.302 seconds
- **Throughput:** 331.28 queries/second
- **Average per Query:** 3.02 ms

## Test 3: Cold Start vs Hot Cache

Query: `OAuth authorization`

- **Cold Start:** 2.91 ms
- **Hot (average):** 2.98 ms
- **Speedup Factor:** 0.98x

## Test 4: Scalability Estimates

Baseline: 8 modules

| Target Scale | Estimated Latency (ms) | Scale Factor |
|--------------|------------------------|--------------|
| 50 modules | 23.55 | 6.2x |
| 200 modules | 94.21 | 25.0x |
| 500 modules | 235.53 | 62.5x |
| 1000 modules | 471.07 | 125.0x |

---

## Summary

- **Average Query Latency:** 3.14 ms
- **Throughput:** 331.28 queries/sec
- **Current Scale:** 8 modules

### Performance at Target Scale

- **@ 50 modules:** 23.55 ms (design target)
- **@ 200 modules:** 94.21 ms (design target)

### Assessment

✅ **EXCELLENT** - Sub-100ms latency at target scale (200 modules)

---

## Implementation Notes

- **Search Algorithm:** Regex-based keyword matching with field weighting
- **Field Weights:** title=5, tag=3, summary=2, overview=1
- **Complexity:** O(n) linear scan over all modules
- **I/O:** Reads all module files on each query (no persistent cache)

## Recommendations

1. Current performance is excellent for the 8-module test set
2. Linear scaling should remain acceptable up to 200 modules
3. For larger scales (500+ modules), consider:
   - In-memory index caching
   - Inverted index for keyword lookup
   - Incremental index updates
