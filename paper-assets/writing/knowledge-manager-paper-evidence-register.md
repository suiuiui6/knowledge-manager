# Knowledge Manager 论文证据登记表

本文件只记录当前能直接支撑论文论点的材料位置，目的是在后续补实验、收紧表述或应对审稿意见时，避免重新全仓库搜证。

## 1. 系统定位与核心机制

- `knowledge-manager/README.md`
  - 第 3-11 行附近：项目被描述为 “structured modules” + “git-native JSON storage” + “MCP-ready retrieval”。
  - 第 67-76 行附近：明确列出 `extract -> staging -> review -> approve`、MCP 复用、长文档分块、日志增强、测试覆盖。
  - 第 131-166 行附近：`review` 与 `serve` 的具体使用方式，以及 `knowledge://index`、`load_module`、`search_modules`、`list_categories`。
  - 第 266-310 行附近：系统流程图与 CLI 命令清单，可直接支撑“CLI + MCP 双接口”与“从原始文本到正式模块”的实现链路。

## 2. MCP 协议合规

- `knowledge-manager/test-results/mcp-protocol.md`
  - 第 10-12 行：`14/14` 通过。
  - 第 29-31 行：确认存在 `list_categories`、`load_module`、`search_modules` 三个工具。
  - 第 74-81 行：协议特性覆盖 JSON-RPC、握手、Resources、Tools。
  - 第 134-143 行：给出 production ready / spec compliant 的结论性描述，但论文中宜写成“协议测试通过”，不要直接照抄为普遍性结论。

## 3. 发布门禁与延迟数据

- `knowledge-manager/test-results/perf-run-production-gate-20260613-r16-matrix-summary.json`
  - `xs.release_verdict.ready_for_production = true`
  - `s.release_verdict.ready_for_production = true`
  - `m.release_verdict.ready_for_production = true`
  - `search_http`:
    - `xs`: mean `207.113 ms`, p95 `220.442 ms`
    - `s`: mean `370.877 ms`, p95 `380.882 ms`
    - `m`: mean `404.838 ms`, p95 `414.091 ms`
  - `mcp_search_modules`:
    - `xs`: mean `208.454 ms`, p95 `230.392 ms`
    - `s`: mean `476.714 ms`, p95 `486.724 ms`
    - `m`: mean `593.72 ms`, p95 `625.424 ms`
  - `module_crud_http` 虽然三档均通过，但论文中不宜把它写成写路径证据已经与读路径同强。

## 4. 路由行为与失败点

- `knowledge-manager/test-results/llm-routing.md`
  - 第 12-17 行附近：5 个场景里 `4/5` 正确，同时无 irrelevant over-loading。
  - 第 103-133 行附近：OAuth vs JWT 的边界失败，直接支撑“系统缺少 out-of-scope 信号”。
  - 第 139-155 行附近：redirect troubleshooting 场景说明 troubleshooting 信号弱，`caveats` 为空。
  - 第 213-219 行附近：5 个场景的总表，可直接支撑 “4/5 场景成功，1 个边界失败，1 个 troubleshooting 不确定”。

## 5. 检索准确性补充风险

- `knowledge-manager/test-results/retrieval-accuracy.md`
  - Query 4 `auth` 返回空结果，直接支撑“短词/缩略词匹配不稳”。
  - Query 6 `user consent` 出现一定噪声，可用于补充“ broad query 下仍有排序噪声”。

## 6. Extractor 与长文档处理

- `knowledge-manager/src/knowledge_manager/extractor.py`
  - 第 124-134 行附近：`_chunk_text()` 分块实现。
  - 第 146-147 行附近：`_effective_chunk_size()` 把 chunk cap 限制为 `4000`。
  - 第 151-159 行附近：抽取时记录 chunk 数量、chunk_size、overlap。
  - 第 171-180 行附近：跨 chunk 的 `seen_ids` 去重逻辑。
  - 第 255 行以后：`_call_llm_with_retry()`，对 JSON 解析失败和返回对象而非数组的情况做重试。
  - Prompt 文本中：明确要求保留源文本原语言。

## 7. 评测框架与指标

- `knowledge-manager/src/knowledge_manager/retrieval_eval.py`
  - 第 9-12 行附近：`first_hit_rank`、`mrr`、`ndcg_at_k`、`recall_at_k` 字段。
  - 第 17-31 行附近：这些指标的计算逻辑。

- `knowledge-manager/src/knowledge_manager/eval_runner.py`
  - 第 37-40 行附近：case 级 rank 指标字段。
  - 第 58-67 行附近：summary 级 `baseline_win_rate`、`false_positive_rate`、`false_negative_rate`、`policy_failure_rate`、`retrieval_failure_rate`。
  - 第 95-104 行附近：评测过程中累计这些统计量。
  - 第 208-217 行附近：最终 summary 输出这些统计指标。

- `knowledge-manager/tests/test_retrieval_eval.py`
  - `test_score_ranked_case_reports_mrr_ndcg_and_hit_position` 明确断言 `first_hit_rank`、`MRR`、`nDCG@k`、`recall@k`。

- `knowledge-manager/tests/test_eval_runner.py`
  - `test_run_eval_suite_reports_baseline_delta_and_failure_decomposition`
  - `test_run_eval_suite_does_not_count_extra_relevant_results_as_false_positives`
  - `test_run_eval_suite_reports_policy_suppressed_modules_and_missing_companions`
  - 这些测试能证明字段存在与基础行为正确，但还不能证明复杂失败场景的 decomposition 已被充分验证。

## 8. 论文中必须保守处理的地方

- 不能把 `4/5` 路由结果写成“自主路由已成熟”。
- 不能把 extractor 的分块、去重和重试写成“长文档问题已解决”。
- 不能把 `baseline_win_rate`、`policy_failure_rate` 等字段的存在写成“已完成严格多 baseline 对比”。
- 不能把 `module_crud_http` 通过写成“写路径证据充分”。
- 不能从 `xs/s/m` 的 gate 结果外推到 `l/xl`。

## 9. 后续优先补证据的方向

1. 多真实语料 judged query 对比。
2. 至少 2 个严肃 baseline。
3. 长文档专项样例与留存输出。
4. 写路径 / upload / create 的补充材料。
5. live conversation 场景下的更长链路路由样例。
