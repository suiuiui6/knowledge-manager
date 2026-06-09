# M10 Spec — 可选向量搜索增强

> Phase 6 M10 | 2026-06-09 | 硬依赖: 无 | 软依赖: M2 (ChatPipeline 的第三路召回)

## 概述

当前 4 层关键词排序已很强，但有一个盲区：概念模糊匹配。用户搜"服务间通信方式"但库里写的是"gRPC"和"消息队列"——关键词完全找不到。向量搜索作为可选增强层，默认关闭，零外部基础设施。

## 配置

```json
{
  "search": {
    "vector": {
      "enabled": false,
      "provider": "ollama",
      "model": "bge-m3",
      "dimensions": 1024,
      "weight": 0.25,
      "rebuild_on_start": false,
      "auto_rebuild_interval_hours": 24
    }
  }
}
```

支持的 provider: `ollama` (本地, 推荐), `local` (sentence-transformers), `openai` (API)

## 核心组件

### 文件: `src/knowledge_manager/vector_index.py`

```python
class VectorIndex:
    """
    零外部依赖的向量索引。
    100K 模块 × 1024维 × float32 = ~400MB 内存, 可接受。
    持久化到 .cache/vector_index.npz 加速重启。
    """

    def __init__(self, kb_path, config):
        self.embeddings: Optional[np.ndarray] = None
        self.module_keys: list[str] = []

    async def rebuild(self, on_progress=None):
        # 1. 遍历所有 published 模块
        # 2. 拼接: title + summary + tags + overview + details
        # 3. 批量调用 embedding provider
        # 4. 归一化 (余弦相似度 = 内积)
        # 5. 持久化到 .cache/vector_index.npz

    def search(self, query: str, top_k: int = 20) -> list[tuple[str, float]]:
        # 1. 生成查询 embedding
        # 2. 内积 = 余弦相似度 (已归一化)
        # 3. argpartition top_k
        # 返回: [(module_key, similarity), ...]
```

### RRF 融合集成

```python
# search_modules 增强
def search_modules(query, kb_path, ..., vector_index=None, vector_weight=0.25):
    keyword_results = _keyword_search(...)     # 现有
    vector_results = _vector_search(...)       # M10 新增

    if vector_results:
        fused = _rrf_fuse(
            keyword=keyword_results,
            vector=vector_results,
            k_keyword=60, k_vector=120,
            weight_keyword=1.0 - vector_weight,
            weight_vector=vector_weight,
        )
    else:
        fused = keyword_results

    return _apply_bayesian_and_truncate(fused, ...)
```

### ChatPipeline 集成 (M2增强)

```
M2 (无vector): keyword + tree
M10 (有vector): keyword + tree + vector → RRF 三路融合
weights: keyword=0.35, tree=0.30, vector=0.25 (未启用vector时自动忽略)
```

## CLI

```bash
km vector rebuild           # 重建向量索引
km vector status            # 显示索引状态 (模块数, 维度, 内存占用)
km vector search "query"    # 纯向量搜索 (测试用)
```

## 新增/修改文件

| 文件 | 操作 | 内容 |
|------|------|------|
| `src/knowledge_manager/vector_index.py` | **新建** | VectorIndex + 3种 provider |
| `src/knowledge_manager/schemas.py` | 修改 | +VectorSearchConfig |
| `src/knowledge_manager/storage.py` | 修改 | search_modules RRF 集成 |
| `src/knowledge_manager/chat.py` | 修改 | _vector_recall 启用 |
| `src/knowledge_manager/cli.py` | 修改 | +vector命令组 |
| `tests/test_vector.py` | **新建** | 向量索引 + RRF 融合测试 |

## Gate Pass 标准

- [ ] `km vector rebuild` 成功生成索引
- [ ] 向量搜索返回语义相关结果 (与关键词搜索不同但合理)
- [ ] RRF 融合后排序优于单路
- [ ] 索引缓存: 重启后从 .cache/ 加载, 不重新计算
- [ ] 未启用时不影响现有搜索行为
- [ ] 100K 模块内存 < 500MB
