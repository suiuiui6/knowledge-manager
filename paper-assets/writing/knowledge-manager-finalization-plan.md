# Knowledge Manager 论文终稿执行计划

日期：2026-06-17

本计划用于把 `knowledge-manager-paper-v2.md` 推进为可投稿终稿。最低目标是达到北大核心等强普刊应用型系统论文水平，终极目标是形成可尝试 SCI 四区应用系统 / 软件工程 / 信息系统类期刊的版本。

## 1. 总判断

当前 `v2` 已经具备论文外壳，但还不能直接称为终稿。主要原因不是语言不够流畅，而是两个硬问题还没收住：一是相关工作缺少真实文献支撑，二是实验部分仍偏“现有证据整理”，还没有完全转成正式的实验设计与对比结果。

终稿不能把 Knowledge Manager 写成通用 RAG 新算法。更稳的定位是：面向小中型团队知识库的结构化知识模块管理与 MCP 按需加载系统。论文贡献应落在系统设计、工程实现、评估协议、边界清楚的对比验证上。

## 2. 终稿核心论点

在小中型团队知识库场景中，Knowledge Manager 通过结构化知识模块、`extract-review-approve` 人工治理流程、git-native JSON 存储与 MCP 按需加载机制，为 AI 协作开发提供了一种比纯文本切块组织方式更便于语义边界保持、人工审查和运行时选择性加载的工程方案；这一结论应由多语料 judged queries、至少两个 baseline、协议测试、发布门禁、路由行为、长文档专项和失败分析共同支撑，其适用范围限制在小中型知识库、读路径 / 搜索路径 / 协议路径较强的场景内。

## 3. 术语锁定

| 术语 | 终稿统一写法 | 说明 |
|---|---|---|
| 系统名称 | Knowledge Manager | 作为项目名保留英文 |
| 结构化知识模块 | structured knowledge modules / 结构化知识模块 | 中文稿第一次出现时给出英文括注即可 |
| 纯切块检索 | chunk-only retrieval / 纯切块检索 | 不写成“所有 RAG” |
| 审核流程 | `extract-review-approve` | 保留代码式流程名，正文解释为抽取、审核、批准 |
| MCP 按需加载 | MCP on-demand loading / MCP 按需加载 | 第一次出现需解释 MCP 用于索引、搜索、加载、分类访问 |
| Git 原生存储 | git-native JSON storage / Git 原生 JSON 存储 | 强调可审查、可追踪、可版本化 |
| 小中型团队知识库 | small-to-medium team knowledge base / 小中型团队知识库 | 终稿不得扩展成“大规模企业知识库” |
| 发布门禁 | release gate / 发布门禁 | 指 `2026-06-13` 的 `xs/s/m` 生产就绪检查 |
| 路由行为 | routing behavior / 路由行为 | 指读取索引后选择模块、避免过载、识别边界的能力 |
| 长文档处理 | long-document handling / 长文档处理 | 只能写“增强”和“专项验证”，不能写“完全解决” |

## 4. 两级目标与验收线

### 4.1 北大核心等强普刊最低线

满足以下条件后，可以认为具备中文强普刊或北大核心应用型稿件的基本完整度：

| 条件 | 最低要求 |
|---|---|
| 论文定位 | 明确是应用型系统 / 工程实现与验证论文 |
| 文献支撑 | Related Work 至少覆盖 5 条技术脉络，每条有真实引用 |
| 真实语料 | 至少 2 类真实团队知识语料 |
| 查询集 | 30-50 个 judged queries |
| baseline | 至少 2 个严肃 baseline：BM25/关键词 chunk baseline、chunk-only retrieval baseline |
| 指标 | `first-hit rank`、MRR、nDCG@k、recall@k、precision@k、latency |
| 失败分析 | 必须包含边界识别、troubleshooting、短词/缩略词、长文档、写路径证据不足 |
| 表图 | 至少 2 图 4 表进入正文 |
| 边界 | 明确不能外推到所有 RAG、`l/xl`、充分 live routing、充分写路径 |

### 4.2 SCI 四区目标线

SCI 四区不是靠翻译中文稿即可达到。若要尝试 SCI 四区，建议满足以下增强条件：

| 条件 | 建议要求 |
|---|---|
| 真实语料 | 3 类语料，覆盖架构文档、runbook/运维文档、API/产品技术文档 |
| 查询集 | 80-120 个 judged queries |
| baseline | 至少 3 个：BM25/关键词、chunked vector retrieval、chunked hybrid retrieval |
| 消融 | 至少 3 个：结构化模块、人工审核、metadata/caveats/scope、MCP 按需加载或 policy-aware retrieval |
| 长文档 | 至少 3 个长文档样例，保存输入、chunk、输出模块、失败类型 |
| 写路径 | create/update/review/approve/search-after-write/load 的端到端验证 |
| 文献 | 相关工作形成主题综述，而不是背景引用堆叠 |
| 英文稿 | 按目标期刊格式重写，不直接机械翻译中文终稿 |

## 5. 总体路线

### Phase 0：冻结论文主线

目标：防止后续写作跑偏。

产出文件：

| 文件 | 内容 |
|---|---|
| `D:\tyh\paper-assets\writing\storyline.md` | 一句话论点、贡献、边界、目标期刊路线 |
| `D:\tyh\paper-assets\writing\claim-evidence-lock.md` | 终稿允许写的 claim 与证据状态 |

任务：

- [ ] 确定中文主标题：建议优先使用“面向小中型团队知识库的结构化知识模块管理与 MCP 按需加载系统”。
- [ ] 确定英文备选标题：建议使用 “Design and Validation of a Structured Knowledge Module System for Small-to-Medium Team Knowledge Bases”。
- [ ] 把贡献固定为 1 个主贡献和 2 个支撑贡献。
- [ ] 删除或降级所有“全面优于 RAG”“自动路由成熟”“长文档完全解决”类表达。
- [ ] 把所有 claim 分成“已支持”“部分支持”“待补证据”。

完成标准：

- [ ] 任何摘要、引言、结论中的强结论都能在 `claim-evidence-lock.md` 找到证据。
- [ ] 终稿不再出现“后续如果补全”“当前这篇稿件还没有”等作者工作台句子。

### Phase 1：正式文献检索与相关工作重建

目标：把 Related Work 从占位骨架升级为可投稿章节。

产出文件：

| 文件 | 内容 |
|---|---|
| `D:\tyh\paper-assets\references\literature-search-plan.md` | 检索式、数据库、筛选标准 |
| `D:\tyh\paper-assets\references\reference-candidates.csv` | 候选文献清单 |
| `D:\tyh\paper-assets\references\claim-citation-map.md` | 每个论文 claim 对应的文献支撑 |
| `D:\tyh\paper-assets\writing\02-related-work.md` | 正式相关工作章节 |

必须覆盖的 5 条文献脉络：

| 脉络 | 服务的论文论点 | 需要的文献类型 |
|---|---|---|
| RAG 与 chunk-based retrieval | 承认主流路线，说明 chunk 在语义召回上的价值与治理边界 | RAG、dense retrieval、hybrid retrieval、chunking strategy |
| 团队知识管理与软件工程知识复用 | 支撑小中型团队知识库不是玩具场景 | software knowledge management、developer documentation、team knowledge reuse |
| human-in-the-loop 知识审核 | 支撑人工 review/approve 的必要性 | human-in-the-loop AI、knowledge curation、quality control |
| git-native / docs-as-code / versioned knowledge | 支撑 JSON + Git 审查、追踪、版本化 | docs-as-code、version control for documentation、collaborative documentation |
| agent 工具调用与运行时上下文加载 | 支撑 MCP 按需加载，不是整库注入 | tool use、agent context management、MCP official spec / docs |

写作要求：

- [ ] 每个小节按“现有路线解决了什么 -> 仍留下什么问题 -> 本文如何定位”组织。
- [ ] 不把 chunk-only 写成 strawman。chunk-based retrieval 的优势要写出来。
- [ ] 对 MCP 可引用官方规范或项目文档，不能只引用二手博客。
- [ ] 如果某个 claim 找不到文献支撑，要改成项目内证据支持的工程观察。

完成标准：

- [ ] `相关工作` 不再承认“尚未补入正式文献”。
- [ ] 每个核心背景 claim 至少有一条真实来源或被改为保守表述。
- [ ] 文献综述不超过正文篇幅比例，避免把应用系统论文写成综述。

### Phase 2：补齐最低可发表实验包

目标：把“现有证据整理”升级为“验证协议 + 对比实验 + 失败分析”。

#### 2.1 Judged queries 与 baseline 对比

产出文件：

| 文件 | 内容 |
|---|---|
| `D:\tyh\paper-assets\eval\corpus-inventory.csv` | 语料元信息 |
| `D:\tyh\paper-assets\eval\query-guidelines.md` | 查询标注规则 |
| `D:\tyh\paper-assets\eval\judged-queries.jsonl` | 查询、相关模块、边界标签 |
| `D:\tyh\paper-assets\eval\baseline-plan.md` | baseline 配置 |
| `D:\tyh\paper-assets\results\main-comparison.csv` | 主实验结果 |
| `D:\tyh\paper-assets\results\main-comparison.md` | 可写进论文的结果解释 |

最小设计：

| 项目 | 北大核心等强普刊 | SCI 四区目标 |
|---|---:|---:|
| 语料 | 2 类 | 3 类 |
| judged queries | 30-50 | 80-120 |
| baseline | 2 个 | 3 个 |
| 指标 | MRR、nDCG@k、recall@k、precision@k、latency | 加 context cost、failure-rate 分解 |

查询类型必须覆盖：

- [ ] in-scope factual retrieval
- [ ] procedure / how-to 查询
- [ ] decision / tradeoff 查询
- [ ] troubleshooting 查询
- [ ] out-of-scope 边界查询
- [ ] 短词、缩略词、同义词、大小写变化
- [ ] 跨模块综合查询

写入论文位置：

- 第 5 节“评估方法”：写语料、查询集、baseline、指标、判定规则。
- 第 6 节“结果”：写主结果表和 corpus-wise breakdown。
- 第 7 节“失败分析”：写代表性失败和边界。

#### 2.2 路由行为与边界识别

产出文件：

| 文件 | 内容 |
|---|---|
| `D:\tyh\paper-assets\eval\routing-suite.jsonl` | 20 个左右路由测试场景 |
| `D:\tyh\paper-assets\results\routing-results.csv` | 应加载模块、实际加载模块、是否过载、是否应拒答 |
| `D:\tyh\paper-assets\results\routing-failure-cases.md` | OAuth/JWT、troubleshooting 等失败说明 |

最小设计：

- [ ] 从现有 OAuth 5 场景扩展到约 20 场景。
- [ ] 保留 OAuth/JWT 作为 out-of-scope 边界案例。
- [ ] 加入 partial-scope：问题一部分在库内，一部分在库外。
- [ ] 加入 troubleshooting：redirect/debug/error handling。
- [ ] 记录模型是否加载 3-6 个模块，分析模块粒度带来的加载开销。

完成标准：

- [ ] 只写“受控场景下有用”，不写“自主路由成熟”。
- [ ] 失败案例必须进入正文或表格，不能只放附录。

#### 2.3 长文档专项

产出文件：

| 文件 | 内容 |
|---|---|
| `D:\tyh\paper-assets\eval\long-doc-manifest.md` | 文档长度、来源、预期模块 |
| `D:\tyh\paper-assets\results\long-doc-results.csv` | chunk 数、重试次数、模块数、失败类型 |
| `D:\tyh\paper-assets\results\long-doc-analysis.md` | 长文档结果解释 |

最小设计：

- [ ] 选 3 个长文档样例，覆盖短 / 中 / 较长输入。
- [ ] 记录字符数、chunk 数、chunk size、overlap、JSON retry、跨块去重。
- [ ] 人工判断模块完整性、重复、语义边界。
- [ ] 保存原始输出和批准后的模块样例。

写法边界：

- [ ] 可以写“实现层面对长文档做了分块、重试和去重增强”。
- [ ] 可以写“专项结果显示风险降低或仍存在边界”。
- [ ] 不能写“长文档问题已完全解决”。

#### 2.4 写路径 / upload / create 路径

产出文件：

| 文件 | 内容 |
|---|---|
| `D:\tyh\paper-assets\results\write-path-e2e.md` | create/update/review/approve/search/load/delete 流程结果 |
| `D:\tyh\paper-assets\results\write-path-e2e.json` | 可复核原始记录 |

最小设计：

- [ ] create module
- [ ] update module
- [ ] review staging module
- [ ] approve module
- [ ] search-after-write
- [ ] load-after-write
- [ ] delete 或 archive 行为
- [ ] text upload -> staging -> approve

写法边界：

- [ ] 如果结果有限，只写“补充验证了关键写路径”。
- [ ] 不把写路径写成和读路径同等充分，除非补齐足够端到端证据。

### Phase 3：终稿章节重构

目标：把 `v2` 改成真正的论文稿，而不是证据说明稿。

推荐终稿结构：

| 章节 | 建议标题 | 主要任务 |
|---|---|---|
| 标题 | 面向小中型团队知识库的结构化知识模块管理与 MCP 按需加载系统 | 准确、可检索、不过度 |
| 摘要 | 摘要 | 场景问题、方法、关键证据、边界 |
| 1 | 引言 | 场景、问题、缺口、贡献、边界 |
| 2 | 相关工作与技术定位 | 文献脉络和本文差异 |
| 3 | 设计目标与系统架构 | 为什么需要模块、审核、Git、MCP |
| 4 | 实现方法 | 抽取、staging、approve、索引、CLI/MCP、长文档增强 |
| 5 | 评估方法 | 研究问题、语料、baseline、指标、判定规则 |
| 6 | 结果分析 | 协议、门禁、对比检索、路由、长文档、写路径 |
| 7 | 失败案例与适用边界 | 具体失败、机制解释、不可外推范围 |
| 8 | 讨论 | 工程意义、与 chunk-only 的关系、治理成本 |
| 9 | 结论 | 贡献、证据、边界、下一步 |
| 附录 | 证据登记与更多结果 | Claim-Evidence、完整测试表、补充失败案例 |

章节改造要求：

| 当前问题 | 终稿处理 |
|---|---|
| 第 2 节承认“还没补文献” | 补文献后改成正式 Related Work |
| 第 5 节按文件列证据 | 改成“评估方法”，按研究问题和指标组织 |
| 第 6 节偏口头说明 | 改成表驱动结果，每个结论有数据或案例 |
| 第 4 节像代码走查 | 保留可复现逻辑，减少源码定位语气 |
| 摘要反复列证据 | 保留关键数字，更多写问题-方法-结果-边界 |
| notes 和 evidence register | 放内部材料或附录，不进正文主干 |

### 各节段落任务规则

- [ ] 每段只做一个任务：背景、问题、方法、结果、比较、解释、局限。
- [ ] 每段首句直接给出本段主任务，不用空泛承接句。
- [ ] 结果段落不混入大段讨论。
- [ ] 讨论段落不重复表格数据。
- [ ] 局限段落必须指向具体机制或证据缺口。

## 6. 图表计划

正文建议至少包含 2 图 5 表。

| 编号 | 类型 | 内容 | 进入章节 | 优先级 |
|---|---|---|---|---|
| 图 1 | 架构图 | raw text -> `.staging` -> review/approve -> JSON/index -> CLI/MCP -> on-demand loading | 第 3 节 | P0 |
| 图 2 | 序列图 | MCP 先读索引，再 search/load/list，而不是整库注入 | 第 3 或第 4 节 | P1 |
| 表 1 | 模块字段表 | `overview/details/examples/references/caveats` 的治理作用 | 第 3 节 | P0 |
| 表 2 | 验证矩阵 | 验证问题、证据来源、指标、支持结论、边界 | 第 5 节 | P0 |
| 表 3 | 主实验表 | Knowledge Manager 与 baseline 的 MRR、nDCG、recall、precision、latency | 第 6 节 | P0 |
| 表 4 | release gate 与延迟 | `xs/s/m`、`ready_for_production`、`search_http`、`mcp_search_modules` | 第 6 节 | P0 |
| 表 5 | 路由与失败案例 | `4/5` 现有结果、扩展场景、OAuth/JWT、troubleshooting | 第 6/7 节 | P0 |
| 表 6 | 长文档专项 | 文档长度、chunk 数、重试、模块数、失败类型 | 第 6/7 节 | P1 |
| 表 7 | 写路径 E2E | create/update/review/approve/search/load/delete | 第 6/7 节 | P1 |

## 7. 写作顺序

终稿不要从摘要开始写。推荐顺序：

1. `05-评估方法`
2. `06-结果分析`
3. `07-失败案例与适用边界`
4. `03-设计目标与系统架构`
5. `04-实现方法`
6. `08-讨论`
7. `02-相关工作与技术定位`
8. `01-引言`
9. `09-结论`
10. `摘要`
11. `标题、关键词、基金/致谢、代码与数据可用性`

理由：

- 评估和结果决定摘要能写多强。
- 局限性先写清楚，能防止引言和讨论过度拔高。
- 相关工作应服务最终论点，最好在结果和边界稳定后写。

## 8. 语言与表述控制

### 可以写的强度

| 证据状态 | 推荐动词 |
|---|---|
| 直接实验支持 | 表明、显示、验证了 |
| 小样本或间接支持 | 初步表明、提示、在当前证据下显示 |
| 工程设计合理性 | 有利于、便于、支持 |
| 仍需谨慎 | 可能、仍需进一步验证 |

### 不应写的表达

- [ ] 全面优于所有 RAG
- [ ] 首次提出
- [ ] 显著领先
- [ ] 革命性
- [ ] 完全解决长文档问题
- [ ] 已证明大规模场景同样成立
- [ ] 自主路由已经成熟
- [ ] 写路径已被充分验证

### 推荐替代表达

| 高风险表达 | 推荐替代表达 |
|---|---|
| 全面优于 chunk-based RAG | 在当前评估范围内显示出更好的工程适配性 |
| 显著提升 | 在若干指标上优于或接近 baseline，具体结果见表 |
| 解决长文档问题 | 对长文档抽取做了分块、重试和去重增强 |
| 实现自主路由 | 在受控场景中观察到可用的模块选择行为 |
| 企业级可用 | 在 `xs/s/m` 规模的 release gate 中达到设定门槛 |

## 9. 投稿路线选择门槛

### Gate 1：文献门槛

- [ ] Related Work 至少有 5 条真实脉络。
- [ ] 每条脉络有代表性论文或官方规范来源。
- [ ] 所有背景性强 claim 都有引用或已降级。

未通过：不能称为终稿，只能称为内部稿。

### Gate 2：实验门槛

- [ ] 至少 2 类语料。
- [ ] 至少 30-50 个 judged queries。
- [ ] 至少 2 个 baseline。
- [ ] 主指标表完整。
- [ ] 失败分析进入正文。

未通过：不建议投北大核心等强普刊。

### Gate 3：SCI 四区门槛

- [ ] 至少 3 类语料。
- [ ] 至少 80-120 个 judged queries。
- [ ] 至少 3 个 baseline。
- [ ] 至少 3 个消融。
- [ ] 长文档和写路径有专项验证。
- [ ] 英文稿按目标期刊重写。

未通过：可以投中文强普刊，不建议强行冲 SCI 四区。

### Gate 4：终稿语言门槛

- [ ] 摘要中每个结果数字都能回到正文表格。
- [ ] 引言中每个贡献都有后文对应章节。
- [ ] 讨论中每个外推都带边界。
- [ ] 结论不新增数据、不新增文献、不新增 promise。
- [ ] 全文每段基本只承担一个任务。

## 10. 推荐时间表

### 第 1 周：冻结主线与文献

- [ ] 完成 storyline 和 claim-evidence-lock。
- [ ] 完成文献检索计划。
- [ ] 建立 reference-candidates.csv。
- [ ] 写出 Related Work 的分组大纲。

### 第 2 周：语料与 judged queries

- [ ] 选择 2-3 类真实语料。
- [ ] 建立 corpus-inventory.csv。
- [ ] 写 query-guidelines.md。
- [ ] 标注 30-50 个最低查询集。

### 第 3 周：baseline 与主实验

- [ ] 冻结 2 个最低 baseline。
- [ ] 跑主对比实验。
- [ ] 生成 main-comparison.csv 和结果表。
- [ ] 同步记录失败样例。

### 第 4 周：专项验证

- [ ] 扩展路由测试到约 20 场景。
- [ ] 完成长文档专项。
- [ ] 完成最小写路径 E2E。
- [ ] 初步决定是否具备 SCI 四区路线潜力。

### 第 5 周：写系统与实验正文

- [ ] 写评估方法。
- [ ] 写结果分析。
- [ ] 写失败案例与适用边界。
- [ ] 写系统架构与实现方法。

### 第 6 周：写引言、相关工作、讨论

- [ ] 完成正式 Related Work。
- [ ] 完成引言。
- [ ] 完成讨论和结论。
- [ ] 完成摘要和关键词。

### 第 7 周：审前自检与改稿

- [ ] 做 claim-evidence 全文核对。
- [ ] 做 AI 套话清理。
- [ ] 做表图编号、引用、术语一致性检查。
- [ ] 决定北大核心等强普刊版或 SCI 四区版。

### 第 8 周：投稿版整理

- [ ] 按目标期刊格式调整。
- [ ] 完成参考文献格式。
- [ ] 完成数据与代码可用性声明。
- [ ] 完成投稿信或中文投稿说明。

## 11. 下一步立即执行项

建议下一轮先做 3 件事：

1. 创建 `storyline.md` 和 `claim-evidence-lock.md`，把主线和 claim 全部锁定。
2. 开始外部文献检索，优先补 RAG/chunking、团队知识管理、human-in-the-loop、docs-as-code、agent context loading 五条线。
3. 设计 `judged-queries.jsonl` 的 schema 和 30-50 个最低查询集，准备后续 baseline 对比。

如果时间有限，优先顺序是：文献检索和 Related Work、judged queries、baseline 对比。没有这三项，终稿很容易仍停留在“项目说明 + 证据登记”的层次。
