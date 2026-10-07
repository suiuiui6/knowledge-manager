# Knowledge Manager Claim-Citation Map

日期：2026-06-17

本文件把终稿中的背景 claim 映射到候选文献。候选文献仍需在正式写稿前核对 DOI、会议/期刊版本和引用格式。

## C1. RAG 是主流知识增强路线，但不能直接等同于团队知识治理方案

候选来源：

- Lewis et al., 2020, `Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks`
- Gao et al., 2023, `Retrieval-Augmented Generation for Large Language Models: A Survey`
- Karpukhin et al., 2020, `Dense Passage Retrieval for Open-Domain Question Answering`

终稿用法：

可以写：RAG 和 dense retrieval 为 LLM 使用外部知识提供了重要技术路线。

不能写：RAG 在团队知识库治理上失败，或 Knowledge Manager 取代 RAG。

## C2. BM25 / dense / late-interaction retrieval 是严肃 baseline，不应被弱化

候选来源：

- Robertson and Zaragoza, 2009, `The Probabilistic Relevance Framework: BM25 and Beyond`
- Karpukhin et al., 2020, `Dense Passage Retrieval for Open-Domain Question Answering`
- Khattab and Zaharia, 2020, `ColBERT`
- Thakur et al., 2021, `BEIR`

终稿用法：

可以写：本文 baseline 应覆盖 lexical、dense 或 hybrid/chunk-based retrieval，避免只和弱关键词搜索比较。

不能写：只要结构化模块存在，就必然检索性能更好。

## C3. MRR、nDCG@k、recall@k 和 precision@k 是检索评价的合理指标

候选来源：

- Jarvelin and Kekalainen, 2002, `Cumulated gain-based evaluation of IR techniques`
- Thakur et al., 2021, `BEIR`
- Robertson and Zaragoza, 2009, BM25/IR evaluation background

终稿用法：

可以写：本文采用 rank-based metrics 评价模块检索排序质量。

不能写：这些指标能完全衡量 LLM 最终回答质量。若要评估回答质量，需要另行设计 answer-level 或 utility-level 评价。

## C4. 软件工程具有知识密集型特征，团队知识复用值得单独研究

候选来源：

- Bjornson and Dingsoyr, `Knowledge Management in Software Engineering`
- Developer documentation / documentation retrieval 相关文献，如 Zhou et al., 2022 `DocPrompting`

终稿用法：

可以写：软件工程知识管理涉及显性知识和隐性经验，团队知识库既服务检索，也服务复用和维护。

不能写：所有团队都必然需要 Knowledge Manager 这类系统。

## C5. 人工审核可作为知识质量控制机制

候选来源：

- Wu et al., 2021, `A Survey of Human-in-the-loop for Machine Learning`
- Wang et al., 2022, `Human-in-the-loop Machine Learning`
- Manzoor et al., 2022, `Expanding Knowledge Graphs with Humans in the Loop`

终稿用法：

可以写：人工参与可用于质量控制、纠错和边界确认。

不能写：本文已证明人工审核一定提高检索指标。除非后续提供 review 前后对比。

## C6. Git-native / docs-as-code 与版本化知识维护相关

候选来源：

- Cadavid et al., 2022, `Documentation-as-code for Interface Control Document Management in Systems of Systems`
- 软件文档与 docs-as-code 相关研究，后续继续补充 ACM/IEEE 文献

终稿用法：

可以写：将知识模块保持为可版本化文本/JSON 文件，有助于沿用开发团队的审查和变更管理习惯。

不能写：Git-native 存储天然降低所有维护成本。需要具体维护案例或用户研究。

## C7. LLM agent 工具调用需要可发现、可调用、可约束的外部能力

候选来源：

- Yao et al., 2022, `ReAct`
- Schick et al., 2023, `Toolformer`
- Patil et al., 2023, `Gorilla`
- Li, 2024, `A Review of Prominent Paradigms for LLM-Based Agents`

终稿用法：

可以写：外部工具和知识源调用已成为 LLM agent 的重要方向，Knowledge Manager 的 MCP 接口属于这一技术脉络下的应用实现。

不能写：本文已验证复杂多步 agent autonomy。

## C8. MCP 是运行时上下文和工具集成的官方协议来源

候选来源：

- Model Context Protocol official specification, 2025-06-18
- MCP Resources specification
- MCP Tools specification

终稿用法：

可以写：MCP 通过 resources 和 tools 提供服务端暴露上下文与能力的标准接口，Knowledge Manager 基于此暴露索引、搜索、加载和分类访问。

不能写：MCP 自身保证安全或治理质量。官方规范也强调实现者需要处理用户同意、隐私、工具安全和访问控制。

