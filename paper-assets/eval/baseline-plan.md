# Knowledge Manager baseline 对比计划

日期：2026-06-17

本文件定义终稿主实验最低 baseline。当前阶段只定义实验协议，不记录结果。

配套文件：

- `corpus-inventory.csv`：真实语料清单模板。
- `judged-queries.schema.json`：judged query 结构约束。
- `judged-queries.template.jsonl`：查询标注模板，不可作为结果使用。
- `../results/main-comparison.csv`：主实验结果表模板。
- `../results/main-comparison.md`：主实验结果解释模板。

## 1. Baseline 原则

baseline 必须足够严肃，不能为了让 Knowledge Manager 显得更好而选择过弱比较对象。本文的论点是“小中型团队知识库中的工程适配性”，不是“全面打败所有 RAG”。

## 2. 最低 baseline

| Baseline | 描述 | 对应论文问题 | 北大核心等强普刊 | SCI 四区 |
|---|---|---|---|---|
| BM25 / keyword chunk baseline | 将源文档或 chunk 建索引，用 BM25 或等价关键词排序返回 top-k | 纯 lexical retrieval 能做到什么 | 必选 | 必选 |
| chunk-only retrieval baseline | 将文档按固定窗口切块，按文本相似度或关键词/embedding 检索 chunk | 仅以 chunk 为组织单元的路线表现如何 | 必选 | 必选 |
| chunked vector retrieval | 对 chunk 建 embedding 索引，用 dense retrieval 返回 top-k | dense retrieval 与结构化模块相比如何 | 可选 | 必选 |
| hybrid retrieval | 结合 BM25 与 vector retrieval，必要时 rerank | 强 baseline 下工程适配性是否仍成立 | 可选 | 建议必选 |
| no-review module baseline | 使用结构化模块但跳过人工 review/approve | 人工审核是否带来治理差异 | 可选 | 建议 |

## 3. 统一评估条件

- [ ] 所有系统使用同一语料。
- [ ] 所有系统使用同一 judged queries。
- [ ] 所有系统返回统一 top-k。
- [ ] 所有系统记录延迟。
- [ ] 不为某一系统手工调优 query。
- [ ] 若使用 embedding，记录模型、维度、索引方式和运行环境。

## 4. 指标表设计

主结果表建议列：

| system | corpus | query_count | MRR | nDCG@5 | recall@5 | precision@5 | mean_latency_ms | p95_latency_ms | avg_loaded_units | notes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|

`avg_loaded_units` 对 Knowledge Manager 表示加载模块数，对 chunk baseline 表示加载 chunk 数。若后续能统计 token，则增加 `avg_context_tokens`。

当前 `../results/main-comparison.csv` 仅包含模板行，状态为 `template_not_measured`。在真实语料和 judged queries 未完成前，不得将该文件写成论文主结果。

## 5. 结果解释边界

可以写：

- 在给定语料、查询集和 baseline 下，Knowledge Manager 在若干指标上表现出更好的工程适配性。
- 结构化模块可能牺牲部分自动 ingest 速度，但换来可审查性和治理边界。
- 如果某些检索指标不优，应解释取舍，而不是回避。

不能写：

- 不受范围限制的 RAG 优势判断。
- 结构化模块天然提高检索准确率。
- baseline 表现较弱就说明 chunk-only 路线不可取。
