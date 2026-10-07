# Knowledge Manager 主实验结果记录模板

日期：TBD

本文件用于记录多语料 judged baseline 对比结果。当前版本是模板，不包含任何已完成实验数据，不能直接写入论文“结果分析”作为主结果。

当前另有 `candidate-baseline-eval-result.json` 和 `candidate-baseline-eval-result.md`，它们来自候选查询的 baseline dry-run。该结果仅用于检查评测链路、模块 ID 映射和结果表结构；在所有查询状态更新为 `author_labeled` 或 `double_checked` 之前，不得并入本主实验结果表。

## 1. 实验状态

| 项目 | 状态 | 说明 |
|---|---|---|
| 真实语料 | 待补 | 至少 2 类真实团队知识语料。 |
| judged queries | 待补 | 北大核心等强普刊路线最低 30-50 条。 |
| baseline | 待补 | 至少 BM25/关键词 chunk baseline 与 chunk-only retrieval baseline。 |
| 主结果表 | 待运行 | 结果应写入 `main-comparison.csv`。 |
| 失败分析 | 待整理 | 边界识别、troubleshooting、短词/缩略词、长文档、写路径。 |
| candidate baseline dry-run | 已运行但不可入主表 | 30 条候选查询仍为 `candidate_needs_author_review`，只能证明评测链路可执行。 |

## 2. 可写入论文的条件

只有当 `main-comparison.csv` 中至少包含 Knowledge Manager、BM25/关键词 chunk baseline 和 chunk-only retrieval baseline 在同一语料、同一 judged queries、同一 top-k 下的结果后，才能把该表作为论文主实验表。

如果使用 candidate dry-run 结果推进正式实验，应先完成两步：第一，由作者逐条确认 query 文本、required modules、boundary note 和 evidence span；第二，将确认后的 JSONL 另存为正式 judged queries，并保留候选版与正式版的差异记录。只有这样，后续计算出的 MRR、nDCG@k、recall@k 和 precision@k 才能进入论文结果部分。

## 3. 结果解释模板

如果 Knowledge Manager 在排序或召回指标上优于 baseline，应写为：

“在给定语料和查询集下，Knowledge Manager 在若干检索指标上表现出更好的工程适配性。该结果不能外推为对所有 chunk-based RAG 的普遍优势。”

如果 Knowledge Manager 在部分检索指标上低于 baseline，应写为：

“结构化模块方案在该指标上未优于 baseline，这提示模块粒度、字段设计或搜索策略仍需改进。该结果并不否定其在审核、追踪和边界表达上的工程价值，但限制了关于检索性能的结论强度。”

## 4. 不得写入论文的说法

- 不得写过强优势判断，除非有明确统计设计和结果。
- 不得用协议测试或 release gate 替代主检索实验。
- 不得把模板行、占位符或单一 OAuth 样例写成多语料 baseline 结果。
- 不得把 candidate dry-run 中的探索性 MRR、nDCG@5、recall@5 或 precision@5 写成正式 judged baseline 结果。
