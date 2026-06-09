# M11 Spec — 插件系统

> Phase 7 M11 | 2026-06-09 | 硬依赖: 无

## 概述

让社区贡献集成，保持核心轻量。插件通过标准化钩子协议在知识提取、审核、搜索、发布流程中注入自定义逻辑。

## 核心接口

### 文件: `src/knowledge_manager/plugin.py`

```python
@dataclass
class PluginManifest:
    name: str
    version: str
    description: str
    author: str
    min_km_version: str = "0.5.0"

@dataclass
class PluginContext:
    kb_path: Path
    config: Config
    storage: "Storage"
    llm_client: "BaseLLMClient"
    cache: "ModuleCache"

# 钩子协议
class ExtractHook(Protocol):
    async def before_extract(self, text, category, ctx) -> str: ...
    async def after_extract(self, modules, ctx) -> list[Module]: ...

class ReviewHook(Protocol):
    async def before_approve(self, module, ctx) -> Module: ...
    async def after_approve(self, module, ctx) -> None: ...

class SearchHook(Protocol):
    async def before_search(self, query, ctx) -> str: ...
    async def after_search(self, query, results, ctx) -> list[SearchResult]: ...
```

## 插件管理

```bash
km plugin search "slack"              # 搜索插件
km plugin install km-plugin-slack     # 安装
km plugin list                         # 已安装
km plugin enable/disable <name>        # 启用/禁用
km plugin uninstall <name>             # 卸载
```

## 示例插件: Slack 通知

审核通过 → 发送 Slack 消息 (带模块标题/标签/摘要)

## 新增/修改文件

| 文件 | 操作 |
|------|------|
| `src/knowledge_manager/plugin.py` | **新建** |
| `src/knowledge_manager/cli.py` | 修改 |
| `.plugins/` | 新目录 (用户空间) |
