# M6 Spec — Web UI 编辑模式 + 审核工作流

> Phase 5 M6 | 2026-06-09 | 硬依赖: M1 (UI shell), M5 (Markdown格式)

## 概述

在 M1 只读 Web UI + M5 Markdown 格式基础上，增加：模块编辑器、新建模块、审核面板、拖拽树排序。核心交付物：编辑端点 + ModuleEditor组件 + StagingPanel组件 + 拖拽树。

## Backend: 写操作端点

### `POST /api/modules` — 新建模块

**请求体:**
```json
{
  "id": "new-endpoint",
  "category": "backend",
  "title": "新API端点规范",
  "summary": "...",
  "content": {
    "overview": "...",
    "details": "..."
  },
  "metadata": {
    "tags": ["api", "rest"],
    "confidence": "medium"
  },
  "submit_to_staging": true
}
```
- `submit_to_staging=true` → 写入 `.staging/` 而非直接发布
- `submit_to_staging=false` → 直接发布 (仅当用户有权限，M13后引入RBAC)

**响应 201:**
```json
{
  "id": "new-endpoint",
  "category": "backend",
  "status": "staged",
  "review_required": true
}
```

### `PUT /api/modules/:cat/:id` — 更新模块

**请求体:** 部分 Module JSON（仅包含要更新的字段）

```json
{
  "title": "JWT配置 (更新版)",
  "content": {
    "details": "更新后的细节内容..."
  },
  "metadata": {
    "tags": ["auth", "jwt", "security", "token"]
  }
}
```

**响应 200:** 更新后的完整 Module

**行为:**
- 直接修改 `.json` 和 `.md` 文件（通过 M5 同步）
- 若模块 status=draft → 保持 draft
- 若模块 status=published → 版本历史记录 (git commit)

### `DELETE /api/modules/:cat/:id` — 删除模块

**响应 200:** `{"deleted": "backend/old-module"}`
**确认:** 请求头 `X-Confirm-Delete: true` 必需

### `GET /api/staging` — 审核列表

**响应 200:**
```json
{
  "items": [
    {
      "module_id": "grpc-best-practices",
      "status": "pending",
      "submitted_by": "张三",
      "submitted_at": "2026-06-09T10:00:00Z",
      "approvals": 0,
      "required_approvals": 1,
      "module_summary": "gRPC服务间通信的最佳实践...",
      "preview": { "title": "gRPC最佳实践", "category": "backend", "tags": ["grpc", "rpc"] }
    }
  ]
}
```

### `POST /api/staging/:module_id/approve` — 批准

```json
{"comment": "LGTM"}
```
**响应:** 200 (若达到所需批准数则自动merge) 或 202 (还需更多批准)

### `POST /api/staging/:module_id/reject` — 拒绝

```json
{"comment": "需要补充错误处理部分"}
```
**响应 200:** 草稿保留在.staging/，状态变为 changes-requested

### `PUT /api/tree` — 更新知识树

```json
{
  "action": "move",
  "node_id": "auth/jwt-config",
  "new_parent": "deployment",
  "position": 0
}
```

支持 action: `move` | `reorder` | `add_section` | `remove_section`

## Frontend: 编辑模式

### 模式切换

M1 的只读查看器 → M6 增加编辑模式切换：

```
┌─────────────────────────────────────────────┐
│  Header: [...]             [只读 | 编辑 ✏️] │
└─────────────────────────────────────────────┘
```

编辑模式开启后：
- ModuleViewer 变为 ModuleEditor (可编辑的 Markdown 编辑器)
- KnowledgeTree 节点可拖拽
- 右上角出现 "新建模块" 按钮

### ModuleEditor.tsx

```typescript
function ModuleEditor({ category, moduleId, isNew }: {
  category: string; moduleId?: string; isNew?: boolean;
}) {
  // 若 moduleId 存在 → 加载现有模块
  // 若 isNew → 空白模板

  const [frontmatter, setFrontmatter] = useState({
    id: '', category: '', title: '', summary: '',
    tags: [], confidence: 'medium', status: 'draft',
    related_modules: [],
  });

  const [body, setBody] = useState({
    overview: '', details: '', examples: '', references: '', caveats: '',
  });

  async function save() {
    const module = { ...frontmatter, content: body, metadata: { tags: frontmatter.tags, ... } };
    if (isNew) {
      await post('/api/modules', module);
    } else {
      await put(`/api/modules/${category}/${moduleId}`, module);
    }
  }

  return (
    <div className="module-editor">
      {/* Frontmatter 表单 */}
      <FrontmatterForm data={frontmatter} onChange={setFrontmatter} />

      {/* Markdown 编辑器 (M5提供parse/render能力) */}
      <MarkdownEditor
        sections={body}
        onChange={setBody}
      />

      <div className="editor-actions">
        <button onClick={save}>保存</button>
        <button onClick={preview}>预览</button>
      </div>
    </div>
  );
}
```

### 编辑器前端技术方案

M6 使用简单的 textarea + 实时预览（左右分栏）：

```
┌──────────────────────────┬──────────────────────────┐
│  编辑 (Markdown)          │  预览 (渲染后)            │
│                          │                          │
│  # 概述                  │  [渲染的HTML]             │
│                          │                          │
│  这是概述内容...          │  这是概述内容...          │
│                          │                          │
│  # 细节                  │  [渲染的HTML]             │
│                          │                          │
│  ...                     │  ...                     │
└──────────────────────────┴──────────────────────────┘
```

**后续增强 (不做在M6):** 引入 CodeMirror 6 或 Monaco Editor 做完整 Markdown 编辑器体验。

### KnowledgeTree 拖拽 (M6增强)

在 M1 KnowledgeTree 基础上增加拖拽：

```typescript
function DraggableTreeNode({ node, onMove }: DraggableNodeProps) {
  const dragRef = useDrag({
    type: 'tree-node',
    item: { id: node.id },
    canDrag: node.type !== 'root',
  });

  const dropRef = useDrop({
    accept: 'tree-node',
    drop: (item) => onMove(item.id, node.id),
  });

  return (
    <div ref={mergeRefs(dragRef, dropRef)} className="tree-node">
      {/* ... existing node render ... */}
    </div>
  );
}
```

拖拽操作:
- 拖到某节点上 = 移动为该节点的子节点
- 拖到某节点上下方 = 同级重新排序
- 拖到树外 = 取消父子关系
- 每次拖拽完成 → `PUT /api/tree` 持久化

### StagingPanel.tsx — 审核面板

```typescript
function StagingPanel() {
  const [items, setItems] = useState<StagingItem[]>([]);

  // GET /api/staging → 列表
  // POST /api/staging/:id/approve → 批准
  // POST /api/staging/:id/reject → 拒绝

  return (
    <div className="staging-panel">
      <h2>待审核模块 ({items.length})</h2>
      {items.map(item => (
        <StagingCard key={item.module_id} item={item}>
          <button onClick={() => approve(item.module_id)}>批准</button>
          <button onClick={() => reject(item.module_id)}>拒绝</button>
          <DiffViewer moduleId={item.module_id} />
        </StagingCard>
      ))}
    </div>
  );
}
```

## 新增/修改文件

| 文件 | 操作 | 内容 |
|------|------|------|
| `src/knowledge_manager/http_server.py` | 修改 | +POST/PUT/DELETE模块 + staging端点 + tree端点 |
| `src/ui/components/ModuleEditor.tsx` | **新建** | 编辑模式 + Markdown编辑器 |
| `src/ui/components/FrontmatterForm.tsx` | **新建** | Frontmatter表单 |
| `src/ui/components/MarkdownEditor.tsx` | **新建** | 左右分栏编辑/预览 |
| `src/ui/components/StagingPanel.tsx` | **新建** | 审核面板 |
| `src/ui/components/DiffViewer.tsx` | **新建** | 模块差异对比 |
| `src/ui/components/Layout.tsx` | 修改 | +编辑模式切换 + 新建模块按钮 |
| `src/ui/components/KnowledgeTree.tsx` | 修改 | +拖拽支持 |
| `src/ui/hooks/useEditor.ts` | **新建** | 编辑状态管理 |
| `tests/test_http_edit.py` | **新建** | 编辑端点测试 |
| `tests/test_staging_api.py` | **新建** | 审核API测试 |

## Gate Pass 标准

- [ ] 新建模块 → staging → 审核批准 → 发布 (完整流程)
- [ ] 编辑现有模块 → JSON/MD 同步更新
- [ ] Markdown 编辑器左右分栏实时预览
- [ ] 审核面板: 批准/拒绝/查看diff
- [ ] 知识树拖拽重排 → 刷新后保持
- [ ] 删除模块有确认对话框
- [ ] 编辑模式切换不影响只读用户体验
- [ ] 未保存修改离开页面时提示
- [ ] 现有 M1 端点不受影响
