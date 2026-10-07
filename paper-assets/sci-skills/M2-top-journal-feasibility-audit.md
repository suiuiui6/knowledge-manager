# 顶刊原文与近似工作：选题可行性复核

日期：2026-10-07；项目：knowledge-manager-journal-20261007。

## 判断

**AI分析：值得继续研究知识检索的可靠性，但现有“可审查知识模块＋按预算加载”题目尚未证明独立方法贡献。** 不建议现在围绕它直接写期刊论文。顶刊论文用来判断问题、证据和方法边界，近期会议/预印本用来检查是否已有相似解决方案；期刊声誉不能替代任务相关性，也不能凭一篇论文的 future work 宣称当前空白。本轮没有核验期刊分区、影响因子或排名，没有做系统综述或复现实验。

推荐保留的研究假设：**在版本演化的软件任务中，有限上下文内的证据选择是否同时满足目标版本适用性和操作前置条件，进而改善可执行任务成功率？** 这只是候选问题，尚不称为新方法或未解决空白。

## 原文来源和实际阅读范围

| ID | 文献与期刊 | 阅读范围与定位 | 来源 |
|---|---|---|---|
| J1 | Embodied large language models enable robots to complete complex tasks in unpredictable environments；Nature Machine Intelligence 7, 592–601 (2025)，DOI 10.1038/s42256-025-01005-x | 出版社 HTML 主文；Results/Evaluation、Discussion、Methods 和图注；补充材料未精读 | https://www.nature.com/articles/s42256-025-01005-x |
| J2 | An automated framework for assessing how well LLMs cite relevant medical references；Nature Communications 16, 3615 (2025)，DOI 10.1038/s41467-025-58551-6 | 出版社 HTML 主文；Introduction、Related Work、Results、Discussion、Methods 和图表说明；补充材料未审查 | https://www.nature.com/articles/s41467-025-58551-6 |
| J3 | Hyper-RAG: combating LLM hallucinations using hypergraph-driven retrieval-augmented generation；Nature Communications 17, 5778 (2026)，DOI 10.1038/s41467-026-71411-1 | 出版社 HTML 主文；Introduction、Results、Discussion/Limitations、Methods 和图表说明；补充材料未审查 | https://www.nature.com/articles/s41467-026-71411-1 |
| J4 | Lost in the Middle: How Language Models Use Long Contexts；TACL 12, 157–173 (2024)，DOI 10.1162/tacl_a_00638 | 官方期刊元数据核验；对应作者预印本 v3 主文 §§2–5、7 及相关附录；出版社全文遭访问挑战，不能称为最终期刊全文精读 | https://aclanthology.org/2024.tacl-1.9/ ； https://arxiv.org/html/2307.03172v3 |
| J5 | Atlas: Few-shot Learning with Retrieval Augmented Language Models；JMLR 24(251), 1–43 (2023) | 官方记录和摘要已核验；全文讨论/局限未完成可追溯精读，不作为本轮局限判断依据 | https://www.jmlr.org/papers/v24/23-0037.html |

J1、J2、J3 已核实为发表期刊论文。J3 页面记载 Published 27 April 2026、Version of record 02 July 2026；不能将其当作未发表预印本。J1 属智能体应用证据，J2 属引用可靠性证据，J3 与知识结构检索直接相关。医学与机器人结果不能外推为软件任务的实测效果。

## 现有方法对比表与不足分析

| 原文/方法 | 作者明确的局限及定位 | 已经解决/尝试的内容 | AI分析：对项目的意义 |
|---|---|---|---|
| J1 / ELLMER | Discussion：准确物体识别、预先可供性知识的假设；检测响应速度；主动切换任务；复杂力学建模 | 运动函数知识库、RAG 与视觉/力反馈结合；机器人任务执行 | 知识库有应用意义，但这些机器人限制不能支持我们预算检索方法的创新 |
| J2 / SourceCheckup、SourceCleanup | Discussion 最后局限段：自动流水线累积误差、人工判定歧义、逐陈述来源映射和多源综合边界、美国来源偏向、网页抽取/付费墙 | 逐陈述来源支持核验、医生验证、回答编辑 | 保存来源 ID 不能等同于来源支持陈述；可追溯性应与事实正确性、任务完成分别测量 |
| J3 / Hyper-RAG | Discussion → Limitations：高阶关系提取开销；跨 chunk 关联不能直接充分抽取，依赖后处理合并；跨文档建模作为未来工作 | 超图多实体关联、关系扩散检索、关联原始 chunk；Methods → Knowledge retrieval 还按最大上下文长度排序选择 | 普通关系扩展、保留原文和预算选择已有覆盖；真正跨边界的前置条件需要证据支持，不能用邻接边冒充依赖 |
| J4 / Lost in the Middle | 作者预印本 §2.2：解码策略范围；§5：检索数量与读者收益的关系和重排/截断建议；Appendix A：知识快照与答案的时间差 | 对相关证据位置进行受控实验 | 激发预算/排序评价，但旧模型和受控 QA 不能证明当前软件智能体仍有相同失败，更不能证明本项目改善它 |

J3 数值保留待复核：摘要/Overall Results 对 GraphRAG 的增益为 6.3%，Discussion 为 5.3%；正文部分对这些差值的叙述也有不同基准表述。不能自行选数、统一为相对提升或挪作本项目结果。本审查结论不依赖这组数字。

## 近似解决方案复核（预印本，不冒充顶刊）

| 文献 | 已读定位 | 重叠和边界 |
|---|---|---|
| Temporal Validity in Retrieval Memory: Eliminating Stale-Fact Errors for AI Agents over Evolving Knowledge；2606.26511v1 | Abstract、Introduction、Related Work、§3、§7 Limitations、§8 Conclusion；https://arxiv.org/html/2606.26511v1 | 已有确定性 supersession 和双时间账本，涉及代码/配置/API 更新。作者局限包括结构化单值模板、复杂抽取、时间代理和小规模验证。简单过期过滤不能当作新颖点；不接受作者关于所有 RAG 的泛化不可能性宣称 |
| STALE: Can LLM Agents Know When Their Memories Are No Longer Valid?；2605.06527v1 | Abstract、§§3–5、Appendix A Limitations and Future Work 及部分诊断附录；https://arxiv.org/html/2605.06527v1 | CUPMem 已有状态裁决、传播感知检索和来源跨度。Appendix A 明确：单次隐式状态转移/单冲突对、LLM 生成后专家验证的场景、LLM judge、预定义状态 schema。复杂反复更新是研究边界，但不是证明软件场景无人解决 |
| Recall Is Not Enough: A Reader-Context Diagnostic for Budget-Constrained Retrieval-Augmented Generation；2607.00725v2 | 主文方法/实验 §§3–6；局限段未完成独立逐项摘录；https://arxiv.org/html/2607.00725v2 | 已有预算子模打包、共享候选集和 focused heuristic 对照。泛化的证据保留/预算打包有直接重叠；不能仅换名称作为创新 |

A-Mem、RAPTOR、MAGMA 的旧卡仍仅代表选择性方法阅读；ReadAgent、DocPrompting、BEIR 仍仅元数据/摘要范围。没有将这些升级为完整精读。

## 改进方向：可检验而非预设新颖

**研究假设 H1：** 在明确目标软件版本、存在多个相互依赖前置条件的任务中，版本适用性与前置条件完整性的联合选择，可能比相关性打包加简单过期过滤更好。

- 未解决问题候选：相关片段已召回，但版本不适配，或缺少必要操作前提导致执行失败。
- 与原文差异候选：软件版本可以并存；目标版本适用性不等于“时间最新”；前置条件可以由可复现执行验证。必须再检索这一差异的已有方案，不能先宣布空白。
- 最小版本：先用本项目真实 Git 快照构造可重放任务和失败证据，人工核验目标版本、必要前提和答案支持跨度；现有 AI 生成模块和标签不能当独立 gold labels。
- 同候选集、同实际读者 token 预算下比较：top-k＋过期过滤、相关性/去重打包、子模打包、依赖闭包选择；有条件再加入图检索及传播失效基线。基线移植须说明能力、参数和成本，不能把简化版说成忠实复现。
- 指标：目标版本适用性、前提覆盖、可执行任务成功率、陈述来源支持、token/延迟/构建更新成本。召回率仅作诊断，不替代任务成功。
- 控制：无更新、无关更新、反复更新、多版本共存、版本未知；避免用最新时间戳机械淘汰旧版本。
- 可证伪结果：若真实失败很少，或强简单基线已解决，或联合方法只在人工偏置任务上改善，则放弃该方法创新主张，转向明确边界的案例/测评研究或重新选题。
- 风险：依赖提取质量、金标准泄漏、单项目泛化、状态 schema 与 CUPMem 重叠、读者模型混淆。没有运行上述实验。

## 与项目代码的关系

项目中 source hash/source span、stale、supersedes/derived_from 等字段提供实现基础，不是效果证据。policy.py 的 stale 抑制已经存在，不能把重新实现该功能视为创新。source_ingestion.py 的 char_start/char_end 是否为真实源偏移仍需独立检查。语料目前为单项目抽取模块和邻接关系；邻接不是经过验证的前置依赖。

## 元数据纠错和阶段决定

ReadAgent 官方 PMLR 记录及 BibTeX 本次核验为 **26396–26415**，更正旧记录 27811–27836。先前“Context-Picker 对应 2605.06527”的配对撤回：该编号实际为 STALE；未找到并核验 Context-Picker 前不能引用它。

由 SCI-Skills 编排角色决定：M2 从通过调整为部分通过，保留旧验收文件作为历史材料。原因是已有近似方案覆盖预算打包、来源追溯和失效传播，当前尚不能具体说明相对强方案的可靠改进；不是因为要求 M2 先完成全部正式实验。M1 的应用问题仍保留，下游方法与论文草稿继续作为候选资产。

**唯一下一步：** 用真实版本演化软件任务，对照已有强方案寻找一个可重复、仍未被解决的具体失败，再决定是否正式立题。
