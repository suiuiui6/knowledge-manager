# Knowledge Manager 论文稿 v2 作者工作 notes

这份文件承接从 v1 主稿中移出的“工作台内容”，保留给作者继续打磨时使用，不再放入主文稿。

## 1. 核心论点（工作定义）

在小中型团队知识库场景中，本文通过 Knowledge Manager 所采用的结构化知识模块、`extract-review-approve` 工作流与 MCP 按需加载机制，实现了比 `chunk-only retrieval` 更清晰的语义边界、更可执行的人工治理与更可审查的知识复用路径，证据来自 README、MCP 协议测试 `14/14` 通过、`2026-06-13` 在 `xs/s/m` 三个规模上的 release gate 结果、路由测试 `4/5` 成功以及评测代码与测试中已实现的检索指标，其适用边界是当前证据主要覆盖读路径、搜索路径与协议路径，尚不能外推到所有 chunk-based RAG、`l/xl` 规模、充分验证的长文档场景和 live conversation 下的自主路由。

## 2. 术语表

| 术语 | 统一写法 | 本文含义 |
|---|---|---|
| 项目名称 | Knowledge Manager | 本文讨论的知识管理系统 |
| 结构化知识模块 | structured knowledge modules | 以模块为单位组织知识，模块包含 `overview`、`details`、`examples`、`references`、`caveats` 等显式字段，而不是只保留文本片段 |
| 纯切块检索 | chunk-only retrieval | 以文本 chunk 作为主要知识组织与检索单位的方式 |
| 审核工作流 | extract-review-approve | 先抽取，再进入 staging，再由人工审核并批准入库的流程 |
| MCP 按需加载 | MCP on-demand loading | 通过 MCP 暴露索引与模块访问能力，由客户端按任务需要选择读取哪些模块 |
| Git 原生存储 | git-native storage | 知识以 JSON 文件和索引文件形式存放，可直接用 git 审查、追踪与版本化 |
| 小中型团队知识库 | small-to-medium team knowledge base | 维护复杂度、协作人数和知识规模都处于可人工治理范围内的团队知识库 |
| 协议合规 | protocol compliance | 系统对 MCP `2024-11-05` 协议中握手、资源、工具与返回格式的满足情况 |
| 发布门禁 | release gate | 生产就绪性检查，本文主要引用 `2026-06-13` 的 `xs/s/m` 三档结果 |
| 路由行为 | routing behavior | 模型在读取索引后选择相关模块、避免无关加载、识别边界的表现 |
| 长文档处理 | long-document handling | 对较长输入执行分块抽取、跨块去重、JSON 重试和保留原语言的实现能力 |

## 3. Claim-Evidence 对照表

| Claim | Evidence | Status |
|---|---|---|
| Knowledge Manager 不是以纯 chunk 作为唯一组织单元，而是以结构化模块为核心 | `knowledge-manager/README.md` 明确写有 “Structured modules, not chunks”，并列出模块字段；README 还给出 `raw text -> .staging/*.json -> human review -> <category>/<id>.json -> CLI/MCP` 流程图 | 已支持 |
| 系统实现了 `extract -> review -> approve -> serve` 工作流 | `knowledge-manager/README.md` 中的 Quick Start 与详细流程包含 `add/extract`、`review`、`approve`、`serve`；`.staging/` 与 approve 动作有清楚说明 | 已支持 |
| 系统采用 git-native JSON 存储，强调可审查与可追踪 | `knowledge-manager/README.md` 明确写有 “Git-native JSON storage” 和 “every approved module is JSON you can diff, review, and version” | 已支持 |
| 系统同时提供 CLI 与 MCP 双接口 | `knowledge-manager/README.md` 写有 “serves both through a CLI and MCP server”；CLI 命令和 MCP 资源/工具列表均已给出 | 已支持 |
| MCP 支持索引读取、模块搜索、模块加载、分类访问 | `knowledge-manager/README.md` 列出 `knowledge://index`、`load_module`、`search_modules`、`list_categories()`；`test-results/mcp-protocol.md` 对这些能力做了实际测试 | 已支持 |
| 协议路径不是概念验证，而是做过完整 MCP 合规测试 | `test-results/mcp-protocol.md` 显示 `14/14` 通过，覆盖握手、资源、工具、错误处理和返回格式 | 已支持 |
| `2026-06-13` 的 release gate 在 `xs/s/m` 上达到 production-ready | `test-results/perf-run-production-gate-20260613-r16-matrix-summary.json` 中 `xs/s/m` 三档的 `ready_for_production` 都为 `true` | 已支持 |
| `search_http` 与 `mcp_search_modules` 有可以写进论文的延迟数据 | 同一 release gate 文件给出 `search_http` 与 `mcp_search_modules` 在 `xs/s/m` 上的 mean 和 p95 | 已支持 |
| 当前评测框架不只是 hit-rate 演示，而是支持 rank-based 与 error-based 指标 | `src/knowledge_manager/eval_runner.py`、`src/knowledge_manager/retrieval_eval.py` 以及相应测试已实现 `first_hit_rank`、`MRR`、`nDCG@k`、`recall@k`、`baseline_win_rate`、`false_positive_rate`、`false_negative_rate`、`policy_failure_rate`、`retrieval_failure_rate` | 已支持 |
| 路由在真实知识库上表现出一定可用性，但仍是边界明确的小样本证据 | `test-results/llm-routing.md` 给出 5 个真实场景，其中 4 个场景模块选择正确，且全部测试无 irrelevant over-loading | 部分支持 |
| 结构化模块 + MCP 按需加载在工程适配性上优于 chunk-only | README 中有设计对照；路由、协议、门禁、可审查存储共同支持“更适合工程治理”这一判断，但缺少多语料 judged baseline 对比 | 部分支持 |
| 系统已证明全面优于所有 chunk-based RAG | 当前没有至少 2 个真实语料、2 个严肃 baseline 的 judged comparison | 待补证据 |
| 长文档问题已经被充分解决 | `src/knowledge_manager/extractor.py` 仅能证明长文档处理已增强：支持分块、`4000` 字符 cap、跨块去重、JSON retry、原语言保留；不能证明“完全解决” | 待补证据 |
| live conversation 下的自主路由已经充分验证 | 现有证据主要来自 `test-results/llm-routing.md` 的 5 个场景，不足以支撑更强结论 | 待补证据 |
| 写路径与 upload/create 路径和读路径一样强 | 当前最强证据仍集中在搜索、协议、读路径和发布门禁；写路径虽在 gate 中有 `module_crud_http`，但整体论文证据链仍偏弱 | 部分支持 |
| 可以外推到 `l/xl` 规模 | 当前 release gate 仅覆盖 `xs/s/m` | 待补证据 |

## 4. v1 中移出的详细大纲

### 1. 系统设计
- 回答什么问题：Knowledge Manager 为什么不把 chunk 当作唯一知识单元，而要引入结构化模块、人工审核和 MCP 按需加载。
- 依赖哪些证据：README 中关于 structured modules、git-native JSON、`extract -> review -> approve`、CLI/MCP 双接口、`knowledge://index` 与三类 MCP 工具的说明；流程图与命令示例。
- 哪些句子不能写大：不能写“取代 RAG”；不能写“理论上优于 chunk”；不能写“已证明最优知识组织形式”。

### 2. 实现细节
- 回答什么问题：系统具体是怎么落地的，尤其是 staging、审批、索引、MCP 暴露和长文档抽取增强是怎么实现的。
- 依赖哪些证据：`extractor.py` 中 `_chunk_text`、`_effective_chunk_size`、跨块去重、`_call_llm_with_retry`；`cli.py` 中 `init/list/search/review/serve` 等命令；README 对目录结构与模块结构的说明。
- 哪些句子不能写大：不能写“长文档处理已完全稳定”；不能写“系统已经实现全自动知识治理”；不能写“人工审核成本可以忽略”。

### 3. 验证设计与证据来源
- 回答什么问题：本文采用了哪些现有证据，分别覆盖系统的哪些方面，哪些方面仍缺少正式实验。
- 依赖哪些证据：`mcp-protocol.md`、`llm-routing.md`、`perf-run-production-gate-20260613-r16-matrix-summary.json`、`eval_runner.py`、`retrieval_eval.py`、相应测试文件。
- 哪些句子不能写大：不能把测试材料写成“完整 benchmark”；不能说已经完成多语料 baseline 对比；不能把 unit/integration/gate 结果包装成全面用户研究。

### 4. 结果分析
- 回答什么问题：当前证据到底说明了什么，特别是协议合规、生产门禁、检索时延、路由效果和评测能力各能支撑到什么程度。
- 依赖哪些证据：协议 `14/14`、`xs/s/m` 三档 `ready_for_production=true`、`search_http` 和 `mcp_search_modules` 延迟、`4/5` 路由结果、评测指标实现与测试。
- 哪些句子不能写大：不能写“显著优于现有方法”；不能写“所有场景都稳定有效”；不能把 `4/5` 写成“高准确率已充分证明”。

### 5. 失败案例与局限性
- 回答什么问题：系统目前具体会在哪些地方失效，哪些是实现上的短板，哪些是证据上的短板。
- 依赖哪些证据：`llm-routing.md` 中 OAuth/JWT 边界失败、troubleshooting 信号弱、细粒度模块带来加载数量偏多；`retrieval-accuracy.md` 中 `auth` 短词失败；`eval_runner` 与测试中关于 failure decomposition 和 FP/FN 定义的边界。
- 哪些句子不能写大：不能把失败点模糊成“还有改进空间”；不能只写泛泛局限，必须点到具体机制。

### 6. 讨论
- 回答什么问题：为什么这些结果更像是一个适用于小中型团队知识库的工程方案，而不是一个普适的 RAG 结论；它的适用边界在哪里。
- 依赖哪些证据：README 的项目定位、git-native 审查与复用逻辑、路由与门禁结果、当前缺失的 judged baseline 对比。
- 哪些句子不能写大：不能写“在大规模场景也成立”；不能写“说明 chunk-only 已经过时”；不能写“可以自然推广到 live agent autonomy”。

## 5. 后续补写清单

1. 至少 `2` 个真实语料上的 judged query 结果，最好能覆盖架构文档、运维/runbook、API/产品技术文档中的两类以上。
2. 至少 `2` 个严肃 baseline 的统一对比，最低可以是关键词/BM25 与 chunked retrieval，对比指标应和现有评测框架对齐。
3. 路由失败案例的更细展开，尤其是 OAuth/JWT 边界失败和 troubleshooting 查询信号弱的问题，最好给出更完整的输入、索引线索和输出。
4. 长文档专项样例，至少需要保存输入规模、分块情况、输出模块质量和失败类型，而不是只引用实现细节。
5. 写路径或 create/upload 路径的补充证据，哪怕不做大实验，也需要给出一组更直接的验证结果。
6. 如果准备投更强期刊，需要补一个“人工审核为何必要”的真实团队场景描述，最好来自实际知识修订或错误纠正过程。
7. 如果要写正式 Related Work，需要作者自己补入真实参考文献并做分组。

## 6. v1 中最像 AI 套话的句子及替换

1. 原句：
“这些结果说明，结构化、经人工审核的知识模块结合 MCP 按需加载，在小中型团队知识库中具有较好的工程适配性。”
替换：
“从当前材料看，把知识整理成可审核模块，再通过 MCP 按需读取，至少在小中型团队知识库里是讲得通的，而且维护起来比纯切块路径更顺手一些。”

2. 原句：
“现有材料能够较稳地支持几项结论。”
替换：
“按现有证据能写得比较稳的，其实主要有下面几件事。”

3. 原句：
“这一方案已经表现出较好的工程可用性和治理可见性。”
替换：
“就目前这批结果看，系统已经不只是能跑起来，还能把知识怎么进库、怎么改、怎么被读取这几件事交代清楚。”

4. 原句：
“这样的设计更偏工程治理，而不是算法创新。”
替换：
“这套设计的重心不在算法新意，而在知识进入、审核、存放和使用这条链路怎么收得住。”
