# M3 Spec — 知识树 + LLM推理导航

> Phase 5 M3 | 2026-06-09 | 硬依赖: 无 | 软依赖: M2 (作为ChatPipeline的第三路召回)

## 概述

将 M1 中从 categories 临时生成的平铺树升级为真正的层次化知识树，并实现 LLM 在树上的多步推理导航。核心交付物：层次化知识树数据模型 + 三种构建方式 + TreeNavigator。

## 数据模型

### schemas.py 新增

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
    path: str = ""
    page_range: Optional[tuple[int, int]] = None
    children: list["TreeNode"] = Field(default_factory=list)
    # 非module节点的聚合信息
    module_count: int = 0
    word_count: int = 0
    # module/section节点特有
    confidence: Optional[str] = None
    status: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
```

### Index 模型改造

```python
class Index(BaseModel):
    # ... 现有字段 ...
    tree: Optional[TreeNode] = None  # M3新增
```

## 树的三种构建方式

### 方式A：Markdown标题提取 (`tree_builder.py`)

```python
def build_tree_from_markdown(md_text: str, category: str) -> TreeNode:
    """
    解析 Markdown 标题层级:
    # 认证与授权          → category 节点 (level 1)
    ## JWT配置            → module 节点 (level 2)
    ### 签名算法选择      → section 节点 (level 3, 挂在 module 下)
    """
    # 核心算法: 栈式追踪标题层级
    # - 遇到 level=N 标题, 弹出栈中 >= N 的节点
    # - 新节点挂到栈顶节点的 children
    # - 推入栈中
```

**触发时机:** `km add` 提取模块后自动对提取源文本构建子树。M5 中每个模块的 `.md` 文件也可被解析。

**slugify 中文标题:**
```python
def slugify(title: str) -> str:
    """中文标题 → kebab-case id"""
    # 方案: 用 jieba 分词 + 拼音首字母, 或用简单的 hash 截断
    # M3 初始方案: 保留纯ASCII字符, 中文替换为 pinyin 首字母
```

### 方式B：LLM自动构建

```python
async def build_tree_from_llm(modules: list[Module], llm_client) -> TreeNode:
    """
    将扁平模块列表交给LLM构建层次化分组:
    - 输入: 所有模块的 [category, id, title, summary, tags, related_modules]
    - LLM根据主题逻辑关系将模块组织成树
    - 紧密相关的模块(互相引用)放在同一子树
    """
```

**CLI 触发:**
```bash
km tree build --llm
# 输出: 建议的树结构预览 → 确认 → 写入 index.json
```

### 方式C：Web UI 手动拖拽 (M6中实现)

在 M6 的编辑模式中，KnowledgeTree 组件支持拖拽重排。

## 树存储与查询

### storage.py 新增

```python
def save_tree(tree: TreeNode, kb_path: Path) -> None:
    index = load_index(kb_path)
    index.tree = tree
    save_index(index, kb_path)

def get_tree(kb_path: Path) -> TreeNode:
    """升级M1版本：优先返回 index.tree，fallback到category平铺"""
    index = load_index(kb_path)
    if index is None:
        return TreeNode(id="root", type=TreeNodeType.ROOT, title="Empty KB")
    if index.tree is not None:
        return index.tree
    return _build_tree_from_categories(index)  # M1 fallback

def get_subtree(node_path: str, kb_path: Path) -> Optional[TreeNode]:
    """在树中查找指定路径的节点，返回以它为根的子树 (深度=2)"""

def find_modules_under(node: TreeNode) -> list[str]:
    """递归收集某节点下所有 module 的 key (category/id)"""
```

### rebuild_index 增强

```python
def rebuild_index(kb_path: Path, build_tree: bool = False) -> Index:
    index = load_index(kb_path) or Index()
    # ... 现有逻辑 ...
    if build_tree and index.tree is None:
        # 从 Markdown 文件自动构建 (M5后)
        from knowledge_manager.tree_builder import build_tree_from_files
        index.tree = build_tree_from_files(kb_path)
    elif not build_tree and index.tree is None:
        index.tree = _build_tree_from_categories(index)  # M1 fallback
    save_index(index, kb_path)
    return index
```

## LLM 推理导航 (`tree_navigator.py`)

### 核心算法

```python
class TreeNavigator:
    """LLM在知识树上的多步推理导航"""

    def __init__(self, tree_root: TreeNode, llm_client, max_steps: int = 5):
        self.tree_root = tree_root
        self.llm = llm_client
        self.max_steps = max_steps

    async def navigate(self, query: str) -> NavigationResult:
        """
        从根开始，每步让LLM选择: explore | drill | load | backtrack | done
        - explore: 查看当前节点的子节点列表
        - drill: 深入某个子节点
        - load: 加载某个module的完整内容
        - backtrack: 回退到父节点探索其他分支
        - done: 当前节点就是最佳答案

        最大步数: max_steps (默认5)
        """
```

### 导航Prompt

```
你是一个知识库导航助手，在知识树上找到最能回答用户问题的模块。

知识树结构 (当前节点: {current_node.title}):
{tree_snapshot}

导航规则:
1. 如果子节点中有明显匹配的，drill进去
2. 如果当前层级没有明显匹配，列出候选，请求澄清
3. 如果到达叶子模块且内容匹配，done
4. 如果叶子模块不够，backtrack
5. 最多导航 {max_steps} 步。当前第 {step_num} 步。

用户问题: {query}

请按JSON格式返回下一步决策:
{"action": "explore|drill|load|backtrack|done", "target_node": "node-id", "reasoning": "..."}
```

### 返回结构

```python
@dataclass
class NavigationStep:
    step: int
    action: str
    node_id: str
    node_title: str
    reasoning: str

@dataclass
class NavigationResult:
    query: str
    path: list[NavigationStep]      # 完整导航路径
    final_module: Optional[Module]  # 最终找到的模块
    alternatives: list[Module]      # 备选模块
    confidence: float               # 0-1
```

## 与搜索流水线的集成

### ChatPipeline 中启用树召回 (M2增强)

```python
# chat.py — _tree_recall 从空实现变为真实调用
async def _tree_recall(self, query: str, intent: str) -> list[ScoredModule]:
    if not self.tree_index:
        return []
    navigator = TreeNavigator(self.tree_index, self.llm)
    result = await navigator.navigate(query)
    if result.final_module:
        return [ScoredModule(module=result.final_module, score=result.confidence,
                             source="tree", highlights=None,
                             navigation_path=result.path)]
    return []
```

### RRF权重重调

```
M2 (无tree): keyword=0.75, vector=0.0
M3 (有tree): keyword=0.40, tree=0.35, vector=0.0
M10 (全量):  keyword=0.35, tree=0.30, vector=0.25
```

## CLI

```bash
# 查看知识树
km tree show                    # 打印树结构
km tree show auth               # 只看 auth 子树
km tree show auth/jwt-config    # 模块在树中的位置 + 兄弟节点

# LLM构建树
km tree build --llm             # 让LLM重新组织树结构
km tree build --from-md         # 从Markdown标题重建

# LLM树导航
km tree navigate "jwt的签名算法是什么"
  → 输出导航路径 (root → auth → auth/jwt-config → [section]签名算法)
  → 加载对应模块内容
```

## 新增/修改文件

| 文件 | 操作 | 内容 |
|------|------|------|
| `src/knowledge_manager/tree_builder.py` | **新建** | build_tree_from_markdown, build_tree_from_llm, slugify |
| `src/knowledge_manager/tree_navigator.py` | **新建** | TreeNavigator + NavigationResult |
| `src/knowledge_manager/schemas.py` | 修改 | +TreeNode, TreeNodeType |
| `src/knowledge_manager/storage.py` | 修改 | +save_tree, get_tree增强, get_subtree, find_modules_under |
| `src/knowledge_manager/chat.py` | 修改 | _tree_recall 启用真实调用 |
| `src/knowledge_manager/http_server.py` | 修改 | `/api/tree` 返回版本升级 |
| `src/knowledge_manager/cli.py` | 修改 | +tree命令组 |
| `src/ui/components/KnowledgeTree.tsx` | 修改 | 支持section级节点 + 导航路径高亮 |
| `tests/test_tree.py` | **新建** | 树构建 + 导航测试 |

## Gate Pass 标准

- [ ] `rebuild_index` 自动生成category级树 (fallback)
- [ ] `build_tree_from_markdown` 正确解析 H1/H2/H3 层级
- [ ] `km tree build --llm` 生成合理树结构 (人工评审)
- [ ] TreeNavigator 从根导航到正确叶子模块 (≥80%准确率)
- [ ] `/api/tree` 返回完整树 JSON
- [ ] `/api/tree/:cat/:id` 返回子树
- [ ] ChatPipeline 树召回通路正常工作 (M2的ChatPanel能显示树召回来源)
- [ ] 现有 `/api/modules` 不受影响 (向后兼容)
