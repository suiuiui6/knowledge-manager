# M8 Spec — 间隔重复记忆系统 (FSRS)

> Phase 6 M8 | 2026-06-09 | 硬依赖: 无

## 概述

基于 FSRS v5 算法的间隔重复记忆系统。从知识模块自动生成问答卡片，通过间隔重复帮团队成员将关键知识内化。从"库里有"变成"脑子里有"。

## 数据模型

### schemas.py 新增

```python
class ReviewGrade(int, Enum):
    AGAIN = 1    # 完全忘记
    HARD = 2     # 回忆起部分
    GOOD = 3     # 正确回忆
    EASY = 4     # 轻松正确

class MemoryCard(BaseModel):
    id: str
    module_key: str
    module_title: str
    category: str
    front: str            # 问题
    back: str             # 答案 (≤150字)
    source_field: str     # 从模块哪个字段生成
    fsrs_state: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    last_review_at: Optional[datetime] = None
    next_review_at: Optional[datetime] = None
    review_count: int = 0
    total_grade_sum: int = 0

class MemoryStats(BaseModel):
    total_cards: int = 0
    due_today: int = 0
    due_this_week: int = 0
    avg_retention: float = 0.0   # 90天预测保留率
    streak_days: int = 0
    total_reviews: int = 0
```

## 核心组件

### 文件: `src/knowledge_manager/memory.py`

```
FSRSScheduler:
  - schedule(card, grade) → 更新 stability/difficulty/next_review
  - get_due_cards(cards, limit) → 按优先级排序的到期卡片
  - FSRS v5 算法: 17个参数, stability/difficulty 更新公式

CardGenerator:
  - generate_cards_for_module(module, llm, max_cards) → 场景化问答卡片
  - select_modules_for_memory(kb_path) → 筛选高价值模块
    (confidence=high, status=published, 按load_count排序)
```

### FSRS 核心参数

```python
DEFAULT_WEIGHTS = [
    0.4072, 1.1829, 3.1262, 15.4722, 7.2102, 0.5316,
    1.0651, 0.0234, 1.616, 0.0304, 0.0611, 1.8455,
    0.172, 0.913, 2.6026, 0.3674, 0.7462, 0.9478, 0.0,
]
```

### 卡片生成 Prompt

场景化问题，不是"XX是什么?"，而是"如果我们遇到Y情况，应该怎么做? 为什么?"

## CLI

```bash
km memory init              # 扫描KB → LLM生成卡片 → 保存到 .memory/cards.json
km memory today             # 今日到期卡片 (交互式问答)
km memory stats             # 统计: 总卡片/连续复习/预测保留率
km memory grade <card_id> <1-4>  # 记录复习结果
```

## 与健康评分的联动

模块健康评分新增 `team_retention` 维度 (权重15%)：基于该模块卡片的 FSRS stability 平均值。

## 新增/修改文件

| 文件 | 操作 | 内容 |
|------|------|------|
| `src/knowledge_manager/memory.py` | **新建** | FSRSScheduler + CardGenerator |
| `src/knowledge_manager/schemas.py` | 修改 | +MemoryCard, MemoryStats, ReviewGrade |
| `src/knowledge_manager/cli.py` | 修改 | +memory命令组 |
| `src/knowledge_manager/mcp_server.py` | 修改 | +get_review_cards, grade_review_card tools |
| `tests/test_memory.py` | **新建** | FSRS调度 + 卡片生成测试 |

## Gate Pass 标准

- [ ] `km memory init` 生成卡片 (≥1张/高价值模块)
- [ ] FSRS 调度器: Again→1min, Good→1d, Easy→4d (首次)
- [ ] 卡片到期排序: 过期久 > 难度高 > 不稳定
- [ ] `km memory today` 交互式复习
- [ ] 卡片持久化到 `.memory/cards.json`
