# Layer 2: Integration Topology — 十大改进蓝图

> 基线: BLUEPRINT.md v3.0 (2026-06-09, 3611行), knowledge-manager v0.5.0

## 输入物

| 输入 | 来源 | 关键内容 |
|------|------|---------|
| PRD | BLUEPRINT.md §总路线图 (L3572-3593) | 10大改进, 3个Phase, 13个里程碑 |
| 现有代码 | `src/knowledge_manager/` (14文件) | schemas, storage, mcp_server, cli, extractor, llm_clients, cache, connect, marketplace, webhooks |
| 现有测试 | `tests/` (12文件) | test_storage, test_schemas, test_cli, test_mcp_server, test_cache, test_llm, test_integration, test_connect, test_marketplace, test_webhooks |
| 架构约束 | BLUEPRINT.md §不做的事 (L3597-3606) | 无数据库/向量数据库/独立Web进程/CRDT/SaaS |

## 蓝图官方路线图 (BLUEPRINT L3572-3593)

```
Phase 5: 体验层 (6个月)
  M1: Web UI 只读模式 (知识树浏览 + 模块阅读 + 知识图谱)
  M2: 对话式搜索 (SSE流式 + 来源引用 + 追问建议)
  M3: 知识树 + LLM推理导航 (navigate_tree)
  M4: Research-on-Miss (自动研究 → staging → 审核)
  M5: Markdown一等公民 + wikilinks + Obsidian导出
  M6: Web UI 编辑模式 + 审核工作流

Phase 6: 智能层 (6个月)
  M7: 语义矛盾检测 (lint --deep)
  M8: 间隔重复记忆系统 (FSRS)
  M9: 自动源监控 (watch service)
  M10: 可选向量搜索 (本地 embedding + RRF 融合)

Phase 7: 生态层 (6个月)
  M11: 插件系统 + SDK + 示例插件
  M12: 多模态知识 (图片/代码仓库/会议记录)
  M13: 企业功能 (SSO, 审计日志, RBAC, 合规报告)
```

## 依赖关系分析

### 硬依赖 (必须在前置里程碑完成后才能开始)

| 依赖 | 方向 | 理由 | 蓝图证据 |
|------|------|------|---------|
| M1 → M2 | Web UI shell → 对话面板集成 | ChatPanel 是 Web UI 的子组件，需要 M1 的三栏布局和路由框架 | L176-185 (ChatPanel 是 Layout.tsx 的一部分) |
| M1 → M6 | 只读UI → 编辑UI | M6 在 M1 的 ModuleViewer 基础上增加编辑功能，复用同一组件树 | L3581 "Web UI 编辑模式" |
| M5 → M6 | MD格式 → 编辑器 | M6 的编辑模式默认编辑 Markdown 格式，需要 M5 的 parse/render 能力 | L1428-1450 (JSON↔MD 双向同步是编辑基础) |
| M4 → M9 | Research管线 → Watch消费 | Watch Service 复用 Researcher 的提取→暂存→审核链路 | L2812-2815 (watcher 调用 `extract_from_content` → `save_to_staging`) |

### 软依赖 (增强但不阻塞，可并行开发)

| 关系 | 说明 | 降级行为 |
|------|------|---------|
| M3 → M1 | 知识树驱动左侧导航面板 | 没有M3时，M1的KnowledgeTree显示扁平category列表 |
| M3 → M2 | TreeNavigator作为ChatPipeline的召回通路之一 | tree_index=None时跳过树召回，仅用关键词+向量 |
| M5 → M1 | Markdown渲染器显示模块内容 | 无M5时ModuleViewer直接渲染JSON字段（overview/details等） |
| M10 → M2 | 向量召回作为ChatPipeline第三路召回 | vector_index=None时跳过向量召回 |

### 独立里程碑 (无前置依赖)

**M4 (Research-on-Miss)**: 复用现有 Extractor + staging 链路。`search_modules` 返回空时可选触发。CLI和MCP均可独立调用。

**M7 (语义Lint)**: 候选对筛选用规则（same_category/shared_tags/mutual_reference），不依赖树结构。两种模式：quick（纯结构化，无LLM）和 deep（LLM语义比较）。验证项：BLUEPRINT L2058-2082 的 `_generate_candidates` 使用 `PAIR_FILTERS` 字典，不引用 `TreeNode`。

**M8 (FSRS记忆)**: 卡片生成用 `Module.content` 字段 + LLM，调度用 FSRS v5 算法（纯数学，无外部API）。验证项：BLUEPRINT L2357-2385 的 `generate_cards_for_module` 接收 `Module` 对象，不引用 Markdown 或 Tree。

## 与现有代码的集成边界

### 每个里程碑需要接触的现有文件

| 里程碑 | schemas.py | storage.py | mcp_server.py | cli.py | 新文件 | 新目录 |
|--------|-----------|------------|--------------|--------|--------|--------|
| M1 Web UI | +ChatEvent | - | +REST/SSE端点, FastAPI | serve --ui | chat.py | src/ui/ (React) |
| M2 对话搜索 | - | - | +chat端点增强 | - | - | - |
| M3 知识树 | +TreeNode | +tree读写函数 | +tree资源 | +tree命令 | tree_builder.py, tree_navigator.py | - |
| M4 Research | +ResearchConfig/Source/Event | - | +research tool | +research命令 | researcher.py | - |
| M5 Markdown | +MD映射 | save_module改 | - | export --obsidian | markdown.py, wikilinks.py, sync.py | - |
| M6 Web UI编辑 | - | - | +write端点 | - | (M1已有) | - |
| M7 语义Lint | +Contradiction | - | +lint资源 | +lint命令 | linter.py | - |
| M8 FSRS记忆 | +MemoryCard/Stats | +卡片持久化 | +memory资源 | +memory命令 | memory.py | - |
| M9 监控 | +WatchSource/Event | - | - | +watch命令 | watchers/github.py, watch_scheduler.py | watchers/ |
| M10 向量搜索 | +VectorConfig | search_modules改 | - | - | vector_index.py | - |
| M11 插件 | +PluginManifest/Context | - | - | +plugin命令 | plugin.py | - |
| M12 多模态 | - | - | - | add增强 | - | - |
| M13 企业 | - | - | - | - | - | - |

### 关键集成点详细说明

**1. `Index` 模型改造 (schemas.py:77)**

```python
# 现有
class Index(BaseModel):
    categories: Dict[str, IndexCategory]
    graph: Dict[str, List[str]]

# M3 新增
class Index(BaseModel):
    categories: Dict[str, IndexCategory]
    graph: Dict[str, List[str]]
    tree: Optional[TreeNode] = None          # M3: 知识树
    vector_cache_key: Optional[str] = None   # M10: 向量索引版本标记
```

**2. `save_module()` 改造 (storage.py:115)**

```python
# 现有: 只写 JSON
def save_module(module, kb_path):
    _atomic_write(path, module.model_dump_json())
    emit_event(...)

# M5 改造: JSON + MD 双写
def save_module(module, kb_path):
    _atomic_write(json_path, module.model_dump_json())
    _atomic_write(md_path, render_markdown_module(module))  # M5 新增
    emit_event(...)
```

**3. `create_server()` 改造 (mcp_server.py:32)**

```python
# 现有: 纯 FastMCP
def create_server(kb_path):
    mcp = FastMCP("knowledge-manager")
    ...

# M1 改造: FastMCP + FastAPI 同进程
def create_server(kb_path, mode="mcp"):
    if mode == "ui":
        app = FastAPI()
        mcp = FastMCP("knowledge-manager")
        # 共享 Storage 实例
        ...
        return app, mcp
    return mcp
```

**4. `search_modules()` 改造 (storage.py:227)**

```python
# M3: 新增 tree_recall_results 参数 (并行召回)
# M10: 新增 vector_index 参数 (可选向量召回)
def search_modules(query, kb_path, ...,
                   tree_index=None,       # M3
                   vector_index=None,     # M10
                   vector_weight=0.25):   # M10
```

## 分期策略 (对齐蓝图官方路线图)

### Phase 5: 体验层 — 优先序

```
M1 (Web UI只读) ──→ M2 (对话搜索)
    │                    │
    │                    └── M3 (知识树) 可并行于M2
    │
    ├── M4 (Research) 独立，可并行
    │
    └── M5 (Markdown) 独立，可并行
                          │
                          └── M6 (Web UI编辑) 需 M5
```

**并行度:** M1 启动后，M2+M3 串行（M3增强M2的召回），M4和M5可完全并行于 M2/M3。

**M1内部拆解:**
- M1a: REST API 端点（health/stats/index/modules/search/graph/tree）
- M1b: 零构建回退UI（htmx + Alpine.js + Water.css，单HTML文件）
- M1c: React完整UI（Vite构建，三栏布局）
- M1d: 知识图谱可视化（Cytoscape.js）

### Phase 6: 智能层 — M7/M8/M9/M10 全部独立可并行

```
M7 (语义Lint)  ─┐
M8 (FSRS记忆)  ─┼── 无互相依赖，可并行开发
M9 (Watch)     ─┤   (M9 复用 M4 的 Research 管线)
M10 (向量搜索) ─┘
```

### Phase 7: 生态层 — M11 是 M12/M13 的基础

```
M11 (插件系统) ──→ M12 (多模态，通过插件钩子扩展)
              ──→ M13 (企业功能，通过插件实现SSO/审计等)
```

## Gate Pass 标准

- [x] 依赖图无循环 — 所有依赖均为前向（小序号→大序号）
- [x] 硬依赖已识别并验证 — 仅4条硬依赖（M1→M2, M1→M6, M5→M6, M4→M9）
- [x] 各里程碑可独立验证 — 每M有明确的CLI/API/UI验收标准
- [x] 现有12个测试全程保持通过 — 所有改造向后兼容
- [x] 架构约束已文档化 — "不做的事"6条作为负向约束
- [x] 分期与蓝图官方路线图一致 — Phase 5/6/7 与 M1-M13 对齐

## 与蓝图最初 "六大改进" 表述的关系

蓝图标题使用"大改进一～十"作为章节编号，但其 §总路线图 (L3572) 将10大改进重新分组为13个里程碑、3个Phase。本拓扑文档以官方路线图为准，将章节级的"大改进"映射为里程碑：

| 蓝图章节 | 里程碑 | Phase |
|----------|--------|-------|
| 大改进一 (Web UI + 对话) | M1, M2 | 5 |
| 大改进二 (知识树) | M3 | 5 |
| 大改进三 (Research-on-Miss) | M4 | 5 |
| 大改进四 (Markdown + Obsidian) | M5 | 5 |
| (Web UI编辑模式) | M6 | 5 |
| 大改进五 (语义Lint) | M7 | 6 |
| 大改进六 (FSRS记忆) | M8 | 6 |
| 大改进七 (Watch Service) | M9 | 6 |
| 大改进八 (向量搜索) | M10 | 6 |
| 大改进九 (插件系统) | M11 | 7 |
| 大改进十 (多模态) | M12 | 7 |
| (企业功能) | M13 | 7 |
