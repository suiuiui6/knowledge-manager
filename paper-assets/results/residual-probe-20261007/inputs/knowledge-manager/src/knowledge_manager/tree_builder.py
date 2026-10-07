import re
from pathlib import Path

from knowledge_manager.schemas import TreeNode, TreeNodeType


def slugify(title: str) -> str:
    """Chinese/English title -> kebab-case id. Falls back to simple hash for pure-CJK."""
    ascii_part = re.sub(r"[^a-zA-Z0-9\s-]", "", title).strip().lower()
    if ascii_part:
        return re.sub(r"\s+", "-", ascii_part)[:40]
    # Pure Chinese: use pinyin first letters, or hash
    try:
        import jieba
        from itertools import accumulate
        words = list(jieba.cut(title))
        initials = "".join(w[0] for w in words if w.strip())
        if len(initials) >= 3:
            return initials.lower()[:20]
    except ImportError:
        pass
    return f"sec-{abs(hash(title)) % 10000:04d}"


def build_tree_from_markdown(md_text: str, category: str) -> TreeNode:
    lines = md_text.split("\n")
    root = TreeNode(id="root", type=TreeNodeType.ROOT, title=category or "Root")
    stack: list[tuple[int, TreeNode]] = [(0, root)]
    current_module: TreeNode | None = None

    for line in lines:
        match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if not match:
            continue

        level = len(match.group(1))
        title = match.group(2).strip()
        node_id = slugify(title)

        while stack and stack[-1][0] >= level:
            stack.pop()

        parent = stack[-1][1]

        if level == 1:
            node = TreeNode(id=node_id, type=TreeNodeType.CATEGORY, title=title, path=node_id)
            parent.children.append(node)
            stack.append((level, node))
            current_module = None
        elif level == 2:
            parent_path = parent.path
            full_path = f"{parent_path}/{node_id}" if parent_path else node_id
            node = TreeNode(id=node_id, type=TreeNodeType.MODULE, title=title, path=full_path)
            parent.children.append(node)
            stack.append((level, node))
            current_module = node
        else:
            if current_module:
                full_path = f"{current_module.path}#{node_id}"
                node = TreeNode(id=f"{current_module.id}#{node_id}", type=TreeNodeType.SECTION, title=title, path=full_path)
                current_module.children.append(node)
                stack.append((level, node))

    return root


async def build_tree_from_llm(modules: list, llm_client) -> TreeNode:
    summaries = []
    for m in modules:
        key = f"{m.category}/{m.id}"
        tags_str = ", ".join(m.metadata.tags[:5]) if hasattr(m.metadata, "tags") else ""
        summaries.append(f"- [{key}] {m.title}: {m.summary[:100]}  tags:[{tags_str}]  related:{m.metadata.related_modules[:3]}")

    module_text = "\n".join(summaries[:200])

    prompt = f"""Organize the following knowledge modules into a hierarchical tree.

Modules:
{module_text}

Rules:
- Group modules by topic, not just by their current category
- Related modules (mutually referencing) should be in the same branch
- Modules with clear ordering (e.g. "Choosing X" before "Implementing X") should be ordered accordingly
- Create category-level groupings under the root

Return ONLY a JSON tree structure:
{{
  "children": [
    {{
      "id": "group-name",
      "type": "category",
      "title": "Group Title",
      "summary": "short description",
      "children": [
        {{ "id": "original-category/original-id", "type": "module", "title": "Module Title", "summary": "short summary" }}
      ]
    }}
  ]
}}"""

    response = await llm_client.complete(prompt)

    try:
        import json
        data = json.loads(response.strip())
        root = TreeNode(id="root", type=TreeNodeType.ROOT, title="Knowledge Base")
        _parse_llm_tree(data, root)
        return root
    except Exception:
        return TreeNode(id="root", type=TreeNodeType.ROOT, title="Knowledge Base (parse failed)")


def _parse_llm_tree(data: dict, parent: TreeNode) -> None:
    import json as _json
    for child_data in data.get("children", []):
        node_type = TreeNodeType(child_data.get("type", "module"))
        node = TreeNode(
            id=child_data.get("id", ""),
            type=node_type,
            title=child_data.get("title", ""),
            summary=child_data.get("summary", ""),
            path=child_data.get("id", ""),
        )
        if "children" in child_data:
            _parse_llm_tree(child_data, node)
        parent.children.append(node)


def rebuild_tree_from_files(kb_path: Path) -> TreeNode | None:
    """Scan .md files in kb_path and build tree from their headings. Returns None if no .md files."""
    from knowledge_manager.storage import list_modules

    modules = list_modules(kb_path)
    if not modules:
        return None

    root = TreeNode(id="root", type=TreeNodeType.ROOT, title="Knowledge Base")
    for m in modules:
        md_path = kb_path / m.category / f"{m.id}.md"
        if md_path.exists():
            try:
                subtree = build_tree_from_markdown(md_path.read_text(encoding="utf-8"), m.category)
                # Merge subtree children into root
                for child in subtree.children:
                    child.id = f"{m.category}/{child.id}"
                    if child.path and not child.path.startswith(m.category):
                        child.path = f"{m.category}/{child.path}"
                    root.children.append(child)
            except Exception:
                pass

    if not root.children:
        return None
    return root
