# M5 Spec — Markdown一等公民 + Obsidian双向同步

> Phase 5 M5 | 2026-06-09 | 硬依赖: 无

## 概述

将 Markdown 提升为与 JSON 同等的一等公民存储格式，实现 JSON↔MD 双向同步、`[[wikilinks]]` 自动解析、Obsidian vault导出。核心交付物：`markdown.py` + `wikilinks.py` + `sync.py`。

## YAML Frontmatter ↔ Module Schema 映射

### 规范

```yaml
---
id: jwt-config
category: auth
title: JWT Token 配置
summary: 我们使用RS256非对称签名的JWT，Access Token过期时间24h
tags: [auth, jwt, security, api]
confidence: high
status: published
source: internal-runbook
expires_at: null
review_interval_days: 90
related_modules:
  - auth/token-rotation
  - auth/oauth-flow
  - deployment/secrets-management
created_at: "2026-05-28T10:00:00Z"
updated_at: "2026-06-01T14:30:00Z"
---

# 概述

...

# 细节

...

# 示例

...

# 参考

...

# 注意事项

...
```

### 映射表

```python
# markdown.py
FRONTMATTER_TO_SCHEMA = {
    "id":                ("id", str),
    "category":          ("category", str),
    "title":             ("title", str),
    "summary":           ("summary", str),
    "tags":              ("metadata.tags", list),
    "confidence":        ("metadata.confidence", str),
    "status":            ("metadata.status", str),
    "source":            ("metadata.source", str),
    "expires_at":        ("metadata.expires_at", optional_datetime),
    "review_interval_days": ("metadata.review_interval_days", optional_int),
    "related_modules":   ("metadata.related_modules", list),
    "created_at":        ("created_at", datetime),
    "updated_at":        ("updated_at", datetime),
}

MD_SECTION_TO_CONTENT = {
    "# 概述": "overview",
    "# 细节": "details",
    "# 示例": "examples",
    "# 参考": "references",
    "# 注意事项": "caveats",
}
```

## Markdown 解析与渲染

### `markdown.py`

```python
def parse_markdown_module(md_text: str) -> Module:
    """Markdown → Module 解析:
    1. 提取 YAML frontmatter (---...---)
    2. 映射 frontmatter 到 Module 字段
    3. 解析 body: H1标题 → content字段
    4. 验证 + 返回 Module 对象
    """

def render_markdown_module(module: Module) -> str:
    """Module → Markdown 渲染:
    1. 从 Module 字段生成 YAML frontmatter
    2. 从 ModuleContent 字段生成 H1分段
    3. 过滤空值
    """
```

### Frontmatter 验证

```python
def validate_frontmatter(fm: dict) -> list[str]:
    """检查必填字段、类型、枚举值"""
    errors = []
    if not fm.get("id"):
        errors.append("Missing required field: id")
    if not fm.get("title") or len(fm["title"]) < 5:
        errors.append("title must be >= 5 chars")
    if fm.get("confidence") not in (None, "high", "medium", "low"):
        errors.append("confidence must be high/medium/low")
    if fm.get("status") not in (None, "draft", "reviewed", "published", "deprecated", "archived"):
        errors.append("Invalid status value")
    return errors
```

## `[[wikilinks]]` 解析器

### `wikilinks.py`

```python
WIKILINK_PATTERN = re.compile(r'\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]')

@dataclass
class Wikilink:
    target: str          # "auth/oauth-flow" 或 "RS256"
    display_text: str
    resolved: bool = False
    resolved_path: str = ""

def parse_wikilinks(text: str) -> list[Wikilink]:
    """提取所有 [[wikilinks]]"""

def resolve_wikilinks(links: list[Wikilink], kb_path: Path) -> list[Wikilink]:
    """四级解析策略:
    1. 精确路径: "auth/oauth-flow" → 直接匹配 category/id
    2. ID搜索: "oauth-flow" → 搜索所有模块的 id 字段
    3. 标题搜索: "OAuth流程" → 搜索所有模块的 title 字段
    4. 模糊匹配: "RS256" → 搜索内容中包含该词的最相关模块
    """

def auto_update_related_modules(module: Module, kb_path: Path) -> Module:
    """从模块内容中提取 wikilinks → 自动更新 related_modules"""
    full_text = f"{module.content.overview}\n{module.content.details}\n..."
    links = parse_wikilinks(full_text)
    resolved = resolve_wikilinks(links, kb_path)
    new_related = set(module.metadata.related_modules)
    for link in resolved:
        if link.resolved:
            new_related.add(link.resolved_path)
    module.metadata.related_modules = sorted(new_related)
    return module
```

## 双向同步 (`sync.py`)

### 核心逻辑

```python
class MarkdownSync:
    @staticmethod
    def sync_on_save(module: Module, kb_path: Path) -> None:
        """保存模块时同时写入 .json 和 .md"""
        json_path = module.to_file_path(kb_path)
        md_path = json_path.with_suffix('.md')
        _atomic_write(json_path, module.model_dump_json(indent=2))
        _atomic_write(md_path, render_markdown_module(module))

    @staticmethod
    def sync_on_rebuild(kb_path: Path) -> list[SyncConflict]:
        """重建索引时检测 JSON/MD 不同步:
        - 只有JSON → 生成MD
        - 只有MD → 解析并生成JSON
        - 两边都有 → 比较时间戳, 以较新的为准同步另一方
        - MD解析失败 → 报告冲突
        """
```

### storage.py 集成

```python
# save_module 改造
def save_module(module: Module, kb_path: Path) -> None:
    json_path = module.to_file_path(kb_path)
    existed = json_path.exists()
    MarkdownSync.sync_on_save(module, kb_path)  # M5: JSON + MD 双写
    # ... emit webhook event ...

# rebuild_index 改造
def rebuild_index(kb_path: Path, check_sync: bool = True) -> Index:
    if check_sync:
        conflicts = MarkdownSync.sync_on_rebuild(kb_path)
        if conflicts:
            _report_sync_conflicts(conflicts)
    # ... 现有重建逻辑 ...
```

### 冲突处理

```python
@dataclass
class SyncConflict:
    path: str
    error: str
    action_required: str   # "手动修复 Markdown 格式错误" | "检查 frontmatter 必填字段"

# CLI
$ km sync check       # 检查同步状态
$ km sync fix         # 自动修复可自动修复的冲突
$ km sync conflicts   # 列出需要手动处理的冲突
```

## Obsidian 导出

```bash
km export --obsidian ./my_vault

# 生成结构:
my_vault/
├── .obsidian/
│   ├── graph.json              # Graph View 配置 (category → color)
│   └── templates/
│       └── module.md           # 新建模块模板
├── auth/
│   ├── jwt-config.md
│   └── oauth-flow.md
├── deployment/
│   └── k8s-config.md
├── _index.md                   # Dataview 全局索引页
├── _health.md                  # 健康状态页
└── _graph.md                   # 知识图谱入口
```

### 导出实现

```python
def export_obsidian(kb_path: Path, output_dir: Path) -> None:
    """将所有模块导出为 Obsidian vault"""
    output_dir.mkdir(parents=True, exist_ok=True)
    obsidian_dir = output_dir / ".obsidian"
    obsidian_dir.mkdir(exist_ok=True)

    # 写入 Graph View 配置 (category → color mapping)
    _write_graph_config(obsidian_dir, kb_path)

    # 写入模板
    _write_templates(obsidian_dir)

    # 写入所有模块的 .md 文件
    for module in list_modules(kb_path):
        md_text = render_markdown_module(module)
        out_path = output_dir / module.category / f"{module.id}.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md_text, encoding='utf-8')

    # 写入 Dataview 索引页
    _write_index_md(output_dir, kb_path)
    _write_health_md(output_dir, kb_path)
```

### Dataview 查询模板

```markdown
# 全局知识索引

## 按分类

\`\`\`dataview
TABLE summary, confidence, status
FROM "auth"
SORT file.name ASC
\`\`\`

## 需要复习的模块 (>90天未更新)

\`\`\`dataview
TABLE review_interval_days, date(updated_at) as "最后更新"
FROM ""
WHERE status = "published"
  AND date(updated_at) < date(today) - dur(90 days)
SORT updated_at ASC
\`\`\`

## 孤岛模块 (无关联)

\`\`\`dataview
TABLE category, tags
FROM ""
WHERE length(related_modules) = 0 AND status = "published"
\`\`\`
```

## 新增/修改文件

| 文件 | 操作 | 内容 |
|------|------|------|
| `src/knowledge_manager/markdown.py` | **新建** | parse/render/validate Markdown |
| `src/knowledge_manager/wikilinks.py` | **新建** | Wikilink 解析 + 四级解析 + related_modules自动更新 |
| `src/knowledge_manager/sync.py` | **新建** | MarkdownSync + SyncConflict |
| `src/knowledge_manager/storage.py` | 修改 | save_module/rebuild_index 集成同步逻辑 |
| `src/knowledge_manager/cli.py` | 修改 | +export命令组, +sync命令组 |
| `tests/test_markdown.py` | **新建** | roundtrip, 边界情况, frontmatter验证 |
| `tests/test_wikilinks.py` | **新建** | 解析 + 解析策略测试 |
| `tests/test_sync.py` | **新建** | 同步逻辑 + 冲突检测 |

## Gate Pass 标准

- [ ] Module → MD → Module roundtrip 完全一致
- [ ] MD 手动编辑后 rebuild 自动更新 JSON
- [ ] `[[wikilinks]]` 正确解析并更新 related_modules
- [ ] `km export --obsidian ./vault` 生成可用 Obsidian vault
- [ ] Obsidian vault 中 Dataview 查询正确
- [ ] sync_on_rebuild 检测并报告冲突
- [ ] 现有 JSON-only 模块自动生成 MD
- [ ] `/api/modules/:cat/:id.md` 端点可用 (替换M1的501)
