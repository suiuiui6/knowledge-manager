# Knowledge Manager — 未来蓝图

## 当前定位

knowledge-manager v0.5.0 的架构深度已经超过 PageIndex 和 llm-wiki：4层搜索排序、贝叶斯反馈学习、知识市场+依赖解析、多KB联邦、人工审核门控、Git原生全流程。

问题：这些能力全部藏在CLI和MCP后面。PageIndex有对话界面，llm-wiki有Web UI和Obsidian兼容。**用户选产品不看架构，看体验。**

## 北极星

> 从"Agent的知识后端"进化为"人和Agent共享的第二大脑"

- 知识不是被检索的，是**自动生长**的（research-on-miss）
- 知识不是被存储的，是**被记住**的（间隔重复）
- 知识不是孤立的，是**被验证**的（矛盾检测）
- 知识不是JSON文件，是**人类可浏览编辑**的（Markdown + Web UI）

---

# 大改进一：Web UI + 对话式搜索

## 为什么是决定性改进

当前用户使用 knowledge-manager 的路径：

```
终端敲 km search "jwt token"
  → 看 JSON 数组输出
  → 找到模块ID
  → km show jwt-config -c auth
  → 读 JSON 的 content.details 字段
  → 回到 MCP agent 提问
```

PageIndex 用户的路径：

```
打开 chat.pageindex.ai
  → 输入 "JWT过期时间是多少？"
  → 得到自然语言答案 + 页码引用
```

llm-wiki (Oshayr) 用户的路径：

```
打开 localhost:8420
  → 看到 Wikipedia 风格的wiki首页
  → 左侧导航树, 右侧知识图谱
  → 搜索框输入 → 实时过滤页面列表
  → 点击页面 → Markdown渲染阅读
  → 聊天侧边栏 → RAG增强问答
```

**差距不在能力，在交互。** knowledge-manager 的4层搜索排序比两个竞品都强，但用户感知不到——他们只看到JSON。

## 架构设计

### 服务模式

```bash
# 纯MCP模式 (现有, 不变)
km serve

# MCP + Web UI 模式 (新增)
km serve --ui                    # 仅 localhost
km serve --ui --host 0.0.0.0    # 局域网可访问
km serve --ui --port 8420        # 自定义端口
```

内部实现：一个进程同时运行 FastMCP (stdio) 和 FastAPI (HTTP + WebSocket)。两个协议共享同一个 Storage 实例和 ModuleCache。

```
┌────────────────────────────────────────────┐
│                 km serve --ui               │
│                                             │
│  ┌──────────────┐    ┌──────────────────┐  │
│  │  FastMCP      │    │  FastAPI          │  │
│  │  (stdio)      │    │  (localhost:8420) │  │
│  │               │    │                   │  │
│  │  resources:   │    │  GET /api/        │  │
│  │   index       │    │   health          │  │
│  │   health      │    │                   │  │
│  │   stats       │    │  GET /api/index   │  │
│  │   changelog   │    │  GET /api/modules │  │
│  │               │    │  GET /api/modules/ │  │
│  │  tools:       │    │   :cat/:id        │  │
│  │   load_module │    │                   │  │
│  │   search      │    │  POST /api/search │  │
│  │   expand      │    │  POST /api/chat   │  │
│  │   deep_search │    │   (SSE stream)    │  │
│  │   graph       │    │                   │  │
│  │   federated   │    │  GET /api/graph   │  │
│  │               │    │  GET /api/tree    │  │
│  └──────────────┘    │                   │  │
│                       │  WebSocket /ws    │  │
│                       │   (live updates)  │  │
│                       └──────────────────┘  │
│                                             │
│  共享: Storage, ModuleCache, RankModel      │
└────────────────────────────────────────────┘
```

### REST API 设计

```
# 知识库概览
GET  /api/health              → KBHealthReport (JSON)
GET  /api/stats               → UsageStats (JSON)
GET  /api/index               → Index (JSON, 不含模块全文)

# 知识树 (新)
GET  /api/tree                → TreeNode (层次化树结构)
GET  /api/tree/:cat/:id       → TreeNode (以该模块为根的子树)

# 模块操作
GET  /api/modules             → list[ModuleSummary] (?category=&status=&tag=&page=&limit=)
GET  /api/modules/:cat/:id    → Module (JSON 全文, 含 content)
GET  /api/modules/:cat/:id.md → Module (Markdown 全文, 含 frontmatter)

# 搜索
POST /api/search              → SearchResponse
  Body: { "query": "...", "category": "", "include_archived": false, "top_k": 10 }
  Response: { "results": [...], "intent": "how-to", "took_ms": 12 }

# 对话式搜索
POST /api/chat                → SSE stream
  Body: { "query": "...", "history": [...], "mode": "precise|creative" }
  SSE events:
    - event: status    data: {"stage": "intent_classification", "intent": "reference"}
    - event: status    data: {"stage": "tree_navigation", "path": ["auth", "auth/jwt-config"]}
    - event: status    data: {"stage": "keyword_search", "candidates": 15}
    - event: status    data: {"stage": "reranking", "method": "rrf"}
    - event: token     data: {"text": "JWT", "source": null}
    - event: token     data: {"text": " token", "source": null}
    - event: token     data: {"text": " 过期时间", "source": "auth/jwt-config"}
    - event: citation  data: {"module": "auth/jwt-config", "title": "JWT配置", "snippet": "..."}
    - event: done      data: {"took_ms": 2340, "sources": [...]}

# 知识图谱
GET  /api/graph               → GraphData (nodes + edges, 前端可视化用)
GET  /api/graph/:cat/:id      → GraphData (以该模块为中心的局部图)

# 推荐
GET  /api/recommendations     → RecommendationReport

# 审核 (需要认证时才开启)
GET  /api/staging             → list[StagingEntry]
POST /api/staging/:id/approve
POST /api/staging/:id/reject
POST /api/staging/:id/request-changes   Body: { "comment": "..." }

# 研究 (Research-on-Miss)
POST /api/research            → SSE stream
  Body: { "query": "...", "depth": "shallow|deep" }
  SSE events 流式返回研究进度

# 记忆 (间隔重复)
GET  /api/memory/today        → list[ReviewCard]
POST /api/memory/grade        Body: { "card_id": "...", "grade": 1-4 }

# 配置
GET  /api/config              → Config (API keys已脱敏)
PUT  /api/config              → Config (部分更新)

# 插件
GET  /api/plugins             → list[PluginInfo]
POST /api/plugins/:name/enable
POST /api/plugins/:name/disable
```

### 前端架构

```
src/ui/                          # 新增目录
├── index.html                   # SPA入口, 零构建模式可用
├── main.tsx                     # React入口 (需要构建时)
├── components/
│   ├── Layout.tsx               # 三栏布局 (树 + 内容 + 图谱)
│   ├── KnowledgeTree.tsx        # 左侧知识树
│   │   ├── TreeNode.tsx         # 递归树节点
│   │   └── TreeSearch.tsx       # 树内过滤搜索
│   ├── ChatPanel.tsx            # 对话面板
│   │   ├── ChatMessage.tsx      # 单条消息 (含引用标记)
│   │   ├── ChatInput.tsx        # 输入框 (支持 @mention 模块)
│   │   └── CitationPopover.tsx  # 引用悬浮卡片
│   ├── ModuleViewer.tsx         # 模块内容渲染
│   │   ├── MarkdownRenderer.tsx # Markdown → React (支持 wikilinks)
│   │   ├── ModuleMeta.tsx       # 元数据面板 (tags/状态/置信度)
│   │   └── RelatedModules.tsx   # 相关模块列表
│   ├── GraphView.tsx            # 知识图谱可视化
│   │   ├── ForceGraph.tsx       # 力导向图 (Cytoscape.js)
│   │   ├── GraphControls.tsx    # 缩放/过滤/布局切换
│   │   └── NodeDetail.tsx       # 节点点击详情弹出
│   ├── Dashboard.tsx            # 首页仪表盘
│   │   ├── StatsCards.tsx       # 统计卡片
│   │   ├── HealthChart.tsx      # 健康趋势图
│   │   └── RecentActivity.tsx   # 最近活动
│   ├── StagingPanel.tsx         # 审核面板
│   │   ├── StagingList.tsx      # 待审核列表
│   │   └── DiffViewer.tsx       # 新增/修改差异对比
│   ├── MemoryPanel.tsx          # 间隔重复面板
│   │   ├── ReviewCard.tsx       # 复习卡片 (正面/背面翻转)
│   │   └── MemoryStats.tsx      # 记忆统计
│   └── SettingsPanel.tsx        # 配置管理
├── hooks/
│   ├── useChat.ts               # SSE流式对话
│   ├── useSearch.ts             # 搜索防抖
│   ├── useGraph.ts              # 图谱数据
│   ├── useTree.ts               # 知识树数据
│   └── useMemory.ts             # 记忆卡片
├── lib/
│   ├── api.ts                   # API 客户端
│   ├── wikilinks.ts             # [[wikilinks]] 解析器
│   └── markdown.ts              # Markdown 渲染 + 自定义插件
├── styles/
│   └── globals.css              # TailwindCSS
└── vite.config.ts               # Vite 构建配置
```

### 零构建模式

对于不想安装 Node.js 的用户，提供一个单HTML文件模式：

```python
# src/knowledge_manager/ui_fallback.py

FALLBACK_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Knowledge Manager</title>
  <script src="https://cdn.jsdelivr.net/npm/htmx.org@1.9/dist/htmx.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/alpinejs@3.x/dist/cdn.min.js"></script>
  <link href="https://cdn.jsdelivr.net/npm/water.css@2/out/water.min.css" rel="stylesheet">
</head>
<body>
  <!-- 只读浏览模式, 用 htmx + Alpine.js 构建 -->
  ...
</body>
</html>"""

def serve_fallback_ui():
    """当没有前端构建产物时, 使用内嵌的单HTML只读UI"""
    ...
```

`km serve --ui` 启动时检查前端构建产物是否存在：存在则用完整React UI，不存在则用零构建回退UI。

### 对话式搜索的检索-生成流水线

这是整个Web UI的核心技术链路：

```python
# src/knowledge_manager/chat.py (新文件)

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator

@dataclass
class ChatEvent:
    type: str  # "status", "token", "citation", "done", "error"
    data: dict

class ChatPipeline:
    """对话式搜索的完整检索-生成流水线"""

    def __init__(self, kb_path: Path, llm_client, rank_model, tree_index, vector_index=None):
        self.kb_path = kb_path
        self.llm = llm_client
        self.rank_model = rank_model
        self.tree_index = tree_index
        self.vector_index = vector_index

    async def chat(self, query: str, history: list[dict], mode: str = "precise") -> AsyncIterator[ChatEvent]:
        """
        主流水线:

        1. 查询理解 (改写 + 意图分类)
        2. 多路召回 (树推理 + 关键词 + 语义)
        3. RRF 融合排序
        4. 上下文组装
        5. LLM 生成答案 (流式)
        6. 后处理 (引用注入, 追问建议)
        """

        # ── Step 1: 查询理解 ──
        yield ChatEvent("status", {"stage": "query_understanding", "message": "分析查询意图..."})

        # 查询改写: 结合对话历史, 将省略/指代补全
        rewritten = await self._rewrite_query(query, history)

        # 意图分类: 复用 storage.py 中现有的 _classify_intent
        intent = _classify_intent(rewritten)

        yield ChatEvent("status", {
            "stage": "query_understanding",
            "rewritten": rewritten,
            "intent": intent,
        })

        # ── Step 2: 多路召回 (并行) ──
        yield ChatEvent("status", {"stage": "retrieval", "message": "检索相关知识..."})

        tree_results, keyword_results, vector_results = await asyncio.gather(
            self._tree_recall(rewritten, intent),
            self._keyword_recall(rewritten, intent),
            self._vector_recall(rewritten) if self.vector_index else asyncio.sleep(0, result=[]),
        )

        # ── Step 3: RRF 融合 ──
        yield ChatEvent("status", {"stage": "ranking", "message": "融合排序..."})

        fused = self._rrf_fuse(
            tree=tree_results,
            keyword=keyword_results,
            vector=vector_results,
            weights={"tree": 0.4, "keyword": 0.35, "vector": 0.25},
        )

        # 贝叶斯反馈调整
        fused = self.rank_model.apply(fused, rewritten)

        # 取 top-5 作为上下文
        top_modules = fused[:5]

        yield ChatEvent("status", {
            "stage": "ranking",
            "candidates": len(fused),
            "selected": len(top_modules),
            "top_titles": [m.title for m in top_modules],
        })

        # ── Step 4: 上下文组装 ──
        yield ChatEvent("status", {"stage": "context_assembly", "message": "组装上下文..."})

        system_prompt = self._build_system_prompt(top_modules, intent)
        user_prompt = self._build_user_prompt(rewritten, history)

        # ── Step 5: LLM 生成答案 (流式) ──
        yield ChatEvent("status", {"stage": "generation", "message": "生成答案..."})

        full_response = ""
        citations = set()

        async for chunk in self.llm.stream_chat(system_prompt, user_prompt):
            # 检测 chunk 中是否包含来源引用标记
            text = chunk.get("text", "")
            full_response += text

            # 实时注入引用: 当流式输出提到模块名时, 附带引用信息
            source_info = self._detect_source_reference(text, top_modules)
            if source_info:
                citations.add(source_info["module_key"])

            yield ChatEvent("token", {
                "text": text,
                "source": source_info["module_key"] if source_info else None,
            })

        # ── Step 6: 后处理 ──
        # 收集所有引用到的模块
        cited_modules = []
        for key in citations:
            mod = self._find_module(key, top_modules)
            if mod:
                cited_modules.append({
                    "key": key,
                    "title": mod.title,
                    "snippet": mod.summary,
                    "confidence": mod.metadata.confidence,
                    "updated_at": mod.updated_at.isoformat(),
                })
        for event in citations:
            yield ChatEvent("citation", event_data)

        # 生成追问建议
        follow_ups = await self._generate_follow_ups(query, full_response, top_modules)

        yield ChatEvent("done", {
            "took_ms": ...,
            "sources": cited_modules,
            "follow_ups": follow_ups,
            "navigation_path": tree_results[0].path if tree_results else None,
        })

    async def _tree_recall(self, query: str, intent: str) -> list[ScoredModule]:
        """树状推理召回: LLM在知识树上导航"""
        if not self.tree_index:
            return []

        navigator = TreeNavigator(self.llm, self.tree_index)
        results = await navigator.navigate(query, max_steps=5)
        return results

    async def _keyword_recall(self, query: str, intent: str) -> list[ScoredModule]:
        """关键词召回: 复用现有 search_modules (4层排序)"""
        results = search_modules(
            query, self.kb_path,
            limit=20,
            boost_ids=[],
            include_archived=False,
        )
        return [
            ScoredModule(
                module=r.module,
                score=r.score,
                source="keyword",
                highlights=r.highlights,
            )
            for r in results
        ]

    async def _vector_recall(self, query: str) -> list[ScoredModule]:
        """向量语义召回 (可选)"""
        if not self.vector_index:
            return []
        return self.vector_index.search(query, top_k=20)

    def _rrf_fuse(self, tree, keyword, vector, weights) -> list[ScoredModule]:
        """
        Reciprocal Rank Fusion:
        每个结果路独立排名 → RRF分数 = Σ 1/(k + rank_i)

        三路排名的 k 值不同:
        - tree: k=30 (树推理排名更稀疏, 小k让头部权重更大)
        - keyword: k=60 (标准)
        - vector: k=120 (向量召回噪声多, 大k平滑)
        """
        ...

    def _build_system_prompt(self, modules, intent) -> str:
        """
        系统提示词:

        - 知识来源: 列出每个模块的 title + summary + confidence
        - 引用规则: 引用模块内容时使用 [ref:category/id] 标记
        - 意图适配: how-to 类问题注重示例, decision-record 类注重理由
        - 边界意识: 不知道就说不知道，不编造
        """
        ...

    async def _generate_follow_ups(self, query, response, modules) -> list[str]:
        """LLM根据当前问答生成3个自然的追问建议"""
        ...
```

### SSE 流的前端消费

```typescript
// src/ui/hooks/useChat.ts

interface ChatState {
  messages: ChatMessage[];
  isStreaming: boolean;
  currentStatus: string;
  currentSources: Citation[];
}

function useChat() {
  const [state, setState] = useState<ChatState>({...});

  async function sendMessage(query: string, history: ChatMessage[]) {
    setState(s => ({ ...s, isStreaming: true }));

    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, history, mode: 'precise' }),
    });

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let currentAnswer = '';
    const sources: Citation[] = [];

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const event = JSON.parse(line.slice(6));

        switch (event.type) {
          case 'status':
            setState(s => ({ ...s, currentStatus: event.data.message }));
            break;

          case 'token':
            currentAnswer += event.data.text;
            // 增量更新最后一条消息
            setState(s => ({
              ...s,
              messages: s.messages.with(-1, {
                ...s.messages.at(-1),
                content: currentAnswer,
              }),
            }));
            break;

          case 'citation':
            sources.push(event.data);
            setState(s => ({ ...s, currentSources: [...sources] }));
            break;

          case 'done':
            setState(s => ({
              ...s,
              isStreaming: false,
              messages: s.messages.with(-1, {
                ...s.messages.at(-1),
                sources: event.data.sources,
                followUps: event.data.follow_ups,
              }),
            }));
            break;

          case 'error':
            setState(s => ({ ...s, isStreaming: false }));
            break;
        }
      }
    }
  }

  return { state, sendMessage };
}
```

### 知识图谱可视化

```typescript
// src/ui/components/GraphView/ForceGraph.tsx

interface GraphNode {
  id: string;           // "auth/jwt-config"
  label: string;        // "JWT配置"
  category: string;     // "auth"
  status: string;       // "published" | "deprecated" | "archived"
  confidence: string;   // "high" | "medium" | "low"
  inDegree: number;     // 被引用次数
  outDegree: number;    // 引用次数
  // 可视化属性
  size: number;         // 与被引用次数成正比
  color: string;        // category → 颜色映射
}

interface GraphEdge {
  source: string;       // "auth/jwt-config"
  target: string;       // "auth/token-rotation"
  weight: number;       // 0.0-1.0
  label?: string;       // 可选边标签
}

function ForceGraph({ nodes, edges, onNodeClick }) {
  useEffect(() => {
    const cy = cytoscape({
      container: containerRef.current,
      elements: [
        ...nodes.map(n => ({
          data: { id: n.id, label: n.label, ...n },
        })),
        ...edges.map((e, i) => ({
          data: {
            id: `e${i}`,
            source: e.source,
            target: e.target,
            weight: e.weight,
          },
        })),
      ],
      style: [
        {
          selector: 'node',
          style: {
            'label': 'data(label)',
            'width': 'mapData(size, 5, 80, 20, 80)',
            'height': 'mapData(size, 5, 80, 20, 80)',
            'background-color': 'data(color)',
            'border-width': 2,
            'border-color': '#fff',
            'font-size': '10px',
            'text-valign': 'bottom',
            'text-halign': 'center',
            'text-margin-y': 8,
          },
        },
        {
          selector: 'node[status="deprecated"]',
          style: { 'border-color': '#f59e0b', 'border-style': 'dashed' },
        },
        {
          selector: 'node[status="archived"]',
          style: { 'opacity': 0.4 },
        },
        {
          selector: 'edge',
          style: {
            'width': 'mapData(weight, 0, 1, 1, 5)',
            'line-color': '#94a3b8',
            'target-arrow-color': '#94a3b8',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            'opacity': 0.6,
          },
        },
      ],
      layout: {
        name: 'cose',           // 力导向布局
        animate: true,
        nodeRepulsion: 8000,
        idealEdgeLength: 120,
        gravity: 0.3,
      },
    });

    cy.on('click', 'node', (evt) => {
      const nodeId = evt.target.id();
      onNodeClick(nodeId);
    });

    // 悬停时高亮邻居节点
    cy.on('mouseover', 'node', (evt) => {
      const node = evt.target;
      const neighborhood = node.closedNeighborhood();
      cy.elements().difference(neighborhood).addClass('dimmed');
    });
    cy.on('mouseout', 'node', () => {
      cy.elements().removeClass('dimmed');
    });

    return () => cy.destroy();
  }, [nodes, edges]);

  return <div ref={containerRef} style={{ width: '100%', height: '600px' }} />;
}
```

---

# 大改进二：层次化知识树 + LLM推理导航

## 当前问题

`index.json` 是平的：`category → [module1, module2, module3]`。查询"第三章那个配置参数"时，现有搜索只能做关键词匹配，无法理解"第三章"这个位置约束。

PageIndex 的核心创新就是用 LLM 做**树上推理**：先看目录定位章节，再沿树向下找到具体段落。knowledge-manager 需要同样甚至更强的能力。

## 数据模型

在 `index.json` 中与 `categories` 并存：

```json
{
  "version": "1.0",
  "categories": { "..." },
  "graph": { "..." },
  "tree": {
    "id": "root",
    "type": "root",
    "title": "Knowledge Base",
    "summary": "",
    "children": [
      {
        "id": "auth",
        "type": "category",
        "title": "认证与授权",
        "summary": "用户身份验证和权限管理的所有决策与实现",
        "path": "auth",
        "children": [
          {
            "id": "auth/jwt-config",
            "type": "module",
            "title": "JWT配置",
            "summary": "过期时间24h, RS256签名",
            "path": "auth/jwt-config",
            "page_range": [1, 3],     // 对应来源文档的页码范围
            "children": [
              {
                "id": "auth/jwt-config#signing",
                "type": "section",
                "title": "签名算法选择",
                "summary": "为什么选RS256而不是HS256",
                "path": "auth/jwt-config#signing",
                "children": []
              }
            ]
          },
          {
            "id": "auth/oauth-flow",
            "type": "module",
            "title": "OAuth2.0流程",
            "summary": "授权码模式 + PKCE",
            "path": "auth/oauth-flow",
            "children": []
          }
        ]
      },
      {
        "id": "deployment",
        "type": "category",
        "title": "部署与运维",
        "children": [...]
      }
    ]
  }
}
```

### Schema (schemas.py 新增)

```python
class TreeNodeType(str, Enum):
    ROOT = "root"
    CATEGORY = "category"
    MODULE = "module"
    SECTION = "section"

class TreeNode(BaseModel):
    id: str
    type: TreeNodeType
    title: str
    summary: str = ""
    path: str = ""          # 完整路径: "auth/jwt-config#signing"
    page_range: Optional[tuple[int, int]] = None
    children: list["TreeNode"] = Field(default_factory=list)
    # 元信息
    module_count: int = 0   # 子树中的模块总数 (非module节点)
    word_count: int = 0     # 子树中的总词数 (非module节点)
    # module/section 特有
    confidence: Optional[str] = None
    status: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
```

## 树的三种构建方式

### 方式A：从 Markdown 标题提取

```python
# src/knowledge_manager/tree_builder.py (新文件)

def build_tree_from_markdown(md_text: str, category: str) -> TreeNode:
    """
    解析 Markdown 标题层级:

    # 认证与授权          → category 节点
    ## JWT配置            → module 节点
    ### 签名算法选择      → section 节点 (挂在 module 下)
    ### 过期策略          → section 节点
    ## OAuth2.0流程       → module 节点

    规则:
    - # (H1) = category
    - ## (H2) = module
    - ### (H3) 及更深 = section
    - 同级的 module 按出现顺序排列
    """
    lines = md_text.split('\n')
    root = TreeNode(id="root", type=TreeNodeType.ROOT, title="Root")
    stack = [(0, root)]  # (heading_level, node)

    current_module = None

    for line in lines:
        match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if not match:
            continue

        level = len(match.group(1))
        title = match.group(2).strip()
        node_id = slugify(title)

        # 弹出所有不比当前层级更深的节点
        while stack and stack[-1][0] >= level:
            stack.pop()

        parent = stack[-1][1]

        if level == 1:
            # H1 = category
            node = TreeNode(
                id=node_id,
                type=TreeNodeType.CATEGORY,
                title=title,
                path=node_id,
            )
            parent.children.append(node)
            stack.append((level, node))
            current_module = None

        elif level == 2:
            # H2 = module
            node = TreeNode(
                id=node_id,
                type=TreeNodeType.MODULE,
                title=title,
                path=f"{parent.path}/{node_id}",
            )
            parent.children.append(node)
            stack.append((level, node))
            current_module = node

        else:
            # H3+ = section, 挂在最近的 module 下
            if current_module:
                node = TreeNode(
                    id=f"{current_module.id}#{node_id}",
                    type=TreeNodeType.SECTION,
                    title=title,
                    path=f"{current_module.path}#{node_id}",
                )
                current_module.children.append(node)
                stack.append((level, node))

    return root

def slugify(title: str) -> str:
    """中文标题 → kebab-case id"""
    # 中英混合 → 拼音化 + slug
    ...
```

### 方式B：LLM 自动构建

```python
async def build_tree_from_llm(
    modules: list[Module],
    llm_client,
) -> TreeNode:
    """
    将现有扁平模块列表交给LLM, 让其构建合理的树状分组:

    提示词大致内容:
    - 输入: 所有模块的 [category, id, title, summary, tags, related_modules]
    - 任务: 将这些模块组织成一个层级树
    - 规则:
        - 根节点下是领域分组 (如 auth, deployment, backend)
        - 每个分组下按主题逻辑排列模块
        - 紧密相关的模块 (互相引用) 应该放在同一子树
        - 有明确先后关系的模块 (如 "选择" → "实现" → "优化") 标注顺序
    - 输出: JSON格式的树结构

    这个方法适用于知识库已经有很多模块, 需要重新组织结构的情况。
    """
    ...
```

### 方式C：手动拖拽 (在 Web UI 中)

在 Web UI 的 KnowledgeTree 组件中支持拖拽：
- 模块在树中拖动到不同位置
- 拖动到某个模块上方 = 创建"前置于"关系
- 拖动到某个模块下方 = 成为子节点
- 拖出树外 = 取消父子关系

每次拖拽通过 `PUT /api/tree` 持久化。

## LLM 推理导航

这是对标 PageIndex 核心能力的功能：

```python
# src/knowledge_manager/tree_navigator.py (新文件)

@dataclass
class NavigationStep:
    step: int
    action: str           # "explore" | "drill" | "load" | "backtrack" | "done"
    node_id: str
    node_title: str
    reasoning: str        # LLM 的推理: "用户提到了签名算法, auth分支更可能包含..."
    candidates: list[str] # 当前层级考虑的节点

@dataclass
class NavigationResult:
    query: str
    path: list[NavigationStep]
    final_module: Optional[Module]
    alternatives: list[Module]
    confidence: float

class TreeNavigator:
    """LLM在知识树上的多步推理导航"""

    NAVIGATION_SYSTEM_PROMPT = """\
你是一个知识库导航助手。你的任务是在知识树上找到最能回答用户问题的模块。

知识树结构:
{tree_snapshot}

导航规则:
1. 从根节点开始, 每次选择最相关的子节点深入
2. 如果当前层级没有明显匹配, 列出所有子节点并请求用户澄清
3. 如果到达叶子模块, 判断它是否足以回答问题
4. 如果叶子模块不够, 回溯到上一级尝试其他分支
5. 最多导航 {max_steps} 步

当前导航状态:
{current_state}

用户问题: {query}

请按以下格式做出下一步决策:
{{
  "action": "explore|drill|load|backtrack|done",
  "target_node": "node-id",
  "reasoning": "为什么选择这个节点",
  "confidence": 0.0-1.0
}}
"""

    async def navigate(
        self,
        query: str,
        max_steps: int = 5,
    ) -> NavigationResult:
        steps: list[NavigationStep] = []
        current_node = self.tree_root
        visited: set[str] = set()

        for step_num in range(1, max_steps + 1):
            # 获取当前节点的上下文 (子节点列表 + 摘要)
            tree_snapshot = self._render_tree_snapshot(current_node, depth=2)
            current_state = self._render_navigation_state(steps, current_node, visited)

            # 让LLM决定下一步
            prompt = self.NAVIGATION_SYSTEM_PROMPT.format(
                tree_snapshot=tree_snapshot,
                current_state=current_state,
                query=query,
                max_steps=max_steps,
            )

            response = await self.llm.complete_json(prompt)

            action = response["action"]
            target_id = response.get("target_node")
            reasoning = response["reasoning"]

            step = NavigationStep(
                step=step_num,
                action=action,
                node_id=target_id or current_node.id,
                node_title=current_node.title,
                reasoning=reasoning,
                candidates=[c.title for c in current_node.children],
            )
            steps.append(step)

            if action == "done":
                # 当前节点就是答案
                final_module = self._load_module_for_node(current_node)
                return NavigationResult(
                    query=query,
                    path=steps,
                    final_module=final_module,
                    alternatives=self._find_alternatives(current_node),
                    confidence=response.get("confidence", 0.5),
                )

            elif action == "drill":
                # 深入子节点
                child = self._find_child(current_node, target_id)
                if child is None:
                    # LLM选择了不存在的节点, 让它重试
                    continue
                visited.add(current_node.id)
                current_node = child

            elif action == "backtrack":
                # 回退到父节点
                parent = self._find_parent(current_node)
                if parent is None:
                    break
                current_node = parent

            elif action == "explore":
                # 在当前层级探索其他子节点
                pass  # 下一轮LLM会看到更广的树快照

            elif action == "load":
                # 明确加载某个模块
                target_node = self._find_node(target_id)
                if target_node and target_node.type == TreeNodeType.MODULE:
                    final_module = self._load_module_for_node(target_node)
                    return NavigationResult(
                        query=query,
                        path=steps,
                        final_module=final_module,
                        alternatives=[],
                        confidence=response.get("confidence", 0.5),
                    )

        # 超过最大步数, 返回当前找到的最佳候选
        best = self._best_candidate(current_node, query)
        return NavigationResult(
            query=query,
            path=steps,
            final_module=best,
            alternatives=self._find_alternatives(current_node),
            confidence=0.3,
        )

    def _render_tree_snapshot(self, node: TreeNode, depth: int) -> str:
        """将树的当前层级渲染为LLM可读的文本"""
        lines = []
        self._render_node_recursive(node, depth, 0, lines)
        return '\n'.join(lines)

    def _render_node_recursive(self, node: TreeNode, max_depth: int, current_depth: int, lines: list[str]):
        indent = "  " * current_depth
        type_icon = {"root": "📁", "category": "📂", "module": "📄", "section": "§"}
        icon = type_icon.get(node.type, "•")

        lines.append(f"{indent}{icon} [{node.id}] {node.title}")
        if node.summary:
            lines.append(f"{indent}   {node.summary[:80]}")

        if current_depth < max_depth:
            for child in node.children:
                self._render_node_recursive(child, max_depth, current_depth + 1, lines)
```

## 与搜索的融合

```
用户查询 "JWT过期时间是多少?"
       ↓
并行执行:
  ┌─ TreeNavigator.navigate()
  │   根 → auth (explore)
  │   auth → auth/jwt-config (drill)
  │   auth/jwt-config → [leaf] (done)
  │   返回: NavigationResult (final_module, path, confidence=0.92)
  │
  └─ search_modules("JWT 过期 时间")
      返回: [auth/jwt-config: 0.95, auth/token-rotation: 0.72, ...]
       ↓
RRF融合 → 最终排序 → LLM生成答案
```

树推理提供了位置感知（"JWT过期时间在jwt-config模块中"），关键词搜索提供了覆盖面（"token-rotation模块也提到了过期"），两者通过RRF融合。

---

# 大改进三：自动研究补全 (Research-on-Miss)

## 当前行为 vs 目标行为

**当前：**
```
用户查询 → search_modules → 无结果 → 返回 [] → 用户只能自己去查资料
```

**目标：**
```
用户查询 → search_modules → 无结果/低置信度
  →
  自动触发研究流水线:
  1. 分析查询 → 确定需要什么类型的知识
  2. 从配置的研究源搜索 (代码仓库/docs/web)
  3. LLM阅读多源内容, 提取结构化知识
  4. 写入 .staging/ → 通知用户审核
  5. 返回临时答案 (标注"未审核")
  →
  用户下次 km review 时看到草稿, 可批准/拒绝/修改
```

## 数据模型

```python
# schemas.py 新增

class ResearchSource(BaseModel):
    """单个研究源配置"""
    type: Literal["code_repo", "doc_dir", "web_search", "api"]
    path: str = ""                          # 本地路径 或 URL
    include_patterns: list[str] = Field(default_factory=list)   # ["*.py", "*.md"]
    exclude_patterns: list[str] = Field(default_factory=list)   # ["*test*"]
    category_hint: str = ""                 # 提取到的模块应归入哪个分类

class ResearchConfig(BaseModel):
    enabled: bool = True
    auto_approve_threshold: float = 0.85    # 置信度超过此值可自动批准
    sources: list[ResearchSource] = Field(default_factory=list)
    default_depth: Literal["shallow", "deep"] = "shallow"
    max_llm_calls_per_query: int = 8
    max_total_tokens_per_query: int = 32000

class ResearchEvent(BaseModel):
    """记录一次研究活动"""
    id: str
    query: str
    triggered_by: str = ""                  # "search_miss" | "user_request"
    depth: str = "shallow"
    sources_searched: list[str] = Field(default_factory=list)
    modules_generated: list[str] = Field(default_factory=list)
    llm_calls: int = 0
    total_tokens: int = 0
    took_ms: int = 0
    status: str = "completed"               # "in_progress" | "completed" | "failed"
    error: str = ""
    created_at: datetime = Field(default_factory=utc_now)
```

## 研究流水线

```python
# src/knowledge_manager/researcher.py (新文件)

@dataclass
class ResearchProgress:
    stage: str
    message: str
    detail: dict

class Researcher:
    """自动研究引擎"""

    def __init__(self, kb_path: Path, config: ResearchConfig, llm_client, storage):
        self.kb_path = kb_path
        self.config = config
        self.llm = llm_client
        self.storage = storage

    async def research(
        self,
        query: str,
        depth: str = None,
        on_progress: Callable[[ResearchProgress], None] = None,
    ) -> ResearchResult:
        """
        主研究流程:

        1. 查询分解 (Query Decomposition)
        2. 源选择 (Source Selection)
        3. 并行搜索 (Parallel Search)
        4. 内容综合 (Content Synthesis)
        5. 模块提取 (Module Extraction)
        6. 暂存与通知 (Staging & Notification)
        """
        depth = depth or self.config.default_depth
        took_start = time.time()
        llm_calls = 0

        # ── Step 1: 查询分解 ──
        if on_progress:
            on_progress(ResearchProgress("decompose", "分析查询...", {}))

        sub_queries = await self._decompose_query(query)
        # "微服务间用什么协议通信？" →
        #   ["gRPC 服务间通信协议",
        #    "消息队列 RabbitMQ Kafka 技术选型",
        #    "REST vs gRPC 内部服务通信"]

        # ── Step 2: 源选择 ──
        if on_progress:
            on_progress(ResearchProgress("select_sources", f"选择研究源 (共{len(self.config.sources)}个)...", {}))

        # 每个子查询匹配最相关的研究源
        source_assignments = self._assign_sources(sub_queries, self.config.sources)
        # {
        #   "gRPC 服务间通信协议": [code_repo: "../backend", doc_dir: "../docs"],
        #   "消息队列...": [doc_dir: "../rfcs"],
        #   "REST vs gRPC...": [code_repo: "../backend", web_search: "docs.internal.com"],
        # }

        # ── Step 3: 并行搜索 ──
        if on_progress:
            on_progress(ResearchProgress("searching", "搜索多源...", {"sources": len(source_assignments)}))

        search_tasks = []
        for sub_q, sources in source_assignments.items():
            for source in sources:
                search_tasks.append(self._search_source(sub_q, source))

        # 限制并行数以避免资源过载
        all_results: list[SourceResult] = []
        for batch in chunked(search_tasks, 5):
            batch_results = await asyncio.gather(*batch, return_exceptions=True)
            for r in batch_results:
                if not isinstance(r, Exception):
                    all_results.append(r)

        # ── Step 4: 内容综合 ──
        if on_progress:
            on_progress(ResearchProgress("synthesizing", f"综合 {len(all_results)} 个来源...", {}))

        synthesis = await self._synthesize(query, all_results, depth)
        llm_calls += 1

        # ── Step 5: 模块提取 ──
        if on_progress:
            on_progress(ResearchProgress("extracting", "提取结构化模块...", {}))

        # 复用现有 Extractor, 输入为综合后的文本
        extractor = Extractor(self.llm, self.storage.config.extraction)
        modules = await extractor.extract(
            text=synthesis,
            category=self._infer_category(query, all_results),
            existing_categories=self._existing_categories(),
        )
        llm_calls += len(modules)  # 粗略估计

        # ── Step 6: 暂存 ──
        if on_progress:
            on_progress(ResearchProgress("staging", f"暂存 {len(modules)} 个模块...", {}))

        staged_ids = []
        for mod in modules:
            # 标注来源
            mod.metadata.source = f"research-on-miss: {', '.join(r.source_label for r in all_results)}"
            # 降低初始置信度 (等待人工审核)
            if mod.metadata.confidence == "high":
                mod.metadata.confidence = "medium"
            # 写入 .staging/
            self.storage.save_to_staging(mod, self.kb_path)
            staged_ids.append(f"{mod.category}/{mod.id}")

        # ── 统计 ──
        took_ms = int((time.time() - took_start) * 1000)

        # 记录研究事件
        event = ResearchEvent(
            id=str(uuid.uuid4()),
            query=query,
            depth=depth,
            sources_searched=[r.source_label for r in all_results],
            modules_generated=staged_ids,
            llm_calls=llm_calls,
            total_tokens=...,  # 从 llm_client 获取
            took_ms=took_ms,
        )
        self._record_event(event)

        return ResearchResult(
            query=query,
            modules=modules,
            staged_ids=staged_ids,
            sources_used=[r.source_label for r in all_results],
            took_ms=took_ms,
            answer_synthesis=synthesis[:500],  # 摘要用于即时回复
        )

    async def _search_source(self, query: str, source: ResearchSource) -> SourceResult:
        """对单个研究源执行搜索"""
        if source.type == "code_repo":
            return await self._search_code_repo(query, source)
        elif source.type == "doc_dir":
            return await self._search_doc_dir(query, source)
        elif source.type == "web_search":
            return await self._search_web(query, source)
        elif source.type == "api":
            return await self._search_api(query, source)

    async def _search_code_repo(self, query: str, source: ResearchSource) -> SourceResult:
        """
        代码仓库搜索策略:

        1. grep 关键代码模式 (函数定义, 配置常量, import 语句)
        2. 读取匹配文件的上下文 (前后50行)
        3. 优先读取 README.md, ARCHITECTURE.md, DESIGN.md
        4. 排除 vendor/, node_modules/, __pycache__/
        """
        repo_path = Path(source.path)
        results = []

        # 关键词提取: LLM从查询中提取代码搜索关键词
        code_keywords = await self._extract_code_keywords(query)
        # "gRPC 服务间通信" → ["grpc", "protobuf", "stub", "channel"]

        for kw in code_keywords[:5]:  # 限制关键词数量
            # 使用 ripgrep (或 subprocess + grep)
            try:
                output = subprocess.run(
                    ["rg", "-l", "-i", kw, str(repo_path),
                     "--glob=!vendor/**", "--glob=!node_modules/**",
                     "--glob=!__pycache__/**", "--glob=!.git/**"],
                    capture_output=True, text=True, timeout=10,
                )
                for file_path in output.stdout.strip().split('\n')[:3]:  # 最多3个文件
                    if file_path:
                        content = Path(file_path).read_text()[:2000]  # 最多2000字符
                        results.append(SourceChunk(
                            source_label=f"code:{source.path}",
                            file_path=file_path,
                            content=content,
                            relevance=self._quick_relevance(content, kw),
                        ))
            except Exception:
                continue

        return SourceResult(
            source_label=f"code_repo:{source.path}",
            chunks=results,
            total_found=len(results),
        )

    async def _search_doc_dir(self, query: str, source: ResearchSource) -> SourceResult:
        """
        文档目录搜索策略:

        1. 文件名匹配 (fuzzy match)
        2. 文件内容关键词搜索
        3. 优先匹配 .md, .txt, .rst 文件
        """
        ...

    async def _search_web(self, query: str, source: ResearchSource) -> SourceResult:
        """
        Web搜索策略 (需要用户显式开启):

        1. 仅搜索 allowed_domains 内的内容
        2. 使用内部搜索引擎或 API
        3. 不做公开互联网搜索 (安全边界)
        """
        ...

    async def _synthesize(self, query: str, results: list[SourceResult], depth: str) -> str:
        """
        LLM 综合多源内容:

        浅层 (shallow):
          - 选出相关度最高的 3 个 chunks
          - LLM 写一个综合摘要 (不超过 2000 字)

        深层 (deep):
          - 选出相关度最高的 10 个 chunks
          - LLM 先分组 (按子主题)
          - 每组内综合
          - 最后跨组综合 (不超过 5000 字)
          - 标注信息冲突 (如果不同源给不同答案)
        """
        if depth == "shallow":
            top_chunks = sorted(results, key=lambda r: max(c.relevance for c in r.chunks), reverse=True)
            combined = "\n---\n".join(
                f"来源: {c.file_path}\n{c.content[:1000]}"
                for chunk_group in top_chunks[:3]
                for c in chunk_group.chunks[:1]
            )
            prompt = f"""\
根据以下来源回答用户问题。如果来源不足以回答, 明确指出。不编造。

用户问题: {query}

来源:
{combined}

请用中文回答 (不超过 500 字), 标注每个信息的来源。
如果不同来源有冲突, 明确指出。
"""
            return await self.llm.complete(prompt)

        else:
            # deep: 多轮综合
            ...
```

## MCP Server 集成

```python
# mcp_server.py 新增 tool

@mcp.tool(name="research")
def research_tool(query: str, depth: str = "shallow") -> str:
    """当知识库中没有相关知识时, 自动研究并生成草稿模块。

    Args:
        query: 研究问题
        depth: "shallow" (快速, 3源以内) 或 "deep" (全面, 多轮综合)

    Returns:
        研究结果, 包含临时答案和生成的草稿模块列表
    """
    researcher = Researcher(kb_path, research_config, llm_client, storage)
    result = asyncio.run(researcher.research(query, depth))
    return json.dumps({
        "query": result.query,
        "temporary_answer": result.answer_synthesis,
        "staged_modules": result.staged_ids,
        "sources_used": result.sources_used,
        "took_ms": result.took_ms,
        "hint": f"使用 km review 审核草稿模块: {', '.join(result.staged_ids)}",
    }, indent=2)
```

## 安全边界

```python
# 研究引擎的安全约束

class ResearchSafety:
    """研究引擎的安全边界"""

    MAX_SOURCE_SIZE = 50_000      # 单个源最多读取50KB
    MAX_TOTAL_SOURCES = 10        # 单次研究最多10个源
    MAX_OUTPUT_TOKENS = 5000      # 综合输出最多5000 tokens
    MAX_RESEARCH_TIME_MS = 60000  # 单次研究超时60秒
    FORBIDDEN_PATHS = [           # 禁止访问的路径
        "/etc/", "/proc/", "/sys/",
        "~/.ssh/", "~/.aws/", "~/.config/",
        "*.env", "*.key", "*.pem",
    ]

    @classmethod
    def validate_source(cls, source: ResearchSource) -> None:
        """验证研究源是否在安全边界内"""
        if source.type in ("code_repo", "doc_dir"):
            path = Path(source.path).expanduser().resolve()
            for forbidden in cls.FORBIDDEN_PATHS:
                if fnmatch(str(path), forbidden):
                    raise ValueError(f"Source path {path} is forbidden: matches {forbidden}")

        if source.type == "web_search":
            assert source.allowed_domains, "Web search requires allowed_domains"
```

---

# 大改进四：Markdown 一等公民 + Obsidian 双向同步

## 目标架构

```
my_kb/
├── index.json
├── config.json
├── .staging/
├── auth/
│   ├── jwt-config.json      # JSON (现有格式, 系统主存储)
│   ├── jwt-config.md        # Markdown (人类编辑格式)
│   ├── oauth-flow.json
│   └── oauth-flow.md
└── deployment/
    ├── k8s-config.json
    └── k8s-config.md

JSON ←→ MD 双向同步:
- save_module() → 同时写 JSON 和 MD
- km rebuild → 比较时间戳, 以较新的为准, 自动同步另一方
- JSON 是系统权威格式 (用于搜索索引, MCP, API)
- MD 是人类编辑格式 (用于 Obsidian, $EDITOR, Web UI)
```

## Markdown 格式规范

```markdown
---
id: jwt-config
category: auth
title: JWT Token 配置
summary: 我们使用RS256非对称签名的JWT，Access Token过期时间24小时，Refresh Token 7天
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

我们选择 [[RS256]] 而非 HS256 作为JWT签名算法。核心原因：在微服务架构下，
多个服务需要独立验证JWT签名，但不能共享对称密钥。

## 决策背景

2025年Q2从单体迁移到微服务时，我们面临JWT签名方案的选择：

| 方案 | 优点 | 缺点 | 我们的评估 |
|------|------|------|-----------|
| HS256 | 简单, 速度快 | 需要共享密钥, 安全风险 | ❌ 不适用于多服务 |
| RS256 | 非对称, 公钥可分发 | 签名速度慢 ~10x | ✅ 安全优先 |
| EdDSA | 更快更安全 | 库支持不成熟 | ⏳ 未来考虑 |

详见 [[auth/oauth-flow]]

# 实现细节

## Token 结构

\`\`\`json
{
  "sub": "user_123",
  "iat": 1717200000,
  "exp": 1717286400,
  "scope": ["read", "write"],
  "jti": "unique-token-id"
}
\`\`\`

## 关键配置

\`\`\`python
# settings.py
JWT_ALGORITHM = "RS256"
JWT_ACCESS_TOKEN_EXPIRE_HOURS = 24
JWT_REFRESH_TOKEN_EXPIRE_DAYS = 7
JWT_KEY_PATH = "/etc/secrets/jwt-private.pem"
JWKS_ENDPOINT = "https://api.example.com/.well-known/jwks.json"
\`\`\`

## 黑名单机制

使用 Redis 管理已撤销的 Token, key 格式为 `bl:jti:{jti}`,
TTL 与 token 剩余有效期一致。详见 [[deployment/redis-config]]

# 注意事项

- **性能**: RS256签名比HS256慢约10x, 不要在热路径频繁生成token。
  登录时生成一次, 后续用refresh token续期。
- **JWKS缓存**: JWKS端点需要CDN缓存 (TTL: 1小时),
  否则每次token验证都请求JWKS会显著增加延迟。
- **密钥轮换**: 私钥每年轮换一次, 轮换期间同时发布新旧两个公钥到JWKS。
- **调试陷阱**: 本地开发时如果遇到 "Invalid token" 错误,
  检查系统时间是否同步 (JWT的 `iat` 验证需要时钟偏差 < 30秒)。
```

### YAML Frontmatter 与 Module Schema 的映射

```python
# src/knowledge_manager/markdown.py (新文件)

FRONTMATTER_TO_SCHEMA = {
    # frontmatter_key → (schema_field, type_converter)
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
    # Markdown H1 → Module.content field
    "概述":     "overview",
    "# 概述":   "overview",
    "细节":     "details",
    "# 细节":   "details",
    "# 实现细节": "details",
    "示例":     "examples",
    "例子":     "examples",
    "# 示例":   "examples",
    "参考":     "references",
    "# 参考":   "references",
    "注意事项": "caveats",
    "陷阱":     "caveats",
    "# 注意事项": "caveats",
}

def parse_markdown_module(md_text: str) -> Module:
    """Markdown → Module 解析"""

    # 1. 提取 YAML frontmatter
    fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', md_text, re.DOTALL)
    if not fm_match:
        raise ValueError("No YAML frontmatter found")

    frontmatter = yaml.safe_load(fm_match.group(1))
    body = md_text[fm_match.end():]

    # 2. 解析 frontmatter → Module 字段
    module_data = {}
    for fm_key, (schema_path, converter) in FRONTMATTER_TO_SCHEMA.items():
        if fm_key in frontmatter:
            value = frontmatter[fm_key]
            # nested schema path: "metadata.tags" → set in nested dict
            _set_nested(module_data, schema_path, converter(value))

    # 3. 解析 body → ModuleContent
    content_data = {
        "overview": "",
        "details": "",
        "examples": "",
        "references": "",
        "caveats": "",
    }
    current_section = "overview"  # 默认
    current_text: list[str] = []

    for line in body.split('\n'):
        h_match = re.match(r'^(#{1,3})\s+(.+)$', line)
        if h_match:
            # 保存上一个 section
            if current_text:
                content_data[current_section] = '\n'.join(current_text).strip()
                current_text = []

            heading = h_match.group(2).strip()
            # 映射标题到 content field
            section_found = None
            for pattern, field in MD_SECTION_TO_CONTENT.items():
                if pattern.lstrip('#').strip().lower() == heading.lower():
                    section_found = field
                    break
            if section_found:
                current_section = section_found
            continue

        current_text.append(line)

    # 保存最后一个 section
    if current_text:
        content_data[current_section] = '\n'.join(current_text).strip()

    # 4. 构建 Module
    module_data["content"] = ModuleContent(**content_data)
    if "metadata" in module_data:
        module_data["metadata"] = ModuleMetadata(**module_data["metadata"])
    return Module(**module_data)


def render_markdown_module(module: Module) -> str:
    """Module → Markdown 渲染"""

    # 1. Frontmatter
    fm = {
        "id": module.id,
        "category": module.category,
        "title": module.title,
        "summary": module.summary,
        "tags": module.metadata.tags,
        "confidence": module.metadata.confidence,
        "status": module.metadata.status,
        "source": module.metadata.source,
        "expires_at": module.metadata.expires_at.isoformat() if module.metadata.expires_at else None,
        "review_interval_days": module.metadata.review_interval_days,
        "related_modules": module.metadata.related_modules,
        "created_at": module.created_at.isoformat(),
        "updated_at": module.updated_at.isoformat(),
    }
    # 过滤 None 值
    fm = {k: v for k, v in fm.items() if v is not None and v != [] and v != ""}

    fm_yaml = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # 2. Body
    sections = []
    field_to_heading = [
        ("overview", "# 概述"),
        ("details", "# 细节"),
        ("examples", "# 示例"),
        ("references", "# 参考"),
        ("caveats", "# 注意事项"),
    ]
    for field, heading in field_to_heading:
        text = getattr(module.content, field, "")
        if text:
            sections.append(f"{heading}\n\n{text}\n")

    body = '\n'.join(sections)

    return f"---\n{fm_yaml}---\n\n{body}"
```

## `[[wikilinks]]` 解析器

```python
# src/knowledge_manager/wikilinks.py (新文件)

WIKILINK_PATTERN = re.compile(r'\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]')

@dataclass
class Wikilink:
    target: str          # "auth/oauth-flow" 或 "RS256"
    display_text: str    # "OAuth流程" 或 None (用target显示)
    resolved: bool = False
    resolved_path: str = ""  # 解析后的完整路径: "auth/oauth-flow"

def parse_wikilinks(text: str) -> list[Wikilink]:
    """从文本中提取所有 [[wikilinks]]"""
    links = []
    for match in WIKILINK_PATTERN.finditer(text):
        links.append(Wikilink(
            target=match.group(1).strip(),
            display_text=match.group(2).strip() if match.group(2) else None,
        ))
    return links

def resolve_wikilinks(
    links: list[Wikilink],
    kb_path: Path,
) -> list[Wikilink]:
    """解析 wikilinks 到具体的模块路径

    解析策略:
    1. 精确匹配: "auth/oauth-flow" → "auth/oauth-flow"
    2. ID搜索: "oauth-flow" → 搜索所有模块, 找 id="oauth-flow"
    3. 标题搜索: "OAuth流程" → 搜索所有模块, 找 title 匹配
    4. 模糊匹配: "RS256" → 搜索内容中包含 RS256 的模块, 取最相关的
    """
    index = load_index(kb_path)
    resolved = []

    for link in links:
        # 策略1: 精确路径
        if '/' in link.target:
            parts = link.target.split('/', 1)
            if parts[0] in index.categories:
                for mod in index.categories[parts[0]].modules:
                    if mod.id == parts[1]:
                        link.resolved = True
                        link.resolved_path = link.target
                        resolved.append(link)
                        continue

        # 策略2: 按ID搜索
        found = False
        for cat_name, cat in index.categories.items():
            for mod in cat.modules:
                if mod.id == link.target:
                    link.resolved = True
                    link.resolved_path = f"{cat_name}/{mod.id}"
                    found = True
                    break
            if found:
                break

        if found:
            resolved.append(link)
            continue

        # 策略3: 按标题搜索 (小写比较)
        target_lower = link.target.lower()
        for cat_name, cat in index.categories.items():
            for mod in cat.modules:
                if mod.title.lower() == target_lower:
                    link.resolved = True
                    link.resolved_path = f"{cat_name}/{mod.id}"
                    found = True
                    break
            if found:
                break

        # 策略4: 未解析的链接保留原样
        link.resolved = False
        resolved.append(link)

    return resolved

def auto_update_related_modules(module: Module, kb_path: Path) -> Module:
    """从模块内容中提取 wikilinks, 自动更新 related_modules"""
    full_text = f"{module.content.overview}\n{module.content.details}\n{module.content.examples}\n{module.content.references}\n{module.content.caveats}"
    links = parse_wikilinks(full_text)
    resolved = resolve_wikilinks(links, kb_path)

    new_related = set(module.metadata.related_modules)
    for link in resolved:
        if link.resolved and link.resolved_path != f"{module.category}/{module.id}":
            new_related.add(link.resolved_path)

    module.metadata.related_modules = sorted(new_related)
    return module
```

## 双向同步机制

```python
# src/knowledge_manager/sync.py (新文件)

class MarkdownSync:
    """JSON ↔ Markdown 双向同步"""

    @staticmethod
    def sync_on_save(module: Module, kb_path: Path) -> None:
        """保存模块时同时写入 JSON 和 MD"""
        json_path = module.to_file_path(kb_path)
        md_path = json_path.with_suffix('.md')

        # 写入 JSON (现有逻辑)
        save_module_json(module, json_path)

        # 写入 Markdown (新增)
        md_content = render_markdown_module(module)
        md_path.write_text(md_content, encoding='utf-8')

    @staticmethod
    def sync_on_rebuild(kb_path: Path) -> list[SyncConflict]:
        """重建索引时检测 JSON/MD 不同步, 自动修复"""
        conflicts = []

        for json_path in kb_path.rglob("*.json"):
            if json_path.name in ("index.json", "config.json"):
                continue
            if json_path.parent.name.startswith('.'):
                continue

            md_path = json_path.with_suffix('.md')

            if not md_path.exists():
                # 只有 JSON, 生成 MD
                module = load_module_from_json(json_path)
                md_content = render_markdown_module(module)
                md_path.write_text(md_content, encoding='utf-8')
                continue

            if not json_path.exists():
                # 只有 MD, 生成 JSON
                md_content = md_path.read_text(encoding='utf-8')
                module = parse_markdown_module(md_content)
                save_module_json(module, json_path)
                continue

            # 两边都存在, 比较时间戳
            json_mtime = json_path.stat().st_mtime
            md_mtime = md_path.stat().st_mtime

            if abs(json_mtime - md_mtime) < 1.0:
                continue  # 时间戳接近, 视为同步

            if json_mtime > md_mtime:
                # JSON 更新 → 重新生成 MD
                module = load_module_from_json(json_path)
                md_content = render_markdown_module(module)
                md_path.write_text(md_content, encoding='utf-8')
            else:
                # MD 更新 → 重新生成 JSON
                md_content = md_path.read_text(encoding='utf-8')
                try:
                    module = parse_markdown_module(md_content)
                    save_module_json(module, json_path)
                except Exception as e:
                    conflicts.append(SyncConflict(
                        path=str(md_path),
                        error=str(e),
                        action_required="手动修复 Markdown 格式错误",
                    ))

        return conflicts

@dataclass
class SyncConflict:
    path: str
    error: str
    action_required: str
```

## Obsidian 导出

```bash
km export --obsidian ./my_obsidian_vault

# 生成:
my_obsidian_vault/
├── .obsidian/
│   ├── graph.json           # Graph View 颜色配置
│   ├── templates/
│   │   ├── module.md        # 新建模块模板
│   │   └── category.md     # 新建分类模板
│   └── dataview/
│       └── queries.md       # Dataview 查询示例
├── auth/
│   ├── jwt-config.md
│   ├── oauth-flow.md
│   └── api-keys.md
├── deployment/
│   └── k8s-config.md
├── _index.md                # 全局索引页 (Dataview 驱动的仪表盘)
├── _health.md               # 健康状态页
└── _graph.md                # 知识图谱入口
```

Obsidian Dataview 查询模板示例：

```markdown
# 全局知识索引

## 按分类

\`\`\`dataview
TABLE summary, confidence, status
FROM "auth"
SORT file.name ASC
\`\`\`

## 需要复习的模块

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
WHERE length(related_modules) = 0
  AND status = "published"
\`\`\`
```

---

# 大改进五：语义矛盾检测 (lint --deep)

## 不是字符串比较, 是语义理解

简单矛盾（结构化lint能发现） vs 深层矛盾（需要LLM理解）：

```
简单: 模块A字段X=24, 模块B字段X=1     ← grep能发现
深层: 模块A说"我们选的微服务",          ← 需要理解两段文字在讲同一件事
      模块B说"我们回归了单体"           但得出相反结论
```

## 检测维度

```python
class ContradictionType(str, Enum):
    FACT = "fact"                    # 事实数字/配置矛盾
    DECISION = "decision"            # 架构决策矛盾
    TIMELINE = "timeline"            # 时间线断裂 (A说已迁移, B说还在用旧的)
    TERMINOLOGY = "terminology"      # 同一事物不同名称
    STALE_REFERENCE = "stale_ref"   # 引用了已废弃/归档的模块

class Severity(str, Enum):
    ERROR = "error"      # 明确矛盾, 必须解决
    WARNING = "warning"  # 可能矛盾, 需要确认
    INFO = "info"        # 建议改进, 不影响正确性

class Contradiction(BaseModel):
    id: str
    type: ContradictionType
    severity: Severity
    modules: list[str]              # 涉及的模块 ["auth/jwt-config", "auth/oauth-flow"]
    description: str                # 人类可读的描述
    evidence: list[ContradictionEvidence]  # 具体证据
    suggestion: str                 # 修复建议
    auto_fixable: bool = False      # 是否可以自动修复
    auto_fix_description: str = ""  # 自动修复会做什么

class ContradictionEvidence(BaseModel):
    module_key: str
    field: str                      # "content.details"
    excerpt: str                    # 原文摘录 (矛盾点周围文字)
    claim: str                      # LLM提取的核心声明
```

## 检测流水线

```python
# src/knowledge_manager/linter.py (新文件)

class DeepLinter:
    """语义矛盾检测引擎"""

    # 候选对筛选规则
    PAIR_FILTERS = {
        "same_category": lambda a, b: a.category == b.category,
        "shared_tags": lambda a, b: bool(set(a.metadata.tags) & set(b.metadata.tags)),
        "mutual_reference": lambda a, b: (
            f"{b.category}/{b.id}" in a.metadata.related_modules or
            f"{a.category}/{a.id}" in b.metadata.related_modules
        ),
        "title_overlap_keywords": lambda a, b: _title_keyword_overlap(a, b) > 0.5,
    }

    # 矛盾检测的 LLM prompt
    CONTRADICTION_PROMPT = """\
你是一个知识库质量检查器。检查以下两个模块是否存在语义矛盾。

模块 A ({module_a_key}):
  标题: {module_a_title}
  摘要: {module_a_summary}
  内容概述: {module_a_overview}
  细节: {module_a_details}

模块 B ({module_b_key}):
  标题: {module_b_title}
  摘要: {module_b_summary}
  内容概述: {module_b_overview}
  细节: {module_b_details}

检测维度:
1. 事实矛盾: 两个模块对同一事物的数值、配置、状态描述不一致
2. 决策矛盾: 两个模块描述的架构/技术决策互相冲突
3. 时间线断裂: 一个模块说某件事已完成/已迁移, 另一个暗示仍在进行/使用旧方案
4. 术语不一致: 两个模块用不同名称指代同一事物
5. 废弃引用: 模块A引用了已废弃或归档的模块B

如果不是矛盾, 返回 {{"contradiction": false}}
如果是矛盾, 返回:
{{
  "contradiction": true,
  "type": "fact|decision|timeline|terminology|stale_ref",
  "severity": "error|warning|info",
  "description": "简洁描述矛盾之处 (中文, 1-2句)",
  "evidence_a": "模块A中的原文摘录",
  "evidence_b": "模块B中的原文摘录",
  "suggestion": "修复建议 (中文)",
  "auto_fixable": true/false,
  "auto_fix_description": "如果可以自动修复, 描述修复方式"
}}

注意:
- 如果两个模块描述的可能是不同场景/环境/时间段, 不一定是矛盾, 标记为 info
- 如果确定是矛盾, 标记为 error 或 warning
- 不要过度标记: "选择X"和"考虑过Y"不是矛盾, "选择X"和"选择了Y"才是
"""

    async def lint_all(self, kb_path: Path, mode: str = "deep") -> list[Contradiction]:
        """
        mode:
        - "quick": 只检查结构化规则 (同字段数值冲突、废弃引用)
        - "deep": 完整语义矛盾检测 (含LLM比较)
        """

        index = load_index(kb_path)
        all_modules = self._load_all_modules(kb_path)

        # ── Phase 1: 候选对筛选 ──
        # 不需要 O(n²) 比较, 用规则筛选出可能矛盾的模块对
        candidates = self._generate_candidates(all_modules)
        # 通常: 127个模块 → ~175对候选 (远小于 C(127,2) = 8001)

        # ── Phase 2: 结构化检查 (快速, 不需要LLM) ──
        structural_issues = self._structural_check(all_modules, index)

        # ── Phase 3: 语义检查 (需要LLM, 并行处理) ──
        if mode == "deep":
            semantic_issues = await self._semantic_check(candidates, kb_path)
        else:
            semantic_issues = []

        # ── Phase 4: 结果排序 ──
        all_issues = structural_issues + semantic_issues
        all_issues.sort(key=lambda c: (
            {"error": 0, "warning": 1, "info": 2}[c.severity],
            -len(c.modules),  # 影响更多模块的排前面
        ))

        return all_issues

    def _generate_candidates(self, modules: list[Module]) -> list[tuple[Module, Module]]:
        """生成候选比较对, 用规则剪枝"""
        pairs = set()

        for i, a in enumerate(modules):
            for j, b in enumerate(modules):
                if i >= j:
                    continue

                key = (f"{a.category}/{a.id}", f"{b.category}/{b.id}")

                # 只要满足任一规则, 就加入候选
                if (self.PAIR_FILTERS["same_category"](a, b) or
                    self.PAIR_FILTERS["shared_tags"](a, b) or
                    self.PAIR_FILTERS["mutual_reference"](a, b) or
                    self.PAIR_FILTERS["title_overlap_keywords"](a, b)):
                    pairs.add(key)

        # 还原为 module 对象
        module_map = {f"{m.category}/{m.id}": m for m in modules}
        return [
            (module_map[a_key], module_map[b_key])
            for a_key, b_key in pairs
            if a_key in module_map and b_key in module_map
        ]

    def _structural_check(self, modules: list[Module], index: Index) -> list[Contradiction]:
        """
        结构化检查 (不需要LLM, 快速):

        1. 废弃引用: module 的 related_modules 中包含已 archived/deprecated 的模块
        2. 断链: module 的 related_modules 中包含不存在的模块
        3. 过期模块: expires_at 已过但 status 仍是 published
        4. 孤立模块: 没有被任何模块引用, 也没有引用任何模块
        """
        issues = []

        # 构建状态映射
        module_status = {
            f"{m.category}/{m.id}": m.metadata.status
            for m in modules
        }

        for module in modules:
            module_key = f"{module.category}/{module.id}"

            for ref in module.metadata.related_modules:
                # 检查废弃引用
                if ref in module_status and module_status[ref] in ("deprecated", "archived"):
                    issues.append(Contradiction(
                        id=str(uuid.uuid4()),
                        type=ContradictionType.STALE_REFERENCE,
                        severity=Severity.WARNING,
                        modules=[module_key, ref],
                        description=f"模块引用了已{module_status[ref]}的模块: {ref}",
                        evidence=[
                            ContradictionEvidence(
                                module_key=module_key,
                                field="metadata.related_modules",
                                excerpt=ref,
                                claim=f"引用了 {ref}",
                            ),
                        ],
                        suggestion=f"更新引用或取消关联",
                        auto_fixable=True,
                        auto_fix_description=f"从 related_modules 中移除 {ref}",
                    ))

                # 检查断链
                if ref not in module_status:
                    issues.append(Contradiction(
                        id=str(uuid.uuid4()),
                        type=ContradictionType.STALE_REFERENCE,
                        severity=Severity.ERROR,
                        modules=[module_key],
                        description=f"引用了不存在的模块: {ref}",
                        evidence=[...],
                        suggestion="检查是否为拼写错误, 或创建对应模块",
                        auto_fixable=False,
                    ))

        return issues

    async def _semantic_check(
        self,
        candidates: list[tuple[Module, Module]],
        kb_path: Path,
    ) -> list[Contradiction]:
        """
        语义检查 (需要LLM)

        策略:
        - 每批 10 对, 并行发送给 LLM
        - 每对比较用一个独立的 prompt
        - 聚合所有结果
        """
        all_issues = []

        for batch in chunked(candidates, 10):
            tasks = []
            for mod_a, mod_b in batch:
                tasks.append(self._compare_pair(mod_a, mod_b))

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in batch_results:
                if isinstance(result, Contradiction):
                    all_issues.append(result)
                elif isinstance(result, Exception):
                    logger.warning(f"LLM contradiction check failed: {result}")

        return all_issues

    async def _compare_pair(self, a: Module, b: Module) -> Optional[Contradiction]:
        """LLM比较一对模块, 判断是否存在矛盾"""
        prompt = self.CONTRADICTION_PROMPT.format(
            module_a_key=f"{a.category}/{a.id}",
            module_a_title=a.title,
            module_a_summary=a.summary,
            module_a_overview=a.content.overview[:300],
            module_a_details=a.content.details[:500],
            module_b_key=f"{b.category}/{b.id}",
            module_b_title=b.title,
            module_b_summary=b.summary,
            module_b_overview=b.content.overview[:300],
            module_b_details=b.content.details[:500],
        )

        response = await self.llm.complete_json(prompt)

        if not response.get("contradiction"):
            return None

        return Contradiction(
            id=str(uuid.uuid4()),
            type=ContradictionType(response["type"]),
            severity=Severity(response["severity"]),
            modules=[f"{a.category}/{a.id}", f"{b.category}/{b.id}"],
            description=response["description"],
            evidence=[
                ContradictionEvidence(
                    module_key=f"{a.category}/{a.id}",
                    field="content",
                    excerpt=response.get("evidence_a", ""),
                    claim="",
                ),
                ContradictionEvidence(
                    module_key=f"{b.category}/{b.id}",
                    field="content",
                    excerpt=response.get("evidence_b", ""),
                    claim="",
                ),
            ],
            suggestion=response["suggestion"],
            auto_fixable=response.get("auto_fixable", False),
            auto_fix_description=response.get("auto_fix_description", ""),
        )
```

### CLI 输出设计

```bash
$ km lint
🔍 结构化检查... 发现 2 issues (0.3s)

$ km lint --deep
🔍 结构化检查... 发现 2 issues (0.3s)
🧠 语义分析... 比较 175 对候选模块... (估计 30s)

================================================================================
                        知识库质量报告
================================================================================

🔴 Errors (1)
───────────────────────────────────────────────────────────────────────────────
[E1] 断链引用
   📄 backend/api-gateway → ❌ deployment/eks-config (模块不存在)
   建议: 可能是 deployment/k8s-config 的拼写错误? (Levenshtein距离=2)

🟡 Warnings (2)
───────────────────────────────────────────────────────────────────────────────
[W1] 决策冲突 - 微服务 vs 单体
   📄 architecture/microservices: "我们选择微服务架构以提高团队独立性"
   📄 architecture/platform-evolution: "2026Q1决定回归模块化单体以降低运维成本"
   影响范围: 2个模块互相引用
   建议: 这两个模块描述的是不同时间点的决策。建议在 architecture/platform-evolution
         中明确说明"我们之前(2025)使用微服务, 2026Q1起逐步迁移到模块化单体"。
         并在 architecture/microservices 开头添加废弃声明。
   → 操作: [f]一键修复(添加交叉引用说明)  [e]手动编辑  [i]忽略

[W2] 废弃引用
   📄 auth/jwt-config → auth/old-session (已废弃)
   建议: 更新引用为 auth/session-management
   → 操作: [f]自动替换引用  [i]忽略

🔵 Info (1)
───────────────────────────────────────────────────────────────────────────────
[I1] 术语不一致
   📄 auth/oauth-flow: "OAuth服务"
   📄 backend/api-gateway: "Auth0"
   📄 deployment/service-map: "认证平台"
   这三个模块可能指向同一服务
   建议: 统一术语, 推荐使用 "Auth0 (OAuth认证服务)"

================================================================================
总计: 1 error, 2 warnings, 1 info
完整报告已保存到 .lint/lint-report-2026-06-09.json
```

---

# 大改进六：间隔重复记忆系统 (FSRS)

## 设计理念

知识库的终极价值——不是被LLM检索到, 而是被**团队成员内化**。如果每个人都不知道库里有什么, 每次遇到问题都要重新搜索, 那知识库只是"外部存储", 不是"第二大脑"。

间隔重复把关键知识从"库里有"变成"脑子里有"。

## 数据模型

```python
# schemas.py 新增

class ReviewGrade(int, Enum):
    AGAIN = 1    # 完全忘记
    HARD = 2     # 回忆起部分, 很困难
    GOOD = 3     # 正确回忆, 有些犹豫
    EASY = 4     # 轻松正确回忆

class MemoryCard(BaseModel):
    id: str
    module_key: str        # "auth/jwt-config"
    module_title: str
    category: str
    # 卡片内容
    front: str             # 问题/提示
    back: str              # 答案/内容
    source_field: str      # 从模块的哪个字段生成: "content.details"
    # FSRS 状态
    fsrs_state: dict = Field(default_factory=dict)
    # {
    #   "stability": 0.0,       # 记忆稳定性 (天)
    #   "difficulty": 0.0,      # 卡片难度 (0-1)
    #   "elapsed_days": 0,      # 自上次复习以来的天数
    #   "scheduled_days": 0,    # 计划的下次复习间隔
    #   "reps": 0,              # 总复习次数
    #   "lapses": 0,            # 遗忘次数
    #   "last_review": null,    # 上次复习日期
    #   "due": null,            # 下次到期日期
    # }
    # 元数据
    created_at: datetime = Field(default_factory=utc_now)
    last_review_at: Optional[datetime] = None
    next_review_at: Optional[datetime] = None
    review_count: int = 0
    total_grade_sum: int = 0    # 用于计算平均掌握度

class MemoryStats(BaseModel):
    total_cards: int = 0
    due_today: int = 0
    due_this_week: int = 0
    avg_retention: float = 0.0    # 预测的90天记忆保留率
    streak_days: int = 0          # 连续复习天数
    total_reviews: int = 0
    cards_by_category: dict[str, int] = Field(default_factory=dict)
```

## 卡片自动生成

```python
# src/knowledge_manager/memory.py (新文件)

CARD_GENERATION_PROMPT = """\
根据以下知识模块, 生成一张间隔重复记忆卡片。

模块标题: {title}
模块分类: {category}
模块摘要: {summary}

模块内容:
{content}

生成规则:
1. 卡片正面 = 一个问题或提示, 能够检验读者是否真正理解了这个知识
   - 不是简单的"XX是什么?", 而是场景化的问题
   - 例如: "如果我们需要支持多服务验证JWT但不共享密钥, 应该选什么签名算法? 为什么?"
2. 卡片背面 = 简洁准确的答案 (不超过150字)
3. 一张卡片只覆盖一个知识点, 如果模块内容多, 只选最核心的一个
4. 聚焦于"我们团队的做法和原因", 不是通用理论

返回JSON:
{{
  "front": "问题 (中文)",
  "back": "答案 (中文, ≤150字)",
  "source_field": "content.details|content.overview|content.caveats"
}}
"""

async def generate_cards_for_module(
    module: Module,
    llm_client,
    max_cards: int = 3,
) -> list[MemoryCard]:
    """为一个模块生成记忆卡片"""

    prompt = CARD_GENERATION_PROMPT.format(
        title=module.title,
        category=module.category,
        summary=module.summary,
        content=f"概述: {module.content.overview}\n细节: {module.content.details}\n注意事项: {module.content.caveats}",
    )

    cards = []
    for i in range(max_cards):
        response = await llm_client.complete_json(prompt)
        card = MemoryCard(
            id=f"{module.category}/{module.id}/card-{i}",
            module_key=f"{module.category}/{module.id}",
            module_title=module.title,
            category=module.category,
            front=response["front"],
            back=response["back"],
            source_field=response["source_field"],
        )
        cards.append(card)

    return cards

def select_modules_for_memory(
    kb_path: Path,
    max_modules: int = 50,
) -> list[Module]:
    """
    筛选值得生成卡片的模块:

    1. confidence = high (确定性高的知识才值得记)
    2. status = published (草稿和废弃的不记)
    3. 按 load_count 排序 (经常被用的优先)
    4. 排除已有 ≥3 张卡片的模块
    5. 作者/审核者标记为 "值得记忆" 的优先
    """
    ...
```

## FSRS 调度器

```python
class FSRSScheduler:
    """
    FSRS v5 算法的 Python 实现

    核心公式:
    - retrievability (R): 在当前时间点回忆的概率
      R(t) = (1 + (t / (9 * S))) ^ -1
      其中 S = stability (记忆稳定性), t = 自上次复习的天数

    - 新 stability (S'):
      S' = S * (1 + (e ^ (w * (1 - R))) * ln(D) * (R ^ w2))
      其中 D = difficulty, w = 参数向量

    - 新 difficulty (D'):
      D' = D + w4 * (G - 3)
      其中 G = grade (1-4)
    """

    # FSRS v5 默认参数 (来自社区最优拟合)
    DEFAULT_WEIGHTS = [
        0.4072,   # w0
        1.1829,   # w1
        3.1262,   # w2
        15.4722,  # w3
        7.2102,   # w4
        0.5316,   # w5
        1.0651,   # w6
        0.0234,   # w7
        1.616,    # w8
        0.0304,   # w9
        0.0611,   # w10
        1.8455,   # w11
        0.172,    # w12
        0.913,    # w13
        2.6026,   # w14
        0.3674,   # w15
        0.7462,   # w16
        0.9478,   # w17
        0.0,      # w18 (unused)
    ]

    def schedule(
        self,
        card: MemoryCard,
        grade: ReviewGrade,
        review_time: datetime = None,
    ) -> MemoryCard:
        """
        根据 FSRS 算法计算下次复习时间

        基本间隔 (首次):
        - Again (1): 1 分钟
        - Hard (2):  10 分钟
        - Good (3):  1 天
        - Easy (4):  4 天

        后续间隔 = 上次间隔 * ease_factor * grade_modifier
        - Again: 重置间隔, ease_factor -= 0.20
        - Hard:  间隔 * 1.2, ease_factor -= 0.15
        - Good:  间隔 * ease_factor
        - Easy:  间隔 * ease_factor * 1.3, ease_factor += 0.15

        ease_factor 范围: [1.3, 2.5]
        """
        review_time = review_time or datetime.now(timezone.utc)

        state = card.fsrs_state
        current_stability = state.get("stability", 0.0)
        current_difficulty = state.get("difficulty", 0.3)
        elapsed_days = state.get("elapsed_days", 0)

        G = int(grade)

        # 计算当前可提取性
        if current_stability > 0:
            retrievability = (1 + (elapsed_days / (9 * current_stability))) ** -1
        else:
            retrievability = 1.0  # 新卡片

        # 更新 difficulty
        # D' = D + w4 * (G - 3)
        D = current_difficulty + self.DEFAULT_WEIGHTS[4] * (G - 3)
        D = max(0.01, min(1.0, D))  # clamp

        # 更新 stability
        if G == ReviewGrade.AGAIN:
            # 遗忘: stability 重置
            S = self.DEFAULT_WEIGHTS[6]  # 最小 stability
        else:
            # 记忆: stability 增长
            S = current_stability * (
                1 + math.exp(self.DEFAULT_WEIGHTS[8]) *
                (11 - D) *
                (current_stability ** -self.DEFAULT_WEIGHTS[9]) *
                (math.exp(self.DEFAULT_WEIGHTS[10] * (1 - retrievability)) - 1)
            )

        # 计算下次复习间隔 (天)
        interval_days = S * (
            0.2 if G == ReviewGrade.HARD else
            1.0 if G == ReviewGrade.GOOD else
            1.5
        )

        # 更新卡片状态
        card.fsrs_state = {
            "stability": S,
            "difficulty": D,
            "elapsed_days": 0,
            "scheduled_days": interval_days,
            "reps": state.get("reps", 0) + 1,
            "lapses": state.get("lapses", 0) + (1 if G == ReviewGrade.AGAIN else 0),
            "last_review": review_time.isoformat(),
        }
        card.last_review_at = review_time
        card.next_review_at = review_time + timedelta(days=interval_days)
        card.review_count += 1
        card.total_grade_sum += int(G)

        return card

    def get_due_cards(
        self,
        cards: list[MemoryCard],
        limit: int = 20,
    ) -> list[MemoryCard]:
        """获取今天到期的卡片, 按优先级排序"""
        now = datetime.now(timezone.utc)
        due = [
            c for c in cards
            if c.next_review_at is None or c.next_review_at <= now
        ]
        # 排序: 过期的优先 → 高难度的优先 → 稳定性低的优先
        due.sort(key=lambda c: (
            c.next_review_at or now,           # 过期越久越优先
            -c.fsrs_state.get("difficulty", 0), # 难度高优先
            c.fsrs_state.get("stability", 0),   # 不稳定的优先
        ))
        return due[:limit]
```

## CLI

```bash
# 为知识库生成记忆卡片
$ km memory init
  扫描 127 个模块...
  筛选出 42 个高价值模块
  LLM生成 98 张记忆卡片
  已保存到 .memory/cards.json

# 今日复习
$ km memory today

📋 今日复习 (6张卡片到期)

┌────┬──────────────────────────────────────────┬──────────┬───────────┬──────┐
│ #  │ 卡片                                       │ 分类      │ 上次复习   │ 间隔  │
├────┼──────────────────────────────────────────┼──────────┼───────────┼──────┤
│ 1  │ 为什么选RS256而不是HS256?                   │ auth     │ 1天前      │ 3d   │
│ 2  │ 🔺 K8s HPA的最小/最大副本数是多少?           │ deploy   │ 3天前      │ 7d   │
│ 3  │ gRPC服务间通信的超时重试策略是什么?          │ backend  │ 7天前      │ 14d  │
│ 4  │ Redis缓存穿透的解决方案?                    │ backend  │ 14天前     │ 30d  │
│ 5  │ 数据库迁移的零停机步骤?                     │ backend  │ 30天前     │ 60d  │
│ 6  │ 为什么不用GraphQL而选REST?                  │ arch     │ 60天前     │ 90d  │
└────┴──────────────────────────────────────────┴──────────┴───────────┴──────┘

选择卡片编号查看 [1-6, 'all']: 1

📖 卡片 #1
┌──────────────────────────────────────────────────────────────┐
│ Q: 如果我们需要支持多服务验证JWT但不共享密钥,                  │
│    应该选什么签名算法? 为什么?                                 │
│                                                              │
│ [按任意键显示答案]                                            │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ A: RS256非对称签名。每个服务从JWKS端点获取公钥独立验证签名,    │
│    不需要共享密钥。代价是签名速度比HS256慢约10x。              │
│                                                              │
│ 📎 来源: auth/jwt-config (更新于 2026-06-01)                  │
└──────────────────────────────────────────────────────────────┘

掌握程度: [1]完全忘记 [2]困难 [3]正确 [4]轻松: 3
✅ 下次复习: 4天后 (6月13日)

# 统计
$ km memory stats
┌──────────────────────────┬────────┐
│ 指标                      │ 数值    │
├──────────────────────────┼────────┤
│ 总卡片数                   │ 98     │
│ 今日已复习                 │ 4/6    │
│ 连续复习天数               │ 12 🔥  │
│ 预测保留率 (90天)          │ 87.3%  │
│ 总复习次数                 │ 347    │
│ 平均掌握度                 │ 3.2/4  │
└──────────────────────────┴────────┘
```

## MCP 集成

```python
@mcp.tool(name="get_review_cards")
def get_review_cards_tool(count: int = 5) -> str:
    """获取今天到期的记忆复习卡片，供 Agent 提醒用户复习"""
    ...

@mcp.tool(name="grade_review_card")
def grade_review_card_tool(card_id: str, grade: int) -> str:
    """记录用户对一张复习卡片的掌握程度 (1-4)"""
    ...
```

## 与模块健康评分的联动

```python
# 模块健康评分新增 team_retention 维度

# 旧权重
HEALTH_WEIGHTS_OLD = {
    "freshness": 0.35,    # 更新频率
    "usage": 0.35,        # 被搜索/加载的次数
    "completeness": 0.30, # 内容完整性
}

# 新权重 (引入团队记忆维度)
HEALTH_WEIGHTS_NEW = {
    "freshness": 0.30,
    "usage": 0.30,
    "completeness": 0.25,
    "team_retention": 0.15,  # 新增: 团队对该模块的记忆保持度
}

def compute_team_retention(module_key: str, cards: list[MemoryCard]) -> float:
    """
    团队记忆保持度 (0-100):
    - 基于该模块所有卡片的 FSRS stability 平均值
    - stability 高 → 团队已经内化了这个知识 → 高价值
    - 有卡片但从未复习 → 低分
    - 没有卡片 → 中性分 (50)
    """
    mod_cards = [c for c in cards if c.module_key == module_key]
    if not mod_cards:
        return 50.0

    stabilities = [
        c.fsrs_state.get("stability", 0)
        for c in mod_cards
        if c.review_count > 0
    ]
    if not stabilities:
        return 30.0  # 有卡片但未复习 → 偏低

    avg_stability = sum(stabilities) / len(stabilities)
    # 将 stability 映射为 0-100 分
    # stability=0 → 0分, stability=30天 → 80分, stability=90天 → 100分
    return min(100, 100 * (1 - math.exp(-avg_stability / 15)))
```

---

# 大改进七：自动源监控 (Watch Service)

## 设计

知识库不应只依赖手动 `km add`。团队的知识来源是持续流动的：代码仓库的新commit、技术博客的RSS、架构决策的RFC文档。Watch Service 把这些流自动引入知识库。

### 后台服务架构

```bash
# 启动监控守护进程
km watch serve &

# 注册监控源
km watch add github --repo org/backend --path "docs/**" --category backend
km watch add github --repo org/backend --path "rfcs/**" --category decisions
km watch add rss --url "https://engineering.blog.com/feed.xml" --category external
km watch add local --path "../shared-docs" --category general --auto-categorize
km watch add arxiv --query "cat:cs.AI AND (rag OR knowledge)" --category research

# 管理
km watch list       # 列出所有监控源
km watch status     # 查看每个源的最近处理状态
km watch logs       # 查看处理历史
km watch run --now  # 立即触发所有源的全量拉取
km watch remove github/org-backend  # 移除监控源
```

### 数据模型

```python
class WatchSource(BaseModel):
    id: str
    type: Literal["github", "rss", "local", "arxiv", "webhook"]
    enabled: bool = True
    # 源配置
    config: dict = Field(default_factory=dict)
    # e.g. github: {"repo": "org/backend", "branch": "main", "paths": ["docs/**"]}
    # e.g. rss: {"url": "https://...", "last_etag": "..."}
    # e.g. local: {"path": "../shared-docs", "patterns": ["*.md"]}
    # e.g. arxiv: {"query": "cat:cs.AI", "max_results": 10}
    # 知识提取配置
    extraction: WatchExtractionConfig

class WatchExtractionConfig(BaseModel):
    category: str = ""          # 提取的模块归入哪个分类
    auto_categorize: bool = False   # 是否让LLM自动分类
    chunk_size: int = 8000
    max_modules_per_item: int = 3
    # 审核策略
    auto_approve: bool = False     # 是否自动批准 (高风险源不要开)
    notify_on_new: bool = True     # 新模块是否通知
    notify_webhook: str = ""       # 通知的 webhook URL

class WatchEvent(BaseModel):
    """记录一次监控处理"""
    id: str
    source_id: str
    triggered_at: datetime
    trigger_type: str          # "schedule" | "webhook" | "manual"
    items_found: int = 0       # 发现的新条目数
    items_processed: int = 0   # 成功处理的条目数
    modules_generated: int = 0 # 生成的模块数
    errors: list[str] = Field(default_factory=list)
    took_ms: int = 0
    cursor_after: str = ""     # 处理后的游标位置
```

### GitHub Watcher 实现

```python
# src/knowledge_manager/watchers/github.py (新文件)

class GitHubWatcher:
    """监控 GitHub 仓库的新 commit/PR/release, 从指定路径提取知识"""

    def __init__(self, source: WatchSource, llm_client, storage):
        self.source = source
        self.llm = llm_client
        self.storage = storage

    async def poll(self) -> WatchEvent:
        """
        拉取自上次游标以来的新内容:

        1. 获取上次处理到的 commit SHA (游标)
        2. 拉取该 SHA 之后的所有 commit
        3. 对于每个 commit:
           a. 获取变更文件列表
           b. 过滤出匹配 include_patterns 的文件
           c. 获取这些文件的 diff
           d. LLM 分析 diff: 这是新知识/更新知识/无关变更?
           e. 如果是新知识 → 提取为模块
           f. 如果是更新 → 找到对应模块, 生成更新建议
        4. 更新游标
        """
        repo = self.source.config["repo"]
        paths = self.source.config.get("paths", ["**"])
        cursor = self.source.config.get("cursor")  # last commit SHA

        # 获取新 commits
        if cursor:
            commits = await self._gh_api(f"repos/{repo}/commits?since={cursor}")
        else:
            commits = await self._gh_api(f"repos/{repo}/commits?per_page=5")

        event = WatchEvent(
            id=str(uuid.uuid4()),
            source_id=self.source.id,
            triggered_at=datetime.now(timezone.utc),
            trigger_type="schedule",
        )

        for commit in commits[:10]:  # 每次最多处理10个commit
            sha = commit["sha"]
            diff_files = await self._gh_api(f"repos/{repo}/commits/{sha}")

            for file_info in diff_files.get("files", []):
                filename = file_info["filename"]

                # 路径匹配
                if not self._match_path(filename, paths):
                    continue

                # 只处理文档类文件
                if not filename.endswith(('.md', '.txt', '.rst', '.adoc')):
                    patch = file_info.get("patch", "")
                    if len(patch) < 200:  # 代码变更太小, 忽略
                        continue
                    # 对代码变更做摘要提取
                    content = f"File: {filename}\n\nCommit: {commit['commit']['message']}\n\nDiff:\n{patch}"
                else:
                    # 文档文件: 获取完整内容
                    content = await self._gh_api(
                        f"repos/{repo}/contents/{filename}?ref={sha}"
                    )
                    content = base64.b64decode(content["content"]).decode()

                # LLM 判断是否需要提取
                should_extract = await self._should_extract(
                    filename, content, commit["commit"]["message"]
                )

                if should_extract:
                    modules = await self._extract_from_content(content, filename)
                    for mod in modules:
                        self.storage.save_to_staging(mod, self.kb_path)
                    event.modules_generated += len(modules)

                event.items_processed += 1

            event.items_found += len(diff_files.get("files", []))

        # 更新游标
        if commits:
            event.cursor_after = commits[0]["sha"]

        return event

    async def _should_extract(
        self, filename: str, content: str, commit_message: str
    ) -> bool:
        """LLM判断这个文件变更是否包含值得提取的知识"""
        prompt = f"""\
判断以下文件变更是否包含值得录入知识库的内容。

文件名: {filename}
Commit 消息: {commit_message}

文件内容摘要 (前500字符):
{content[:500]}

值得录入的标准:
- 包含架构决策或技术选型理由
- 包含配置策略或参数选择的解释
- 包含流程/规范/最佳实践的说明
- 包含踩坑记录或注意事项

不值得录入:
- 纯代码重构 (没有解释为什么)
- 依赖版本升级
- 格式修正/typo修复
- 临时的调试代码

返回JSON: {{"extract": true/false, "reason": "一句话原因"}}
"""
        response = await self.llm.complete_json(prompt)
        return response.get("extract", False)

    def _match_path(self, filepath: str, patterns: list[str]) -> bool:
        """检查文件路径是否匹配任一 glob pattern"""
        return any(fnmatch(filepath, p) for p in patterns)
```

### 调度器

```python
# src/knowledge_manager/watch_scheduler.py (新文件)

class WatchScheduler:
    """后台调度器, 定期轮询所有监控源"""

    # 默认轮询间隔
    DEFAULT_INTERVALS = {
        "github": 300,    # 5分钟
        "rss": 600,       # 10分钟
        "local": 120,     # 2分钟 (文件系统监控用 watchdog 事件)
        "arxiv": 86400,   # 每天 (arXiv 每天更新一次)
    }

    def __init__(self, kb_path: Path, config: WatchConfig):
        self.kb_path = kb_path
        self.config = config
        self.scheduler = AsyncIOScheduler()
        self.watchers: dict[str, Any] = {}  # source_id → watcher instance

    async def start(self):
        """启动所有监控源的后台调度"""
        for source in self.config.sources:
            if not source.enabled:
                continue

            # 创建 watcher 实例
            watcher = self._create_watcher(source)
            self.watchers[source.id] = watcher

            # 注册定时任务
            interval = self.DEFAULT_INTERVALS.get(source.type, 600)
            self.scheduler.add_job(
                self._poll_source,
                'interval',
                seconds=interval,
                args=[source.id],
                id=f"watch_{source.id}",
                next_run_time=datetime.now() + timedelta(seconds=5),  # 启动5秒后首次运行
            )

        self.scheduler.start()

    async def _poll_source(self, source_id: str):
        """轮询单个监控源"""
        watcher = self.watchers.get(source_id)
        if not watcher:
            return

        try:
            event = await watcher.poll()
            self._record_event(event)

            if event.modules_generated > 0:
                # 通知用户
                self._notify_new_modules(event)

            # 更新游标
            self._update_cursor(source_id, event.cursor_after)

        except Exception as e:
            logger.error(f"Watch source {source_id} failed: {e}")

    def _notify_new_modules(self, event: WatchEvent):
        """通知用户有新模块待审核"""
        source = self._get_source(event.source_id)
        if source and source.extraction.notify_on_new:
            message = (
                f"📥 Watch [{source.id}] 发现 {event.modules_generated} 个新知识模块, "
                f"来自 {event.items_processed} 个变更。\n"
                f"运行 `km review` 审核。"
            )
            # CLI 输出
            console.print(f"[green]{message}[/green]")
            # Webhook 通知
            if source.extraction.notify_webhook:
                self._send_webhook(source.extraction.notify_webhook, message)
```

---

# 大改进八：可选向量搜索增强

## 设计原则

当前4层关键词排序已经很强，但有一个盲区：**概念模糊匹配**。用户搜"服务间通信方式"但库里写的是"gRPC"和"消息队列"——关键词匹配完全找不到。

向量搜索作为**可选的增强层**，默认关闭，不引入外部基础设施。

### 配置

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

### 内存向量索引

```python
# src/knowledge_manager/vector_index.py (新文件)

class VectorIndex:
    """
    零外部依赖的向量索引

    使用 numpy 做内存内向量搜索。
    100K 模块 × 1024维 = ~400MB 内存 (float32), 可接受。
    """

    def __init__(self, kb_path: Path, config: VectorSearchConfig):
        self.kb_path = kb_path
        self.config = config
        self.embeddings: Optional[np.ndarray] = None
        self.module_keys: list[str] = []
        self._lock = threading.Lock()
        self._cache_path = kb_path / ".cache" / "vector_index.npz"

    async def rebuild(self, on_progress=None) -> None:
        """
        重建向量索引:

        1. 遍历所有 published 模块
        2. 拼接每模块的可搜索文本 (title + summary + tags + overview + details)
        3. 调用 embedding 服务生成向量
        4. 存入 numpy array
        5. 持久化到 .cache/vector_index.npz (加速下次启动)
        """
        index = load_index(self.kb_path)
        if index is None:
            return

        # 收集所有可搜索模块
        modules = []
        for cat in index.categories.values():
            for mod_summary in cat.modules:
                module = load_module(mod_summary.id, mod_summary.category, self.kb_path)
                if module and module.metadata.status in ("published", "reviewed"):
                    modules.append(module)

        if not modules:
            return

        # 构建文本
        texts = []
        keys = []
        for i, module in enumerate(modules):
            text = f"{module.title}\n{module.summary}\n{' '.join(module.metadata.tags)}\n{module.content.overview}\n{module.content.details}"
            texts.append(text)
            keys.append(f"{module.category}/{module.id}")

            if on_progress and i % 10 == 0:
                on_progress(i, len(modules))

        # 批量生成 embeddings
        embeddings = await self._embed(texts)

        # 归一化 (余弦相似度 = 内积)
        embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)

        with self._lock:
            self.embeddings = embeddings
            self.module_keys = keys

        # 持久化
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            self._cache_path,
            embeddings=embeddings,
            module_keys=np.array(keys, dtype=object),
        )

    def search(self, query: str, top_k: int = 20) -> list[tuple[str, float]]:
        """
        向量语义搜索

        返回: [(module_key, cosine_similarity), ...]
        """
        if self.embeddings is None or len(self.embeddings) == 0:
            try:
                self._load_from_cache()
            except Exception:
                return []

        if self.embeddings is None:
            return []

        # 生成查询嵌入
        query_embedding = asyncio.run(self._embed([query]))[0]
        query_embedding = query_embedding / np.linalg.norm(query_embedding)

        with self._lock:
            # 余弦相似度 (已归一化 → 内积)
            scores = np.dot(self.embeddings, query_embedding)
            # top_k
            if top_k >= len(scores):
                indices = np.argsort(-scores)
            else:
                indices = np.argpartition(-scores, top_k)[:top_k]
                indices = indices[np.argsort(-scores[indices])]

            return [
                (self.module_keys[i], float(scores[i]))
                for i in indices[:top_k]
            ]

    async def _embed(self, texts: list[str]) -> np.ndarray:
        """
        调用 embedding provider 生成向量

        支持的 provider:
        - ollama:         本地 Ollama 服务 (推荐, 零外部依赖)
        - sentence-transformers: 本地 Python 库 (需要 pip install)
        - openai:         OpenAI API (需要网络)
        """
        provider = self.config.provider

        if provider == "ollama":
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.config.ollama_base_url}/api/embed",
                    json={"model": self.config.model, "input": texts},
                    timeout=60,
                )
                data = response.json()
                return np.array(data["embeddings"], dtype=np.float32)

        elif provider == "local":
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(self.config.model)
            return model.encode(texts, normalize_embeddings=True)

        elif provider == "openai":
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                    json={"model": "text-embedding-3-small", "input": texts},
                )
                data = response.json()
                return np.array([d["embedding"] for d in data["data"]], dtype=np.float32)

        raise ValueError(f"Unknown embedding provider: {provider}")

    def _load_from_cache(self) -> None:
        """从缓存文件加载向量索引 (加速启动)"""
        if not self._cache_path.exists():
            return

        data = np.load(self._cache_path, allow_pickle=True)
        with self._lock:
            self.embeddings = data["embeddings"]
            self.module_keys = list(data["module_keys"])
```

### RRF 融合集成

```python
# storage.py 中 search_modules 的改造

def search_modules(
    query: str,
    kb_path: Path,
    category: str = None,
    limit: int = 10,
    boost_ids: list[str] = None,
    include_archived: bool = False,
    vector_index: VectorIndex = None,  # 新增
    vector_weight: float = 0.25,       # 新增
) -> list[SearchResult]:
    """
    搜索主函数: 关键词 + 树推理 + 向量 (可选) → RRF 融合
    """

    # 1. 关键词搜索 (现有逻辑)
    keyword_results = _keyword_search(
        query, kb_path, category, boost_ids, include_archived, limit=limit*2
    )

    # 2. 向量搜索 (可选)
    vector_results = []
    if vector_index is not None:
        raw_vector = vector_index.search(query, top_k=limit*2)
        # 过滤 (category, archive, 等)
        vector_results = _post_filter_vector_results(raw_vector, kb_path, category, include_archived)

    # 3. RRF 融合
    if vector_results:
        fused = _rrf_fuse(
            keyword=keyword_results,
            vector=vector_results,
            k_keyword=60,
            k_vector=120,  # 向量噪声多, 大k平滑
            weight_keyword=1.0 - vector_weight,
            weight_vector=vector_weight,
        )
    else:
        fused = keyword_results

    # 4. 贝叶斯调整 + 截断
    return _apply_bayesian_and_truncate(fused, limit, query, kb_path)


def _rrf_fuse(
    keyword: list[ScoredModule],
    vector: list[tuple[str, float]],
    k_keyword: int = 60,
    k_vector: int = 120,
    weight_keyword: float = 0.75,
    weight_vector: float = 0.25,
) -> list[ScoredModule]:
    """
    Reciprocal Rank Fusion:

    score(module) = Σ w_i / (k_i + rank_i)

    其中:
    - w_i = 该路的权重
    - k_i = 该路的平滑参数 (大k = 排名差异影响小)
    - rank_i = 模块在该路中的排名 (从1开始)
    """

    # 构建排名映射
    keyword_rank = {
        f"{r.module.category}/{r.module.id}": i + 1
        for i, r in enumerate(keyword)
    }
    vector_rank = {
        key: i + 1
        for i, (key, _) in enumerate(vector)
    }

    all_keys = set(keyword_rank.keys()) | set(vector_rank.keys())

    scores = {}
    for key in all_keys:
        score = 0.0
        if key in keyword_rank:
            score += weight_keyword / (k_keyword + keyword_rank[key])
        if key in vector_rank:
            score += weight_vector / (k_vector + vector_rank[key])
        scores[key] = score

    # 排序
    sorted_keys = sorted(scores, key=scores.get, reverse=True)

    # 重建 ScoredModule 列表
    keyword_map = {
        f"{r.module.category}/{r.module.id}": r
        for r in keyword
    }
    module_map = {}
    for key in sorted_keys:
        if key in keyword_map:
            module_map[key] = keyword_map[key]
        else:
            # 纯向量召回的结果, 需要加载模块
            parts = key.split("/", 1)
            mod = load_module(parts[1], parts[0], kb_path)
            if mod:
                module_map[key] = ScoredModule(
                    module=mod,
                    score=float(scores[key]),
                    source="vector",
                    highlights=None,
                )

    return [module_map[key] for key in sorted_keys if key in module_map]
```

---

# 大改进九：插件系统

## 设计目标

knowledge-manager 不可能覆盖所有团队的工具链。插件系统让社区贡献集成, 保持核心轻量。

## 插件接口

```python
# src/knowledge_manager/plugin.py (新文件)

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Protocol

@dataclass
class PluginManifest:
    name: str                    # "km-plugin-slack"
    version: str                 # "1.0.0"
    description: str
    author: str
    license: str = "MIT"
    dependencies: list[str] = field(default_factory=list)
    min_km_version: str = "0.5.0"

@dataclass
class PluginContext:
    """插件运行上下文, 由宿主注入"""
    kb_path: Path
    config: Config
    storage: "Storage"
    llm_client: "BaseLLMClient"
    cache: "ModuleCache"
    logger: logging.Logger

# ── 钩子协议 ──

class ExtractHook(Protocol):
    """在知识提取前后执行的钩子"""
    async def before_extract(self, text: str, category: str, ctx: PluginContext) -> str:
        """修改或增强原始文本 (例如: 自动翻译、格式标准化)"""
        ...
    async def after_extract(self, modules: list[Module], ctx: PluginContext) -> list[Module]:
        """修改或过滤提取结果 (例如: 自动添加特定tags)"""
        ...

class ReviewHook(Protocol):
    """在审核流程中执行的钩子"""
    async def before_approve(self, module: Module, ctx: PluginContext) -> Module:
        """批准前最后检查 (例如: 合规检查、敏感信息扫描)"""
        ...
    async def after_approve(self, module: Module, ctx: PluginContext) -> None:
        """批准后通知 (例如: Slack通知、Jira更新)"""
        ...

class SearchHook(Protocol):
    """在搜索流程中执行的钩子"""
    async def before_search(self, query: str, ctx: PluginContext) -> str:
        """查询预处理 (例如: 查询扩展, 术语转换)"""
        ...
    async def after_search(self, query: str, results: list[SearchResult], ctx: PluginContext) -> list[SearchResult]:
        """结果后处理 (例如: 过滤、重排、注入外部结果)"""
        ...

class PublishHook(Protocol):
    """在发布流程中执行的钩子"""
    async def before_publish(self, module: Module, ctx: PluginContext) -> Module:
        """发布前处理 (例如: 格式转换、水印添加)"""
        ...

# ── 插件基类 ──

class PluginBase(ABC):
    """所有插件必须继承此类"""

    manifest: PluginManifest

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx

    # 可选钩子: 子类按需覆盖

    async def on_load(self) -> None:
        """插件加载时调用 (注册资源、初始化连接)"""
        pass

    async def on_unload(self) -> None:
        """插件卸载时调用 (清理资源)"""
        pass

    # CLI 扩展
    def register_commands(self) -> list[click.Command]:
        """注册自定义 CLI 命令"""
        return []

    # MCP 扩展
    def register_mcp_tools(self) -> list[callable]:
        """注册自定义 MCP tools"""
        return []

    def register_mcp_resources(self) -> list[callable]:
        """注册自定义 MCP resources"""
        return []

    # Web UI 扩展
    def register_ui_panels(self) -> list[dict]:
        """
        注册 Web UI 面板:
        {
            "id": "my-panel",
            "title": "My Panel",
            "icon": "chart",
            "component": "MyPanel",  # React 组件名 (由插件JS提供)
            "position": "sidebar",  # sidebar | main | bottom
        }
        """
        return []

    # 钩子 (插件按需实现对应的 Protocol)
    extract_hook: Optional[ExtractHook] = None
    review_hook: Optional[ReviewHook] = None
    search_hook: Optional[SearchHook] = None
    publish_hook: Optional[PublishHook] = None
```

## 插件管理器

```python
class PluginManager:
    """插件生命周期管理"""

    def __init__(self, kb_path: Path):
        self.kb_path = kb_path
        self.plugins: dict[str, PluginBase] = {}
        self.plugin_dir = kb_path / ".plugins"
        self.plugin_dir.mkdir(exist_ok=True)

    def discover(self) -> list[PluginManifest]:
        """发现已安装的插件"""
        manifests = []
        for plugin_path in self.plugin_dir.iterdir():
            if plugin_path.is_dir() and (plugin_path / "manifest.json").exists():
                manifest = json.loads((plugin_path / "manifest.json").read_text())
                manifests.append(PluginManifest(**manifest))
        return manifests

    async def install(self, plugin_name: str, version: str = "latest") -> None:
        """安装插件 (从 marketplace 下载并安装)"""
        ...

    async def load(self, plugin_name: str) -> PluginBase:
        """加载插件"""
        # 1. 查找插件目录
        plugin_path = self.plugin_dir / plugin_name
        if not plugin_path.exists():
            raise ValueError(f"Plugin not found: {plugin_name}")

        # 2. 读取 manifest
        manifest = json.loads((plugin_path / "manifest.json").read_text())

        # 3. 动态导入插件模块
        spec = importlib.util.spec_from_file_location(
            plugin_name,
            plugin_path / "plugin.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 4. 实例化插件
        plugin_class = getattr(module, manifest["entry_class"])
        ctx = PluginContext(
            kb_path=self.kb_path,
            ...
        )
        plugin = plugin_class(ctx)
        plugin.manifest = PluginManifest(**manifest)

        # 5. 调用 on_load
        await plugin.on_load()

        self.plugins[plugin_name] = plugin
        return plugin

    async def unload(self, plugin_name: str) -> None:
        """卸载插件"""
        if plugin_name in self.plugins:
            await self.plugins[plugin_name].on_unload()
            del self.plugins[plugin_name]
```

## 示例插件：Slack 通知

```python
# .plugins/km-plugin-slack/plugin.py

class SlackNotifier(PluginBase):
    """审核事件通知到 Slack"""

    manifest = PluginManifest(
        name="km-plugin-slack",
        version="1.0.0",
        description="审核事件通知到 Slack 频道",
        author="community",
    )

    def __init__(self, ctx: PluginContext):
        super().__init__(ctx)
        self.webhook_url = ""

    async def on_load(self) -> None:
        self.webhook_url = self.ctx.config.get("slack_webhook_url", "")

    class ReviewNotifier(ReviewHook):
        async def after_approve(self, module: Module, ctx: PluginContext) -> None:
            message = {
                "text": f"✅ 知识模块已审核通过",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"*新知识模块已审核通过*\n"
                                f"📄 *{module.title}*\n"
                                f"📁 {module.category}/{module.id}\n"
                                f"🏷️ {' '.join(f'`{t}`' for t in module.metadata.tags)}\n"
                                f"📝 {module.summary[:200]}"
                            ),
                        },
                    },
                ],
            }
            async with httpx.AsyncClient() as client:
                await client.post(self.webhook_url, json=message)

    review_hook = ReviewNotifier()
```

### CLI

```bash
km plugin search "slack"              # 搜索插件
km plugin install km-plugin-slack     # 安装
km plugin list                         # 已安装列表
km plugin enable km-plugin-slack       # 启用
km plugin disable km-plugin-slack      # 禁用 (不卸载, 保留配置)
km plugin uninstall km-plugin-slack    # 卸载
km plugin config km-plugin-slack set slack_webhook_url "https://..."
```

---

# 大改进十：多模态知识

## 图片理解

```bash
km add architecture.png -c architecture
  → LLM Vision 分析图片
  → 生成模块: "微服务架构图 (2026 Q1)"
    overview: "当前生产环境的微服务拓扑..."
    details: "共有6个服务: API Gateway (Kong), Auth Service, ..."
    examples: "[图片: architecture.png] (base64 embedded for local, path ref for KB)"
```

```python
async def extract_from_image(
    image_path: Path,
    category: str,
    llm_client,
) -> list[Module]:
    """从图片中提取知识模块"""

    # 读取图片
    image_data = base64.b64encode(image_path.read_bytes()).decode()

    prompt = """\
分析这张图片, 提取其中的知识。

如果是架构图/流程图:
- 识别关键组件和它们之间的关系
- 提取数据流向
- 标注技术栈选择

如果是截图:
- 提取关键信息和上下文
- 标注操作步骤

返回JSON数组的模块。每个模块的 examples 字段包含 "图片: <filename>" 引用。
"""

    response = await llm_client.complete_vision(prompt, [image_data])
    ...
```

## 代码仓库理解

```bash
km add --repo ../backend --category backend
  →
  扫描目录结构
  读取关键文件 (README.md, ARCHITECTURE.md, config/*.yaml, main entry points)
  LLM 分析代码结构和依赖关系
  生成多个模块:
    - backend/overview         (项目概述)
    - backend/api-structure    (API路由结构)
    - backend/database-schema  (数据库设计)
    - backend/auth-mechanism   (认证机制)
    - backend/config-management (配置管理)
  related_modules 自动反映代码依赖关系
```

## 会议记录理解

```bash
km add meeting-2026-06-09.txt -c decisions
  →
  LLM 分析会议记录:
  - 识别架构决策 → 提取为 decision-record 类型模块
  - 识别行动项 → 生成 todo 模块 (status: draft)
  - 识别风险讨论 → 更新相关模块的 caveats
  - 识别问题讨论 → 生成 faq 模块
```

---

# 总路线图

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

---

## 不做的事

| 不做 | 理由 |
|------|------|
| 迁移到数据库 | 文件系统+Git是可审计性的根基, 也是区别于所有竞品的护城河 |
| 引入向量数据库 (Milvus/Qdrant) | 100K模块以下内存 numpy 足够, 引入外部基础设施增加运维负担 |
| 独立 Web 服务器进程 | `km serve --ui` 一站式, MCP + HTTP 同进程共享状态 |
| 实时协同编辑 (CRDT/OT) | Git 就是异步协作的最佳协议, 实时编辑是分布式系统的泥潭 |
| SaaS 托管版 | 本地优先是哲学选择, 数据主权不可妥协 |
| 前端框架强制要求 | 零构建回退UI保证 `pip install` 后立即可用 |

---

*蓝图版本: v3.0 | 日期: 2026-06-09 | 基于 PageIndex + llm-wiki 深度竞争分析*
