# M1 Backend API Spec — Web UI 只读模式

> Phase 5 M1 | 2026-06-09 | 依赖: 无

## 概述

在现有 FastMCP (stdio) 旁边启动 FastAPI (HTTP)，共享 Storage 实例。零认证（只读端点），`km serve --ui` 单进程运行。

## 启动模式

```bash
km serve --ui                    # localhost:8420, 含零构建回退UI
km serve --ui --host 0.0.0.0    # 局域网可访问
km serve --ui --port 8420        # 自定义端口
```

## 端点总览

```
GET  /api/health                  → KBHealthReport
GET  /api/stats                   → UsageStats
GET  /api/index                   → Index (不含模块全文)
GET  /api/tree                    → TreeNode (完整知识树)
GET  /api/tree/:cat/:id           → TreeNode (子树)
GET  /api/modules                 → list[ModuleSummary] (?category=&status=&tag=&page=&limit=)
GET  /api/modules/:cat/:id        → Module (JSON全文)
GET  /api/modules/:cat/:id.md     → Module (Markdown, M5后才可用)
POST /api/search                  → SearchResponse
GET  /api/graph                   → GraphData
GET  /api/graph/:cat/:id          → GraphData (局部图)
GET  /api/recommendations         → RecommendationReport
GET  /ui                          → Web UI (SPA入口)
GET  /ui/fallback                 → 零构建回退UI (单HTML)
```

---

## 端点详细定义

### 1. `GET /api/health`

**响应 200:**
```json
{
  "generated_at": "2026-06-09T12:00:00Z",
  "total_modules": 127,
  "total_categories": 8,
  "overall_score": 72.5,
  "category_breakdown": {
    "auth": {"name": "auth", "total_modules": 12, "avg_score": 85.0, "at_risk_count": 1},
    "backend": {"name": "backend", "total_modules": 23, "avg_score": 68.2, "at_risk_count": 4}
  },
  "at_risk_modules": [
    {
      "module_id": "old-session",
      "category": "auth",
      "title": "旧Session管理",
      "status": "deprecated",
      "score": {"freshness": 0, "usage": 0, "completeness": 60, "overall": 18.0},
      "issues": ["zombie", "stale"],
      "last_load": null,
      "load_count_30d": 0,
      "days_since_update": 210
    }
  ]
}
```
**实现:** 直接调用 `generate_health_report(kb_path).model_dump()`，现有函数无需修改。

---

### 2. `GET /api/stats`

**查询参数:** `?period=30` (7|30|90，默认30)

**响应 200:**
```json
{
  "period_days": 30,
  "total_searches": 1542,
  "total_loads": 873,
  "conversion_rate": 56.6,
  "total_sessions": 42,
  "avg_searches_per_session": 36.7,
  "top_modules": [
    {"module_id": "jwt-config", "category": "auth", "title": "JWT配置", "load_count": 87, "trend": "up"}
  ],
  "unmatched_queries": [
    {"query_hash": "abc123", "query_terms": ["websocket", "连接池"], "count": 5}
  ],
  "daily_activity": [
    {"date": "2026-06-09", "searches": 45, "loads": 23}
  ]
}
```
**实现:** 调用 `aggregate_usage_stats(kb_path, period_days)`，现有函数。

---

### 3. `GET /api/index`

**响应 200:**
```json
{
  "version": "1.0",
  "description": "A curated knowledge base...",
  "categories": {
    "auth": {
      "name": "auth",
      "description": "认证与授权相关...",
      "modules": [
        {"id": "jwt-config", "category": "auth", "title": "JWT配置", "summary": "...", "tags": ["jwt","auth"], "word_count": 420}
      ]
    }
  },
  "stats": {"total_modules": 127, "total_words": 45600, "categories": 8, "last_updated": "..."},
  "updated_at": "2026-06-09T12:00:00Z"
}
```
**实现:** 调用 `load_index(kb_path).model_dump()`，**不返回 graph 字段**（前端用 `/api/graph` 单独获取）。

---

### 4. `GET /api/tree`

返回完整知识树。M1 阶段树由 `rebuild_index` 时从扁平 categories 自动构建（M3 才引入 LLM 树构建）。

**M1 临时行为:** 若 `index.tree` 为 null，从 `index.categories` 动态生成 category 级平铺树（每个 category 一个节点，其子节点为该 category 的 modules）。

**响应 200:**
```json
{
  "id": "root",
  "type": "root",
  "title": "Knowledge Base",
  "summary": "127 modules across 8 categories",
  "children": [
    {
      "id": "auth",
      "type": "category",
      "title": "认证与授权",
      "summary": "用户身份验证和权限管理",
      "path": "auth",
      "module_count": 12,
      "word_count": 3400,
      "children": [
        {
          "id": "auth/jwt-config",
          "type": "module",
          "title": "JWT配置",
          "summary": "过期时间24h, RS256签名",
          "path": "auth/jwt-config",
          "confidence": "high",
          "status": "published",
          "tags": ["auth", "jwt", "security"],
          "children": []
        }
      ]
    }
  ]
}
```

**实现:**
```python
# storage.py 新增
def get_tree(kb_path: Path) -> TreeNode:
    index = load_index(kb_path)
    if index is None:
        return TreeNode(id="root", type="root", title="Empty KB")
    if hasattr(index, 'tree') and index.tree is not None:
        return index.tree
    # M1 fallback: 从 categories 构建平铺树
    return _build_tree_from_categories(index)

def _build_tree_from_categories(index: Index) -> TreeNode:
    from knowledge_manager.schemas import TreeNode, TreeNodeType
    root = TreeNode(id="root", type=TreeNodeType.ROOT, title="Knowledge Base",
                    summary=f"{index.stats.total_modules} modules")
    for cat_name, cat in index.categories.items():
        cat_node = TreeNode(
            id=cat_name, type=TreeNodeType.CATEGORY, title=cat_name,
            summary=cat.description, path=cat_name,
            module_count=len(cat.modules),
            word_count=sum(m.word_count for m in cat.modules),
        )
        for mod in cat.modules:
            cat_node.children.append(TreeNode(
                id=f"{cat_name}/{mod.id}", type=TreeNodeType.MODULE,
                title=mod.title, summary=mod.summary,
                path=f"{cat_name}/{mod.id}",
                tags=mod.tags,
            ))
        root.children.append(cat_node)
    return root
```

---

### 5. `GET /api/tree/:cat/:id`

**路径参数:** `cat` = category名, `id` = module id (不含category前缀)

**响应 200:** 以指定模块为根的子树（深度2层：模块 + 其 related_modules）

**实现:**
```python
def get_subtree(cat: str, mod_id: str, kb_path: Path) -> TreeNode | None:
    module = load_module(mod_id, cat, kb_path)
    if module is None:
        return None
    node = TreeNode(id=f"{cat}/{mod_id}", type=TreeNodeType.MODULE,
                    title=module.title, summary=module.summary, path=f"{cat}/{mod_id}")
    for ref in module.metadata.related_modules:
        parts = ref.split("/", 1)
        if len(parts) == 2:
            related = load_module(parts[1], parts[0], kb_path)
            if related:
                node.children.append(TreeNode(
                    id=ref, type=TreeNodeType.MODULE,
                    title=related.title, summary=related.summary, path=ref,
                ))
    return node
```

---

### 6. `GET /api/modules`

**查询参数:**

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| category | string | - | 按分类过滤 |
| status | string | - | published/draft/deprecated/archived |
| tag | string | - | 按标签过滤（单值精确匹配） |
| page | int | 1 | 页码（1-indexed） |
| limit | int | 50 | 每页条数（max 200） |

**响应 200:**
```json
{
  "items": [
    {
      "id": "jwt-config",
      "category": "auth",
      "title": "JWT配置",
      "summary": "我们使用RS256非对称签名的JWT...",
      "tags": ["auth", "jwt", "security"],
      "confidence": "high",
      "status": "published",
      "word_count": 420,
      "updated_at": "2026-06-01T14:30:00Z"
    }
  ],
  "total": 127,
  "page": 1,
  "limit": 50,
  "pages": 3
}
```

**错误:** 422 若 limit > 200

**实现:** 遍历 `list_modules(kb_path)` + 过滤 + 分页。M1 不做缓存（ModuleCache 是 MCP 专用的）。

---

### 7. `GET /api/modules/:cat/:id`

**响应 200:** Module 完整 JSON（同现有 `km show` 输出）
**响应 404:** `{"error": "Module not found: auth/nonexistent"}`
**响应 410:** `{"error": "Module archived", "module": {...}}` (若 status=archived 且请求不含 ?include_archived=true)

**查询参数:** `?include_archived=true` — 返回已归档模块

---

### 8. `GET /api/modules/:cat/:id.md`

**响应 200:** `text/markdown` 格式的模块内容
**响应 404:** 模块不存在
**响应 501:** M5 之前此端点不可用（Markdown 格式尚未生成）

**M1 行为:** 返回 501 `{"error": "Markdown format not available yet. Use /api/modules/:cat/:id for JSON."}`

---

### 9. `POST /api/search`

**请求体:**
```json
{
  "query": "JWT过期时间",
  "category": "auth",
  "include_archived": false,
  "top_k": 10
}
```

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| query | string | 是 | - | 搜索查询 |
| category | string | 否 | - | 限定分类 |
| include_archived | bool | 否 | false | 包含已归档 |
| top_k | int | 否 | 10 | 返回条数 (max 50) |

**响应 200:**
```json
{
  "query": "JWT过期时间",
  "intent": "reference",
  "results": [
    {
      "id": "jwt-config",
      "category": "auth",
      "title": "JWT配置",
      "summary": "我们使用RS256...",
      "tags": ["auth","jwt","security"],
      "confidence": "high",
      "status": "published",
      "source": "direct",
      "related_modules": ["auth/oauth-flow", "deployment/secrets-management"],
      "snippet": "...包含RS256签名, Access Token过期时间24h...",
      "caveats": "RS256签名比HS256慢约10x"
    }
  ],
  "took_ms": 12
}
```

**实现:** 调用 `search_modules(query, kb_path, ...)` + `_classify_intent(query)`，现有函数封装。

---

### 10. `GET /api/graph`

**响应 200:**
```json
{
  "nodes": [
    {"id": "auth/jwt-config", "label": "JWT配置", "category": "auth", "status": "published", "in_degree": 3, "out_degree": 2}
  ],
  "edges": [
    {"source": "auth/jwt-config", "target": "auth/oauth-flow", "weight": 1.0}
  ],
  "stats": {
    "total_nodes": 127,
    "total_edges": 312,
    "density": 0.0195
  }
}
```

**节点属性:** `in_degree` 和 `out_degree` 用于前端计算节点大小。`category` 用于颜色映射。

**实现:** 调用 `analyze_graph(kb_path)` + 现有 index.graph，组装节点和边。

---

### 11. `GET /api/graph/:cat/:id`

**响应 200:** 以该模块为中心的局部图（该模块 + 其所有 related_modules + 它们之间的边）

```json
{
  "center": "auth/jwt-config",
  "nodes": [...],
  "edges": [...],
  "depth": 1
}
```

---

### 12. `GET /api/recommendations`

**响应 200:** `RecommendationReport` 完整 JSON（同现有 `km recommend --format json`）

---

### 13. `GET /ui` 和 `GET /ui/fallback`

**`/ui`:** 
- 若 `src/ui/dist/index.html` 存在 → 返回 React 构建产物的入口HTML
- 否则 → 302 重定向到 `/ui/fallback`

**`/ui/fallback`:**
- 返回内嵌的单HTML页面（htmx + Alpine.js + Water.css），提供只读浏览功能
- 此HTML作为 Python 字符串常量嵌入源码

**实现 (新文件 `src/knowledge_manager/ui_fallback.py`):**
```python
FALLBACK_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Knowledge Manager</title>
  <script src="https://cdn.jsdelivr.net/npm/htmx.org@1.9/dist/htmx.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/alpinejs@3.x/dist/cdn.min.js" defer></script>
  <link href="https://cdn.jsdelivr.net/npm/water.css@2/out/water.min.css" rel="stylesheet">
</head>
<body>
  <div x-data="app()" x-init="init()">
    <header>
      <h1>Knowledge Manager</h1>
      <div x-text="stats.total_modules + ' modules'"></div>
    </header>
    <main>
      <aside>...</aside>
      <article>...</article>
    </main>
  </div>
</body>
</html>
"""
```

---

## 错误响应规范

所有端点统一错误格式：

```json
{
  "error": "<人类可读的错误描述>",
  "detail": "<可选的技术细节>"
}
```

HTTP 状态码规范：
- 200: 成功
- 404: 资源不存在
- 410: 模块已归档（需显式参数才能访问）
- 422: 请求参数校验失败
- 500: 服务器内部错误
- 501: 功能尚未实现（如 M5 之前的 `/api/modules/:cat/:id.md`）

---

## 实现文件清单

| 文件 | 操作 | 内容 |
|------|------|------|
| `src/knowledge_manager/http_server.py` | **新建** | FastAPI 应用 + 所有 REST 端点 |
| `src/knowledge_manager/ui_fallback.py` | **新建** | 零构建回退 HTML |
| `src/knowledge_manager/mcp_server.py` | 修改 | `create_server` 支持 `mode="ui"` |
| `src/knowledge_manager/cli.py` | 修改 | `serve` 命令支持 `--ui` 参数 |
| `src/knowledge_manager/schemas.py` | 修改 | 新增 `TreeNode`, `TreeNodeType`, `GraphData`, `PaginatedResponse` |
| `src/knowledge_manager/storage.py` | 修改 | 新增 `get_tree()`, `get_subtree()`, `_build_tree_from_categories()` |

## 测试要求

| 测试 | 类型 | 覆盖 |
|------|------|------|
| 所有 GET 端点返回 200 (正常KB) | 集成 | 13个端点 |
| 空KB行为 (无 index.json) | 集成 | 返回空数据而非500 |
| `/api/modules` 分页正确 | 单元 | page/limit/pages 计算 |
| `/api/search` 422 on query="" | 单元 | 参数校验 |
| `/api/modules/:cat/:id.md` 返回 501 | 单元 | M1阶段不可用 |
| `/ui` 返回 HTML (非404) | 集成 | 入口可用 |
