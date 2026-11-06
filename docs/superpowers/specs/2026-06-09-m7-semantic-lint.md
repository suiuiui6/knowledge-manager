# M7 Spec — 语义矛盾检测 (lint --deep)

> Phase 6 M7 | 2026-06-09 | 硬依赖: 无 | 软依赖: M3 (树结构可优化候选对筛选)

## 概述

检测知识库中的语义矛盾：不是字符串比较，而是 LLM 理解两段文字是否在讲同一件事但得出相反结论。两层检测：quick（结构化规则）和 deep（LLM 语义比较）。

## 数据模型

### schemas.py 新增

```python
class ContradictionType(str, Enum):
    FACT = "fact"              # 事实数字/配置矛盾
    DECISION = "decision"       # 架构决策矛盾
    TIMELINE = "timeline"       # 时间线断裂
    TERMINOLOGY = "terminology" # 同一事物不同名称
    STALE_REFERENCE = "stale_ref" # 引用已废弃模块

class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

class ContradictionEvidence(BaseModel):
    module_key: str
    field: str
    excerpt: str
    claim: str = ""

class Contradiction(BaseModel):
    id: str
    type: ContradictionType
    severity: Severity
    modules: list[str]
    description: str
    evidence: list[ContradictionEvidence] = Field(default_factory=list)
    suggestion: str = ""
    auto_fixable: bool = False
    auto_fix_description: str = ""
```

## 检测流水线

### 文件: `src/knowledge_manager/linter.py`

```
Phase 1: 候选对筛选
  用规则剪枝: same_category | shared_tags | mutual_reference | title_overlap
  O(n²) → ~175对 (127模块)

Phase 2: 结构化检查 (quick, 无LLM)
  - 废弃引用: related_modules 包含 archived/deprecated 模块
  - 断链: 引用不存在的模块
  - 过期模块: expires_at 已过但 status 仍是 published
  - 孤立模块: 无入度无出度

Phase 3: 语义检查 (deep, LLM)
  每对候选用 LLM 判断5个维度矛盾
  每批10对并行发送

Phase 4: 结果排序
  severity (error > warning > info) → 影响模块数
```

### 核心类

```python
class DeepLinter:
    PAIR_FILTERS = {
        "same_category": lambda a, b: a.category == b.category,
        "shared_tags": lambda a, b: bool(set(a.tags) & set(b.tags)),
        "mutual_reference": lambda a, b: ...,
        "title_overlap_keywords": lambda a, b: ...,
    }

    async def lint_all(self, kb_path, mode="deep") -> list[Contradiction]:
        ...

    def _structural_check(self, modules, index) -> list[Contradiction]:
        ...

    async def _semantic_check(self, candidates, kb_path) -> list[Contradiction]:
        ...
```

## CLI

```bash
km lint                    # 结构化检查 (quick)
km lint --deep             # 完整语义分析
km lint --fix              # 自动修复可修复的问题
km lint --module auth/jwt  # 只检查特定模块的相关对
```

## 新增/修改文件

| 文件 | 操作 | 内容 |
|------|------|------|
| `src/knowledge_manager/linter.py` | **新建** | DeepLinter + 4阶段检测 |
| `src/knowledge_manager/schemas.py` | 修改 | +Contradiction, ContradictionEvidence, ContradictionType, Severity |
| `src/knowledge_manager/cli.py` | 修改 | +lint命令 |
| `tests/test_linter.py` | **新建** | 结构化检查 + 语义检查测试 |

## Gate Pass 标准

- [ ] `km lint` 检测到废弃引用和断链
- [ ] `km lint --deep` 检测到语义矛盾 (LLM判断)
- [ ] 候选对筛选正确剪枝 (不产生 O(n²) 调用)
- [ ] 自动修复: 废弃引用→移除关联
- [ ] 报告输出 CLI 表格 + JSON 格式
