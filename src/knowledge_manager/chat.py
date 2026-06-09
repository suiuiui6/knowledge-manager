import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Optional

from knowledge_manager.llm_clients import BaseLLMClient
from knowledge_manager.storage import _classify_intent, load_module, search_modules

logger = logging.getLogger("knowledge_manager.chat")


@dataclass
class ChatEvent:
    type: str
    data: dict


def _snippet(text: str, query: str, maxlen: int = 100) -> str:
    if not text or not query:
        return text[:maxlen] if len(text) > maxlen else text
    terms = query.lower().split()
    text_lower = text.lower()
    best_pos = -1
    for term in terms:
        pos = text_lower.find(term)
        if pos != -1 and (best_pos == -1 or pos < best_pos):
            best_pos = pos
    if best_pos == -1:
        return text[:maxlen] + ("..." if len(text) > maxlen else "")
    start = max(0, best_pos - maxlen // 2)
    end = min(len(text), best_pos + maxlen // 2)
    s = text[start:end]
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return prefix + s + suffix


REWRITE_PROMPT = """Combine the conversation history to resolve any pronouns or omissions in the user's current query into a complete, self-contained search query.

Conversation history:
{history}

User's current query: {query}

Rules:
- If the user uses words like "it", "this", "that", replace them with the actual subject from the history
- If the query is a follow-up question, incorporate the context from previous turns
- If it's a completely new topic, keep the original query
- Return ONLY the rewritten query, nothing else. Max 50 words.

Rewritten query:"""


SYSTEM_PROMPT = """You are a knowledgeable assistant answering questions based on a team's knowledge base.

Relevant knowledge modules:
{module_context}

Rules:
- Answer based on the provided knowledge modules
- Cite sources using [ref:category/id] when using information from a module
- If different modules give conflicting information, point it out
- If the modules don't contain enough information, say so honestly
- Keep answers concise and practical
- Use the same language as the user's query"""


FOLLOW_UP_PROMPT = """Based on the conversation below, suggest 3 natural follow-up questions the user might ask next.
Return ONLY a JSON array of strings, no other text.

User: {query}
Assistant: {response}

Follow-up questions (JSON array):"""


class ChatPipeline:
    def __init__(
        self,
        kb_path: Path,
        llm_client: BaseLLMClient,
        tree_index=None,
        vector_index=None,
    ):
        self.kb_path = kb_path
        self.llm = llm_client
        self.tree_index = tree_index
        self.vector_index = vector_index

    async def chat(
        self,
        query: str,
        history: list[dict],
        mode: str = "precise",
    ) -> AsyncIterator[ChatEvent]:
        t_start = time.time()

        # ── Step 1: Query understanding ──
        yield ChatEvent("status", {"stage": "query_understanding", "message": "Understanding query..."})

        rewritten = await self._rewrite_query(query, history)
        intent = _classify_intent(rewritten)

        yield ChatEvent("status", {
            "stage": "query_understanding",
            "rewritten": rewritten,
            "intent": intent,
        })

        # ── Step 2: Multi-recall ──
        yield ChatEvent("status", {"stage": "retrieval", "message": "Retrieving knowledge..."})

        keyword_results = await self._keyword_recall(rewritten)
        tree_results = await self._tree_recall(rewritten, intent)
        vector_results = await self._vector_recall(rewritten)

        # ── Step 3: RRF fusion ──
        yield ChatEvent("status", {"stage": "ranking", "message": "Ranking results..."})

        fused = self._rrf_fuse(
            tree=tree_results,
            keyword=keyword_results,
            vector=vector_results,
            weights={"tree": 0.35 if tree_results else 0, "keyword": 0.65 if not tree_results else 0.40, "vector": 0.25 if vector_results else 0},
        )
        top_modules = fused[:5]

        yield ChatEvent("status", {
            "stage": "ranking",
            "candidates": len(fused),
            "selected": len(top_modules),
            "top_titles": [m["title"] for m in top_modules],
        })

        # ── Step 4: Context assembly ──
        yield ChatEvent("status", {"stage": "context_assembly", "message": "Assembling context..."})

        system_prompt = self._build_system_prompt(top_modules, intent)
        user_prompt = rewritten

        # ── Step 5: LLM generation (streaming) ──
        yield ChatEvent("status", {"stage": "generation", "message": "Generating answer..."})

        full_response = ""
        citations = {}

        temp = 0.3 if mode == "precise" else 0.7
        async for chunk in self._stream_llm(system_prompt, user_prompt, temperature=temp):
            full_response += chunk
            source_key = self._detect_citation(chunk, top_modules)
            yield ChatEvent("token", {"text": chunk, "source": source_key})

        # ── Step 6: Post-processing ──
        cited_modules = []
        for key in self._collect_citations(full_response, top_modules):
            mod = top_modules[0] if top_modules else None
            parts = key.split("/", 1)
            if len(parts) == 2:
                mod = load_module(parts[1], parts[0], self.kb_path)
            if mod:
                cited_modules.append({
                    "key": key,
                    "title": mod.title,
                    "snippet": mod.summary,
                    "confidence": mod.metadata.confidence,
                })
                yield ChatEvent("citation", {
                    "key": key,
                    "title": mod.title,
                    "snippet": mod.summary,
                    "confidence": mod.metadata.confidence,
                })

        follow_ups = await self._generate_follow_ups(query, full_response)

        took_ms = int((time.time() - t_start) * 1000)
        yield ChatEvent("done", {
            "took_ms": took_ms,
            "sources": cited_modules,
            "follow_ups": follow_ups,
        })

    async def _rewrite_query(self, query: str, history: list[dict]) -> str:
        if not history:
            return query
        recent = history[-6:]
        history_text = "\n".join(
            f"{'User' if h['role'] == 'user' else 'Assistant'}: {h['content'][:150]}"
            for h in recent
        )
        prompt = REWRITE_PROMPT.format(history=history_text, query=query)
        try:
            rewritten = await self.llm.complete(prompt)
            result = rewritten.strip()
            return result if result else query
        except Exception:
            logger.warning("Query rewriting failed, using original query")
            return query

    async def _keyword_recall(self, query: str) -> list[dict]:
        results = search_modules(query, self.kb_path, limit=20)
        return [
            {
                "key": f"{r.module.category}/{r.module.id}",
                "title": r.module.title,
                "summary": r.module.summary,
                "confidence": r.module.metadata.confidence,
                "source": "keyword",
                "module": r.module,
            }
            for r in results
        ]

    async def _tree_recall(self, query: str, intent: str) -> list[dict]:
        if not self.tree_index:
            return []
        from knowledge_manager.tree_navigator import TreeNavigator

        navigator = TreeNavigator(self.tree_index, self.llm)
        try:
            result = await navigator.navigate(query)
            if result.final_module_key:
                parts = result.final_module_key.split("/", 1)
                if len(parts) == 2:
                    mod = load_module(parts[1], parts[0], self.kb_path)
                    if mod:
                        return [{
                            "key": result.final_module_key,
                            "title": result.final_title or mod.title,
                            "summary": result.final_summary or mod.summary,
                            "confidence": mod.metadata.confidence,
                            "source": "tree",
                            "module": mod,
                            "navigation_confidence": result.confidence,
                        }]
        except Exception:
            logger.debug("Tree navigation failed, skipping tree recall")
        return []

    async def _vector_recall(self, query: str) -> list[dict]:
        if not self.vector_index:
            return []
        return []

    def _rrf_fuse(
        self,
        tree: list[dict],
        keyword: list[dict],
        vector: list[dict],
        weights: dict,
    ) -> list[dict]:
        k_tree = 30
        k_keyword = 60
        k_vector = 120

        ranks: dict[str, dict] = {}
        scores: dict[str, float] = {}

        for i, item in enumerate(tree):
            key = item["key"]
            ranks[key] = item
            scores[key] = weights.get("tree", 0) / (k_tree + i + 1)

        for i, item in enumerate(keyword):
            key = item["key"]
            if key not in ranks:
                ranks[key] = item
            scores[key] = scores.get(key, 0) + weights.get("keyword", 0.65) / (k_keyword + i + 1)

        for i, item in enumerate(vector):
            key = item["key"]
            if key not in ranks:
                ranks[key] = item
            scores[key] = scores.get(key, 0) + weights.get("vector", 0) / (k_vector + i + 1)

        sorted_keys = sorted(scores, key=scores.get, reverse=True)
        return [ranks[k] for k in sorted_keys if k in ranks]

    def _build_system_prompt(self, modules: list[dict], intent: str) -> str:
        lines = []
        for m in modules:
            lines.append(f"- [{m['key']}] {m['title']}: {m['summary'][:200]}")
        module_context = "\n".join(lines) if lines else "No relevant modules found in the knowledge base."
        return SYSTEM_PROMPT.format(module_context=module_context)

    async def _stream_llm(self, system: str, user: str, temperature: float = 0.3) -> AsyncIterator[str]:
        try:
            import httpx
            cfg = self.llm.config
            base = cfg.base_url or "https://api.deepseek.com"
            url = f"{base}/v1/chat/completions"

            payload = {
                "model": cfg.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
                "max_tokens": cfg.max_tokens,
                "stream": True,
            }
            headers = {"Authorization": f"Bearer {cfg.api_key}"}

            async with httpx.AsyncClient() as client:
                async with client.stream("POST", url, json=payload, headers=headers, timeout=120) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                delta = data.get("choices", [{}])[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue
        except Exception as e:
            logger.warning("Streaming failed, falling back to non-streaming: %s", e)
            try:
                response = await self.llm.complete(
                    f"{system}\n\nUser query: {user}\n\nAnswer:"
                )
                yield response
            except Exception:
                yield "Sorry, I couldn't generate a response. Please try again."

    def _detect_citation(self, chunk: str, modules: list[dict]) -> Optional[str]:
        for m in modules:
            key = m["key"]
            if key in chunk:
                return key
        return None

    def _collect_citations(self, response: str, modules: list[dict]) -> set[str]:
        cited = set()
        for m in modules:
            key = m["key"]
            if key in response:
                cited.add(key)
        return cited

    async def _generate_follow_ups(self, query: str, response: str) -> list[str]:
        if not response or len(response) < 50:
            return []
        prompt = FOLLOW_UP_PROMPT.format(query=query, response=response[:1000])
        try:
            result = await self.llm.complete(prompt)
            parsed = json.loads(result.strip())
            if isinstance(parsed, list):
                return parsed[:3]
        except Exception:
            logger.debug("Follow-up generation failed")
        return []
