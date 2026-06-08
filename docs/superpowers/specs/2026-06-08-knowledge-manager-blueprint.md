# Knowledge Manager — 未来蓝图

**Date:** 2026-06-08
**Status:** Draft
**Classification:** Strategic Blueprint (multi-phase)

## 定位与 Slogan

Knowledge Manager 是一个**面向 Agent 优先团队的轻量知识管理中台**。它以结构化 JSON 模块替代文本切片，以模型主动导航替代被动检索，以 Git 原生存储替代额外基础设施。最终形态：Agent 工作流中"知识"这一层的标准件。

**候选 Slogan：** *"Know what your agents know."*

**核心护城河三支柱：**
1. **结构化模块 + 人类审核** — 知识可 diff、可 review、可审计，不像 RAG 黑盒
2. **模型主动导航** — Agent 读索引、选模块、自主决策，比向量检索更精准
3. **零基础设施** — Git 就是数据库，不需要向量库或搜索服务

---

## 四阶段路线图概览

```
Phase 1: 检索引擎成熟     Phase 2: 协作层       Phase 3: 洞察层        Phase 4: 生态层
  搜索从60→95分           多人共建知识库         知识资产管理            Agent平台标准插件
  ──────────────────────────────────────────────────────────────────────────────────→
  个人开发者               小团队                中大型团队              平台/生态
```

每个阶段可独立交付、独立销售。后一阶段以前一阶段为基础，但不对前一阶段做破坏性变更。

---

## Phase 1: 检索引擎成熟（展开到可执行级别）

**目标：** 检索从当前的启发式+BM25（~60分）提升到规则+信号+行为的多信号融合排序（95分）。

**现状（2026-06）：**
- 回忆层：词边界 + 词干 + 短词部分匹配
- 排序层：字段权重（title:5, tag:3, summary:2, overview:1）+ 匹配质量（exact:3, stem:2, partial:1）+ BM25 三级联动
- 缺口：不支持跨模块关联扩展；不感知模块质量信号（confidence）；不会从用户行为中学习

### Phase 1A: 图扩展 + 置信度加权（立刻可做）

利用模块已有的 `metadata.related_modules` 和 `metadata.confidence` 字段，零额外数据即可提升精度。

#### 1A.1 关联图检索（Graph Expansion）

**动机：** 当前检索只看单模块匹配。如果查询 "JWT 安全最佳实践"，模块 `jwt-tokens` 匹配到了，但 `api-rate-limiting`（其 `related_modules` 中有 `jwt-tokens`）不会自动出现——即使它高度相关。

**方案：**
- 在 `index.json` 中维护全局关联图（category → module → related_modules 的邻接表）
- 搜索时，对 Top-N 候选模块做 1-hop 邻居扩展：如果 `jwt-tokens` 在候选集中，自动将 `jwt-tokens` 的所有 `related_modules` 加入候选
- 扩展模块的分数打折扣系数（如 0.6），保证原始匹配模块排在前面
- 传递给调用方时标记 `"source": "direct"` 或 `"source": "related"`，让调用方知道来源

**索引变更：** `index.json` 新增 `graph` 字段：
```json
{
  "graph": {
    "auth/jwt-tokens": ["api/rate-limiting", "auth/oauth-flow"],
    "auth/oauth-flow": ["auth/jwt-tokens", "api/http-status-codes"]
  }
}
```
每次 `rebuild_index` 时从模块的 `related_modules` 重建。增量更新在 `add_module`/`remove_module` 时同步维护。

**新增 MCP 工具：** `expand_module(module_id, category)` — 返回目标模块及其直接关联模块列表。

#### 1A.2 置信度信号引入

**动机：** 当前排序完全不考虑 `metadata.confidence`（high/medium/low）。两个模块 BM25 分数相同时，high confidence 应该排前面。

**方案：**
- 排序时在 heuristic score 层引入 confidence 乘法因子：high=1.0, medium=0.85, low=0.7
- 搜索结果的 summary 中附带 confidence，让 LLM 调用方自行判断可信度
- 可选：在 review 工作流中提示用户确认/修改 confidence

**CLI 增强：** `km search` 结果中展示 confidence 标记（如 `[high]` `[medium]` `[low]`）

#### 1A.3 具体实现任务

| # | 任务 | 文件 | 测试 |
|---|------|------|------|
| 1 | `index.json` schema 新增 `graph` 字段 | `schemas.py` | schema 验证 |
| 2 | `rebuild_index` 时构建关联图 | `storage.py` | 图结构正确性 |
| 3 | `search_modules` 加入 1-hop 扩展逻辑 | `storage.py` | 邻居出现在结果中 |
| 4 | confidence 乘法因子加入 sort key | `storage.py` | high > medium > low |
| 5 | `expand_module` MCP 工具 | `mcp_server.py` | MCP 工具测试 |
| 6 | CLI search 展示 confidence + source 标记 | `cli.py` | CLI 输出验证 |

---

### Phase 1B: 相关性反馈闭环（需要使用数据积累后启动）

**动机：** 规则能做到 80 分，剩下的 15 分需要从实际使用行为中学习。每个团队的知识库和查询习惯不同，通用的排序规则无法适配所有场景。

**核心思想：** 记录搜索→加载行为对，用这些信号训练轻量排序模型，实现"越用越准"。

#### 1B.1 行为数据采集

**采集的事件：**
```json
{
  "event": "search",
  "timestamp": "2026-07-01T10:30:00Z",
  "query": "JWT token refresh",
  "query_hash": "abc123",
  "results_shown": ["auth/jwt-tokens", "auth/oauth-flow"],
  "results_loaded": ["auth/jwt-tokens"],
  "load_delay_ms": 1200,
  "session_id": "sess-456"
}
```

**存储：** `kb_path/.telemetry/search_events.jsonl` — 每个事件一行 JSON，Git-ignored（本地隐私数据）

**隐私设计（企业刚需）：** 
- 所有数据存储在本地 KB 目录下，不上传任何服务
- `km telemetry disable` 全局关闭
- `km telemetry export` 导出脱敏统计（不含具体查询文本，仅含 query_hash）

#### 1B.2 排序模型演进

**冷启动阶段（< 100 次搜索事件）：**
- 仍使用 Phase 1A 的规则排序
- 后台计算 query → module 的点击率基线

**初级学习阶段（100-1000 次事件）：**
- 朴素贝叶斯：P(module | query_terms) 先验概率
- 每新发搜索，将行为先验作为第四层排序信号
- 排序变为：`(heuristic_score, quality, prior_probability, bm25)`
- 实现简单，可解释，无需 GPU

**成熟学习阶段（> 1000 次事件）：**
- 切换到 pairwise learning-to-rank (RankNet 或 LambdaRank 的极简实现)
- 特征：BM25 分、启发式分、confidence、点击率、模块大小、最后更新时间
- 模型极小（< 1MB），本地加载，不依赖外部服务
- 定期自动重训练（`km train` 或 `km rebuild` 时触发）

#### 1B.3 反馈信号设计

| 信号类型 | 来源 | 含义 | 权重 |
|----------|------|------|------|
| 搜索后立即加载 | `load_delay_ms < 2000` | 强正反馈 | +1.0 |
| 搜索后延迟加载 | `load_delay_ms >= 2000` | 弱正反馈 | +0.3 |
| 搜索后未加载但同级其他模块被加载 | 相对分析 | 弱负反馈 | -0.1 |
| 搜索结果完全未被使用 | 整次搜索无加载 | 查询可能需要改写 | 不计入 |

#### 1B.4 CLI 与配置

```bash
# 查看当前排序模型状态
km rank status
  Model: bayesian
  Events: 847
  Last trained: 2026-07-15T09:00:00Z
  Top features: bm25_score(0.42), prior_prob(0.31), confidence(0.18)

# 强制重训练
km rank retrain

# 切换排序模型
km config set ranking.model "bayesian"    # 或 "rule_only" / "lambdarank"

# 导出训练数据（用于调试或迁移）
km rank export --format jsonl
```

#### 1B.5 具体实现任务

| # | 任务 | 依赖 |
|---|------|------|
| 1 | 搜索事件采集基础设施（JSONL 写入，去重，query_hash） | Phase 1A 完成 |
| 2 | `km telemetry` 子命令组（status/disable/enable/export） | 任务 1 |
| 3 | 朴素贝叶斯排序器（P(module|query_terms) 计算） | 任务 1 |
| 4 | 排序融合逻辑（四信号排序） | 任务 3 |
| 5 | LambdaRank 极简实现 + 特征工程 | 任务 3（可选，看数据量） |
| 6 | `km rank` 子命令组 | 任务 4/5 |
| 7 | `rank_model.json` schema 与持久化 | 任务 3 |
| 8 | 完整的 Phase 1B 集成测试 | 所有任务 |

---

## Phase 2: 协作层（方向性描述）

**目标：** 从单机单人 → 团队共享共建。解决"谁来维护这个知识库"的问题——如果只有一个人能用，卖不出团队价格。

**核心场景：**
- 一个 5-20 人的工程团队共用同一个 KB
- 有人负责撰写和提取知识，有人负责审核，有人负责消费
- 知识变更可追溯、可回滚、可讨论

**关键能力（具体设计待 Phase 1 完成后展开）：**

1. **远程知识库（Remote KB）**
   - KB 托管在 GitHub/GitLab 仓库上
   - `km clone git@github.com:team/knowledge-base.git` 
   - `km pull` / `km push` 封装 git 操作，增加 KB 特有的冲突检测
   - 本质上就是 git，不需要自己造分布式协议

2. **角色与审核流水线**
   - Editor（提交萃取建议） → Reviewer（审核通过） → Consumer（只读消费）
   - `km review` 扩展为多人审核队列（类似 GitHub PR review）
   - 审核意见可以写在模块的 `metadata.review_notes` 中

3. **变更通知**
   - 模块新增/修改/删除时生成 changelog
   - MCP 资源 `knowledge://changelog` 让 Agent 感知知识库变化
   - 可选 Slack/Webhook 通知

4. **知识冲突解决**
   - 两人同时修改同一模块 → git merge conflict 标准流程
   - CLI 辅助 diff 展示和合并

**存储架构演变：**
```
本地 KB (Phase 1)     →     远程 KB (Phase 2)
单机文件系统                GitHub 仓库 + 本地 clone
无冲突                      git 原生冲突解决
单人审核                    多人 PR 式审核
```

---

## Phase 3: 洞察层（方向性描述）

**目标：** 从"存知识和找知识"升级为"管理知识资产"。团队负责人需要知道知识库的健康状态，而非只是使用它。

**核心场景：**
- CTO/技术负责人问："我们的知识库覆盖了哪些技术领域？哪些模块已经过时了？哪些压根没人看过？"
- 新成员入职："我应该先看哪些模块？"
- 知识库增长到 200+ 模块后："这些模块哪些可以合并？哪些该归档？"

**关键能力：**

1. **知识健康度仪表盘**
   - 过时检测：30/60/90 天未更新的模块标记
   - 僵尸检测：从未被任何 Agent 加载过的模块
   - 覆盖率分析：按 category 展示模块密度，发现知识盲区
   - CLI: `km health` 输出一个 Rich 表格

2. **知识图谱可视化**
   - 基于 `related_modules` 的全局关联图
   - 识别"孤岛模块"（无任何关联）和"枢纽模块"（被大量模块引用）
   - MCP 工具 `knowledge_graph` 返回图数据，让 LLM 可以分析结构

3. **使用统计**
   - 哪些模块被加载最多（热门知识）
   - 哪些查询没匹配到任何模块（需求缺口）
   - 模块平均加载深度（Agent 是读了 overview 就走了，还是读到了 details）

4. **知识生命周期管理**
   - 模块状态：`draft → reviewed → published → deprecated → archived`
   - `km archive <module-id>` 标记为归档（保留但不再出现在默认搜索中）
   - 归档模块定期清理建议

---

## Phase 4: 生态层（方向性描述）

**目标：** Knowledge Manager 成为 Agent 工作流中"知识"层的标准连接件。不只是一个独立工具，而是一个可以被任何 Agent 平台按需调用的知识插件。

**核心场景：**
- 用户在 Claude Code 中输入 `/knowledge` 即可搜索团队知识库
- VS Code Copilot 自动从团队 KB 中获取上下文建议
- CI/CD 流水线在部署前检查相关模块是否有过时警告
- 第三方 Agent 平台通过标准 MCP 端点接入知识库

**关键能力：**

1. **一键接入主流 Agent 平台**
   - Claude Code: `.claude/mcp.json` 自动配置生成
   - GitHub Copilot: Extension manifest
   - Cursor/Windsurf: MCP 配置模板
   - 每个平台一个 `km connect <platform>` 命令

2. **知识 Webhook**
   - 模块更新时触发外部工作流
   - 场景：`api-rate-limiting` 模块标记为 deprecated → 自动创建 Jira ticket 提醒相关服务更新

3. **知识市场（Knowledge Marketplace）**
   - 公开的、社区维护的知识模块模板
   - 如 `auth/oauth2-best-practices` — 团队可以直接 `km install community/auth/oauth2-best-practices`
   - 类似 Docker Hub 但面向知识模块
   - 这是最远期的构想，可能需要 Phase 4 成熟后再考虑

4. **多 KB 联邦**
   - 一个 Agent 同时接入多个知识库
   - 如：公司级 KB（所有团队共享）+ 团队级 KB（auth 团队专用）
   - MCP 层做命名空间隔离

**商业模式衔接：**
- 个人开发者：免费，本地 KB
- 小团队（≤5人）：免费，远程 KB via GitHub
- 中大型团队（>5人）：付费，高级洞察 + 知识市场 + SSO
- 平台集成：按 MAU（Monthly Active Agent）收费或许可

---

## 技术架构演进全景

```
Phase 1                     Phase 2                Phase 3                  Phase 4
┌──────────────┐           ┌──────────────┐       ┌──────────────┐        ┌──────────────┐
│  CLI (click) │           │  CLI + Web?  │       │  CLI + Dashboard│     │  CLI + API  │
├──────────────┤           ├──────────────┤       ├──────────────┤        ├──────────────┤
│ MCP Server   │           │ MCP Server   │       │ MCP Server   │        │ MCP Gateway │
│ (stdio)      │           │ (stdio+SSE)  │       │ (stdio+SSE)  │        │ (multi-KB)  │
├──────────────┤           ├──────────────┤       ├──────────────┤        ├──────────────┤
│ Storage      │           │ Storage      │       │ Storage      │        │ Storage     │
│ (local fs)   │           │ (git remote) │       │ (git + cache)│        │ (federated) │
├──────────────┤           ├──────────────┤       ├──────────────┤        ├──────────────┤
│ Search       │           │ Search       │       │ Search       │        │ Search      │
│ (rule+BM25)  │           │ (rule+BM25   │       │ (rule+BM25   │        │ (full model)│
│              │           │  +feedback)  │       │  +behavior)  │        │             │
├──────────────┤           ├──────────────┤       ├──────────────┤        ├──────────────┤
│ -            │           │ Auth (git)   │       │ Analytics    │        │ Marketplace │
│              │           │ Roles (git)  │       │ Health       │        │ Webhooks    │
│              │           │              │       │ Lifecycle    │        │ Federation  │
└──────────────┘           └──────────────┘       └──────────────┘        └──────────────┘
```

**不引入的技术（设计边界）：**
- 不引入向量数据库或 embedding 模型 — 保持零基础设施
- 不引入真实 Web 服务器 — MCP stdio 为默认传输，SSE 只在 Phase 2+ 作为可选
- 不引入 SQL 数据库 — JSON 文件 + Git 是唯一的持久化层
- 不引入消息队列 — 异步操作通过文件锁 + 原子写入解决

---

## 各阶段成功指标

### Phase 1A
- 图扩展使关联模块召回率从 0% 提升到 >60%（人工标注 20 个查询，关联模块应出现在结果中）
- confidence 加权使 high-confidence 模块在同等匹配分数下优先于 low-confidence
- 现有 106 个测试全部通过，新增 ≥15 个测试
- `km search` 输出展示 confidence 和 source 标记

### Phase 1B
- 朴素贝叶斯模型在 100+ 事件后，Top-3 准确率比纯规则提升 ≥10%
- 搜索事件写入开销 < 1ms（不影响搜索响应速度）
- 所有 telemetry 数据在本地，无网络请求
- `km rank status` 可展示模型状态和特征重要性

### Phase 2
- 3 人团队可通过 `km clone/pull/push` 协作
- 多人并发修改同一模块时，git 冲突处理流程清晰可用
- changelog 资源让 Agent 感知知识库变更

### Phase 3
- `km health` 在 < 2s 内完成 200 模块的健康扫描
- 知识图谱数据让 LLM 能回答"哪些模块应该一起读"
- 模块状态机完整（draft→published→deprecated→archived）

### Phase 4
- 3 个 Agent 平台有 `km connect` 一键接入命令
- 知识模块模板市场有 ≥10 个社区贡献模板
- 多 KB 联邦模式下，Agent 可无感知切换不同知识库

---

## 当前状态与下一步

**已完成：**
- Phase 0（MVP）：CLI + MCP server + 提取 + 审核 + 搜索（启发式 + BM25）
- 106 个测试，代码覆盖率良好

**进行中：**
- Phase 1A（图扩展 + 置信度）：设计已在本蓝图中完成，待实现

**推荐下一步：**
1. 本蓝图审阅确认
2. 对 Phase 1A 编写实现计划（invoke writing-plans）
3. 实现 Phase 1A 的 6 个任务
4. 发布 `v0.2.0`，包含图扩展 + 置信度排序
5. 在真实场景中使用并积累搜索行为数据，为 Phase 1B 做准备
