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
 Phase 1 (完整交付)         Phase 2 (待实施)       Phase 3                  Phase 4
┌──────────────┐           ┌──────────────┐       ┌──────────────┐        ┌──────────────┐
│  CLI (click) │           │  CLI + git   │       │  CLI + Dashboard│     │  CLI + API  │
│  init/add/   │           │  clone/pull/ │       │  health/stats │        │  connect     │
│  review/search│          │  push/status │       │  graph/viz    │        │  marketplace │
│  stale/config│           │  diff        │       │               │        │             │
├──────────────┤           ├──────────────┤       ├──────────────┤        ├──────────────┤
│ MCP Server   │           │ MCP Server   │       │ MCP Server   │        │ MCP Gateway │
│ (stdio)      │           │ (stdio)      │       │ (stdio+SSE)  │        │ (multi-KB)  │
│ index资源    │           │ +changelog   │       │ +graph资源   │        │             │
│ 6个工具      │           │ 资源         │       │               │        │             │
├──────────────┤           ├──────────────┤       ├──────────────┤        ├──────────────┤
│ Storage      │           │ Storage      │       │ Storage      │        │ Storage     │
│ (local fs)   │           │ (git remote) │       │ (git + cache)│        │ (federated) │
├──────────────┤           ├──────────────┤       ├──────────────┤        ├──────────────┤
│ Search       │           │ Search       │       │ Search       │        │ Search      │
│ rule+BM25    │           │ +archived    │       │ +analytics   │        │ (full model)│
│ +graph+conf  │           │ filter       │       │               │        │             │
│ +bayesian    │           │              │       │               │        │             │
│ +intent+ctx  │           │              │       │               │        │             │
├──────────────┤           ├──────────────┤       ├──────────────┤        ├──────────────┤
│ Telemetry    │           │ Review       │       │ Analytics    │        │ Marketplace │
│ +Rank Model  │           │ Pipeline     │       │ Health       │        │ Webhooks    │
│ +Synonyms    │           │ +Staging Meta│       │ Lifecycle    │        │ Federation  │
│ +Expiry Mgt  │           │ +Changelog   │       │              │        │             │
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
- Phase 1A（图扩展 + 置信度加权 + expand_module + source 标记）：6 个任务全部完成
- Phase 1B（遥测采集 + 贝叶斯排序 + 排序模型持久化 + rank/telemetry CLI）：8 个任务全部完成
- Phase 1C（6 项评估优化 + 2 项短板增强）：details 字段搜索、category description 自动生成、用户可配置同义词词典、加权图边、模块时效性标记 + `km stale`、查询意图分类、会话级查询上下文
- 154 个测试，全量通过

**下一步（Phase 2A）：**
1. 本蓝图 Phase 2 审阅确认
2. 选择 Phase 2 子阶段（推荐 2A：Git 远程协作，7 个任务）
3. 实现 Phase 2A 的 git 操作封装
4. 发布 `v0.3.0`，包含远程 KB 协作能力
5. 在 2-3 人小团队中试用，收集协作体验反馈
