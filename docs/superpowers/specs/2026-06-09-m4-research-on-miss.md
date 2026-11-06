# M4 Spec — Research-on-Miss

> Phase 5 M4 | 2026-06-09 | 硬依赖: 无

## 概述

当知识库无法回答用户查询时，自动触发研究流水线：查询分解 → 多源搜索 → LLM综合 → 模块提取 → 暂存待审。核心交付物：`researcher.py` + `km research` 命令 + MCP tool。

## 配置模型

### schemas.py 新增

```python
class ResearchSource(BaseModel):
    type: Literal["code_repo", "doc_dir", "web_search", "api"]
    path: str = ""
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    category_hint: str = ""

class ResearchConfig(BaseModel):
    enabled: bool = True
    auto_approve_threshold: float = 0.85
    sources: list[ResearchSource] = Field(default_factory=list)
    default_depth: Literal["shallow", "deep"] = "shallow"
    max_llm_calls_per_query: int = 8
    max_total_tokens_per_query: int = 32000
    max_source_size: int = 50_000
    max_total_sources: int = 10
    timeout_ms: int = 60_000
```

### Config 模型扩展

```python
class Config(BaseModel):
    # ... 现有字段 ...
    research: ResearchConfig = Field(default_factory=ResearchConfig)
```

## 研究流水线 (`researcher.py`)

```
┌─────────────────────────────────────────────────────────────┐
│                    Research Pipeline                        │
│                                                             │
│  Step 1: 查询分解 (Decompose)                                │
│    "微服务间用什么协议通信？"                                   │
│    → ["gRPC 服务间通信协议", "消息队列技术选型", "REST vs gRPC"] │
│                                                             │
│  Step 2: 源选择 (Select Sources)                             │
│    每个子查询匹配最相关的研究源                                  │
│                                                             │
│  Step 3: 并行搜索 (Search, max 5 concurrent)                 │
│    code_repo → rg 关键代码模式                               │
│    doc_dir   → fuzzy filename + content keyword             │
│    web_search → allowed_domains only                        │
│                                                             │
│  Step 4: LLM综合 (Synthesize)                                │
│    shallow: top 3 chunks → 综合摘要 (≤2000字)                 │
│    deep: top 10 → group by subtopic → cross-synthesize      │
│                                                             │
│  Step 5: 模块提取 (Extract)                                   │
│    复用现有 Extractor, 输入=综合文本                           │
│                                                             │
│  Step 6: 暂存 (Stage)                                        │
│    写入 .staging/, confidence降级, 通知用户审核               │
└─────────────────────────────────────────────────────────────┘
```

### 核心接口

```python
class Researcher:
    def __init__(self, kb_path: Path, config: ResearchConfig, llm_client, storage):
        ...

    async def research(
        self, query: str, depth: str = None,
        on_progress: Callable[[ResearchProgress], None] = None,
    ) -> ResearchResult:
        """主入口。返回 ResearchResult 包含临时答案 + 暂存模块列表"""
```

### 本地源搜索策略

**code_repo:**
```python
async def _search_code_repo(self, query: str, source: ResearchSource) -> SourceResult:
    # 1. LLM从查询提取代码搜索关键词
    # "gRPC 服务间通信" → ["grpc", "protobuf", "stub", "channel"]
    # 2. rg -l -i <keyword> <repo_path> (排除 vendor/, node_modules/, .git/)
    # 3. 读取匹配文件的前2000字符
    # 4. 优先匹配 README.md, ARCHITECTURE.md, DESIGN.md, *.proto
```

**doc_dir:**
```python
async def _search_doc_dir(self, query: str, source: ResearchSource) -> SourceResult:
    # 1. 文件名 fuzzy match (fuzzywuzzy)
    # 2. 文件内容关键词搜索
    # 3. 优先 .md, .txt, .rst
```

### 安全边界

```python
class ResearchSafety:
    FORBIDDEN_PATHS = [
        "/etc/", "/proc/", "/sys/",
        "~/.ssh/", "~/.aws/", "~/.config/",
        "*.env", "*.key", "*.pem",
    ]

    @classmethod
    def validate_source(cls, source: ResearchSource) -> None:
        """验证研究源不在禁止路径中"""
        if source.type in ("code_repo", "doc_dir"):
            path = Path(source.path).expanduser().resolve()
            for forbidden in cls.FORBIDDEN_PATHS:
                if fnmatch(str(path), forbidden):
                    raise ValueError(f"Forbidden path: {path}")
        if source.type == "web_search":
            assert source.allowed_domains, "Web search requires allowed_domains"
```

## 触发方式

### 1. 手动CLI

```bash
km research "微服务间用什么协议通信？"
km research "gRPC最佳实践" --depth deep
km research "消息队列选型" --source ../backend --source ../docs
```

### 2. MCP Tool

```python
@mcp.tool(name="research")
def research_tool(query: str, depth: str = "shallow") -> str:
    """当知识库中没有相关知识时，自动研究并生成草稿模块"""
```

### 3. 自动触发 (Search→Research)

```python
# storage.py — search_modules 增强
def search_modules(query, kb_path, ..., auto_research=False):
    results = _do_search(...)
    if not results and auto_research:
        # 返回特殊标记，让Agent决定是否触发research
        return [SearchResult(module=_placeholder("research_needed"), source="auto")]
    return results
```

自动触发默认关闭，需在 config.json 中显式开启。

## CLI 输出设计

```bash
$ km research "gRPC服务间通信的最佳实践"

🔍 分析查询... → 3个子查询
📚 选择研究源... → code_repo:../backend, doc_dir:../docs
🔎 搜索多源 (5并发)...
  ✓ code_repo: ../backend (found 3 files)
  ✓ doc_dir: ../docs (found 2 files)
📝 LLM综合中... (shallow mode, 3 chunks)
📦 提取模块...
  ✓ backend/grpc-best-practices (confidence: medium)
  ✓ backend/grpc-error-handling (confidence: low)
📋 暂存到 .staging/ (2个模块)

💡 临时答案:
gRPC服务间通信推荐使用以下最佳实践:
1. 使用protobuf定义服务接口...
2. 超时设置: 默认5s, 长连接30s...
3. 错误处理: 使用标准gRPC状态码...
⚠️ 以上内容为AI自动研究生成，未经人工审核。

下一步: km review (审核草稿模块)
```

## 新增/修改文件

| 文件 | 操作 | 内容 |
|------|------|------|
| `src/knowledge_manager/researcher.py` | **新建** | Researcher + ResearchSafety + 六阶段流水线 |
| `src/knowledge_manager/schemas.py` | 修改 | +ResearchSource, ResearchConfig, ResearchEvent |
| `src/knowledge_manager/cli.py` | 修改 | +research命令 |
| `src/knowledge_manager/mcp_server.py` | 修改 | +research tool |
| `tests/test_researcher.py` | **新建** | 研究流水线测试 (用本地tmp dir作为source) |

## Gate Pass 标准

- [ ] `km research "query"` 完整执行六阶段流水线
- [ ] 本地 code_repo 源正确调用 rg 搜索
- [ ] 生成的模块写入 .staging/ 且 confidence ≤ medium
- [ ] 安全边界：禁止路径被拒绝
- [ ] 超时保护：60秒超时返回部分结果
- [ ] 空query返回错误
- [ ] MCP research tool 返回可解析的JSON
- [ ] M4不修改 search_modules 的默认行为 (auto_research默认false)
