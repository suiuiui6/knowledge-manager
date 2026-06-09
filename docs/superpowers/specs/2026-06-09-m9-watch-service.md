# M9 Spec — 自动源监控 (Watch Service)

> Phase 6 M9 | 2026-06-09 | 硬依赖: M4 (复用 Research 管线)

## 概述

知识库不应只依赖手动 `km add`。Watch Service 监控外部知识源（GitHub仓库、本地文档目录、RSS、arXiv），自动将新知识引入知识库。复用 M4 的 Researcher 提取→暂存→审核链路。

## 数据模型

### schemas.py 新增

```python
class WatchSource(BaseModel):
    id: str
    type: Literal["github", "rss", "local", "arxiv", "webhook"]
    enabled: bool = True
    config: dict = Field(default_factory=dict)
    extraction: WatchExtractionConfig = Field(default_factory=WatchExtractionConfig)

class WatchExtractionConfig(BaseModel):
    category: str = ""
    auto_categorize: bool = False
    chunk_size: int = 8000
    max_modules_per_item: int = 3
    auto_approve: bool = False
    notify_on_new: bool = True

class WatchEvent(BaseModel):
    id: str
    source_id: str
    triggered_at: datetime
    trigger_type: str     # "schedule" | "webhook" | "manual"
    items_found: int = 0
    modules_generated: int = 0
    errors: list[str] = Field(default_factory=list)
    took_ms: int = 0
    cursor_after: str = ""
```

## 架构

```
km watch serve &                     # 后台守护进程 (APScheduler)
km watch add github --repo org/repo --path "docs/**" --category backend
km watch add local --path "../shared-docs" --auto-categorize
km watch list                        # 列出所有监控源
km watch status                      # 各源最近处理状态
km watch run --now                   # 立即全量拉取
```

### 文件结构

```
src/knowledge_manager/
├── watchers/
│   ├── __init__.py
│   ├── github.py        # GitHubWatcher: poll commits → filter docs → extract
│   ├── local.py         # LocalWatcher: watchdog events → extract new/changed files
│   └── rss.py           # RSSWatcher: poll feed → extract new entries
├── watch_scheduler.py   # WatchScheduler: APScheduler + 后台轮询
```

### GitHub Watcher 核心逻辑

```python
class GitHubWatcher:
    async def poll(self) -> WatchEvent:
        # 1. 获取上次游标 (commit SHA)
        # 2. 拉取新 commits
        # 3. 过滤匹配路径的文件变更
        # 4. LLM 判断: 新知识/更新知识/无关变更?
        # 5. 新知识 → Extractor → save_to_staging
        # 6. 更新 → 生成更新建议
        # 7. 更新游标
```

### 调度器

```python
class WatchScheduler:
    DEFAULT_INTERVALS = {
        "github": 300,    # 5分钟
        "rss": 3600,      # 1小时
        "local": 120,     # 2分钟
        "arxiv": 86400,   # 每天
    }
```

## 新增/修改文件

| 文件 | 操作 | 内容 |
|------|------|------|
| `src/knowledge_manager/watchers/` | **新建目录** | github.py, local.py, rss.py |
| `src/knowledge_manager/watch_scheduler.py` | **新建** | APScheduler 后台调度 |
| `src/knowledge_manager/schemas.py` | 修改 | +WatchSource, WatchExtractionConfig, WatchEvent |
| `src/knowledge_manager/cli.py` | 修改 | +watch命令组 |
| `tests/test_watcher.py` | **新建** | Watcher + Scheduler 测试 |

## Gate Pass 标准

- [ ] `km watch add local --path <dir>` 注册成功
- [ ] 本地文件变更 → 自动提取 → staging (mock fs事件)
- [ ] GitHub watcher 正确调用 API (mock)
- [ ] 游标机制: 不重复处理已处理的 commit
- [ ] 通知: 新模块生成时 CLI 输出 + 可选 webhook
