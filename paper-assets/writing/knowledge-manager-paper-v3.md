# 面向小中型团队知识库的结构化知识模块管理与 MCP 按需加载系统

## 摘要

面向 AI 协作开发的团队知识库正在承担两类任务：一方面，它需要让开发者和代码代理快速定位可用知识；另一方面，它还需要保留知识的责任边界、审核记录和维护路径。仅以文本切块作为组织单元的检索增强生成（retrieval-augmented generation, RAG）方案为知识接入提供了成熟路线，但在小中型团队知识库中，知识片段能否被人工确认、能否被版本化审查、能否按任务边界进入上下文，同样会影响系统长期可用性。

本文围绕 Knowledge Manager 设计并实现了一种应用型知识管理系统。系统以结构化知识模块为基本单元，采用 `extract-review-approve` 工作流控制知识入库，使用 git-native JSON 存储支持审查与追踪，并通过命令行界面（command-line interface, CLI）和模型上下文协议（Model Context Protocol, MCP）双接口提供知识访问。MCP 侧提供索引读取、模块搜索、模块加载和分类访问，使客户端能够先读取索引，再按任务需要加载相关模块，而不是一次性注入全部知识库内容。

现有可复核证据表明，Knowledge Manager 的读路径、搜索路径和协议路径已形成较清晰的工程链路，并覆盖抽取、审核、批准到服务的主要环节。MCP 协议测试在当前项目报告中取得 `14/14` 通过；`2026-06-13` 的 release gate 在 `xs`、`s` 和 `m` 三个规模上均给出 `ready_for_production=true`；`search_http` 与 `mcp_search_modules` 已有 mean 和 p95 时延记录；基于 OAuth 知识库的受控路由测试显示 5 个场景中有 4 个完成正确模块选择。本文将这些结果解释为小中型团队知识库场景下的工程可用性证据，而不是普遍优越性证明。当前证据的强项集中在读路径、搜索路径和协议路径；长文档、写路径、真实会话中的自主路由，以及多语料 baseline 对比仍属于需要独立验证的范围。

**关键词**：知识管理；团队知识库；结构化知识模块；模型上下文协议；检索增强生成；人工审核；Git 原生存储

## 1 引言

AI 协作开发使团队知识库从“文档归档”逐渐转向“人和代码代理共同使用的工作基础设施”。在传统文档使用方式中，知识库主要服务检索、阅读和人工判断；在 LLM 辅助开发场景中，知识还会被自动摘要、引用、转写为代码修改建议，甚至进入工具调用链路。因此，知识是否可检索只是一个起点，知识是否可审查、是否有明确适用边界、是否能在版本演化中被追踪，也会直接影响系统可靠性。

RAG 为大语言模型访问外部知识提供了重要技术路线。早期 RAG 工作通过结合参数化模型与非参数化检索记忆，缓解了模型知识更新和来源可追踪问题[1]；dense retrieval 和检索基准进一步推动了开放域问答和文本检索系统的发展[2-5]。这些工作说明，将外部文本转化为可检索单元并在生成前召回相关内容，是 LLM 使用外部知识的有效方式。

小中型团队知识库的问题并不完全等同于开放域问答。团队内部知识往往包含架构决策、接口约束、部署经验、排障步骤和 caveat。一个文本 chunk 可以命中查询，却不一定说明该知识属于哪个决策边界、是否已经过团队确认、是否仍适用于当前版本，或者与哪些模块共同构成完整流程。对于需要长期维护的团队知识库，这些治理问题会逐渐变成比单次召回更稳定的摩擦来源。

Knowledge Manager 的设计动机来自这一类工程场景。本文不将系统定位为新的检索算法，也不主张其全面替代 chunk-based RAG。本文关注的问题更窄：在小中型团队知识库中，是否可以把知识组织成结构化、经人工审核、可版本化的模块，并通过 MCP 在运行时按需加载，从而更好地支持 AI 协作开发中的知识复用和治理。

本文的主要贡献包括三个方面。第一，提出并实现了以结构化知识模块为核心的知识管理系统，将知识从原始文本转化为包含 `overview`、`details`、`examples`、`references` 和 `caveats` 等字段的模块。第二，设计了 `extract-review-approve` 工作流和 git-native JSON 存储，使知识在进入正式库前经过人工审核，并能用 Git 完成 diff、review 和 version。第三，系统通过 CLI 与 MCP 双接口提供知识服务，并给出协议合规、发布门禁、检索时延、路由行为和评测框架能力等工程验证结果。

本文的结论限定在当前证据能够覆盖的范围内。现有结果能够说明 Knowledge Manager 在 `xs/s/m` 规模、读路径、搜索路径和协议路径上达到项目设定的可运行门槛。对于 `l/xl` 规模、长文档稳健性、完整写路径和 live conversation 下的自主路由，本文只作为边界问题讨论，不作为已经成立的结论。

## 2 相关工作与技术定位

### 2.1 RAG 与 chunk-based retrieval

RAG 研究关注如何让语言模型在生成时访问外部知识。Lewis 等提出的 RAG 框架将 seq2seq 模型与基于检索的非参数化记忆结合，用于知识密集型 NLP 任务[1]。Dense Passage Retrieval 使用双编码器学习问题和段落表示，推动了开放域问答中的 dense retrieval 路线[2]。ColBERT 进一步通过 late interaction 改善检索效率与效果之间的平衡[3]。这些工作共同说明，面向大规模文本集合的语义召回是 LLM 知识增强的重要基础。

chunk-based retrieval 的优势在于接入成本低、适用范围广，并且能复用成熟的信息检索和向量检索框架。BEIR 等基准显示，BM25、dense retrieval、late-interaction 和 reranking 方法在不同数据集上各有表现，BM25 仍是稳健 baseline[4]。因此，本文不会把 chunk-based retrieval 描述为低质量或过时方案。相反，本文在对照评估协议中将其保留为必要比较对象。

chunk-based retrieval 与本文工作的差异主要在知识组织单位。前者通常以文本片段为检索与上下文拼接单位，重点解决“能否召回相关文本”；Knowledge Manager 则把知识组织成经审核的结构化模块，重点处理“召回内容是否有可审查边界、是否可维护、是否能按任务加载”。长上下文和 RAG 相关研究也提醒，扩大上下文窗口并不自动消除检索组织和上下文选择问题[6]。因此，本文与 chunk-based retrieval 的关系不是算法层面的替代，而是面向小中型团队知识治理场景的一种工程取舍。

### 2.2 软件工程知识管理与团队知识复用

软件工程长期被认为是知识密集型活动。知识管理研究指出，软件开发过程涉及需求、架构、设计决策、代码经验和项目上下文等多类知识，这些知识如果不能被保存和复用，会影响团队协作和维护[9]。在 LLM 辅助开发出现后，团队知识库的使用对象还包括代码代理和编辑器插件，知识管理的接口从“人读文档”扩展到“模型按任务读取上下文”。

开发者文档检索相关工作也说明，工程任务中的文档并不只是背景说明，而会直接影响代码生成和任务完成质量。例如 DocPrompting 通过检索文档来支持代码生成，显示了开发者文档在模型辅助编程中的作用[11]。这类研究与本文的共同点在于，都承认工程知识需要进入模型工作流；不同点在于，本文更强调知识进入模型之前的结构化、审核和版本治理。

因此，Knowledge Manager 更适合被放在“团队知识治理与 AI 协作开发基础设施”的脉络中理解。它不是通用问答系统，也不是开放域知识库，而是面向小中型团队内部知识复用的应用型系统。

### 2.3 人工审核知识工作流

human-in-the-loop 研究通常把人工参与视为机器学习系统生命周期的一部分，而不是自动化失败的补丁。相关综述从数据标注、模型训练、评估反馈和系统纠错等角度讨论了人在系统中的作用[12-13]。在人机协作知识扩展场景中，也有研究利用人工验证来控制知识质量[14]。

Knowledge Manager 保留 `extract-review-approve` 流程，原因并不是假设抽取模型不重要，而是团队知识往往需要确认适用条件、风险和上下文。一个自动抽取出的模块即使语义上相似，也可能遗漏 caveat，或者把已经过期的实践写入正式知识库。人工审核在这里承担的是治理边界角色：它决定哪些知识可以被代理直接引用，哪些内容仍停留在 staging 状态。

### 2.4 可版本化文档与 Git 原生存储

Git 原生存储与 docs-as-code 也提供了相近的协作思路。Documentation-as-code 相关研究强调把文档纳入版本控制和工程协作流程[10]。Knowledge Manager 采用 JSON 模块和 `index.json`，使团队可以使用已有的代码审查、diff 和版本管理习惯管理知识变更。这个选择本身并不新，但它适合本文关注的小中型团队维护场景。

### 2.5 LLM 工具调用、MCP 与按需上下文加载

LLM agent 研究表明，语言模型可以通过外部行动和工具调用扩展能力。ReAct 将推理与行动结合，使模型在任务过程中交替生成推理和外部操作[15]；Toolformer 和 Gorilla 等工作进一步讨论了模型学习或调用外部工具、API 的能力[16-17]。这些研究说明，模型使用外部能力已经成为 LLM 应用的重要方向。

MCP 为 LLM 应用和外部数据源、工具之间的连接提供了标准化接口。官方规范将 MCP 描述为连接 LLM 应用与外部数据源和工具的开放协议，并区分 hosts、clients 和 servers；协议使用 JSON-RPC 2.0，并支持 resources、prompts 和 tools 等服务端特性[19]。其中 resources 用于向客户端暴露上下文数据，tools 用于向模型暴露可调用函数[20-21]。需要说明的是，本文的本地协议测试报告采用 MCP `2024-11-05` 协议版本；参考文献中的 MCP 官方页面用于说明协议概念和 resources/tools 设计，不表示本文已完成对 `2025-06-18` 版本的全量合规验证。

Knowledge Manager 的 MCP 接口正是基于这一脉络实现。系统通过 `knowledge://index` 暴露索引资源，通过 `search_modules` 和 `load_module` 提供模块搜索与加载能力，通过 `list_categories` 支持分类访问。这种方式使客户端可以先读索引，再按任务加载模块，避免把整个知识库一次性放入上下文。需要说明的是，MCP 只提供协议层接口，并不自动保证知识质量、访问控制或治理效果；这些仍需要系统自身实现和评估。

### 2.6 检索评价指标与 baseline

检索系统通常需要同时报告命中、排序和效率指标。nDCG 源自基于累积增益的信息检索评价方法，适合衡量排序位置对结果质量的影响[7]；BM25 及其概率相关框架是传统信息检索的重要基础，也常被作为 lexical baseline[8]。BEIR 进一步强调跨数据集、跨检索方法评估的重要性，并显示 BM25 仍然是值得保留的稳健基线[4]。

基于上述评价传统，本文将 BM25/关键词切块检索和 chunk-only retrieval 作为对照实验的必要基线，并采用 `first-hit rank`、MRR、nDCG@k、recall@k、precision@k 和 latency 描述检索排序质量与运行代价。当前项目代码已经支持这些 rank-based 指标和若干 failure-based 字段；本文只将其作为评估框架能力报告，不把尚未运行的多语料 baseline 结果写成实验发现。

## 3 设计目标与系统架构

### 3.1 场景与设计目标

Knowledge Manager 面向的是小中型团队知识库，而不是开放域网页语料或超大规模企业知识平台。本文假定知识规模仍处于可人工治理范围内，团队希望知识既能被开发者维护，也能被 AI 协作客户端按任务读取。

系统设计目标包括四点。第一，知识单元应保留语义边界，使一个模块对应相对完整的概念、流程或实践。第二，知识入库应支持人工审核，以便确认适用条件、遗漏风险和团队当前实践。第三，知识存储应便于审查和追踪，尽量复用开发团队已有版本控制习惯。第四，运行时访问应支持按需加载，避免将整个知识库无差别注入上下文。

**图 1 Knowledge Manager 的知识流转与按需加载路径**

```text
原始文档
  -> extract
  -> .staging/*.json
  -> review / approve
  -> category/module.json + index.json
  -> CLI: list / search / show / review
  -> MCP: knowledge://index -> search_modules -> load_module / list_categories
```

图 1 概括了系统的基本流转路径。前半段强调知识从原始文本进入正式库之前需要经过 staging 和人工审核，后半段强调运行时访问不直接加载整个知识库，而是先通过索引或搜索定位模块，再加载与任务相关的少量内容。

### 3.2 结构化知识模块

Knowledge Manager 以结构化知识模块作为基本组织单元。根据项目 README，模块至少包含 `overview`、`details`、`examples`、`references` 和 `caveats` 等字段。表 1 给出这些字段在系统中的作用。

**表 1 结构化知识模块字段及其治理作用**

| 字段 | 主要内容 | 治理作用 |
|---|---|---|
| `overview` | 模块主题与简要说明 | 帮助人和模型快速判断模块是否相关 |
| `details` | 具体机制、步骤或实践说明 | 承载可复用知识主体 |
| `examples` | 示例、命令、片段或使用方式 | 支持开发者和代理复现 |
| `references` | 来源文档或相关模块线索 | 支持追踪来源和交叉引用 |
| `caveats` | 限制、风险、适用条件 | 避免模型把知识泛化到不适用场景 |

这种结构化并不是为了形式整齐，而是为了让知识在进入检索和加载链路之前就具有可审查字段。与普通 chunk 相比，模块字段能把“这条知识讲什么、怎么用、从哪里来、有什么边界”放到同一对象中。

### 3.3 `extract-review-approve` 工作流

Knowledge Manager 不把模型抽取结果直接写入正式库。系统先将原始文本抽取为候选模块并放入 `.staging/`，随后由人工 review，确认后执行 approve，使模块进入正式分类目录并更新索引。这一流程可概括为：

```text
raw text -> extract -> .staging/*.json -> review -> approve -> category/module.json -> index.json -> CLI/MCP serve
```

该流程会增加入库阶段的人工成本，但它使团队能在知识被代理复用前检查模块边界、caveat 和相关关系。对于团队内部知识，这一步并不只是质量控制，也是责任边界确认。

### 3.4 git-native JSON 存储

Knowledge Manager 将 approved module 存为 JSON 文件，并维护 `index.json`。这种 git-native 存储方式使知识变更可以通过 Git diff、review 和 version 进行追踪。对于小中型团队，复用现有版本控制习惯比引入复杂专用知识平台更贴近既有工作流。

Git 原生存储也使知识治理更接近代码治理。团队可以看到某次变更修改了哪个模块、删除了哪个 caveat、增加了哪些引用或示例。本文并不把这一点描述为技术新颖性，而是把它视为应用系统设计中的维护性取舍。

### 3.5 MCP 按需加载

Knowledge Manager 的运行时访问通过 CLI 和 MCP 双接口提供。CLI 面向人工维护和检查，MCP 面向 AI 客户端和编辑器集成。根据项目 README 和 MCP 测试报告，系统提供 `knowledge://index`、`search_modules`、`load_module` 和 `list_categories` 等能力。

MCP 按需加载的基本路径是：客户端先读取索引或分类信息，再根据任务搜索模块，最后加载少量相关模块进入上下文。这个设计把“定位”和“加载”拆开，使上下文构造更接近任务需求。对于小中型团队知识库，这种访问顺序有助于保留模块边界，也便于分析哪些模块被实际使用。

**图 2 MCP 按需加载序列示意**

```text
AI client -> MCP server: read knowledge://index
AI client -> MCP server: search_modules(query)
MCP server -> AI client: candidate modules
AI client -> MCP server: load_module(module_id)
MCP server -> AI client: selected structured module
AI client: use selected module in task context
```

图 2 展示了 MCP 侧的访问顺序。系统先暴露索引和候选模块，再加载被选中的结构化模块；这一顺序使客户端能够把“知道有哪些知识”和“把哪些知识放入上下文”分开处理。

## 4 实现方法

### 4.1 存储结构与索引

Knowledge Manager 的知识库由分类目录、模块 JSON 文件、`.staging/` 和 `index.json` 组成。正式模块按类别存放，staging 模块用于承接尚未通过人工审核的抽取结果。索引文件用于 MCP 和 CLI 侧快速发现模块。

这种实现方式使系统在文件层面保持透明。维护者可以直接查看模块内容，也可以在版本控制中审查每次变更。对于目标场景而言，这种透明性更贴近开发团队已有的代码审查习惯。

### 4.2 抽取器与长文档增强

Extractor 负责从原始文本生成结构化模块。当前实现并不是将长输入一次性发送给模型，而是通过 `_chunk_text()` 分块处理，并由 `_effective_chunk_size()` 将实际 chunk 大小限制在 `4000` 字符以内。抽取过程中会记录 chunk 数、chunk size 和 overlap 等信息。

分块处理后，系统维护 `seen_ids` 集合，对跨 chunk 重复生成的模块 ID 进行去重。这一处理针对长文本抽取中常见的重复模块问题。它不能保证长文档抽取一定完整，但旨在降低同一知识点重复进入知识库的概率。

Extractor 还实现了 JSON retry。若模型返回内容无法解析为 JSON 数组，系统会将错误信息回写并要求重新输出 JSON 数组；若模型返回 JSON 对象而非数组，也会触发重试。这个机制说明系统没有把 LLM 输出视为天然可靠，而是设置了格式恢复路径。

抽取提示词要求保留源文本原语言。对于中文团队文档或中英文混合文档，这一点可以减少抽取阶段的语境丢失。当前证据只能说明系统在实现层面对长文档和输出格式做了增强，还不能说明长文档问题已经被充分解决。

### 4.3 CLI 与 MCP 服务接口

CLI 提供 `init`、`list`、`search`、`show`、`review` 和 `serve` 等命令，主要服务人工维护、检查和本地调试。MCP 服务则面向外部客户端，提供资源读取与工具调用能力。两类接口访问同一套模块和索引，避免形成两套知识视图。

MCP 侧的关键接口包括索引资源、模块搜索、模块加载和分类访问。协议测试覆盖了初始化握手、资源列表、索引读取、工具列表、模块搜索、模块加载、分类列表和错误处理。对应用型系统论文而言，这些测试结果表明接口链路不是概念描述，而是已经实现并可运行的服务路径。

### 4.4 工程实现范围

当前实现最稳的部分是读路径、搜索路径和协议路径。写路径虽然在 release gate 中出现了 `module_crud_http`，但 upload、create、复杂修改等操作还缺少与读路径同等强度的端到端证据。本文在结果和讨论中将这一点作为边界处理。

## 5 评估方法

### 5.1 研究问题

本文将现有验证组织为四个研究问题。

**RQ1：协议路径是否可用。** 该问题关注 MCP 握手、资源读取、工具调用和错误处理是否符合预期。

**RQ2：系统在设定规模下是否达到工程运行门槛。** 该问题关注 `xs/s/m` 三档 release gate 和关键搜索路径时延。

**RQ3：结构化索引与按需加载是否能支持受控场景下的模块选择。** 该问题关注模型读取索引后能否选择相关模块，以及是否出现无关模块过载。

**RQ4：系统是否支持可复核的检索评价与失败分解。** 该问题关注 rank-based 指标和 failure-based 字段是否已经在代码中实现，并说明这些指标能否支撑统一语料、统一查询集下的 baseline 对比。

### 5.2 当前已完成验证

当前已完成验证包括三类。第一类是 MCP 协议测试，基于真实 OAuth 知识库覆盖 14 个协议路径测试。第二类是 `2026-06-13` release gate，覆盖 `xs`、`s` 和 `m` 三档规模。第三类是 OAuth 知识库上的 5 个受控路由场景。

这些验证可以支撑系统链路可用性，但不能代替多语料 baseline 对比。它们更适合作为应用系统论文中的工程验证层，而不是完整检索 benchmark。表 2 汇总了当前证据能够支持的结论及其边界。

**表 2 当前验证矩阵及其可支持结论**

| 研究问题 | 已用证据 | 可支持结论 | 主要边界 |
|---|---|---|---|
| RQ1 协议路径是否可用 | MCP 协议测试 `14/14` 通过 | MCP 握手、资源读取、工具调用和错误处理链路已跑通 | 只说明当前协议路径可用，不等同于知识质量或安全治理充分 |
| RQ2 设定规模下是否达到工程门槛 | `2026-06-13` release gate，`xs/s/m` 均为 `ready_for_production=true` | 系统在已测小中规模下达到项目设定运行门槛 | 不能外推到 `l/xl` 或复杂生产环境 |
| RQ3 是否支持受控模块选择 | OAuth 知识库 5 个场景中 4 个模块选择正确 | 结构化索引在小样本受控场景下可支持按需加载 | 场景数量少，不能证明真实会话自主路由成熟 |
| RQ4 是否具备检索评价基础 | 评测代码支持 first-hit rank、MRR、nDCG@k、recall@k 和 failure-based 字段 | 项目具备进一步做 judged baseline 对比的指标基础 | 指标实现不等于多语料对比结果已经完成 |

### 5.3 对照评估协议

为避免把系统验证误写成完整 benchmark，本文将已完成验证与对照评估协议分开表述。已完成验证用于回答协议可用性、发布门禁、时延和探索性路由问题；对照评估协议用于定义检索比较应满足的语料、查询、baseline 和指标条件。这样的划分有两个作用：一是避免夸大当前结果，二是为可复现实验保留统一口径。

对照评估应至少包含两类真实团队知识语料，并在统一查询集上比较 Knowledge Manager、BM25/关键词切块检索和 chunk-only retrieval。查询集应覆盖 factual、procedure、decision、troubleshooting、boundary 和 cross-module synthesis 等类型。若进一步面向更强英文期刊，还可以增加 chunked vector retrieval、hybrid retrieval 和 no-review module baseline，但这些扩展不作为本文已完成结果来叙述。表 3 给出的是后续对照评估协议，不是已经完成的主实验结果。

**表 3 judged query 与 baseline 对照评估协议**

| 项目 | 本文建议的最低对照条件 | 可扩展条件 |
|---|---:|---:|
| 语料类型 | 2 类 | 3 类 |
| judged queries | 30-50 | 80-120 |
| baseline | 2 个 | 3 个以上 |
| 查询类型 | factual、procedure、decision、troubleshooting、boundary、synthesis | 增加更多 out-of-scope 和长文档派生查询 |
| 指标 | MRR、nDCG@k、recall@k、precision@k、latency | 增加 context cost、failure decomposition 和 ablation |

### 5.4 指标

当前评测代码已经支持 `first-hit rank`、MRR、nDCG@k 和 recall@k。对照实验在实施时还应报告 precision@k、mean latency、p95 latency、平均加载模块数或 chunk 数；若能记录上下文 token，则应进一步报告平均上下文成本。

Failure-based 指标应谨慎解释。当前 `false_positive_rate`、`false_negative_rate`、`policy_failure_rate` 和 `retrieval_failure_rate` 更接近工程性失败分解，不等于严格因果归因或标准 IR 混淆矩阵。

## 6 结果分析

### 6.1 MCP 协议路径

MCP 协议测试显示系统接口链路已经跑通。本地 MCP 协议测试报告记录总测试数为 `14`，通过数为 `14`，覆盖初始化握手、资源列表、索引读取、工具列表、模块搜索、模块加载、分类列表和错误处理。

这一结果说明 Knowledge Manager 的 MCP 服务不是静态设计。客户端可以通过协议路径发现资源、调用工具并处理错误。该结果不能说明知识组织方式本身优于 chunk-based retrieval，但能支持“系统具备可接入的 MCP 服务路径”这一工程结论。

### 6.2 发布门禁与搜索时延

`2026-06-13` 的 release gate 在 `xs`、`s` 和 `m` 三档规模上均给出 `ready_for_production=true`。搜索相关路径的 mean 与 p95 时延见表 4。

**表 4 release gate 与搜索路径时延**

| 规模 | release verdict | `search_http` mean / p95 (ms) | `mcp_search_modules` mean / p95 (ms) |
|---|---|---:|---:|
| `xs` | `ready_for_production=true` | 207.113 / 220.442 | 208.454 / 230.392 |
| `s` | `ready_for_production=true` | 370.877 / 380.882 | 476.714 / 486.724 |
| `m` | `ready_for_production=true` | 404.838 / 414.091 | 593.720 / 625.424 |

这些结果支持系统在既定小中规模下的服务化可运行性。它们不应被外推到 `l/xl` 规模，也不应被写成“大规模生产环境已充分验证”。

### 6.3 路由行为

OAuth 知识库上的受控路由测试显示，5 个场景中有 4 个场景完成了正确模块选择，且在这 5 个受控场景中未观察到明显 irrelevant over-loading。这个结果与结构化模块标题、摘要和标签提供索引线索的设计一致。

路由测试同时暴露了边界问题。OAuth/JWT 对比场景中，知识库只覆盖 OAuth，但模型仍可能加载 OAuth 模块并依赖自身常识补全 JWT 对比，而不是明确指出 JWT 超出知识库覆盖范围。redirect troubleshooting 场景中，模型能加载与 redirect 机制相关的模块，但模块摘要和 `caveats` 对排障信号暴露不足。表 5 列出了这类路由观察及其解释边界。

**表 5 路由行为与代表性失败**

| 观察 | 当前结果 | 可支持结论 | 边界 |
|---|---|---|---|
| 受控场景正确选择 | 5 个场景中 4 个正确 | 索引引导的按需加载在小样本场景下可用 | 仅支持探索性结论 |
| irrelevant over-loading | 5 个受控场景中未观察到明显过载 | 模块摘要和分类可能减少无关加载 | 场景数量偏少 |
| OAuth/JWT 边界 | 存在 out-of-scope 识别不足 | 需要边界信号或拒答机制 | 不能依赖模型常识补齐库外知识 |
| troubleshooting | redirect 排障信号弱 | `caveats` 和摘要需要加强 | 当前对“怎么查问题”支持弱于“怎么工作” |

### 6.4 评测框架能力

`retrieval_eval.py` 和 `eval_runner.py` 已支持 rank-based 指标和 failure-based 字段。相关测试覆盖 `first-hit rank`、MRR、nDCG@k、recall@k、baseline delta 和 failure decomposition 的基础行为。

为检查评测链路是否能够在真实模块文件上运行，本文补充执行了一个内置 KB smoke eval。该评测使用项目自带 `kb` 中的 7 个已发布模块，覆盖 architecture、operations 和 search 三类模块；7 个低难度查询均命中对应 required module，并输出 first-hit rank、MRR、nDCG@k、recall@k、false-positive / false-negative rate、policy / retrieval failure rate 等字段。这个结果只能说明评测链路可运行，不能替代多语料 judged baseline 对比。

为降低后续评测实施中的口径风险，本文还构建了候选查询级 baseline dry-run 流程。该流程可读取真实模块、固定候选查询集，并同时输出结构化模块检索、BM25/关键词 chunk baseline 和 chunk-only keyword baseline 的 first-hit rank、MRR、nDCG@5、recall@5、precision@5 与延迟字段。由于这批查询标签尚未完成作者确认，dry-run 输出只用于检查评测链路、模块 ID 映射和结果表结构，不进入本文主结果表。

这些结果说明项目已经具备从功能演示走向正式检索评估的基础。问题在于，指标能力和候选 dry-run 本身不等于实验已经完成。要把“结构化模块更适合小中型团队知识库”写成更强结论，仍需在真实语料和统一 baseline 上运行经过作者确认的 judged query 评估。

### 6.5 结果边界

当前结果的解释范围需要收窄到工程验证和探索性场景测试。现有材料尚未包含多个真实语料上的 judged baseline 对比，也没有足够消融来分离结构化模块、人工审核、metadata 字段和 MCP 按需加载各自的贡献。因此，本文只能说明系统在当前证据范围内具备可运行性和较清晰的治理路径，不能把这一点直接提升为对所有 chunk-based RAG 的性能优越结论。

长文档、写路径和 live conversation 自主路由也应保持同样边界。Extractor 已做分块、重试和去重增强，但缺少长文档专项 benchmark。Release gate 中虽然包含写路径相关项目，但 upload、create、复杂修改等操作缺少与读路径同等强度的端到端证据。

## 7 失败案例与适用边界

知识边界识别不足是当前最明确的失败类型。OAuth/JWT 场景说明，当用户问题部分落在知识库之外时，模型可能加载相邻模块并使用自身常识补全回答。对团队知识库而言，这种行为有风险，因为用户可能误以为答案来自已审核知识库。

troubleshooting 信号不足说明当前模块字段还没有充分覆盖排障类任务。系统已有 `caveats` 字段，但测试材料显示某些模块的 `caveats` 为空，摘要也没有突出 debugging 线索。这意味着系统对说明机制类问题支持较强，对故障定位类问题仍需补充结构化字段和标注规范。

短词和缩略词检索也暴露了匹配脆弱性。`retrieval-accuracy.md` 中 `auth` 查询返回空结果，即使相关模块属于 auth 类别。这说明当前检索机制对短词、缩写和词干变体的处理仍不稳定；在对照评估协议中，这类查询应被单独标记，而不能只用普通长查询覆盖。

长文档处理仍属于实现增强而非充分验证。分块、4k cap、跨块去重和 JSON retry 能降低部分抽取风险，但不能自动证明长文档抽取质量稳定。要检验这一部分，需要保存长文档输入、chunk 过程、输出模块、重复情况、失败类型和人工质量判断。

写路径证据弱于读路径。当前论文最稳的证据集中在 MCP 协议、索引读取、搜索时延和模块加载。写路径、upload、create 和复杂修改需要补充 create/update/review/approve/search-after-write/load 的端到端结果，才能和读路径形成对称叙事。

本文适用范围限定在小中型团队知识库。对于超大规模语料、跨组织知识平台、完全自动治理和强 live-agent autonomy 场景，当前证据不足以支撑推广。本文的价值应被理解为一种面向可人工治理规模的应用型系统方案。

## 8 讨论

Knowledge Manager 的主要意义在于把知识治理纳入 LLM 工作流，而不是只优化检索召回。结构化模块、人工审核、Git 存储和 MCP 加载共同构成了一条从原始资料到运行时上下文的链路。对小中型团队而言，这条链路的价值在于可审查、可追踪和可复用。

与 chunk-only retrieval 相比，Knowledge Manager 的优势不应被简单写成“检索性能更高”。更准确的说法是，在需要人工治理和稳定复用的团队知识库中，结构化模块可以提供更清晰的知识边界。Chunk-based retrieval 仍然是强 baseline，尤其在大规模语义召回上可能更有优势。本文的比较重点应放在工程适配性、维护成本和上下文加载行为上。

人工审核带来的成本也需要正视。`extract-review-approve` 流程会降低入库自动化速度，要求维护者投入审核工作。这个取舍是否值得，取决于知识库规模、团队协作方式和知识被代理复用的风险。如果团队知识变化很快且缺少维护人员，人工审核可能成为负担。

MCP 按需加载便于系统接入 AI 客户端，但协议本身不解决知识质量问题。官方规范也强调实现者需要处理用户同意、数据隐私、工具安全和访问控制[19]。因此，Knowledge Manager 的 MCP 接口只能说明系统具备标准化连接路径，不能替代权限、安全和治理设计。

未来工作应优先补齐三类证据。第一，多语料 judged baseline 对比，用于判断结构化模块相对 chunk-only retrieval 的实际收益与代价。第二，metadata 和 `caveats` 消融，用于解释哪些字段真正改善路由或排障。第三，写路径和长文档专项，用于补齐当前最弱的工程证据。

## 9 结论

本文围绕 Knowledge Manager 提出并实现了一种面向小中型团队知识库的结构化知识模块管理与 MCP 按需加载系统。系统通过结构化模块保存知识边界，通过 `extract-review-approve` 工作流保留人工治理，通过 git-native JSON 存储支持审查与追踪，并通过 CLI 与 MCP 双接口服务人类维护者和 AI 客户端。

现有证据表明，Knowledge Manager 在读路径、搜索路径和协议路径上已形成可复核链路。MCP 协议测试 `14/14` 通过，`2026-06-13` 的 release gate 在 `xs/s/m` 三档达到项目设定门槛，搜索路径已有明确时延记录，受控路由测试显示结构化索引能支持有限场景下的模块选择。这些结果支撑其作为小中型团队知识库应用系统的可行性。

本文结论不应超过当前证据。Knowledge Manager 还不能被表述为对 chunk-based RAG 的普遍替代，也不能证明长文档、写路径、`l/xl` 规模或 live conversation 自主路由已经充分成熟。更稳妥的结论是：在可人工治理的小中型团队知识库中，结构化、经审核并支持 MCP 按需加载的知识模块，在设计上更便于审查和追踪；其复用收益仍需要通过多语料 judged baseline 对比继续检验。

## 数据与代码可用性

本文所用系统代码、README、测试结果和论文辅助材料来自 Knowledge Manager 项目。主文中的协议测试、release gate、路由测试和检索失败案例应在投稿时以匿名仓库或补充材料形式提供，包括评测脚本、原始结果文件和必要的复现实验说明。

## 参考文献

[1] Lewis P, Perez E, Piktus A, et al. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. Advances in Neural Information Processing Systems, 2020, 33: 9459-9474. https://arxiv.org/abs/2005.11401

[2] Karpukhin V, Oguz B, Min S, et al. Dense Passage Retrieval for Open-Domain Question Answering. Proceedings of the 2020 Conference on Empirical Methods in Natural Language Processing, 2020: 6769-6781. https://arxiv.org/abs/2004.04906

[3] Khattab O, Zaharia M. ColBERT: Efficient and Effective Passage Search via Contextualized Late Interaction over BERT. Proceedings of the 43rd International ACM SIGIR Conference on Research and Development in Information Retrieval, 2020: 39-48. https://arxiv.org/abs/2004.12832

[4] Thakur N, Reimers N, Rueckle A, Srivastava A, Gurevych I. BEIR: A Heterogeneous Benchmark for Zero-shot Evaluation of Information Retrieval Models. Advances in Neural Information Processing Systems Datasets and Benchmarks Track, 2021. https://arxiv.org/abs/2104.08663

[5] Gao Y, Xiong Y, Gao X, et al. Retrieval-Augmented Generation for Large Language Models: A Survey. arXiv preprint arXiv:2312.10997, 2023. https://arxiv.org/abs/2312.10997

[6] Leng Q, Portes J, Havens S, Zaharia M, Carbin M. Long Context RAG Performance of Large Language Models. arXiv preprint arXiv:2411.03538, 2024. https://arxiv.org/abs/2411.03538

[7] Jarvelin K, Kekalainen J. Cumulated gain-based evaluation of IR techniques. ACM Transactions on Information Systems, 2002, 20(4): 422-446. https://doi.org/10.1145/582415.582418

[8] Robertson S, Zaragoza H. The Probabilistic Relevance Framework: BM25 and Beyond. Foundations and Trends in Information Retrieval, 2009, 3(4): 333-389. https://doi.org/10.1561/1500000019

[9] Bjornson F O, Dingsoyr T. Knowledge Management in Software Engineering: A Systematic Review of Studied Concepts, Findings and Research Methods Used. Information and Software Technology, 2008, 50(11): 1055-1068. https://doi.org/10.1016/j.infsof.2008.03.006

[10] Cadavid H, Andrikopoulos V, Avgeriou P. Documentation-as-code for Interface Control Document Management in Systems of Systems: a Technical Action Research Study. arXiv preprint arXiv:2206.11668, 2022. https://arxiv.org/abs/2206.11668

[11] Zhou S, Alon U, Xu F F, Wang Z, Jiang Z, Neubig G. DocPrompting: Generating Code by Retrieving the Docs. International Conference on Learning Representations, 2023. https://arxiv.org/abs/2207.05987

[12] Wu X, Xiao L, Sun Y, Zhang J, Ma T, He L. A Survey of Human-in-the-loop for Machine Learning. arXiv preprint arXiv:2108.00941, 2021. https://arxiv.org/abs/2108.00941

[13] Wang J, Guo B, Chen L. Human-in-the-loop Machine Learning: A Macro-Micro Perspective. arXiv preprint arXiv:2202.10564, 2022. https://arxiv.org/abs/2202.10564

[14] Manzoor E, Tong J, Vijayaraghavan S, Li R. Expanding Knowledge Graphs with Humans in the Loop. arXiv preprint arXiv:2212.05189, 2022. https://arxiv.org/abs/2212.05189

[15] Yao S, Zhao J, Yu D, et al. ReAct: Synergizing Reasoning and Acting in Language Models. International Conference on Learning Representations, 2023. https://arxiv.org/abs/2210.03629

[16] Schick T, Dwivedi-Yu J, Dessi R, et al. Toolformer: Language Models Can Teach Themselves to Use Tools. Advances in Neural Information Processing Systems, 2023. https://arxiv.org/abs/2302.04761

[17] Patil S G, Zhang T, Wang X, Gonzalez J E. Gorilla: Large Language Model Connected with Massive APIs. arXiv preprint arXiv:2305.15334, 2023. https://arxiv.org/abs/2305.15334

[18] Li X. A Review of Prominent Paradigms for LLM-Based Agents: Tool Use (Including RAG), Planning, and Feedback Learning. arXiv preprint arXiv:2406.05804, 2024. https://arxiv.org/abs/2406.05804

[19] Model Context Protocol. Specification, version 2025-06-18. Accessed 2026-06-17. https://modelcontextprotocol.io/specification/2025-06-18

[20] Model Context Protocol. Resources, version 2025-06-18. Accessed 2026-06-17. https://modelcontextprotocol.io/specification/2025-06-18/server/resources

[21] Model Context Protocol. Tools, version 2025-06-18. Accessed 2026-06-17. https://modelcontextprotocol.io/specification/2025-06-18/server/tools
