# Knowledge Manager judged query 标注指南

日期：2026-06-17

本指南用于构建 `judged-queries.jsonl`，目标是支撑北大核心等强普刊最低线和 SCI 四区扩展线。当前文件只定义协议，不包含实验结果。

配套文件：

- `corpus-inventory.csv`：记录语料元信息。
- `judged-queries.schema.json`：定义每条 query 的字段和取值范围。
- `judged-queries.template.jsonl`：提供模板行，必须替换为真实查询和 approved module id 后才能进入评测。

## 1. 查询集规模

| 路线 | 最低规模 |
|---|---:|
| 北大核心等强普刊 | 30-50 queries |
| SCI 四区目标 | 80-120 queries |

## 2. 语料要求

最低需要 2 类真实团队知识语料：

- 架构 / 工程设计文档
- 运维 / runbook / troubleshooting 文档

SCI 四区目标建议增加：

- API / 产品技术文档

每类语料都需要记录：

- `corpus_id`
- `domain`
- `source_doc_count`
- `approved_module_count`
- `total_chars_or_words`
- `average_doc_length`
- `long_doc_count`
- `notes`

## 3. JSONL schema

每条 query 建议使用以下字段：

```json
{
  "query_id": "A001",
  "corpus_id": "architecture",
  "query": "用户查询文本",
  "task_type": "factual|procedure|decision|troubleshooting|boundary|synthesis",
  "scope_type": "in_scope|out_of_scope|partial_scope",
  "difficulty": "easy|medium|hard",
  "required_modules": ["module-id-1"],
  "nice_to_have_modules": ["module-id-2"],
  "should_refuse_or_boundary_note": false,
  "expected_boundary": "如果部分不在知识库，应说明缺失范围",
  "judge_notes": "为什么这些模块是 required",
  "edge_case_tags": ["short_term", "synonym", "case_variant"]
}
```

如果后续需要让 chunk baseline 的相关性判断更公平，可以补充可选字段：

- `source_doc_ids`：相关源文档 ID。
- `gold_evidence_spans`：短证据片段 ID 或简短描述，不粘贴长篇原文。
- `relevance_grade`：`binary`、`graded_0_2` 或 `graded_0_3`。

这些字段用于评测可复核性，不代表实验结果。

## 4. 查询类型配比

| 类型 | 建议比例 | 目的 |
|---|---:|---|
| factual | 20% | 测基本命中 |
| procedure / how-to | 20% | 测流程型知识 |
| decision / tradeoff | 15% | 测 caveats 和边界 |
| troubleshooting | 15% | 测排障信号 |
| boundary / out-of-scope | 15% | 测拒答或边界提示 |
| cross-module synthesis | 15% | 测多模块组合 |

## 5. required 与 nice-to-have 判定

`required_modules` 只标注完成任务不可缺少的模块。若缺失该模块会导致回答错误、遗漏关键步骤、遗漏重要风险或无法说明适用条件，则标为 required。

`nice_to_have_modules` 标注能改善回答但不是必要的模块。评估 recall 时应与 required 区分，避免把“可有可无”的模块抬成刚性要求。

## 6. 边界查询规则

边界查询必须包含：

- 完全 out-of-scope：知识库没有该主题。
- partial-scope：问题一部分在库内，一部分在库外。
- near-scope：词面相近但概念不同，例如 OAuth vs JWT。

判定时记录：

- 系统是否加载了不该加载的模块。
- 系统是否明确提示知识库覆盖不足。
- 系统是否依赖模型常识补全超出知识库的内容。

## 7. 失败标签

可使用以下标签：

- `short_term`
- `abbreviation`
- `synonym`
- `case_variant`
- `broad_query`
- `troubleshooting_signal_weak`
- `boundary_confusion`
- `multi_module_required`
- `long_doc_derived`
- `missing_caveat`

## 8. baseline 对比要求

同一 query set 必须用于所有系统：

- Knowledge Manager structured modules
- BM25 / keyword chunk baseline
- chunk-only retrieval baseline
- SCI 四区目标可增加 chunked vector retrieval 或 hybrid retrieval

不得为某个系统单独调整 query 或相关性标注。

模板行的 `status` 为 `template`，不得纳入指标统计。由论文作者或本地材料整理者预先构造、但尚未复核的查询可标为 `candidate_needs_author_review`。正式评测前，至少应将查询状态更新为 `author_labeled`；若有第二人复核或作者二次核对，可更新为 `double_checked`。

## 9. 指标

最低报告：

- `first-hit rank`
- MRR
- nDCG@k
- recall@k
- precision@k
- latency mean / p95

建议报告：

- context token count
- loaded module count
- false-positive / false-negative rate
- boundary detection rate
- policy/retrieval failure rate
