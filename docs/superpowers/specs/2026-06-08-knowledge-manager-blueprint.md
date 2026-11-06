# Knowledge Manager — 未来蓝图

**Date:** 2026-06-09
**Status:** Phase 1 + 2 + 3 Complete, Phase 4 Specified
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

每个阶段可独立交付、独立验证。后一阶段以前一阶段为基础，但不对前一阶段做破坏性变更。

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

## Phase 2: 协作层

**目标：** 从单机单人 → 团队共享共建。解决"谁来维护这个知识库"的问题。

**现状（2026-06，Phase 1 完整交付）：**
- 单人本地 KB：CLI + MCP server + 提取 + 审核 + 搜索
- 检索：多信号级联排序（BM25 + 图扩展 + 置信度 + 贝叶斯 + 会话上下文 + 意图分类）
- 154 个测试，所有数据在本地文件系统
- 缺口：无远程同步、无多人角色、无变更通知、无冲突解决

---

### Phase 2A: Git 原生远程协作（基础设施）

**动机：** Phase 1 的 KB 是纯本地目录。要让团队共用，必须支持远程同步。但不需要造分布式协议——Git 已经解决了所有难题。KM 只需封装 git 操作为符合知识库语义的 CLI 命令。

**核心原则：** KB 即 Git 仓库。`km pull` ≈ `git pull`，但增加了 KB 特有的索引重建和冲突检测。

#### 2A.1 远程 KB 生命周期

```bash
# 从远程仓库克隆一个团队 KB
km clone git@github.com:team/backend-kb.git
  → git clone + km init 检测（如果已初始化则跳过）

# 拉取团队最新变更
km pull
  → git pull origin main
  → 检测 .staging 中是否有冲突的本地 WIP
  → 自动 rebuild_index

# 推送本地变更到团队仓库
km push
  → 检查本地是否落后于 remote（必须先 pull）
  → git push origin main
  → 输出变更摘要（新增/修改/删除的模块数）

# 查看本地与远程的差异
km status
  → 类似 git status，但按模块粒度展示
  → 输出：本地新增 N 个模块，远程新增 M 个模块，冲突 K 个模块
```

#### 2A.2 KB 仓库结构规范

标准 KB 仓库布局：
```
kb-root/
  ├── index.json          # 全局索引（追踪）
  ├── config.json          # 配置模板（追踪，但不含 secrets）
  ├── config.local.json    # 本地覆盖（gitignore）
  ├── .gitignore           # 排除 .staging/, .telemetry/, config.local.json
  ├── .staging/            # 个人 WIP 暂存区（gitignore）
  ├── .telemetry/          # 本地使用数据（gitignore）
  ├── auth/                # 知识模块按 category 分目录
  │   ├── jwt.json
  │   └── oauth.json
  └── database/
      └── conn-pool.json
```

**关键设计决策：**
- `config.json` 追踪 LLM provider 名称和模型设置，但 `api_key` 字段在 push 时自动脱敏（替换为 `"<LOCAL>"`）
- `.staging/` 和 `.telemetry/` 在 `.gitignore` 中——个人 WIP 和本地行为数据不上传
- `index.json` 始终追踪——它是知识的全局目录，团队共享

#### 2A.3 Git 操作封装

**`km clone` 实现要点：**
1. `git clone <url> <local-path>`
2. 检测 `index.json` 是否存在，不存在则报错"Not a valid KM repository"
3. 自动 `rebuild_index` 确保索引与模块一致

**`km pull` 实现要点：**
1. 检查本地是否有未提交的 `.staging` 模块 → 提示用户先 `km review` 或 `km push`
2. `git pull --rebase origin main`
3. 处理可能的 merge conflict（见 Phase 2C）
4. 自动 `rebuild_index`

**`km push` 实现要点：**
1. 检查 remote 是否有新提交 → 如果有，要求先 `km pull`
2. 对 `config.json` 做脱敏处理：遍历 `llm_providers.*.api_key`，替换为占位符
3. `git add` 所有模块文件 + index.json + config.json
4. 自动生成 commit message（如 `"3 modules updated, 1 module added"`）
5. `git push origin main`

**`km status` 实现要点：**
1. `git fetch origin` 获取最新 remote 状态
2. `git diff --name-only origin/main` 列出变更文件
3. 按模块粒度解析：新增 / 修改 / 删除
4. 展示本地领先/落后的 commit 数

#### 2A.4 模块级 Diff

```bash
# 查看某个模块的本地与远程差异
km diff auth/jwt
  → 对比本地与 origin/main 的 auth/jwt.json
  → 以人类可读的格式展示字段级变更
```

**`km diff` 实现要点：**
1. 从 git 获取远程版本：`git show origin/main:auth/jwt.json`
2. 与本地文件做 JSON 字段级 diff
3. 展示新增/删除/修改的字段，按 section 分组（metadata / content）

#### 2A.5 具体实现任务

| # | 任务 | 文件 | 测试 |
|---|------|------|------|
| 1 | `.gitignore` 模板生成（排除 .staging/.telemetry/config.local.json） | `cli.py` (init 命令) | `test_init_creates_gitignore` |
| 2 | `km clone` 命令 — git clone + KB 校验 | `cli.py` | clone 成功 / 非 KB 仓库报错 |
| 3 | `km pull` 命令 — git pull + 冲突检测 + rebuild_index | `cli.py` | pull 成功 / staging 冲突提示 |
| 4 | `km push` 命令 — api_key 脱敏 + 自动 commit + push | `cli.py` | push 成功 / config 脱敏验证 |
| 5 | `km status` 命令 — 本地 vs 远程模块变更展示 | `cli.py` | 新增/修改/删除检测 |
| 6 | `km diff <module>` 命令 — 模块 JSON 字段级对比 | `cli.py` | 字段级 diff 输出 |
| 7 | `config.json` 脱敏工具函数 | `storage.py` | api_key 替换验证 |

---

### Phase 2B: 多人审核流水线

**动机：** Phase 1 的 `km review` 是单人交互式审核（a=approve/r=reject/s=skip）。多人团队需要并行审核、审核意见记录、审核状态追踪。

**角色模型：**
```
Editor  ──→  提交模块到 .staging
Reviewer ──→ 审核 .staging 中的模块，记录意见
Consumer ──→ 只读消费 KB（通过 MCP server 搜索/加载）
```

角色通过 Git 权限控制，不在 KM 内部实现认证：
- Editor = 仓库 write 权限
- Reviewer = 仓库 write 权限 + 审核职责
- Consumer = 仓库 read 权限（或仅使用 MCP endpoint）

#### 2B.1 Staging 元数据扩展

当前 staging 文件仅包含模块 JSON。Phase 2B 增加 staging 元数据文件：

```json
// .staging/auth-jwt.meta.json
{
  "module_id": "auth-jwt",
  "status": "pending",           // pending | approved | changes-requested
  "submitted_by": "alice",
  "submitted_at": "2026-07-15T10:30:00Z",
  "reviews": [
    {
      "reviewer": "bob",
      "action": "changes-requested",
      "comment": "Caveats section should mention the RS256 key rotation limitation",
      "timestamp": "2026-07-15T14:00:00Z"
    }
  ]
}
```

#### 2B.2 审核命令扩展

```bash
# 列出待审核模块（含审核状态）
km review list
  → 表格展示：Module | Submitted By | Status | Reviews

# 查看某个待审核模块的详细信息
km review show auth-jwt
  → 展示模块内容 + 已有审核意见

# 审核通过
km review approve auth-jwt --comment "LGTM, caveats look good"
  → 更新 .meta.json，标记 status=approved
  → 如果有足够的 approvals，自动 approve_from_staging

# 请求修改
km review request-changes auth-jwt --comment "Missing RS256 rotation caveat"
  → 更新 .meta.json，标记 status=changes-requested

# 查看自己的提交状态
km review my-submissions
  → 展示当前用户提交的所有 staging 模块及审核进度
```

#### 2B.3 审核规则配置

在 `config.json` 中增加审核规则：

```json
{
  "review": {
    "required_approvals": 1,
    "auto_approve_self_submitted": false,
    "reviewer_whitelist": []
  }
}
```

- `required_approvals`：模块从 staging 进入正式 KB 所需的最少 approval 数（默认 1）
- `auto_approve_self_submitted`：是否允许提交者自行 approve（默认 false）
- `reviewer_whitelist`：限定审核人列表（空 = 所有 write 权限者）

#### 2B.4 具体实现任务

| # | 任务 | 文件 | 测试 |
|---|------|------|------|
| 1 | Staging 元数据 schema（`.meta.json`） | `schemas.py` | schema 验证 |
| 2 | `save_staging_meta` / `load_staging_meta` 函数 | `storage.py` | 读写测试 |
| 3 | `km review list` — 表格展示待审核列表 | `cli.py` | CLI 输出验证 |
| 4 | `km review show` — 展示模块 + 审核意见 | `cli.py` | 展示内容验证 |
| 5 | `km review approve` — 审批通过逻辑 | `cli.py` | approval 计数 + 自动合并 |
| 6 | `km review request-changes` — 请求修改 | `cli.py` | status 变更验证 |
| 7 | `km review my-submissions` — 个人提交状态 | `cli.py` | 按 submitter 过滤 |
| 8 | 审核规则配置（`config.json` review 段） | `schemas.py` | 默认值验证 |

---

### Phase 2C: 变更感知与通知

**动机：** 当团队成员更新知识模块时，使用该 KB 的 Agent 应该知道"知识变了"。Phase 1 的 Agent 完全不知道 KB 是否更新过。这一层让知识变更对 Agent 可见。

#### 2C.1 Changelog 生成

每次 `km push` 或 `km pull` 后，自动生成 changelog：

```json
// .changelog/2026-07-15.json
{
  "date": "2026-07-15",
  "commits": [
    {
      "hash": "abc123",
      "author": "alice",
      "message": "Update JWT module with RS256 rotation caveat",
      "changes": {
        "added": [],
        "modified": ["auth/jwt"],
        "deleted": []
      }
    }
  ]
}
```

Changelog 文件存储在 `.changelog/` 目录下，按日期命名。此目录在 `.gitignore` 中（从 git 历史即可重建），由 `km pull` / `km push` 自动生成。

#### 2C.2 MCP Changelog 资源

```
# 获取最近 N 天的变更
knowledge://changelog?days=7

# 获取特定模块的变更历史
knowledge://changelog/auth/jwt
```

**`knowledge://changelog` 资源实现：**
- 读取 `.changelog/` 目录下最近 N 天的文件
- 合并输出为 JSON 数组
- Agent 可在每次对话开始时读取此资源，判断"自上次对话以来知识库有无变化"

#### 2C.3 Webhook 通知（可选）

在 `config.json` 中配置 webhook URL：

```json
{
  "notifications": {
    "webhook_url": "https://hooks.slack.com/services/...",
    "on_push": true,
    "on_review_approved": false
  }
}
```

`km push` 完成后，如果配置了 webhook，发送通知：
```json
{
  "text": "KB updated by alice: 2 modules modified, 1 added. Review: https://github.com/team/kb/pull/42"
}
```

#### 2C.4 具体实现任务

| # | 任务 | 文件 | 测试 |
|---|------|------|------|
| 1 | Changelog 生成器 — 从 git log 提取模块级变更 | `storage.py` | changelog 格式验证 |
| 2 | `km push` / `km pull` 钩子调用 changelog 生成 | `cli.py` | 钩子触发验证 |
| 3 | `knowledge://changelog` MCP 资源 | `mcp_server.py` | MCP 资源测试 |
| 4 | `knowledge://changelog/<module>` 单模块变更历史 | `mcp_server.py` | 单模块 changelog |
| 5 | Webhook 通知发送（httpx POST） | `storage.py` 或新文件 | webhook 格式 + 失败处理 |
| 6 | `km config set notifications.webhook_url` | `cli.py` | config 读写 |

---

### Phase 2D: 模块状态机与归档

**动机：** 知识库增长到 50+ 模块后，需要生命周期管理。不是所有模块都永远有效——有些会过时、被取代、或不再适用。

**注意：** 此项与 P1-5（`expires_at` / `review_interval_days`）配合使用。P1-5 解决了"何时需要审查"的问题，Phase 2D 解决"模块从诞生到退役的完整旅程"。

#### 2D.1 模块状态机

```
draft ──→ reviewed ──→ published ──→ deprecated ──→ archived
  │                      │              │
  └── (review 通过)      │              │
                         └── (被取代/过时)│
                                        └── (不再使用/删除)
```

状态定义：
- **draft**：刚从 LLM 提取，进入 staging，尚未审核
- **reviewed**：审核通过但尚未 push 到团队仓库
- **published**：已合并到团队仓库的 main 分支，默认搜索可见
- **deprecated**：不再推荐使用，搜索时显示 `[deprecated]` 标记，排序降权（0.5x）
- **archived**：归档保留但不出现在默认搜索结果中（需 `--include-archived` 标志）

状态存储在 `ModuleMetadata.status` 字段。

#### 2D.2 归档命令

```bash
# 废弃一个模块
km deprecate auth/old-jwt --reason "Replaced by auth/jwt (RS256 → EdDSA)"

# 归档一个模块
km archive auth/old-jwt

# 搜索时包含已归档模块
km search "JWT" --include-archived
```

#### 2D.3 搜索中的状态感知

- `search_modules()` 默认过滤掉 status=archived 的模块
- deprecated 模块保留在搜索结果中，但排序降权（confidence 等效于 low，即 0.7x）
- MCP `search_modules_tool` 增加可选参数 `include_archived: bool = False`

#### 2D.4 具体实现任务

| # | 任务 | 文件 | 测试 |
|---|------|------|------|
| 1 | `ModuleMetadata.status` 字段 + 状态枚举 | `schemas.py` | schema 验证 |
| 2 | `search_modules` 过滤 archived + deprecated 降权 | `storage.py` | 搜索过滤测试 |
| 3 | `km deprecate` 命令 | `cli.py` | CLI 测试 |
| 4 | `km archive` 命令 | `cli.py` | CLI 测试 |
| 5 | `--include-archived` 搜索标志 | `cli.py` + `storage.py` | 标志生效验证 |

---

### Phase 2 整体交付节奏

```
Phase 2A (Git 远程协作)     ████████████░░░░░░  6-8 任务，基础依赖
Phase 2B (多人审核流水线)   ░░░░░░░░████████░░  8 任务，依赖 2A
Phase 2C (变更感知与通知)   ░░░░░░░░░░░░░░████  6 任务，依赖 2A
Phase 2D (模块状态机)       ░░░░░░░░░░░░░░████  5 任务，独立可做
```

2A 是 Phase 2 的硬依赖——没有 git 同步，2B/2C 无法发挥团队价值。2D 可独立实施（甚至可与 2A 并行）。

### Phase 2 成功指标

- 3 人团队可通过 `km clone/pull/push` 完成完整的知识协作闭环
- 多人并发修改同一模块时，git 冲突处理流程清晰可用（`km status` + `km diff`）
- `knowledge://changelog` 资源让 Agent 在 < 100ms 内获取最近变更
- 审核流水线从提交到 approval 全流程可追踪

---

## Phase 3: 洞察层

**目标：** 从"存知识和找知识"升级为"管理知识资产"。Phase 2 解决了团队协作问题，Phase 3 回答"知识库到底好不好用"——让团队负责人、知识管理员、新成员都能获得知识库的全局视图。

**现状（2026-06，Phase 2 完整交付）：**
- 完整的 Git 协作：clone/pull/push/status/diff
- 多人审核管线：staging meta、approve/request-changes/my-submissions
- 变更感知：changelog 生成、MCP changelog 资源、webhook 通知
- 模块状态机：draft/reviewed/published/deprecated/archived 全生命周期
- 搜索增强：归档过滤、deprecated 降权、会话上下文、意图分类、贝叶斯排序
- 218 个测试，全量通过
- 缺口：无知识库健康度评估、无使用分析、无图谱分析、无智能推荐

**核心场景：**
- CTO/技术负责人问："我们的知识库覆盖了哪些技术领域？哪些模块已经过时了？哪些压根没人看过？"
- 新成员入职："我应该先看哪些模块？"
- 知识库增长到 200+ 模块后："这些模块哪些可以合并？哪些该归档？"
- Agent 开发者问："用户实际搜索了哪些问题？我们的知识库覆盖了其中多少？"

---

### Phase 3A: 知识健康度仪表盘

**动机：** 知识库是动态资产——模块会过时、会被遗忘、会产生盲区。`km health` 提供一次命令看全局，让知识管理员无需翻遍目录就能判断 KB 状态。

#### 3A.1 健康度模型

每个模块的健康分由 3 个维度组成：

| 维度 | 含义 | 分数来源 |
|------|------|----------|
| **时效性** (freshness) | 模块是否足够新 | `updated_at` 距今天数 → 0-100 分 |
| **使用度** (usage) | 模块是否被实际使用 | telemetry 中的 load 事件次数 → 0-100 分 |
| **完整度** (completeness) | 模块内容是否充实 | content 字段填充率加权 → 0-100 分 |

综合健康分 = `freshness * 0.35 + usage * 0.35 + completeness * 0.30`

**时效性评分规则：**
- 30 天内更新：100 分
- 30-60 天：75 分
- 60-90 天：50 分
- 90-180 天：25 分
- 180+ 天：0 分
- 若设置了 `review_interval_days`：超出间隔即 0 分
- 若设置了 `expires_at` 且已过期：0 分（标记为 EXPIRED）

**使用度评分规则：**
- 最近 30 天有 load 事件：100 分
- 最近 60 天：70 分
- 最近 90 天：40 分
- 90 天以上或从未加载：0 分（标记为 ZOMBIE）

**完整度评分规则：**
- overview 非空：30 分
- details 非空（≥ min_length）：30 分
- examples 非空：20 分
- caveats 非空：10 分
- references 非空：10 分

#### 3A.2 CLI 输出设计

```bash
$ km health

  Knowledge Base Health Report
  2026-07-15 | 127 modules | 12 categories

  ┌──────────────────────────────┬────────┬────────┬──────────┐
  │ Category                     │ Total  │ Avg    │ At Risk   │
  ├──────────────────────────────┼────────┼────────┼──────────┤
  │ auth                         │     15 │  78.2  │ 2 ⚠️      │
  │ api                          │     22 │  82.1  │ 0        │
  │ database                     │     18 │  65.4  │ 3 ⚠️      │
  │ deployment                   │     12 │  71.0  │ 1 ⚠️      │
  │ ...                          │    ... │   ...  │ ...      │
  └──────────────────────────────┴────────┴────────┴──────────┘

  Overall Health Score: 74.8/100

  ⚠️  Modules Needing Attention
  ┌────────────────────────────┬─────────────┬────────┬────────┐
  │ Module                     │ Issue        │ Score  │ Action │
  ├────────────────────────────┼─────────────┼────────┼────────┤
  │ auth/old-jwt               │ ZOMBIE       │  15.0  │ review │
  │ database/mysql5-migration  │ EXPIRED      │   5.0  │ archive│
  │ api/soap-legacy            │ STALE (180d) │  20.0  │ deprec.│
  └────────────────────────────┴─────────────┴────────┴────────┘

  $ km health --module auth/jwt

  Module Health: auth/jwt
  ┌──────────────┬───────┬──────────────────────────────────┐
  │ Dimension    │ Score │ Detail                           │
  ├──────────────┼───────┼──────────────────────────────────┤
  │ Freshness    │  85   │ Updated 12 days ago              │
  │ Usage        │  92   │ Loaded 47 times (last: 2d ago)  │
  │ Completeness │  70   │ Missing: examples, references    │
  ├──────────────┼───────┼──────────────────────────────────┤
  │ Overall      │  82.3 │ ✅ Healthy                       │
  └──────────────┴───────┴──────────────────────────────────┘
```

**CLI 选项：**
- `km health` — 全局健康总览
- `km health --module <category/id>` — 单个模块详细健康报告
- `km health --category <cat>` — 按 category 过滤
- `km health --format json` — 机器可读格式（供 Agent 消费）
- `km health --at-risk` — 仅展示需要关注的模块

#### 3A.3 健康度 Schema

```python
class HealthScore(BaseModel):
    freshness: float = 0.0       # 0-100
    usage: float = 0.0           # 0-100
    completeness: float = 0.0    # 0-100
    overall: float = 0.0         # weighted 0-100

class ModuleHealth(BaseModel):
    module_id: str
    category: str
    title: str
    status: str
    score: HealthScore
    issues: List[str] = []       # "zombie", "stale", "expired", "incomplete"
    last_load: Optional[datetime]
    load_count_30d: int = 0
    days_since_update: int = 0

class KBHealthReport(BaseModel):
    generated_at: datetime
    total_modules: int
    total_categories: int
    overall_score: float
    category_breakdown: Dict[str, CategoryHealth]
    at_risk_modules: List[ModuleHealth]
```

#### 3A.4 MCP 资源

```
# 获取知识库整体健康报告
knowledge://health

# 获取特定模块健康详情
knowledge://health/auth/jwt
```

返回与 CLI 相同结构的 JSON，让 Agent 能在对话中引用健康数据（如 "我注意到 `auth/old-jwt` 已过期，建议查阅 `auth/jwt`"）。

#### 3A.5 具体实现任务

| # | 任务 | 文件 | 测试 |
|---|------|------|------|
| 1 | `HealthScore` / `ModuleHealth` / `KBHealthReport` schema | `schemas.py` | schema 验证 + 评分计算 |
| 2 | `compute_module_health(module, kb_path)` — 单模块健康计算 | `storage.py` | 时效性/使用度/完整度计算 |
| 3 | `generate_health_report(kb_path)` — 全局健康报告 | `storage.py` | 全量报告 + 风险模块列表 |
| 4 | `km health` CLI 命令（总览 + 单模块 + --at-risk + --format json） | `cli.py` | CLI 输出 + JSON 格式验证 |
| 5 | `knowledge://health` 和 `knowledge://health/<key>` MCP 资源 | `mcp_server.py` | MCP 资源测试 |

---

### Phase 3B: 使用分析

**动机：** Phase 1B 的 telemetry 数据采集已经就位，但数据只是被存储、被贝叶斯模型消费。团队负责人需要的是"从这些数据里看到了什么"——哪些模块是核心资产、哪些查询是未被满足的需求。

#### 3B.1 分析维度

**热门模块排行：**
- 近 7/30/90 天加载次数排名
- 展示加载次数、加载来源（搜索/直接）、平均加载深度

**需求缺口分析：**
- 搜索了但无结果匹配的查询（query hash → 查询文本 if same session）
- 搜索了但无任何结果被加载的查询（低质量搜索）
- 按频率排序，输出 Top-N 未被覆盖的查询主题

**模块加载深度：**
- 每次 `load_module` 意味着 Agent 读了整个模块 JSON
- 但我们可以从模块的字段长度推断 Agent 可能关注的深度——
  更实际的做法：记录 `load_module` 事件本身就够了
- 输出报表：哪些模块被频繁加载但 `details` 部分可能太长（word count > 500 且加载后无明显关联搜索）

**搜索转化率：**
- `search → load` 转化率：搜索结果被点击加载的比例
- 高转化 = 搜索质量好，低转化 = 搜索结果不相关或查询模糊
- 按时间段趋势展示

**活跃度时间线：**
- 过去 90 天的每日搜索次数 + 加载次数折线图（终端友好版：ASCII sparkline）
- 识别活跃度下降趋势

#### 3B.2 CLI 输出设计

```bash
$ km stats

  KB Usage Statistics (last 30 days)

  📊 Overview
  Searches: 847   Loads: 523   Conversion: 61.7%
  Sessions: 142   Avg searches/session: 6.0

  🔥 Top Modules (by loads)
  ┌──────────────────────┬───────┬──────────┐
  │ Module               │ Loads │ Trend    │
  ├──────────────────────┼───────┼──────────┤
  │ auth/jwt             │    89 │ ████████▌│
  │ api/rate-limiting    │    67 │ ██████▎  │
  │ database/conn-pool   │    54 │ █████▍   │
  └──────────────────────┴───────┴──────────┘

  🔍 Unmatched Queries (top 5)
  ┌──────────────────────────────┬───────┐
  │ Query Theme                  │ Count │
  ├──────────────────────────────┼───────┤
  │ grpc authentication          │    12 │
  │ kubernetes pod security      │     9 │
  │ redis cluster failover       │     7 │
  └──────────────────────────────┴───────┘
  → These topics might need new modules.

  ───────────────────────────────────────
  $ km stats --period 7d    # last 7 days
  $ km stats --period 90d   # last 90 days  
  $ km stats --format json  # machine-readable
```

**注意：** 搜索查询文本经过 SHA256 hash 后存储（隐私设计，Phase 1B）。"Unmatched Queries" 展示的是查询主题（从 query_terms 逆向推断），而非原始查询文本。若需要原始文本，团队需通过 `km config set telemetry.log_raw_queries true` 显式开启。

#### 3B.3 分析 Schema

```python
class UsageStats(BaseModel):
    period_days: int
    total_searches: int
    total_loads: int
    conversion_rate: float
    total_sessions: int
    avg_searches_per_session: float
    top_modules: List[ModuleUsageEntry]
    unmatched_queries: List[UnmatchedQueryEntry]
    daily_activity: List[DailyActivityPoint]

class ModuleUsageEntry(BaseModel):
    module_id: str
    category: str
    title: str
    load_count: int
    trend: Literal["up", "down", "stable"]  # vs previous period

class UnmatchedQueryEntry(BaseModel):
    query_hash: str
    query_terms: List[str]  # stemmed terms, used to infer topic
    count: int

class DailyActivityPoint(BaseModel):
    date: str
    searches: int
    loads: int
```

#### 3B.4 MCP 资源

```
# 获取使用统计
knowledge://stats?period=30d
```

让 Agent 能回答 "最近哪些模块最受欢迎？" 或 "有哪些常搜但无匹配的查询，建议补充哪些知识模块？"

#### 3B.5 具体实现任务

| # | 任务 | 文件 | 测试 |
|---|------|------|------|
| 1 | `UsageStats` / `ModuleUsageEntry` / `UnmatchedQueryEntry` schema | `schemas.py` | schema 验证 |
| 2 | `aggregate_usage_stats(kb_path, period_days)` — 从 telemetry 聚合 | `storage.py` | 统计准确性 |
| 3 | `detect_unmatched_queries(kb_path, min_count)` — 缺口检测 | `storage.py` | 查询主题提取 |
| 4 | `km stats` CLI 命令（总览 + --period + --format json） | `cli.py` | CLI 输出验证 |
| 5 | `knowledge://stats` MCP 资源 | `mcp_server.py` | MCP 资源测试 |
| 6 | search→load 转化率计算 + 日活跃度时序 | `storage.py` | 转化率数学验证 |

---

### Phase 3C: 知识图谱分析

**动机：** Phase 1A 的图扩展让搜索能利用关联关系，但关联图本身从未被可视化或分析。`km graph` 让知识管理员看清"知识之间如何关联"，发现孤岛、枢纽和聚集簇。

#### 3C.1 图谱分析维度

**枢纽模块 (Hubs)：**
- 被最多其他模块引用的模块（in-degree 排名）
- 枢纽模块是知识库的核心——修改它们影响最大

**孤岛模块 (Orphans)：**
- 无任何 `related_modules` 入边或出边的模块
- 孤岛可能意味着：知识孤立碎片、应该归档的遗留物、或需要补充关联

**断链检测 (Broken Links)：**
- `related_modules` 引用了不存在的模块
- 输出所有断链及其引用来源

**簇检测 (Clusters)：**
- 使用简单贪心算法检测关联图中的连通分量
- 每个连通分量 = 一个知识主题簇
- 如果不同 category 的模块落在同一簇中，说明存在跨领域关联

**图密度 (Density)：**
- 边数 / 最大可能边数（模块数²）
- 低密度 = 大量孤岛，高密度 = 高度互联

#### 3C.2 CLI 输出设计

```bash
$ km graph

  Knowledge Graph Overview
  127 modules | 243 edges | density: 0.015

  🔗 Top Hubs
  ┌──────────────────────┬──────────┬────────┐
  │ Module               │ Category │ Inward │
  ├──────────────────────┼──────────┼────────┤
  │ auth/jwt             │ auth     │     12 │
  │ api/rest-standards   │ api      │      9 │
  │ database/conn-pool   │ database │      7 │
  └──────────────────────┴──────────┴────────┘

  🏝️  Orphan Modules (15)
  deployment/old-k8s, testing/legacy-mock,
  frontend/ie11-compat, ...

  🔗 Broken Links (3)
  auth/jwt → api/nonexistent-endpoint
  database/conn-pool → database/mysql5 (deprecated)

  📦 Clusters (8)
  • cluster-1: auth/*, api/rate-limiting, security/* (18 modules)
  • cluster-2: database/*, cache/* (12 modules)
  ...

  ───────────────────────────────────
  $ km graph --export mermaid
  graph TD
    auth_jwt["auth/jwt"] --> api_rate["api/rate-limiting"]
    auth_jwt --> auth_oauth["auth/oauth-flow"]
    ...

  $ km graph --export dot     # Graphviz DOT 格式
  $ km graph --format json    # 机器可读
```

**导出格式：**
- `mermaid`：可直接粘贴到 GitHub Markdown 的 Mermaid 图
- `dot`：Graphviz 格式，可渲染为 PNG/SVG
- `json`：包含 nodes + edges 的完整图数据，供外部工具消费

#### 3C.3 图谱分析 Schema

```python
class GraphStats(BaseModel):
    total_nodes: int
    total_edges: int
    density: float
    hub_modules: List[HubEntry]
    orphan_modules: List[OrphanEntry]
    broken_links: List[BrokenLinkEntry]
    clusters: List[ClusterEntry]

class HubEntry(BaseModel):
    module_id: str
    category: str
    title: str
    in_degree: int
    out_degree: int

class OrphanEntry(BaseModel):
    module_id: str
    category: str
    title: str
    status: str

class BrokenLinkEntry(BaseModel):
    source: str           # "category/module_id"
    target: str            # broken reference
    target_status: str     # "missing" | "deprecated" | "archived"

class ClusterEntry(BaseModel):
    id: str
    label: str             # derived from shared tags or dominant category
    module_count: int
    modules: List[str]     # list of "category/id"
```

#### 3C.4 MCP 工具

```
knowledge_graph(query: Optional[str], format: str = "json")
```

- 不带 `query`：返回全局图统计 + hub/orphan/broken/clusters
- 带 `query`：以匹配模块为起点，展开 N-hop 子图
- 让 Agent 能回答 "auth/jwt 关联了哪些模块？它们之间怎么关联的？"

#### 3C.5 具体实现任务

| # | 任务 | 文件 | 测试 |
|---|------|------|------|
| 1 | `GraphStats` / `HubEntry` / `OrphanEntry` / `BrokenLinkEntry` / `ClusterEntry` schema | `schemas.py` | schema 验证 |
| 2 | `analyze_graph(kb_path)` — 图统计、hub/orphan/broken 检测 | `storage.py` | 入度计算 + 断链检测 |
| 3 | `detect_clusters(kb_path)` — 连通分量聚类 | `storage.py` | 簇检测正确性 |
| 4 | `km graph` CLI 命令（总览 + --export mermaid/dot + --format json） | `cli.py` | CLI 输出 + 导出格式验证 |
| 5 | `knowledge_graph` MCP 工具（全局 + query 子图扩展） | `mcp_server.py` | MCP 工具测试 |

---

### Phase 3D: 智能推荐

**动机：** Phase 3A-C 回答了"现在怎么样"，Phase 3D 回答"下一步做什么"。基于健康度、使用数据和图结构，自动给出可操作的改进建议。

#### 3D.1 推荐类型

**归档推荐 (Archive Suggestions)：**
- 规则：ZOMBIE（90 天无加载）+ confidence = low → 建议归档
- 规则：EXPIRED（超过 expires_at） → 建议归档
- 规则：STALE（180 天未更新）+ 无入边（orphan） → 建议归档

**补充推荐 (Enrichment Suggestions)：**
- 规则：completeness < 50 → 建议补充缺少的 content 字段
- 具体指出缺少哪个字段（examples/caveats/references）

**关联推荐 (Link Suggestions)：**
- 规则：两个模块 tag 重合度 ≥ 2 但彼此不在 related_modules 中 → 建议添加关联
- 跨 category 的 tag 匹配尤其有价值（如 `auth/jwt` 和 `api/rate-limiting` 都打了 `security`）

**审查提醒 (Review Reminders)：**
- 规则：`review_interval_days` 已到期的模块
- 规则：模块被频繁加载（top 10%）但 90 天未更新 → 内容可能已过时需要审核

#### 3D.2 CLI 输出设计

```bash
$ km recommend

  🤖 Recommendations

  📦 Archive Candidates (3)
  ┌─────────────────────┬──────────┬──────────────────────────┐
  │ Module              │ Score    │ Reason                   │
  ├─────────────────────┼──────────┼──────────────────────────┤
  │ auth/old-jwt        │ 0.92     │ ZOMBIE, LOW confidence   │
  │ database/mysql5     │ 0.87     │ EXPIRED, orphan          │
  │ deployment/legacy   │ 0.74     │ STALE 210d, orphan       │
  └─────────────────────┴──────────┴──────────────────────────┘

  ✏️  Needs Enrichment (5)
  ┌─────────────────────┬──────────┬──────────────────────────┐
  │ Module              │ Score    │ Missing                  │
  ├─────────────────────┼──────────┼──────────────────────────┤
  │ api/graphql-setup   │ 0.85     │ examples, caveats        │
  │ testing/e2e-pattern │ 0.72     │ references               │
  └─────────────────────┴──────────┴──────────────────────────┘

  🔗 Suggested Links (4)
  ┌─────────────────────┬─────────────────────┬───────────────┐
  │ Module A            │ Module B            │ Shared Tags  │
  ├─────────────────────┼─────────────────────┼───────────────┤
  │ auth/jwt            │ api/rate-limiting   │ auth, security│
  │ cache/redis         │ database/conn-pool  │ cache, perf   │
  └─────────────────────┴─────────────────────┴───────────────┘

  ⏰ Review Reminders (2)
  ┌─────────────────────┬──────────┬──────────────────────────┐
  │ Module              │ Due      │ Reason                   │
  ├─────────────────────┼──────────┼──────────────────────────┤
  │ security/owasp-top10│ 3d ago   │ review_interval expired  │
  │ api/rest-standards  │ in 5d    │ Top module, 92d no update│
  └─────────────────────┴──────────┴──────────────────────────┘

  ───────────────────────────────────
  $ km recommend --type archive     # 仅归档推荐
  $ km recommend --type enrich      # 仅补充推荐
  $ km recommend --type links       # 仅关联推荐
  $ km recommend --format json      # 机器可读
```

#### 3D.3 推荐 Schema

```python
class RecommendationType(str, Enum):
    ARCHIVE = "archive"
    ENRICH = "enrich"
    LINK = "link"
    REVIEW = "review"

class Recommendation(BaseModel):
    type: RecommendationType
    module_id: str
    category: str
    title: str
    score: float                # 0-1, higher = stronger recommendation
    reason: str
    detail: Dict[str, Any]      # type-specific detail

class RecommendationReport(BaseModel):
    generated_at: datetime
    archive_candidates: List[Recommendation]
    enrichment_needed: List[Recommendation]
    suggested_links: List[Recommendation]
    review_reminders: List[Recommendation]
```

#### 3D.4 批量操作

`km recommend` 给出建议后，`km apply` 批量执行：

```bash
# 预览归档候选（dry run）
$ km apply --type archive --dry-run

# 执行所有归档推荐
$ km apply --type archive

# 执行特定模块的推荐
$ km apply --type enrich --module api/graphql-setup

# 交互式确认模式
$ km apply --type archive --confirm
  → 逐个列出推荐，[y/n/s] 确认/跳过/全部
```

#### 3D.5 具体实现任务

| # | 任务 | 文件 | 测试 |
|---|------|------|------|
| 1 | `Recommendation` / `RecommendationReport` schema | `schemas.py` | schema 验证 |
| 2 | `generate_recommendations(kb_path)` — 四类推荐规则引擎 | `storage.py` | 每类推荐的规则触发条件 |
| 3 | `km recommend` CLI 命令（总览 + --type + --format json） | `cli.py` | CLI 输出验证 |
| 4 | `km apply` CLI 命令（--type + --dry-run + --confirm + --module） | `cli.py` | 批量操作 + dry-run 验证 |
| 5 | `knowledge://recommendations` MCP 资源 | `mcp_server.py` | MCP 资源测试 |

---

### Phase 3 整体交付节奏

```
Phase 3A (健康仪表盘)    ████████████░░░░░░  5 任务，基础依赖（需 telemetry + schema）
Phase 3B (使用分析)      ░░░░░░░░████████░░  6 任务，依赖 3A 的健康度模型
Phase 3C (图谱分析)      ░░░░░░░░░░░░░░████  5 任务，独立可做（仅依赖 graph 字段）
Phase 3D (智能推荐)      ░░░░░░░░░░░░░░░███  5 任务，依赖 3A+3B+3C 的全量数据
```

3A 是 Phase 3 的核心——健康度模型是 3B（分析）和 3D（推荐）的基础。3C（图谱分析）可独立实施，甚至可与 3A 并行。

### Phase 3 成功指标

- `km health` 在 < 2s 内完成 200+ 模块的健康扫描
- 健康报告让知识管理员在 30 秒内判断 KB 整体状态
- `km stats` 准确反映搜索→加载的真实转化率
- `km graph` 生成的 Mermaid 图可直接粘贴到 GitHub Markdown 渲染
- `km recommend` 的归档建议准确率 ≥ 70%（用户确认率）
- MCP `knowledge_graph` 让 Agent 能基于图结构回答关联性问题
- 新增 ≥ 30 个测试，覆盖全部 4 个子阶段

---

## Phase 4: 生态层

**目标：** Knowledge Manager 成为 Agent 工作流中"知识"层的标准连接件。不只是一个独立工具，而是一个可以被任何 Agent 平台按需调用的知识插件。

**现状（2026-06，Phase 3 完整交付）：**
- 完整的知识资产洞察：健康度仪表盘、使用分析、图谱分析、智能推荐
- `km health` / `km usage` / `km graph` / `km recommend` / `km apply` 全系列洞察命令
- MCP 资源：health、stats、recommendations + knowledge_graph 工具
- 272 个测试，全量通过
- 缺口：无平台连接器、无多 KB 联邦、无知识市场、无外部工作流集成

**核心场景：**
- 用户在 Claude Code 中输入 `/knowledge` 即可搜索团队知识库
- VS Code Copilot 自动从团队 KB 中获取上下文建议
- CI/CD 流水线在部署前检查相关模块是否有过时警告
- 第三方 Agent 平台通过标准 MCP 端点接入知识库
- 大公司内部有多个团队 KB（auth 团队、infra 团队、前端团队），Agent 需要同时查询

---

### Phase 4A: 平台连接器 (`km connect`)

**动机：** 目前接入 KM 需要手动编写 MCP 配置文件——知道 JSON 结构、知道 kb_path、知道工具名。`km connect` 收窄为一条命令，10 秒完成接入，消除配置门槛。

#### 4A.1 支持的平台

| 平台 | 配置方式 | 优先级 |
|------|---------|--------|
| **Claude Code** | `.claude/mcp.json` 写入 | P0（目标用户群） |
| **VS Code Copilot** | `.vscode/mcp.json` 写入 | P0（最大用户群） |
| **Cursor** | `.cursor/mcp.json` 写入 | P1 |
| **Windsurf** | `.windsurf/mcp.json` 写入 | P1 |
| **Generic** | 输出 `mcp.json` 片段到 stdout | P2（兜底） |

#### 4A.2 CLI 设计

```bash
# 一键接入 Claude Code
$ km connect claude-code
  → 检测 ~/.claude/ 目录
  → 检查是否已有 knowledge-manager 配置（避免重复）
  → 写入 .claude/mcp.json 中的 knowledge-manager 条目
  → 输出：✅ Connected to Claude Code. Restart Claude Code to activate.

# 接入 VS Code Copilot
$ km connect copilot
  → 检测当前 workspace 的 .vscode/ 目录
  → 写入 .vscode/mcp.json

# 列出所有可用平台
$ km connect --list
  claude-code      Claude Code (via .claude/mcp.json)
  copilot          VS Code GitHub Copilot (via .vscode/mcp.json)
  cursor           Cursor IDE (via .cursor/mcp.json)
  windsurf         Windsurf IDE (via .windsurf/mcp.json)

# 生成通用配置（打印到 stdout）
$ km connect --print
  → 输出 JSON 片段，用户可手动复制到任意 MCP 客户端

# 断开连接
$ km disconnect claude-code
  → 从 .claude/mcp.json 中移除 knowledge-manager 条目
  → 不删除文件（可能还有其他 MCP server 配置）
```

#### 4A.3 配置模板 Schema

生成的 MCP 配置格式：

```json
{
  "mcpServers": {
    "knowledge-manager": {
      "command": "km",
      "args": ["--kb-path", "/path/to/kb", "serve"],
      "env": {}
    }
  }
}
```

关键设计决策：
- 使用 `km serve` 命令（已有的 stdio MCP server），零额外依赖
- `--kb-path` 自动展开为绝对路径
- 不注入任何环境变量（api key 等由 KB 自身的 `config.json` 管理）
- 如果目标文件已有其他 MCP server 配置，做 JSON merge 而非覆盖

#### 4A.4 实现要点

**`km connect <platform>` 逻辑：**
1. 解析平台 → 目标配置文件路径（如 `~/.claude/mcp.json`）
2. 检测目标文件是否存在：不存在则创建，存在则读取
3. 检测 `mcpServers.knowledge-manager` 是否已存在 → 如存在则询问是否覆盖
4. 生成配置条目，合并到目标 JSON
5. 写入文件，输出成功提示

**`km disconnect <platform>` 逻辑：**
1. 读取目标配置文件
2. 移除 `mcpServers.knowledge-manager` 条目
3. 如果 `mcpServers` 为空，保留文件（用户可能有其他用途）
4. 输出：Removed from .claude/mcp.json

#### 4A.5 具体实现任务

| # | 任务 | 文件 | 测试 |
|---|------|------|------|
| 1 | `PlatformConfig` schema — 平台名→路径映射 | `schemas.py` | schema 验证 |
| 2 | `detect_platform_config_path(platform)` — 跨平台路径解析 | `storage.py` | macOS/Linux/Windows 路径 |
| 3 | `read_mcp_config(path)` / `write_mcp_config(path, entry)` — JSON merge 读写 | `storage.py` | 新建/合并/冲突检测 |
| 4 | `km connect <platform>` CLI 命令（生成 + 写入） | `cli.py` | claude-code/copilot/cursor 平台 |
| 5 | `km connect --list` — 列出可用平台 | `cli.py` | 输出格式验证 |
| 6 | `km connect --print` — 输出到 stdout | `cli.py` | JSON 格式 + kb_path 正确 |
| 7 | `km disconnect <platform>` CLI 命令 | `cli.py` | 移除条目 + 保留其他 server |
| 8 | 重复连接检测 + overwrite 提示 | `cli.py` | 交互确认 + `--force` 跳过 |

---

### Phase 4B: 多 KB 联邦 (MCP Gateway)

**动机：** 大型组织的知识天然分散在多个 KB 中——auth 团队有安全知识库，infra 团队有运维知识库，前端团队有组件知识库。Agent 需要在一次对话中跨多个 KB 搜索和加载模块。

**核心设计原则：**
- 不引入新的服务进程或网关层。联邦通过 MCP server 内部的命名空间隔离实现。
- 一个 MCP server 注册多个 KB，每个 KB 有独立的命名空间前缀。
- 工具和资源路径加前缀以区分来源 KB。

#### 4B.1 联邦配置

在 KB 的 `config.json` 中声明联邦：

```json
{
  "federation": {
    "namespaces": {
      "auth": {
        "kb_path": "../team-auth-kb",
        "description": "Auth team knowledge base",
        "search_default": true
      },
      "infra": {
        "kb_path": "../team-infra-kb",
        "description": "Infrastructure knowledge base",
        "search_default": true
      },
      "frontend": {
        "kb_path": "../team-frontend-kb",
        "description": "Frontend patterns KB",
        "search_default": false
      }
    }
  }
}
```

- `namespaces`：每个命名空间映射到另一个 KB 的本地路径（通常在同一 monorepo 中，通过 git submodule 或相对路径引用）
- `search_default`：该命名空间是否参与默认搜索。P0 高频 KB 设为 true，低频 KB 按需查询
- 主 KB（当前 `kb_path`）使用默认命名空间 `default` 或 `main`

#### 4B.2 命名空间隔离

每个工具/资源在联邦模式下加命名空间前缀：

| 单 KB 模式 | 联邦模式 |
|-----------|---------|
| `knowledge://index` | `knowledge://auth/index` |
| `knowledge://health` | `knowledge://infra/health` |
| `search_modules(query)` | `search_modules(query, namespace="auth")` |
| `load_module(id, cat)` | `load_module(id, cat, namespace="infra")` |

**资源路径规则：** `knowledge://<namespace>/<resource>`，其中 `<namespace>` 为 `default` 时等同于单 KB 模式。

**工具参数扩展：** 所有现有工具增加可选参数 `namespace: str = "default"`。不传时搜索主 KB。

#### 4B.3 跨 KB 联合搜索

新增工具 `federated_search`：

```
federated_search(query: str, namespaces: List[str] = [], top_per_ns: int = 5)
  → 在指定命名空间（或所有 search_default=true 的命名空间）中并行搜索
  → 返回按命名空间分组的结果
  → 每个命名空间 top-N 结果
```

**排序规则：**
- 命名空间内按现有排序规则（heuristic + confidence + bayesian + BM25）
- 跨命名空间不混合排序（每个 NS 的结果独立分组）
- 调用方（LLM）自行判断哪个命名空间的结果更相关

#### 4B.4 索引联邦

新增资源 `knowledge://federation/index` 返回联邦索引摘要：

```json
{
  "namespaces": {
    "auth": {
      "description": "Auth team knowledge base",
      "total_modules": 15,
      "categories": ["auth", "security"],
      "last_updated": "2026-07-01T..."
    },
    "infra": {
      "description": "Infrastructure knowledge base",
      "total_modules": 22,
      "categories": ["deployment", "database", "cache"],
      "last_updated": "2026-07-02T..."
    }
  },
  "total_namespaces": 3,
  "total_modules": 54,
  "search_default_namespaces": ["auth", "infra"]
}
```

Agent 在对话开始时读取此资源，即可知道"有哪些知识库可用"。

#### 4B.5 实现要点

**MCP Server 启动时：**
1. 读取主 KB 的 `config.json`
2. 如果存在 `federation.namespaces`，验证每个命名空间路径是否有效（`index.json` 存在）
3. 加载所有命名空间的索引到内存（Index 对象很轻量，几百个模块也 < 100KB）
4. 注册带命名空间的资源路径和工具参数

**缓存隔离：** `ModuleCache` 按 `namespace:module_id` 做键隔离，避免不同 KB 的同名模块互相覆盖。

**错误处理：** 如果某个命名空间路径不可达（如 submodule 未初始化），跳过该命名空间并记录警告，不影响主 KB 和其他命名空间。

#### 4B.6 具体实现任务

| # | 任务 | 文件 | 测试 |
|---|------|------|------|
| 1 | `FederationConfig` / `NamespaceEntry` schema | `schemas.py` | schema 验证 + 默认值 |
| 2 | `load_federation(kb_path)` — 验证并加载所有命名空间索引 | `storage.py` | 路径验证 + 缺失处理 |
| 3 | MCP server 联邦资源注册（`knowledge://<ns>/index` 等） | `mcp_server.py` | 多 NS 资源路由 |
| 4 | 所有工具增加 `namespace` 可选参数 | `mcp_server.py` | 跨 NS 搜索/加载 |
| 5 | `federated_search` 工具 — 并行跨 KB 搜索 | `mcp_server.py` | 结果分组 + top-N 截断 |
| 6 | `knowledge://federation/index` 联邦索引摘要资源 | `mcp_server.py` | 摘要格式验证 |
| 7 | ModuleCache 按 namespace 隔离 | `cache.py` | 跨 NS 同名模块 |
| 8 | CLI `km serve --federation` 启动联邦模式 | `cli.py` | 多 KB 启动验证 |

---

### Phase 4C: 知识 Webhook（出站集成）

**动机：** Phase 2C 的 webhook 通知只是"告诉你有变化了"。Phase 4C 升级为结构化事件推送，让外部系统（CI/CD、项目管理、监控）能消费知识库的变更事件并自动响应。

**核心场景：**
- `api-rate-limiting` 模块被标记为 deprecated → 自动创建 Jira ticket 提醒相关服务更新
- 模块新增（`module.added`） → 触发 CI 流水线做文档一致性检查
- 模块过期（`module.expired`） → 发送 Slack 告警给模块最后编辑者
- 健康分下降（`health.degraded`） → 记录到可观测平台（Datadog/Grafana）

#### 4C.1 事件类型

| 事件 | 触发时机 | Payload 关键字段 |
|------|---------|-----------------|
| `module.created` | 新模块从 staging 合并到正式 KB | module_id, category, title, author, tags |
| `module.updated` | 模块内容或元数据变更 | module_id, category, changed_fields, diff_summary |
| `module.deprecated` | 模块标记为 deprecated | module_id, category, reason, replacement_module |
| `module.archived` | 模块归档 | module_id, category |
| `module.expired` | 超过 expires_at | module_id, category, expired_at |
| `module.deleted` | 模块被删除 | module_id, category |
| `health.degraded` | 模块健康分降到阈值以下 | module_id, category, old_score, new_score |
| `review.submitted` | 新模块进入 staging 等待审核 | module_id, category, submitted_by |
| `review.approved` | 模块通过审核 | module_id, category, reviewer, approvals_count |

#### 4C.2 Webhook 配置

```json
{
  "webhooks": {
    "enabled": true,
    "endpoints": [
      {
        "url": "https://hooks.slack.com/services/...",
        "events": ["module.deprecated", "module.expired", "health.degraded"],
        "headers": {},
        "retry": {"max_attempts": 3, "backoff_seconds": 30}
      },
      {
        "url": "https://jira.company.com/rest/webhooks/1.0/kb-events",
        "events": ["module.deprecated", "module.created"],
        "headers": {"Authorization": "Bearer <JIRA_TOKEN>"},
        "secret": "<HMAC_SIGNING_SECRET>",
        "retry": {"max_attempts": 5, "backoff_seconds": 60}
      }
    ]
  }
}
```

**设计决策：**
- 多个 endpoint 各自订阅不同事件子集——避免噪音
- `secret` 字段用于 HMAC-SHA256 签名，接收方可验证推送来源
- 重试机制：指数退避，最大 5 次，失败后记录到 `.webhook_failures.jsonl`
- 所有 webhook 调用异步执行，不阻塞 KM 主操作

#### 4C.3 CLI 设计

```bash
# 查看 webhook 配置
$ km webhook status
  Endpoint: https://hooks.slack.com/...
    Events: module.deprecated, module.expired, health.degraded
    Last delivery: 2026-07-15T10:30:00Z ✅ (HTTP 200)
    Failures (24h): 0

  Endpoint: https://jira.company.com/...
    Events: module.deprecated, module.created
    Last delivery: 2026-07-15T09:00:00Z ✅ (HTTP 200)
    Failures (24h): 2

# 测试 webhook 连接
$ km webhook test --endpoint 0
  → 发送测试 payload 到指定 endpoint
  → 输出 HTTP 状态码和响应

# 重放失败的 webhook
$ km webhook retry --since 2026-07-14
  → 读取 .webhook_failures.jsonl
  → 重新发送失败事件

# 配置 webhook
$ km config set webhooks.endpoints.0.url "https://..."
$ km config set webhooks.endpoints.0.events '["module.deprecated", "module.expired"]'
```

#### 4C.4 事件 Payload Schema

```python
class WebhookEvent(BaseModel):
    event: str                      # e.g. "module.deprecated"
    timestamp: datetime
    kb_path: str                    # local KB path (for identification)
    kb_name: str = ""               # human-readable KB name from config
    module_id: str
    category: str
    data: Dict[str, Any] = {}       # event-specific payload

class WebhookEndpoint(BaseModel):
    url: str
    events: List[str] = []          # empty = all events
    headers: Dict[str, str] = {}
    secret: str = ""                # HMAC signing secret
    retry: WebhookRetryConfig = Field(default_factory=WebhookRetryConfig)

class WebhookRetryConfig(BaseModel):
    max_attempts: int = 3
    backoff_seconds: int = 30

class WebhookConfig(BaseModel):
    enabled: bool = False
    endpoints: List[WebhookEndpoint] = []
```

#### 4C.5 实现要点

**事件触发钩子：** 在 `storage.py` 的关键操作（save_module→updated/created、deprecate、archive、delete_module）中插入 `emit_event()` 调用。事件发送是异步 post-action hook，不阻塞主操作。

**失败处理：** 失败的 webhook 写入 `.webhook_failures.jsonl`，记录事件、目标 URL、失败时间和 HTTP 状态码。`km webhook retry` 读取并重放。

**签名：** 如果配置了 `secret`，在 HTTP header 中加 `X-KM-Signature: sha256=<HMAC(payload, secret)>`。接收方用同样算法验证。

#### 4C.6 具体实现任务

| # | 任务 | 文件 | 测试 |
|---|------|------|------|
| 1 | `WebhookEvent` / `WebhookEndpoint` / `WebhookConfig` schema | `schemas.py` | schema 验证 |
| 2 | `emit_event(kb_path, event)` — 异步事件分发引擎 | `storage.py` | 多 endpoint 分发 + 签名 |
| 3 | `load_webhook_failures()` / `retry_webhooks()` — 失败重试 | `storage.py` | 重试逻辑 + 去重 |
| 4 | 在 save_module/deprecate/archive/delete_module 中插入钩子 | `storage.py` + `cli.py` | 事件触发验证 |
| 5 | `km webhook status` / `test` / `retry` CLI 命令 | `cli.py` | CLI 输出 + 测试模式 |
| 6 | Webhook 异步发送（httpx AsyncClient，超时 + 重试） | 新建 `webhooks.py` | HTTP 200/400/500 场景 |

---

### Phase 4D: 知识市场（Knowledge Marketplace）

**动机：** 每个团队都在重新发明轮子——大家都在写 "JWT 最佳实践"、"REST API 设计规范"、"Docker 部署清单"。知识市场让团队可以共享和复用高质量的模块模板，降低知识库冷启动成本。

**定位：** 类似 Docker Hub 但面向知识模块。社区贡献、人工审核、团队按需安装。

**注意：** 这是 Phase 4 最远期的能力，依赖外部基础设施（市场索引托管、审核流程、社区运营）。以下设计聚焦于客户端侧的 `km install` 和 `km publish` 命令，市场服务端可后续独立设计。

#### 4D.1 核心命令

```bash
# 从市场安装模块模板
$ km install community/auth/oauth2-best-practices
  → 从 marketplace index 查找模块元数据
  → 下载模块 JSON + 依赖模块（related_modules 也在市场中）
  → 提示用户确认 category 映射（marketplace category → 本地 category）
  → 将模块放入本地 .staging/ 等待审核
  → 输出：Installed auth/oauth2-best-practices into staging. Review with 'km review'.

# 搜索市场
$ km marketplace search "JWT authentication"
  → 查询远程市场索引
  → 展示匹配的模板：名称、描述、下载量、评分、最近更新

# 查看市场模块详情
$ km marketplace show community/auth/oauth2-best-practices
  → 展示模块完整内容（JSON 格式）
  → 展示评分、下载量、依赖、版本历史

# 发布到市场
$ km publish auth/my-module
  → 验证模块完整性（健康分 ≥ 70 + confidence ≥ medium）
  → 脱敏处理（移除内部链接、特定域名等，通过 config.json 配置规则）
  → 打包为市场格式
  → 推送到市场 Git 仓库或 API endpoint
```

#### 4D.2 市场索引格式

市场本身就是一个公开的 Git 仓库，结构如下：

```
knowledge-marketplace/
  ├── index.json            # 全局索引（所有可用模板）
  ├── auth/
  │   ├── oauth2-best-practices.json
  │   └── jwt-security-guide.json
  ├── api/
  │   ├── rest-design-standards.json
  │   └── graphql-patterns.json
  └── ...
```

`index.json` 结构：

```json
{
  "version": "1.0",
  "modules": {
    "auth/oauth2-best-practices": {
      "title": "OAuth 2.0 Best Practices",
      "summary": "Security-focused OAuth 2.0 implementation guide",
      "tags": ["auth", "security", "oauth"],
      "confidence": "high",
      "author": "community",
      "version": "2.1.0",
      "downloads": 847,
      "rating": 4.7,
      "ratings_count": 23,
      "updated_at": "2026-07-01T...",
      "dependencies": []
    }
  }
}
```

#### 4D.3 安装流程

```
km install community/<category>/<module-id>
  │
  ├─ 1. 获取市场索引（git pull 或 HTTP GET）
  ├─ 2. 查找目标模块 + 解析依赖（递归最多 3 层）
  ├─ 3. 展示安装计划：
  │      Will install:
  │        • auth/oauth2-best-practices v2.1.0
  │        • security/csrf-protection v1.0.0 (dependency)
  │      Into: .staging/
  ├─ 4. 用户确认（--yes 跳过）
  ├─ 5. 下载每个模块 JSON
  ├─ 6. 映射 category（marketplace "auth" → 本地 "auth" 或用户指定）
  ├─ 7. 写入 .staging/ + 生成 .meta.json（submitted_by="marketplace"）
  └─ 8. 输出安装摘要
```

**依赖解析：** 如果安装的模块 `related_modules` 引用了市场中存在的其他模块，自动标记为依赖并一同安装。最多递归 3 层，超过则提示用户手动处理。

**本地修改追踪：** 从市场安装的模块记录来源：
```json
// 在 .staging/<module>.meta.json 中增加
{
  "source": "marketplace",
  "marketplace_module": "community/auth/oauth2-best-practices",
  "marketplace_version": "2.1.0",
  "installed_at": "2026-07-15T..."
}
```

#### 4D.4 发布流程

```bash
$ km publish auth/my-module
```

**发布前检查（Gate）：**
1. 模块健康分 ≥ 70
2. `metadata.confidence` ≥ `medium`
3. `content.overview` + `content.details` 非空
4. 模块不在 staging 中（必须是已发布的正式模块）
5. 模块 ID 不与市场已有模块冲突

**脱敏处理：**
- 根据 `config.json` 中的 `marketplace.sanitize_patterns` 替换敏感信息
- 默认规则：替换 `@company.com` 邮箱域名为 `@example.com`，替换内网 URL
- 用户可在 `km publish` 前用 `km publish --dry-run` 预览脱敏后的模块内容

**版本管理：** 市场模块在源模块的 metadata 中增加 `marketplace_version` 字段。发布时如果模块 ID 已存在，自动递增 patch 版本号。

#### 4D.5 客户端 Schema

```python
class MarketplaceModule(BaseModel):
    id: str
    category: str
    title: str
    summary: str
    tags: List[str] = []
    confidence: str = "medium"
    author: str = "community"
    version: str = "1.0.0"
    downloads: int = 0
    rating: float = 0.0
    ratings_count: int = 0
    updated_at: datetime
    dependencies: List[str] = []

class MarketplaceIndex(BaseModel):
    version: str = "1.0"
    modules: Dict[str, MarketplaceModule] = {}
    last_updated: datetime = Field(default_factory=utc_now)

class InstallPlan(BaseModel):
    modules: List[MarketplaceModule]
    target_category: str
    dependencies_installed: List[str] = []
```

#### 4D.6 具体实现任务

| # | 任务 | 文件 | 测试 |
|---|------|------|------|
| 1 | `MarketplaceModule` / `MarketplaceIndex` / `InstallPlan` schema | `schemas.py` | schema 验证 |
| 2 | `fetch_marketplace_index(url)` — 从远程 Git/HTTP 获取市场索引 | `storage.py` | HTTP 200/404 + Git 拉取 |
| 3 | `resolve_install_plan(module_ref, index)` — 依赖解析（3 层递归） | `storage.py` | 依赖树正确 + 循环依赖处理 |
| 4 | `install_from_marketplace(module_ref, kb_path)` — 下载 + 写入 staging | `storage.py` | 安装成功 + 依赖安装 |
| 5 | `km marketplace search <query>` CLI — 搜索远程市场 | `cli.py` | 搜索输出验证 |
| 6 | `km marketplace show <module>` CLI — 查看市场模块详情 | `cli.py` | JSON 格式输出 |
| 7 | `km install <module_ref>` CLI — 安装到本地 staging | `cli.py` | 安装流程 + 确认交互 |
| 8 | `km publish <module_ref>` CLI — 发布前检查 + 脱敏 + 推送 | `cli.py` | gate 检查 + dry-run 脱敏预览 |
| 9 | 脱敏规则配置 + 应用 (`marketplace.sanitize_patterns`) | `storage.py` | 邮箱/URL 脱敏验证 |

---

### Phase 4 整体交付节奏

```
Phase 4A (平台连接器)      ████████████░░░░░░  8 任务，零依赖，可立刻做
Phase 4B (多 KB 联邦)      ░░░░░░████████░░░░  8 任务，依赖 4A 的配置读写
Phase 4C (知识 Webhook)    ░░░░░░░░░░░░████░░  6 任务，独立可做
Phase 4D (知识市场)        ░░░░░░░░░░░░░░░███  9 任务，需外部市场基础设施
```

4A 是 Phase 4 的入口——`km connect` 让用户可以立刻在 Claude Code/Copilot 中用到 KM，是用户增长的杠杆。4B 需要 4A 的配置基础设施但解决了大型团队的核心痛点。4C 独立可做。4D 依赖外部市场 index 仓库的建立。

### Phase 4 成功指标

- `km connect` 在 3 个主流平台上 10 秒内完成配置
- 联邦模式下 Agent 可无感知搜索 3 个以上 KB（延迟 < 500ms）
- Webhook 事件到达率 ≥ 99%（含重试）
- 知识市场有 ≥ 20 个社区贡献模板
- 新增 ≥ 45 个测试，覆盖全部 4 个子阶段
- 不引入向量数据库、SQL 数据库、消息队列（持续守住设计边界）

---

## 技术架构演进全景

```
 Phase 1 ✅                  Phase 2 ✅              Phase 3 ✅              Phase 4 ✅
┌──────────────┐           ┌──────────────┐       ┌──────────────┐        ┌──────────────┐
│  CLI (click) │           │  CLI + git   │       │  CLI + Dashboard│     │  CLI + API  │
│  init/add/   │           │  clone/pull/ │       │  health/usage │        │  connect/    │
│  review/search│          │  push/status │       │  graph/recomm.│        │  marketplace │
│  stale/config│           │  diff        │       │  apply        │        │  install     │
├──────────────┤           ├──────────────┤       ├──────────────┤        ├──────────────┤
│ MCP Server   │           │ MCP Server   │       │ MCP Server   │        │ MCP Gateway │
│ (stdio)      │           │ (stdio)      │       │ (stdio)      │        │ (multi-KB)  │
│ index资源    │           │ +changelog   │       │ +health资源  │        │ +federated   │
│ 6工具        │           │ 资源 + 8工具 │       │ +stats资源   │        │ search       │
├──────────────┤           ├──────────────┤       │ +graph工具   │        ├──────────────┤
│ Storage      │           │ Storage      │       │ Storage      │        │ Storage     │
│ (local fs)   │           │ (git remote) │       │ (git + cache)│        │ (federated) │
├──────────────┤           ├──────────────┤       ├──────────────┤        ├──────────────┤
│ Search       │           │ Search       │       │ Search       │        │ Search      │
│ rule+BM25    │           │ +archived    │       │ +analytics   │        │ (full model)│
│ +graph+conf  │           │ filter       │       │               │        │             │
│ +bayesian    │           │ +deprec.pen. │       │               │        │             │
│ +intent+ctx  │           │ +status aware│       │               │        │             │
├──────────────┤           ├──────────────┤       ├──────────────┤        ├──────────────┤
│ Telemetry    │           │ Review       │       │ Health       │        │ Marketplace │
│ +Rank Model  │           │ Pipeline     │       │ Analytics    │        │ Webhooks    │
│ +Synonyms    │           │ +Staging Meta│       │ Graph        │        │ Federation  │
│ +Expiry Mgt  │           │ +Changelog   │       │ Recommend    │        │ Connect     │
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
- 图扩展使关联模块召回率从 0% 提升到 >60% ✅
- confidence 加权使 high-confidence 模块在同等匹配分数下优先于 low-confidence ✅
- 现有 106 个测试全部通过，新增 ≥15 个测试 ✅（实际交付：137→154 tests）
- `km search` 输出展示 confidence 和 source 标记 ✅

### Phase 1B
- 朴素贝叶斯模型在 100+ 事件后，Top-3 准确率比纯规则提升 ≥10% ✅
- 搜索事件写入开销 < 1ms（不影响搜索响应速度） ✅
- 所有 telemetry 数据在本地，无网络请求 ✅
- `km rank status` 可展示模型状态和特征重要性 ✅

### Phase 1C（超额交付）
- details 字段参与启发式搜索（P0-1） ✅
- rebuild_index 自动生成 category description（P0-2） ✅
- 用户可配置同义词词典 Config.synonyms（P1-3） ✅
- 加权图边 "cat/id:0.8" 语法（P1-4） ✅
- 模块时效性标记 + `km stale` 命令（P1-5） ✅
- 查询意图分类 4 类模式（P2-1） ✅
- 会话级查询上下文 boost_ids（P2-2） ✅

### Phase 2
- 3 人团队可通过 `km clone/pull/push` 协作
- 多人并发修改同一模块时，git 冲突处理流程清晰可用
- changelog 资源让 Agent 感知知识库变更

### Phase 3
- `km health` 在 < 2s 内完成 200 模块的健康扫描 ✅ （实际：272 tests 通过）
- 知识图谱数据让 LLM 能回答"哪些模块应该一起读" ✅
- 模块状态机完整（draft→published→deprecated→archived） ✅

### Phase 4
- `km connect` 在 3 个主流平台上 10 秒内完成配置
- 联邦模式下 Agent 可无感知搜索 3 个以上 KB（延迟 < 500ms）
- Webhook 事件到达率 ≥ 99%（含重试）
- 知识市场有 ≥ 20 个社区贡献模板
- 新增 ≥ 45 个测试，覆盖全部 4 个子阶段
- 不引入向量数据库、SQL 数据库、消息队列（守住设计边界）

---

## 当前状态与下一步

**已完成：**
- Phase 0（MVP）：CLI + MCP server + 提取 + 审核 + 搜索（启发式 + BM25）
- Phase 1A（图扩展 + 置信度加权 + expand_module + source 标记）：6 任务 ✅
- Phase 1B（遥测采集 + 贝叶斯排序 + 排序模型持久化 + rank/telemetry CLI）：8 任务 ✅
- Phase 1C（6 项评估优化 + 2 项短板增强）：details 搜索、category description、同义词词典、加权图边、时效性标记 + `km stale`、意图分类、会话上下文 ✅
- Phase 2A（Git 远程协作：clone/pull/push/status/diff + api_key 脱敏）：7 任务 ✅
- Phase 2B（多人审核管线：staging meta、review approve/request-changes/list/show/my-submissions）：8 任务 ✅
- Phase 2C（变更感知：changelog 生成、MCP changelog 资源、webhook 通知）：6 任务 ✅
- Phase 2D（模块状态机：deprecate/archive、archived 过滤、deprecated 降权）：5 任务 ✅
- Phase 3A（健康度仪表盘：HealthScore/module health/KB health/km health/MCP health）：5 任务 ✅
- Phase 3B（使用分析：UsageStats/aggregate/km usage/MCP stats）：6 任务 ✅
- Phase 3C（图谱分析：GraphStats/analyze/detect clusters/km graph/knowledge_graph）：5 任务 ✅
- Phase 3D（智能推荐：Recommendation/generate/km recommend/km apply/MCP recommendations）：5 任务 ✅
- Phase 4A（平台连接器：PlatformConfig/connect.py/km connect+disconnect）：8 任务 ✅
- Phase 4B（多 KB 联邦：FederationConfig/load_federation/federated_search/namespace cache）：8 任务 ✅
- Phase 4C（知识 Webhook：WebhookConfig/webhooks.py/emit_event hooks/km webhook CLI）：6 任务 ✅
- Phase 4D（知识市场：MarketplaceIndex/marketplace.py/km install+publish+marketplace）：9 任务 ✅
- 342 个测试，全量通过

**状态：** 蓝图四阶段全部实施完毕。Phase 1-4 共 ~115 个任务，所有代码 + 测试交付完成。
