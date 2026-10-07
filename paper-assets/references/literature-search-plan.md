# Knowledge Manager 外部文献检索计划

日期：2026-06-17

目标：为 Knowledge Manager 终稿补齐 Related Work 与关键 claim 的真实文献支撑，使稿件达到北大核心等强普刊最低线，并为 SCI 四区英文稿预留扩展空间。

## 1. 检索工作流

本阶段使用 `multi-source-search` 工作流。优先源为 CrossRef、arXiv、ACL Anthology、ACM Digital Library、IEEE Xplore、Springer、ScienceDirect、Semantic Scholar；中文投稿时可人工补 CNKI / 万方中的“知识管理”“软件工程知识复用”“技术文档管理”相关文献。

## 2. 检索脉络

| 脉络 | 论文中服务的位置 | 英文检索式 | 需要回答的问题 |
|---|---|---|---|
| RAG 与 chunk-based retrieval | 相关工作 2.1 | `"retrieval augmented generation" survey`, `"chunking" "retrieval augmented generation"`, `"dense retrieval" "open-domain question answering"`, `"hybrid retrieval" RAG` | chunk-based / dense / hybrid retrieval 解决了什么，为什么它仍是强 baseline |
| 信息检索评价指标 | 评估方法 | `"nDCG" information retrieval evaluation`, `"mean reciprocal rank" retrieval evaluation`, `"BEIR" benchmark information retrieval`, `"Recall@k" retrieval evaluation` | 为什么使用 MRR、nDCG@k、recall@k、precision@k |
| 团队知识管理与软件工程知识复用 | 引言、相关工作 2.2 | `"knowledge management" "software engineering" systematic review`, `"software engineering knowledge management" empirical`, `"developer documentation" knowledge reuse` | 软件工程为什么是知识密集型工作，团队知识库为什么值得研究 |
| human-in-the-loop 与知识审核 | 相关工作 2.3、讨论 | `"human-in-the-loop" machine learning survey`, `"knowledge curation" human-in-the-loop`, `"human review" knowledge base quality` | 人工审核为何不是流程负担，而是治理机制 |
| docs-as-code / git-native documentation | 相关工作 2.4、系统设计 | `"docs as code" software documentation research`, `"documentation-as-code" version control`, `"software documentation" "version control"` | Git 管理文档和知识模块的合理性在哪里 |
| Agent 工具调用与运行时上下文加载 | 相关工作 2.5、MCP 设计 | `"LLM agents" "tool use" survey`, `"Toolformer" language models use tools`, `"ReAct" language models tools`, `"Model Context Protocol" specification` | LLM 客户端为什么需要工具调用和按需上下文 |
| 长上下文与 RAG 边界 | 局限性、讨论 | `"long context" RAG performance`, `"long context" retrieval augmented generation`, `"context engineering" large language models survey` | 为什么不能简单用长上下文替代检索或模块化治理 |

## 3. 纳入标准

- [ ] 优先选择同行评审论文、arXiv 预印本中的高相关技术论文、官方规范文档。
- [ ] 每条文献必须服务一个明确 claim，不为堆数量而引用。
- [ ] RAG / retrieval 相关文献必须包含至少 1 篇基础论文、1 篇综述、1 篇 baseline/benchmark 文献。
- [ ] MCP 相关引用优先使用官方 specification，不用营销博客支撑协议事实。
- [ ] 对 docs-as-code 和团队知识管理，优先找软件工程或信息系统领域论文。

## 4. 排除标准

- [ ] 只讨论商业产品功能、没有方法或实证内容的博客。
- [ ] 无法核对作者、年份、出处的二手网页。
- [ ] 与“结构化知识模块、人工审核、Git 存储、MCP 按需加载”没有直接关系的泛 AI 文章。
- [ ] 只支持“AI 很重要”这类背景空话的文献。

## 5. Related Work 初步结构

### 2.1 Retrieval-augmented generation and chunk-based retrieval

任务：承认 RAG、dense retrieval、hybrid retrieval 的价值，说明本文不是否定它们，而是研究小中型团队知识库中的知识治理单位问题。

### 2.2 Knowledge management in software engineering

任务：说明软件工程是知识密集型活动，团队知识库不只是问答材料，还承载决策、经验、约束和维护责任。

### 2.3 Human-reviewed knowledge workflows

任务：说明人工审核在知识质量控制中有合理性，本文的 `extract-review-approve` 是治理机制，而不是自动化不足。

### 2.4 Versioned documentation and docs-as-code

任务：把 git-native JSON 存储放入 versioned documentation / docs-as-code 脉络，说明 diff、review、version 对团队协作的价值。

### 2.5 Tool use, MCP, and on-demand context loading

任务：把 MCP 按需加载放入 LLM tool use 和 context management 脉络，说明客户端为什么需要先读索引、再搜索和加载模块。

### 2.6 Evaluation of retrieval-oriented knowledge systems

任务：说明 judged queries、MRR、nDCG@k、recall@k、latency、failure analysis 是本文评估设计的来源。

## 6. 输出要求

| 文件 | 要求 |
|---|---|
| `reference-candidates.csv` | 至少 20 条候选，标注主题、角色、支撑 claim、验证状态 |
| `claim-citation-map.md` | 每个背景 claim 对应 1-3 条候选文献 |
| `02-related-work.md` | 按主题综合，而不是逐篇列举 |
| `references.bib` | 后续正式写稿前生成 BibTeX，当前阶段可先留空 |

