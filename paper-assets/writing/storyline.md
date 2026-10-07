# Knowledge Manager 论文主线锁定

日期：2026-06-17

本文定位为面向小中型团队知识库的应用型系统论文。它不主张提出新的 RAG 算法，也不主张全面替代 chunk-based retrieval。

## 一句话论点

在小中型团队知识库的 AI 协作开发场景中，本文通过 Knowledge Manager 的结构化知识模块、`extract-review-approve` 人工审核流程、Git 原生 JSON 存储和 MCP 按需加载机制，实现了更清晰的知识边界表达、更可审查的知识治理路径和更可控的运行时加载方式；证据来自 MCP 协议测试 `14/14` 通过、`2026-06-13` release gate 在 `xs/s/m` 三档达到项目设定门槛、搜索路径时延记录、受控路由 `4/5` 结果，以及评测框架已支持 rank-based 和 failure-based 指标；其适用边界是当前证据主要覆盖读路径、搜索路径和协议路径，不能外推到所有 RAG、`l/xl` 规模、充分长文档处理、完整写路径或真实会话中的全自动路由。

## 主贡献

Knowledge Manager 提供了一种面向小中型团队知识库的结构化知识管理与 MCP 按需加载系统，把知识从原始文本转化为经审核、可追踪、可按任务加载的结构化模块。

## 支撑贡献

1. 系统采用 `extract-review-approve` 流程和 Git 原生 JSON 存储，使知识入库前具有人工审核环节，并支持 diff、review 和 version。
2. 系统通过 CLI 与 MCP 双接口提供知识访问，MCP 侧支持索引读取、模块搜索、模块加载和分类访问，使客户端能够先定位模块，再按需加载。
3. 论文以协议测试、release gate、搜索时延、受控路由和评测框架能力作为工程验证证据，同时明确列出 baseline、长文档、写路径和真实会话路由的证据缺口。

## 目标读者

本文主要面向软件工程、信息系统、知识管理、AI 工程应用方向的应用型期刊读者。读者关心的是系统是否可复现、证据是否清楚、边界是否诚实，而不是算法理论创新。

## 标题锁定

中文题名：面向小中型团队知识库的结构化知识模块管理与 MCP 按需加载系统

英文备选：Design and Validation of a Structured Knowledge Module System for Small-to-Medium Team Knowledge Bases

## 不写大的句子

- 不写不受范围限制的 RAG 优势判断。
- 不写首创性口号。
- 不写缺少统计或基线支撑的领先判断。
- 不写“长文档问题已经解决”。
- 不写“自主路由已经成熟”。
- 不写“写路径已被充分验证”。
- 不写把小中规模结果外推为大规模结论。

## 当前交付物状态

- Word 投稿型初稿：`paper-assets/deliverables/knowledge-manager-paper-v3-submission-draft.docx`
- 主稿 Markdown：`paper-assets/writing/knowledge-manager-paper-v3.md`
- 图 1 / 图 2：`paper-assets/figures/`
- 主实验评测材料模板：`paper-assets/eval/` 与 `paper-assets/results/`

当前交付物已经具备论文主文、参考文献、表格和两张图片，但还不能称为完全可投终稿，因为多语料 judged baseline 对比、长文档专项和写路径 E2E 尚未完成。
