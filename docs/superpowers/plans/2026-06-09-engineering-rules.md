# Layer 5: Engineering Rules — All Phases

> 2026-06-09 | 覆盖: Phase 5 (M1-M6) 已完成, Phase 6 (M7-M10), Phase 7 (M11-M13)

## Phase 5 考核结果

| 规则 | Phase 5 执行情况 |
|------|-----------------|
| 仓库边界 | ✅ Python/前端/测试三大目录, 9新文件边界清晰 |
| 里程碑隔离 | ✅ 每M独立模块, 无交叉污染 |
| 向后兼容 | ✅ 426 tests 全程保持, 旧 index.json 可读 |
| 密钥安全 | ✅ sanitize_config 在所有展示路径调用 |
| 测试纪律 | ✅ 每M≥2单元, 每端点≥1集成, 新增6个测试文件 |
| Git工作流 | ✅ feat/knowledge-manager-phase2 分支, 6次squash-friendly提交 |
| 代码审查 | ✅ 无裸except:pass, 无未使用导入, 类型标注完整 |
| 依赖管理 | ✅ 仅新增 fastapi/uvicorn/pyyaml, 无数据库/Redis |
| 日志规范 | ✅ logger 使用正确, 无敏感信息泄露 |

## Phase 6/7 补充规则 (不变更原有规则)

- **M7-M8 均为独立模块**: 无外部依赖, 可并行开发
- **M9 引入 apscheduler**: 需评估对启动时间的影响
- **M10 引入 numpy**: 仅在此模块内使用, 不污染其他模块
- **M11-M13 为可选插件**: 不增加核心依赖
- 每完成一个 Phase 更新此文档的考核结果

## 1. 仓库边界

### 1.1 目录结构约定

```
D:/tyh/knowledge-manager/          ← Python 包根目录 (poetry)
├── src/knowledge_manager/          ← 所有 Python 源码
│   ├── http_server.py              ← M1: FastAPI 端点 (新)
│   ├── ui_fallback.py              ← M1: 零构建回退 HTML (新)
│   ├── chat.py                     ← M2: ChatPipeline (新)
│   ├── tree_builder.py             ← M3: 树构建 (新)
│   ├── tree_navigator.py           ← M3: LLM导航 (新)
│   ├── researcher.py               ← M4: 研究引擎 (新)
│   ├── markdown.py                 ← M5: MD解析/渲染 (新)
│   ├── wikilinks.py                ← M5: Wikilink解析 (新)
│   ├── sync.py                     ← M5: JSON↔MD同步 (新)
│   ├── schemas.py                  ← 所有里程碑的模型 (修改)
│   ├── storage.py                  ← 核心存储逻辑 (修改)
│   ├── mcp_server.py               ← MCP模式 (修改)
│   ├── cli.py                      ← CLI命令 (修改)
│   ├── extractor.py                ← 现有: 不改
│   ├── llm_clients.py              ← 现有: 不改
│   ├── cache.py                    ← 现有: 不改
│   ├── connect.py                  ← 现有: 不改
│   ├── marketplace.py              ← 现有: 不改
│   └── webhooks.py                 ← 现有: 不改
├── src/ui/                         ← M1: React 前端 (新目录)
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   ├── main.tsx
│   ├── App.tsx
│   ├── components/                 ← 每个组件一个文件
│   ├── hooks/                      ← 每个hook一个文件
│   ├── lib/                        ← api.ts, types.ts
│   └── styles/                     ← globals.css
├── tests/                          ← 现有测试目录
│   ├── test_storage.py             ← 现有
│   ├── test_schemas.py             ← 现有
│   ├── test_http_server.py         ← M1新增
│   ├── test_chat.py                ← M2新增
│   ├── test_tree.py                ← M3新增
│   ├── test_researcher.py          ← M4新增
│   ├── test_markdown.py            ← M5新增
│   ├── test_wikilinks.py           ← M5新增
│   ├── test_sync.py                ← M5新增
│   ├── test_http_edit.py           ← M6新增
│   └── test_staging_api.py         ← M6新增
├── docs/
│   ├── BLUEPRINT.md                ← 蓝图 (只读参考)
│   └── superpowers/
│       ├── plans/                  ← 集成拓扑 + 工程规则
│       └── specs/                  ← 每个里程碑的详细规格
├── pyproject.toml
├── .gitignore
└── README.md
```

### 1.2 前端产物边界

- React 源码在 `src/ui/`，构建产物在 `src/ui/dist/`
- `src/ui/dist/` 加入 `.gitignore`（不提交构建产物）
- `http_server.py` 通过检查 `src/ui/dist/index.html` 是否存在来决定提供 React UI 还是回退 UI
- Python 包发布时不包含 `src/ui/` 目录（通过 `poetry` 的 `include` 控制，当前只包含 `src/knowledge_manager`）

### 1.3 知识库数据边界

- `test_kb/` 已加入 `.gitignore`（测试用临时知识库）
- `.staging/` 已加入 `.gitignore`
- `config.json` 已加入 `.gitignore`（含API keys）
- 测试中创建的知识库目录必须放在临时路径（`tmp_path` fixture）

## 2. 里程碑隔离

### 2.1 按里程碑禁用功能

所有新功能必须通过配置开关控制，未完成或未测试的里程碑默认关闭：

```python
# schemas.py — M1 新增
class UIConfig(BaseModel):
    enabled: bool = False           # km serve --ui 总开关

class ChatConfig(BaseModel):
    enabled: bool = False           # M2: 对话搜索

class TreeConfig(BaseModel):
    enabled: bool = False           # M3: 知识树导航

class ResearchConfig(BaseModel):
    enabled: bool = False           # M4: 自动研究
    auto_trigger: bool = False      # 从搜索空结果自动触发

class MarkdownConfig(BaseModel):
    enabled: bool = False           # M5: MD同步
    auto_sync: bool = False         # save时自动双写

class EditConfig(BaseModel):
    enabled: bool = False           # M6: Web UI编辑
```

**规则:** 每个里程碑的代码合并到 main 后，相应 config 默认值改为 `True`。

### 2.2 向后兼容承诺

- 旧版本生成的 `index.json` 必须可被新版本读取（`Optional` 字段 + 默认值）
- 旧版本生成的 `*.json` 模块文件必须可被新版本读取
- 新增的 `.md` 文件与 `.json` 文件共存，不替换
- `mcp_server.py` 的 MCP 协议行为不变（新增 tools 可，现有 tools 签名不可变）

### 2.3 特性检测

```python
# 任何消费方都可以检查功能是否可用
def is_feature_available(kb_path: Path, feature: str) -> bool:
    """检查某个里程碑功能是否可用"""
    cfg = _load_config_safe(kb_path)
    if cfg is None:
        return False
    flags = {
        "ui": cfg.ui.enabled,
        "chat": cfg.chat.enabled,
        "tree": cfg.tree.enabled,
        "research": cfg.research.enabled,
        "markdown": cfg.markdown.enabled,
        "edit": cfg.edit.enabled,
    }
    return flags.get(feature, False)
```

## 3. 密钥与敏感信息

### 3.1 API Key 处理

- LLM API keys 仅存储在 `config.json` 中（已 gitignore）
- `sanitize_config()` 函数（已有）在展示/导出时必须调用
- 日志中绝不输出 API key
- 测试用 API key 从环境变量 `KM_TEST_API_KEY` 读取
- `config.local.json` (gitignored) 覆盖 `config.json` 中的字段（本地开发）

### 3.2 示例配置

- `examples/sample_knowledge_base/config.json` 中的 API key 必须为空字符串
- 所有文档和输出中的 API key 必须替换为 `<LOCAL>` 占位符

### 3.3 Webhook 密钥

- `webhook.secret` 用于 HMAC 签名（已有）
- 日志中绝不输出 secret 明文

### 3.4 前端安全

- 前端不直接访问 LLM API（所有 LLM 调用通过后端代理）
- `/api/config` 端点返回的配置必须调用 `sanitize_config()`
- 不设 `/api/config` PUT 端点（配置修改通过 CLI）

## 4. 测试纪律

### 4.1 测试金字塔

```
        ┌─────┐
        │ E2E │  少量: 完整 km serve --ui 启动 + 浏览器交互 (Playwright)
        ├─────┤
        │集成 │  中等: API端点测试 (TestClient), CLI命令端到端
        ├─────┤
        │单元 │  大量: 纯函数测试, 模型序列化, 搜索排序, 流水线步骤
        └─────┘
```

### 4.2 每个里程碑的最低测试要求

| 测试类型 | 要求 | 示例 |
|---------|------|------|
| 单元测试 | 每个新增模块 ≥2 个测试 | `test_tree.py::test_build_from_markdown`, `test_tree.py::test_slugify_chinese` |
| 模型测试 | 每个新增 Schema ≥1 个 roundtrip 测试 | `test_schemas.py::test_tree_node_roundtrip` |
| 集成测试 | 每个新增端点 ≥1 个测试 | `test_http_server.py::test_get_tree` |
| 回归测试 | 现有 12 个测试文件必须保持通过 | `pytest tests/` 全绿 |

### 4.3 测试运行规范

```bash
# 日常开发
pytest tests/ -x --tb=short          # 遇错停止，简洁回溯

# 提交前
pytest tests/ --cov=src/knowledge_manager --cov-report=term-missing

# 每个里程碑完成时
pytest tests/ -v --cov=src/knowledge_manager --cov-report=html
```

### 4.4 测试 Fixture 约定

```python
# conftest.py 提供共享 fixture
@pytest.fixture
def tmp_kb(tmp_path):
    """创建一个最小知识库用于测试"""
    kb = tmp_path / "test_kb"
    kb.mkdir()
    # 写入最小 config.json 和 index.json
    ...

@pytest.fixture
def sample_module():
    """返回一个完整的示例 Module 对象"""
    return Module(
        id="test-module",
        category="test",
        title="Test Module Title",
        summary="A test module for unit tests",
        content=ModuleContent(overview="test overview", details="test details content"),
        metadata=ModuleMetadata(tags=["test"], confidence="high"),
    )
```

### 4.5 测试命名约定

```
tests/
├── test_schemas.py          # test_<被测试模块>.py
├── test_storage.py
├── test_chat.py
├── test_tree.py
├── test_researcher.py
├── test_markdown.py
├── test_wikilinks.py
├── test_sync.py
├── test_http_server.py      # FastAPI端点测试
├── test_http_edit.py        # 编辑端点测试
├── test_staging_api.py      # 审核API测试
├── test_cli.py              # CLI命令测试 (已有)
└── test_integration.py      # 跨模块集成测试 (已有)
```

## 5. Git 工作流

### 5.1 分支策略

```
master ← 主分支 (稳定，可发布)
  ↑
  ├── feat/m1-web-ui-readonly    ← M1 实现分支
  ├── feat/m2-chat-search        ← M2 实现分支
  ├── feat/m3-knowledge-tree     ← M3 实现分支
  ├── feat/m4-research-on-miss   ← M4 实现分支
  ├── feat/m5-markdown-sync      ← M5 实现分支
  └── feat/m6-ui-edit-review     ← M6 实现分支
```

**规则:**
- 每个里程碑一个 feature branch，从 master 切出
- 完成后 squash merge 到 master
- 不直接在 master 上提交
- Commit message 格式: `feat(M1): <描述>` / `fix(M1): <描述>`

### 5.2 提交粒度

- 一个 commit 做一件事（可独立 revert）
- 不要在同一个 commit 中混合新功能和重构
- Commit message 描述 WHY，不是 WHAT

### 5.3 推送前检查清单

```
[ ] pytest tests/ 全绿
[ ] mypy src/knowledge_manager/ 无新增错误
[ ] black --check src/ tests/ 通过
[ ] 无调试打印 (print, console.log)
[ ] 无注释掉的代码
[ ] 未提交 config.json / .env
```

### 5.4 子模块管理（父仓库 D:/tyh）

父仓库通过 git submodule 跟踪 knowledge-manager。每次 knowledge-manager 有重要更新后：

```bash
cd D:/tyh
git add knowledge-manager
git commit -m "chore: bump knowledge-manager submodule (M1 complete)"
```

## 6. 代码审查标准

### 6.1 每个 PR 必须检查

| 检查项 | 标准 |
|--------|------|
| 类型覆盖 | 所有新增函数有类型标注 |
| 错误处理 | HTTP端点返回合适的4xx/5xx而非500 |
| 向后兼容 | 现有测试仍通过，现有API签名不变 |
| 配置开关 | 新功能受配置开关控制 |
| 日志 | 关键操作有日志，不含敏感信息 |
| 测试 | 满足该里程碑的最低测试要求 |

### 6.2 不接受

- 裸 `except:` 或 `except Exception: pass`
- 硬编码路径（必须用 `kb_path` 参数）
- 在 `storage.py` 中引入 UI 框架依赖
- 在 `schemas.py` 中引用 `react` 或前端类型
- `print()` 调试输出（用 `logger.debug()`）

## 7. 依赖管理

### 7.1 Python 依赖

新增依赖必须满足以下条件之一：
- 已在 BLUEPRINT.md 中明确提及（如 FastAPI, uvicorn）
- 是标准库的一部分
- 经过 `pip install` 零配置可用

**Phase 5 新增依赖:**
```
fastapi = "^0.115.0"       # M1: Web API框架
uvicorn = "^0.32.0"        # M1: ASGI服务器
sse-starlette = "^2.0.0"   # M2: SSE支持
pyyaml = "^6.0"             # M5: YAML frontmatter解析 (可能已间接依赖)
```

不引入: 数据库驱动、消息队列、Redis客户端、向量数据库。

### 7.2 前端依赖

前端依赖通过 `package.json` 管理，与 Python 包完全独立。详见 `m1-frontend.md` 中的 `package.json` 规范。

## 8. 日志与可观测性

### 8.1 日志级别

```python
logger.debug("...")    # 开发调试
logger.info("...")     # 关键操作 (启动、构建、同步)
logger.warning("...")  # 非致命异常 (文件缺失、LLM调用重试)
logger.error("...")    # 需要关注的错误 (配置错误、写入失败)
```

### 8.2 关键操作日志

以下操作必须有 `logger.info` 记录：
- `km serve --ui` 启动/停止
- `rebuild_index` 开始/完成 (含模块数和耗时)
- `sync_on_rebuild` 发现冲突
- `research` 各阶段进度
- ChatPipeline 各阶段耗时

### 8.3 禁止记录

- API key
- 用户查询原文（可记录 query_hash）
- 模块全文内容
- Webhook secret

## 9. 文档纪律

### 9.1 新模块必须包含

- 模块级 docstring (1行，描述职责)
- 公开函数的类型标注

### 9.2 不写

- 多段 docstring
- 方法内的注释（除非 WHY 非显而易见）
- README 或单独的说明 markdown（除非用户明确要求）

### 9.3 规格文档是活的

当实现过程中发现规格有误，**先更新 spec 文档**，再修改代码。spec 是实现的约束，不是实现后的记录。

---

## Gate Pass 标准

- [x] 仓库边界明确 (Python/前端/测试/数据目录分离)
- [x] 里程碑隔离机制有开关控制 + 特性检测函数
- [x] 向后兼容有具体承诺 (4条)
- [x] 密钥处理有明确规范 (sanitize + 环境变量 + gitignore)
- [x] 测试纪律有量化要求 (每模块2+单元, 每端点1+集成, 回归全绿)
- [x] Git工作流有分支策略 + 提交规范 + 推送检查清单
- [x] 代码审查标准有硬性规则 (类型/错误处理/兼容/开关/日志/测试)
- [x] 依赖管理明确 Phase 5 新增依赖列表
- [x] 日志规范 (4级 + 关键操作 + 禁止记录项)
- [x] 文档纪律 (docstring最小化 + spec先行)
