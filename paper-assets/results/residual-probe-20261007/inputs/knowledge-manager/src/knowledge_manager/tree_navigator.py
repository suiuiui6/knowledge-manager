import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from knowledge_manager.llm_clients import BaseLLMClient
from knowledge_manager.schemas import TreeNode, TreeNodeType

logger = logging.getLogger("knowledge_manager.tree_navigator")


@dataclass
class NavigationStep:
    step: int
    action: str
    node_id: str
    node_title: str
    reasoning: str
    candidates: list[str] = field(default_factory=list)


@dataclass
class NavigationResult:
    query: str
    path: list[NavigationStep]
    final_module_key: Optional[str] = None
    final_title: str = ""
    final_summary: str = ""
    alternatives: list[str] = field(default_factory=list)
    confidence: float = 0.0


NAVIGATION_PROMPT = """You are navigating a knowledge tree to find the module that best answers a user's question.

Current tree location:
{tree_snapshot}

Navigation state: Step {step_num}/{max_steps}
Previously visited: {visited}

User question: {query}

Choose your next action:
- "explore": list all children of the current node for consideration
- "drill": go deeper into a specific child node (provide target_node)
- "load": this node IS the answer, load its full content
- "backtrack": go back to the parent node and try another branch
- "done": you've found the best answer (provide reasoning)

Return ONLY a JSON object:
{{"action": "drill|load|backtrack|done", "target_node": "node-id", "reasoning": "why this choice", "confidence": 0.0-1.0}}"""


class TreeNavigator:
    def __init__(self, tree_root: TreeNode, llm_client: BaseLLMClient, max_steps: int = 5):
        self.tree_root = tree_root
        self.llm = llm_client
        self.max_steps = max_steps
        self._node_index: dict[str, TreeNode] = {}
        self._parent_map: dict[str, str] = {}
        self._build_index(tree_root, None)

    def _build_index(self, node: TreeNode, parent_id: str | None) -> None:
        self._node_index[node.id] = node
        if parent_id:
            self._parent_map[node.id] = parent_id
        for child in node.children:
            self._build_index(child, node.id)

    async def navigate(self, query: str) -> NavigationResult:
        steps: list[NavigationStep] = []
        current_node = self.tree_root
        visited: set[str] = set()

        for step_num in range(1, self.max_steps + 1):
            snapshot = self._render_snapshot(current_node)
            visited_str = ", ".join(visited) if visited else "none"

            prompt = NAVIGATION_PROMPT.format(
                tree_snapshot=snapshot,
                step_num=step_num,
                max_steps=self.max_steps,
                visited=visited_str,
                query=query,
            )

            try:
                response = await self.llm.complete(prompt)
                response = response.strip()
                if response.startswith("```"):
                    response = response.split("\n", 1)[1].rsplit("\n```", 1)[0]
                decision = json.loads(response)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning("Failed to parse LLM navigation response: %s", e)
                break

            action = decision.get("action", "done")
            target_id = decision.get("target_node", current_node.id)
            reasoning = decision.get("reasoning", "")
            confidence = decision.get("confidence", 0.5)

            children_ids = [c.id for c in current_node.children]
            step = NavigationStep(
                step=step_num, action=action, node_id=current_node.id,
                node_title=current_node.title, reasoning=reasoning,
                candidates=children_ids,
            )
            steps.append(step)

            if action == "done":
                return NavigationResult(
                    query=query, path=steps,
                    final_module_key=current_node.path or current_node.id,
                    final_title=current_node.title,
                    final_summary=current_node.summary,
                    alternatives=children_ids if current_node.type != TreeNodeType.MODULE else [],
                    confidence=confidence,
                )

            elif action == "load":
                target_node = self._node_index.get(target_id, current_node)
                return NavigationResult(
                    query=query, path=steps,
                    final_module_key=target_node.path or target_node.id,
                    final_title=target_node.title,
                    final_summary=target_node.summary,
                    alternatives=[c.id for c in target_node.children],
                    confidence=confidence,
                )

            elif action == "drill":
                if target_id in self._node_index:
                    visited.add(current_node.id)
                    current_node = self._node_index[target_id]
                elif current_node.children:
                    current_node = current_node.children[0]

            elif action == "backtrack":
                parent_id = self._parent_map.get(current_node.id)
                if parent_id and parent_id in self._node_index:
                    current_node = self._node_index[parent_id]
                else:
                    break

            elif action == "explore":
                pass

        best = self._find_best_leaf(current_node, query)
        if best and best.type == TreeNodeType.MODULE:
            return NavigationResult(
                query=query, path=steps,
                final_module_key=best.path or best.id,
                final_title=best.title,
                final_summary=best.summary,
                confidence=0.3,
            )

        return NavigationResult(query=query, path=steps, confidence=0.1)

    def _render_snapshot(self, node: TreeNode, depth: int = 2) -> str:
        lines = []
        self._render_node(node, depth, 0, lines)
        return "\n".join(lines)

    def _render_node(self, node: TreeNode, max_depth: int, current_depth: int, lines: list[str]) -> None:
        indent = "  " * current_depth
        icon = {"root": "[root]", "category": "[cat]", "module": "[mod]", "section": "[sec]"}.get(node.type.value if hasattr(node.type, 'value') else str(node.type), "[?]")
        lines.append(f"{indent}{icon} [{node.id}] {node.title}")
        if node.summary:
            lines.append(f"{indent}   {node.summary[:80]}")
        if current_depth < max_depth:
            for child in node.children:
                self._render_node(child, max_depth, current_depth + 1, lines)

    async def navigate_beam(self, query: str, beam_width: int = 3, max_depth: int = 3) -> NavigationResult:
        """Beam search: explore multiple branches in parallel, keep top-k.

        Unlike greedy navigate(), this evaluates all children at each level,
        scores them for relevance, and keeps the best `beam_width` paths.
        """
        steps: list[NavigationStep] = []
        candidates: list[tuple[TreeNode, float]] = [(self.tree_root, 1.0)]
        best_module: TreeNode | None = None
        best_module_score = 0.0

        for depth in range(max_depth):
            # Gather all children of all current candidates
            all_children: list[tuple[TreeNode, TreeNode, float]] = []  # (child, parent, parent_score)
            for parent, parent_score in candidates:
                for child in parent.children:
                    all_children.append((child, parent, parent_score))

            if not all_children:
                break

            # Score each child
            scored: list[tuple[TreeNode, float, str]] = []
            for child, parent, parent_score in all_children:
                kw_score = self._relevance_score(child, query)
                combined = 0.4 * parent_score + 0.6 * kw_score
                reasoning = f"keyword_rel={kw_score:.2f}, parent_score={parent_score:.2f}"
                scored.append((child, combined, reasoning))

            # If we're at module level and found good matches, track best
            for child, score, _ in scored:
                if child.type == TreeNodeType.MODULE and score > best_module_score:
                    best_module_score = score
                    best_module = child

            # Keep top-k
            scored.sort(key=lambda x: x[1], reverse=True)
            candidates = [(node, score) for node, score, _ in scored[:beam_width]]

            steps.append(NavigationStep(
                step=depth + 1, action="beam_expand",
                node_id=candidates[0][0].id if candidates else "none",
                node_title=f"evaluated {len(all_children)} nodes, kept {len(candidates)}",
                reasoning=f"top: {', '.join(f'{n.title}({s:.2f})' for n, s in candidates[:3])}",
                candidates=[n.id for n, _ in candidates],
            ))

        if best_module:
            return NavigationResult(
                query=query, path=steps,
                final_module_key=best_module.path or best_module.id,
                final_title=best_module.title,
                final_summary=best_module.summary,
                alternatives=[n.id for n, _ in candidates],
                confidence=best_module_score,
            )

        # Fallback to best leaf
        best = self._find_best_leaf(self.tree_root, query)
        if best and best.type == TreeNodeType.MODULE:
            return NavigationResult(
                query=query, path=steps,
                final_module_key=best.path or best.id,
                final_title=best.title,
                final_summary=best.summary,
                confidence=0.3,
            )
        return NavigationResult(query=query, path=steps, confidence=0.1)

    def _relevance_score(self, node: TreeNode, query: str) -> float:
        """Score node relevance to query using multi-field keyword matching."""
        query_lower = query.lower()
        query_terms = query_lower.split()
        score = 0.0

        title_lower = node.title.lower()
        summary_lower = node.summary.lower()

        # Title matches
        if query_lower in title_lower:
            score += 5.0
        for term in query_terms:
            if term in title_lower:
                score += 1.5

        # Summary matches
        if query_lower in summary_lower:
            score += 3.0
        for term in query_terms:
            if len(term) > 3 and term in summary_lower:
                score += 0.8

        # Tag matches
        if node.tags:
            for tag in node.tags:
                if query_lower in tag.lower() or tag.lower() in query_lower:
                    score += 2.0

        # Module type bonus (modules are leaf answers)
        if node.type == TreeNodeType.MODULE:
            score *= 1.2

        return min(score, 10.0)

    def _find_best_leaf(self, node: TreeNode, query: str) -> TreeNode | None:
        query_lower = query.lower()
        best: TreeNode | None = None
        best_score = 0.0

        def _search(n: TreeNode) -> None:
            nonlocal best, best_score
            if n.type == TreeNodeType.MODULE:
                score = 0.0
                if query_lower in n.title.lower():
                    score += 3
                if query_lower in n.summary.lower():
                    score += 2
                if n.tags:
                    for tag in n.tags:
                        if query_lower in tag.lower():
                            score += 1
                if score > best_score:
                    best_score = score
                    best = n
            for child in n.children:
                _search(child)

        _search(node)
        return best
