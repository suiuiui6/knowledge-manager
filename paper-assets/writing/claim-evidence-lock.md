# Knowledge Manager Claim-Evidence 锁定表

日期：2026-06-17

本文件用于约束终稿写作。摘要、引言、结果、讨论和结论中的强结论必须能回到本表。

| Claim | Evidence | Status | Manuscript wording |
|---|---|---|---|
| Knowledge Manager 以结构化知识模块组织知识，而不是只依赖文本 chunk。 | 主稿中的模块字段、README 信息、系统设计描述。 | 已支持 | “系统以结构化知识模块为基本组织单元。” |
| 系统实现 `extract-review-approve` 工作流。 | `.staging/`、review、approve、index 更新路径。 | 已支持 | “知识入库前经过抽取、审核和批准。” |
| 系统采用 Git 原生 JSON 存储，支持审查和追踪。 | approved modules、`index.json`、Git diff/review/version 设计。 | 已支持 | “该存储方式贴近开发团队既有代码审查流程。” |
| 系统提供 CLI 与 MCP 双接口。 | README 和主稿中的 CLI 命令、MCP 资源/工具描述。 | 已支持 | “系统通过 CLI 和 MCP 双接口服务人工维护者与 AI 客户端。” |
| MCP 支持索引读取、模块搜索、模块加载和分类访问。 | `knowledge://index`、`search_modules`、`load_module`、`list_categories`。 | 已支持 | “MCP 侧支持索引读取、模块搜索、模块加载和分类访问。” |
| MCP 协议路径可运行。 | MCP 协议测试 `14/14` 通过。 | 已支持 | “协议测试表明 MCP 接口链路已实现并可运行。” |
| `xs/s/m` 三档达到项目设定门槛。 | `2026-06-13` release gate 三档 `ready_for_production=true`。 | 已支持 | “在已测小中规模下达到项目设定运行门槛。” |
| 搜索路径有明确时延记录。 | `search_http` 与 `mcp_search_modules` mean/p95 时延表。 | 已支持 | “搜索路径已有 mean 和 p95 时延记录。” |
| 受控路由场景中观察到模块选择能力。 | OAuth 知识库 5 个受控场景中 4 个正确。 | 部分支持 | “在小样本受控场景下观察到可用的模块选择行为。” |
| 评测框架可运行并输出 rank/failure 指标。 | 内置 KB smoke eval 7 个低难度查询跑通；输出 first-hit rank、MRR、nDCG@k、recall@k、false-positive/false-negative rate、policy/retrieval failure rate。 | 已支持 | “项目评测框架已具备运行和输出相关指标的能力。” |
| 结构化模块更利于保持语义边界和人工治理。 | 模块字段、人工审核、Git 存储、MCP 按需加载的设计证据；缺少消融。 | 部分支持 | “在设计上更便于审查和追踪；复用收益仍需评估。” |
| 系统检索性能普遍优于 chunk-only retrieval。 | 缺少多语料 judged baseline。 | 待补证据 | 不写。只能写“需要通过 baseline 对比检验”。 |
| 长文档处理已充分解决。 | 只有分块、4k cap、去重、JSON retry、原语言保留、日志增强。 | 待补证据 | 不写。只能写“实现层面做了增强”。 |
| live conversation 下自主路由成熟。 | 只有 5 个受控路由场景。 | 待补证据 | 不写。只能写“真实会话证据仍弱”。 |
| `l/xl` 规模同样成立。 | release gate 只覆盖 `xs/s/m`。 | 待补证据 | 不写。只能写“不能外推到 `l/xl`”。 |
| 写路径与读路径同等充分。 | upload/create/update 等缺少完整 E2E。 | 待补证据 | 不写。只能写“写路径证据弱于读路径”。 |

## 摘要允许写入的数字

- MCP 协议测试：`14/14`
- release gate：`2026-06-13`，`xs/s/m` 均为 `ready_for_production=true`
- 搜索路径：`search_http` 和 `mcp_search_modules` mean/p95 时延
- 路由：5 个受控场景中 4 个模块选择正确

## 摘要不允许写入的内容

- baseline 胜率或 MRR/nDCG/recall 数字，除非主实验运行完成。
- 用户研究、专家评审、统计显著性，除非后续真实补充。
- 长文档专项结论，除非专项验证完成。
- 写路径充分性结论，除非 E2E 验证完成。
