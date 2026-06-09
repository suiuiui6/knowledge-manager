# M2 Spec — 对话式搜索

> Phase 5 M2 | 2026-06-09 | 硬依赖: M1 (Web UI shell)

## 概述

在 M1 只读浏览基础上，增加对话式搜索：用户自然语言提问 → 多路召回 → RRF融合 → LLM流式生成答案 + 来源引用。核心交付物：`POST /api/chat` SSE端点 + ChatPanel 前端组件。

## Backend: ChatPipeline

### 新增文件: `src/knowledge_manager/chat.py`

```python
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

@dataclass
class ChatEvent:
    type: str  # "status" | "token" | "citation" | "done" | "error"
    data: dict

class ChatPipeline:
    def __init__(self, kb_path: Path, llm_client, rank_model, tree_index=None, vector_index=None):
        ...

    async def chat(self, query: str, history: list[dict], mode: str = "precise") -> AsyncIterator[ChatEvent]:
        """六阶段流水线: 查询理解 → 多路召回 → RRF融合 → 上下文组装 → LLM流式生成 → 后处理"""
```

### SSE 事件协议

```
event: status
data: {"stage":"query_understanding","intent":"reference","rewritten":"JWT的过期时间是多少"}

event: status
data: {"stage":"retrieval","message":"检索相关知识..."}

event: status
data: {"stage":"ranking","candidates":15,"selected":5,"top_titles":["JWT配置","Token轮换","OAuth2.0流程"]}

event: token
data: {"text":"JWT","source":null}

event: token
data: {"text":" token","source":null}

event: token
data: {"text":" 过期时间是","source":"auth/jwt-config"}

event: citation
data: {"key":"auth/jwt-config","title":"JWT配置","snippet":"Access Token过期时间24h...","confidence":"high"}

event: done
data: {"took_ms":2340,"sources":[...],"follow_ups":["怎么配置JWT的refresh token?","RS256和HS256的区别是什么?"]}
```

### `POST /api/chat` 端点

**请求体:**
```json
{
  "query": "JWT过期时间是多少",
  "history": [
    {"role": "user", "content": "认证是怎么做的"},
    {"role": "assistant", "content": "我们使用JWT进行认证..."}
  ],
  "mode": "precise"
}
```
- `history` 最大保留最近10轮对话
- `mode` = `"precise"` | `"creative"` → 调 LLM temperature (precise=0.3, creative=0.7)

**响应:** `text/event-stream` (SSE)

**错误响应:**
- 400: query为空
- 503: LLM不可用

### 六阶段流水线

```
Step 1: 查询理解 (~50ms)
  ├── 查询改写: 结合history将省略/指代补全
  │   "它的过期时间" + history[user曾问jwt] → "JWT的过期时间"
  └── 意图分类: 复用 storage._classify_intent()

Step 2: 多路召回 (~200ms, 并行)
  ├── 关键词召回: search_modules(query, limit=20)  ← 现有函数
  ├── 树推理召回: TreeNavigator.navigate(query)     ← M3接入, M2返回空
  └── 向量召回: VectorIndex.search(query)          ← M10接入, M2返回空

Step 3: RRF融合 (~10ms)
  RRF_score = Σ w_i / (k_i + rank_i)
  weights: keyword=0.75, tree=0.0(M2), vector=0.0(M2)
  贝叶斯反馈调整 + 取 top-5

Step 4: 上下文组装 (~5ms)
  系统提示词 = 模块列表(title+summary+confidence) + 引用规则 + 意图适配
  用户提示词 = 改写后的query + 历史对话

Step 5: LLM流式生成 (~2000ms)
  流式输出, 实时检测模块名引用 → 注入 citation 事件

Step 6: 后处理 (~200ms)
  收集所有引用, 生成3个追问建议
```

### 查询改写实现

```python
REWRITE_PROMPT = """\
结合对话历史，将用户的省略/指代补全为完整的搜索查询。

对话历史:
{history}

用户当前问题: {query}

规则:
- 如果用户使用了"它"、"这个"、"那个"等指代词，替换为历史中提到的主体
- 如果当前问题是全新话题，保持原样
- 只返回改写后的查询，不要额外解释
- 最多20个字

改写后的查询:"""

async def _rewrite_query(self, query: str, history: list[dict]) -> str:
    if not history:
        return query
    # 取最近3轮对话
    recent = history[-6:]
    history_text = "\n".join(
        f"{'用户' if h['role']=='user' else '助手'}: {h['content'][:100]}"
        for h in recent
    )
    prompt = REWRITE_PROMPT.format(history=history_text, query=query)
    rewritten = await self.llm.complete(prompt, max_tokens=30)
    return rewritten.strip() or query
```

### 合并到 M1 API

M1 的 `http_server.py` 新增一个端点：

```python
@app.post("/api/chat")
async def chat_endpoint(body: ChatRequest):
    """对话式搜索 — SSE 流式响应"""
    if not body.query.strip():
        raise HTTPException(400, "query is required")
    pipeline = ChatPipeline(kb_path, llm_client, rank_model)
    return StreamingResponse(
        _sse_generator(pipeline.chat(body.query, body.history, body.mode)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

async def _sse_generator(events: AsyncIterator[ChatEvent]):
    async for event in events:
        yield f"event: {event.type}\ndata: {json.dumps(event.data)}\n\n"
```

## Frontend: ChatPanel

### 组件位置

ChatPanel 是 M1 三栏布局的**新右侧面板**（可切换：图谱视图 ↔ 对话视图）。

```
┌────────────┬────────────────────────┬───────────────────┐
│  Sidebar   │  MainContent           │  RightPanel       │
│  (280px)   │  (flex-grow)           │  (360px)          │
│            │                        │                   │
│  Tree      │  [Dashboard / Module]  │  [Graph | Chat]   │ ← 切换tab
│            │                        │                   │
└────────────┴────────────────────────┴───────────────────┘
```

### ChatPanel.tsx

```typescript
interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: Citation[];
  followUps?: string[];
  timestamp: Date;
}

interface Citation {
  key: string;       // "auth/jwt-config"
  title: string;
  snippet: string;
  confidence: string;
}

function ChatPanel() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [currentStreaming, setCurrentStreaming] = useState('');
  const [currentSources, setCurrentSources] = useState<Citation[]>([]);
  const [statusText, setStatusText] = useState('');

  async function sendMessage(query: string) {
    const userMsg: ChatMessage = { id: nanoid(), role: 'user', content: query, timestamp: new Date() };
    setMessages(prev => [...prev, userMsg]);
    setIsStreaming(true);
    setCurrentStreaming('');
    setCurrentSources([]);

    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query,
        history: messages.map(m => ({ role: m.role, content: m.content })),
        mode: 'precise',
      }),
    });

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let answerText = '';
    let sources: Citation[] = [];

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
            setStatusText(event.message || event.stage);
            break;
          case 'token':
            answerText += event.text;
            setCurrentStreaming(answerText);
            break;
          case 'citation':
            sources.push(event);
            setCurrentSources([...sources]);
            break;
          case 'done':
            const assistantMsg: ChatMessage = {
              id: nanoid(), role: 'assistant',
              content: answerText,
              sources: event.sources,
              followUps: event.follow_ups,
              timestamp: new Date(),
            };
            setMessages(prev => [...prev, assistantMsg]);
            setIsStreaming(false);
            setCurrentStreaming('');
            setCurrentSources([]);
            break;
          case 'error':
            setIsStreaming(false);
            break;
        }
      }
    }
  }

  return (
    <div className="chat-panel">
      <div className="chat-messages">
        {messages.map(msg => (
          <ChatMessage key={msg.id} message={msg} />
        ))}
        {isStreaming && (
          <ChatMessage
            message={{ role: 'assistant', content: currentStreaming }}
            isStreaming
            liveSources={currentSources}
          />
        )}
      </div>
      <ChatInput onSend={sendMessage} disabled={isStreaming} />
    </div>
  );
}
```

### ChatMessage 渲染

```typescript
function ChatMessage({ message, isStreaming, liveSources }) {
  return (
    <div className={`chat-message ${message.role}`}>
      <div className="chat-message-content">
        <MarkdownText text={message.content} />
        {message.sources && message.sources.length > 0 && (
          <div className="chat-sources">
            <span className="sources-label">参考:</span>
            {message.sources.map(s => (
              <CitationBadge key={s.key} citation={s} />
            ))}
          </div>
        )}
        {message.followUps && (
          <div className="chat-followups">
            {message.followUps.map(q => (
              <button key={q} onClick={() => onFollowUp(q)}>{q}</button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

### CitationBadge — 悬浮卡片

点击引用徽章时，弹出模块摘要卡片（不跳转页面）：

```typescript
function CitationBadge({ citation }: { citation: Citation }) {
  return (
    <span className="citation-badge" title={`${citation.title}: ${citation.snippet}`}>
      📄 {citation.title}
      <span className="citation-confidence">{citation.confidence}</span>
    </span>
  );
}
```

### 流式文本的 Markdown 增量渲染

M1 的 ContentBlock 组件扩展支持流式 Markdown 渲染：

```typescript
// 使用简单的流式渲染: 逐字显示 + 检测代码块边界
function MarkdownText({ text, isStreaming }: { text: string; isStreaming?: boolean }) {
  // 将文本拆分为段落，检测代码块 ``` 边界
  const blocks = parseStreamingMarkdown(text);
  return (
    <>
      {blocks.map((block, i) => {
        if (block.type === 'code')
          return <pre key={i}><code>{block.content}</code></pre>;
        if (block.type === 'text')
          return <p key={i}>{block.content}</p>;
        return null;
      })}
      {isStreaming && <span className="cursor-blink">▌</span>}
    </>
  );
}
```

## CLI 集成

M2 新增 `km chat` 命令（终端对话）：

```bash
$ km chat
🤖 KM Chat (precise mode). Type /quit to exit.

You: JWT的过期时间是多少？

🔍 分析查询意图... (reference)
📚 检索相关知识... (15 candidates → top 5)
🤖 JWT Access Token的过期时间是24小时，Refresh Token的过期时间是7天。
   我们选择24小时是在安全性和用户体验之间的平衡。
   [ref: auth/jwt-config] [ref: auth/oauth-flow]

💡 相关追问:
  1. 怎么配置JWT的refresh token?
  2. RS256和HS256的区别是什么?
  3. Token黑名单是怎么实现的?

You: 怎么配置refresh token?

🤖 Refresh Token配置在 settings.py 中:
   JWT_REFRESH_TOKEN_EXPIRE_DAYS = 7
   ...
```

**实现:** CLI 命令调用 ChatPipeline.chat()，输出到终端（非SSE，直接打印完整结果）。

## 新增/修改文件

| 文件 | 操作 | 内容 |
|------|------|------|
| `src/knowledge_manager/chat.py` | **新建** | ChatPipeline + ChatEvent + 六阶段流水线 |
| `src/knowledge_manager/http_server.py` | 修改 | 新增 `POST /api/chat` SSE端点 |
| `src/knowledge_manager/cli.py` | 修改 | 新增 `km chat` 命令 |
| `src/ui/components/ChatPanel.tsx` | **新建** | 对话面板 |
| `src/ui/components/ChatMessage.tsx` | **新建** | 单条消息渲染 |
| `src/ui/components/ChatInput.tsx` | **新建** | 输入框 |
| `src/ui/components/CitationPopover.tsx` | **新建** | 引用悬浮卡片 |
| `src/ui/hooks/useChat.ts` | **新建** | SSE流消费Hook |
| `src/ui/components/Layout.tsx` | 修改 | 右侧栏增加 Graph/Chat tab切换 |
| `tests/test_chat.py` | **新建** | ChatPipeline 测试 |

## Gate Pass 标准

- [ ] `POST /api/chat` 返回有效的 SSE 流
- [ ] SSE 流包含所有6种事件类型 (status/token/citation/done/error)
- [ ] 对话面板显示消息历史 + 流式生成中的文本
- [ ] 引用徽章可点击，显示模块摘要
- [ ] 追问建议可点击发起新对话
- [ ] `km chat` CLI 可用
- [ ] 空查询返回 400
- [ ] 知识库为空时对话仍可用（LLM直接回答 + 标注"无相关知识"）
