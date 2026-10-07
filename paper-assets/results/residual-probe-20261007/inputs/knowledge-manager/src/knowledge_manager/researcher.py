import asyncio
import logging
import subprocess
import uuid
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Callable, Optional

from knowledge_manager.llm_clients import BaseLLMClient
from knowledge_manager.schemas import ResearchConfig, ResearchSource

logger = logging.getLogger("knowledge_manager.researcher")


FORBIDDEN_PATHS = [
    "/etc/", "/proc/", "/sys/",
    "~/.ssh/", "~/.aws/", "~/.config/",
    "*.env", "*.key", "*.pem",
]


@dataclass
class SourceChunk:
    source_label: str
    file_path: str
    content: str
    relevance: float = 0.5


@dataclass
class SourceResult:
    source_label: str
    chunks: list[SourceChunk] = field(default_factory=list)
    total_found: int = 0


@dataclass
class ResearchProgress:
    stage: str
    message: str
    detail: dict = field(default_factory=dict)


@dataclass
class ResearchResult:
    query: str
    modules: list = field(default_factory=list)
    staged_ids: list[str] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)
    took_ms: int = 0
    answer_synthesis: str = ""


class Researcher:
    def __init__(self, kb_path: Path, config: ResearchConfig, llm_client: BaseLLMClient):
        self.kb_path = kb_path
        self.config = config
        self.llm = llm_client

    async def research(
        self,
        query: str,
        depth: str | None = None,
        on_progress: Callable[[ResearchProgress], None] | None = None,
    ) -> ResearchResult:
        import time
        t_start = time.time()
        depth = depth or self.config.default_depth
        llm_calls = 0

        # Step 1: Decompose
        if on_progress:
            on_progress(ResearchProgress("decompose", "Analyzing query..."))
        sub_queries = await self._decompose_query(query)
        llm_calls += 1
        if not sub_queries:
            sub_queries = [query]

        # Step 2: Select sources
        if on_progress:
            on_progress(ResearchProgress("select", f"Selecting from {len(self.config.sources)} sources..."))
        assignments = self._assign_sources(sub_queries)

        # Step 3: Parallel search
        if on_progress:
            on_progress(ResearchProgress("search", f"Searching {len(self.config.sources)} sources..."))
        all_results: list[SourceResult] = []
        tasks = []
        for sub_q, sources in assignments.items():
            for src in sources[:5]:  # max 5 per sub-query
                tasks.append(self._search_source(sub_q, src))
        for batch in _chunked(tasks, 5):
            batch_results = await asyncio.gather(*batch, return_exceptions=True)
            for r in batch_results:
                if isinstance(r, SourceResult) and r.chunks:
                    all_results.append(r)

        # Step 4: Synthesize
        if on_progress:
            on_progress(ResearchProgress("synthesize", f"Synthesizing {len(all_results)} sources..."))
        synthesis = await self._synthesize(query, all_results, depth)
        llm_calls += 1

        # Step 5: Extract modules
        if on_progress:
            on_progress(ResearchProgress("extract", "Extracting structured modules..."))
        modules = await self._extract_modules(synthesis, query)

        # Step 6: Stage
        if on_progress:
            on_progress(ResearchProgress("stage", f"Staging {len(modules)} modules..."))
        staged = self._stage_modules(modules, query)

        took_ms = int((time.time() - t_start) * 1000)
        return ResearchResult(
            query=query,
            modules=modules,
            staged_ids=staged,
            sources_used=[r.source_label for r in all_results],
            took_ms=took_ms,
            answer_synthesis=synthesis[:500],
        )

    async def _decompose_query(self, query: str) -> list[str]:
        prompt = f"""Break down this research question into 2-4 specific sub-questions for searching.

Question: {query}

Return ONLY a JSON array of strings. Example: ["sub-question 1", "sub-question 2"]"""
        try:
            import json
            resp = await self.llm.complete(prompt)
            parsed = json.loads(resp.strip())
            if isinstance(parsed, list):
                return [s for s in parsed if isinstance(s, str) and s.strip()][:4]
        except Exception:
            pass
        return [query]

    def _assign_sources(self, sub_queries: list[str]) -> dict[str, list[ResearchSource]]:
        result: dict[str, list[ResearchSource]] = {}
        for q in sub_queries:
            result[q] = list(self.config.sources)
        return result

    async def _search_source(self, query: str, source: ResearchSource) -> SourceResult:
        self._validate_source(source)

        if source.type == "code_repo":
            return await self._search_code_repo(query, source)
        elif source.type == "doc_dir":
            return await self._search_doc_dir(query, source)
        elif source.type == "web":
            return await self._search_web(query, source)
        else:
            return SourceResult(source_label=f"{source.type}:{source.path}")

    async def _search_code_repo(self, query: str, source: ResearchSource) -> SourceResult:
        repo_path = Path(source.path).expanduser().resolve()
        if not repo_path.exists():
            return SourceResult(source_label=f"code_repo:{source.path}")

        keywords = await self._extract_code_keywords(query)
        chunks = []
        for kw in keywords[:5]:
            try:
                output = subprocess.run(
                    ["rg", "-l", "-i", kw, str(repo_path),
                     "--glob=!vendor/**", "--glob=!node_modules/**",
                     "--glob=!.git/**", "--glob=!__pycache__/**"],
                    capture_output=True, text=True, timeout=10,
                )
                for file_path in output.stdout.strip().split("\n")[:3]:
                    if file_path:
                        try:
                            content = Path(file_path).read_text(encoding="utf-8", errors="ignore")[:2000]
                            chunks.append(SourceChunk(
                                source_label=f"code:{source.path}",
                                file_path=file_path,
                                content=content,
                                relevance=0.6,
                            ))
                        except Exception:
                            pass
            except Exception:
                continue

        return SourceResult(source_label=f"code_repo:{source.path}", chunks=chunks, total_found=len(chunks))

    async def _search_doc_dir(self, query: str, source: ResearchSource) -> SourceResult:
        doc_path = Path(source.path).expanduser().resolve()
        if not doc_path.exists():
            return SourceResult(source_label=f"doc_dir:{source.path}")

        chunks = []
        patterns = source.include_patterns or ["*.md", "*.txt", "*.rst"]
        for pat in patterns:
            for f in doc_path.rglob(pat):
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")[:2000]
                    if _quick_relevance(content, query) > 0.3:
                        chunks.append(SourceChunk(
                            source_label=f"doc:{source.path}",
                            file_path=str(f),
                            content=content,
                            relevance=_quick_relevance(content, query),
                        ))
                except Exception:
                    pass
                if len(chunks) >= 5:
                    break
            if len(chunks) >= 5:
                break

        return SourceResult(source_label=f"doc_dir:{source.path}", chunks=chunks, total_found=len(chunks))

    async def _search_web(self, query: str, source: ResearchSource) -> SourceResult:
        chunks = []
        try:
            import httpx
            search_url = source.config.get("search_url", "https://html.duckduckgo.com/html/")
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    search_url,
                    params={"q": query},
                    timeout=15,
                    headers={"User-Agent": "knowledge-manager/0.5.1"},
                )
                if resp.status_code == 200:
                    # Extract text from HTML results
                    import re as _re
                    text = _re.sub(r"<[^>]+>", " ", resp.text)
                    text = _re.sub(r"\s+", " ", text)
                    # Split into ~500 char chunks
                    for i in range(0, min(len(text), 3000), 500):
                        chunks.append(text[i:i+500])
        except Exception as e:
            logger.warning("Web search failed for %s: %s", query, e)

        return SourceResult(
            source_label=f"web:{query[:40]}",
            chunks=chunks if chunks else [f"No web results for: {query}"],
            total_found=len(chunks),
        )

    async def _extract_code_keywords(self, query: str) -> list[str]:
        prompt = f"""Extract 3-5 code search keywords from this query.
Return ONLY a JSON array of lowercase strings.

Query: {query}"""
        try:
            import json
            resp = await self.llm.complete(prompt)
            parsed = json.loads(resp.strip())
            if isinstance(parsed, list):
                return [str(k).lower() for k in parsed[:5]]
        except Exception:
            pass
        return [query.lower()]

    async def _synthesize(self, query: str, results: list[SourceResult], depth: str) -> str:
        chunks = []
        for r in results[:10]:
            for c in r.chunks[:3]:
                chunks.append(f"[{c.source_label}]\n{c.content[:1000]}")

        combined = "\n---\n".join(chunks[:10])
        if not combined:
            return ""

        prompt = f"""Answer the user's question based on the following sources.
If sources don't contain enough information, say so honestly. Don't fabricate.

Question: {query}

Sources:
{combined}

Provide a concise answer (Chinese, max 500 words). Cite sources using [source:label]."""
        try:
            return await self.llm.complete(prompt)
        except Exception:
            return ""

    async def _extract_modules(self, synthesis: str, query: str) -> list:
        if not synthesis.strip():
            return []
        try:
            from knowledge_manager.extractor import Extractor
            from knowledge_manager.storage import _load_config_safe

            cfg = _load_config_safe(self.kb_path)
            extractor = Extractor(self.llm, cfg.extraction if cfg else None)
            modules = await extractor.extract(synthesis, "research", "")
            for m in modules:
                m.metadata.source = f"research-on-miss: {query[:80]}"
                if m.metadata.confidence == "high":
                    m.metadata.confidence = "medium"
            return modules
        except Exception as e:
            logger.warning("Module extraction failed: %s", e)
            return []

    def _stage_modules(self, modules: list, query: str) -> list[str]:
        from knowledge_manager.storage import save_to_staging
        from knowledge_manager.schemas import StagingMeta
        from knowledge_manager.storage import save_staging_meta

        staging = self.kb_path / ".staging"
        staging.mkdir(exist_ok=True)

        staged = []
        for m in modules:
            save_to_staging(m, staging)
            meta = StagingMeta(module_id=m.id, submitted_by="research-on-miss")
            save_staging_meta(meta, staging)
            staged.append(f"{m.category}/{m.id}")
        return staged

    def _validate_source(self, source: ResearchSource) -> None:
        if source.type in ("code_repo", "doc_dir"):
            p = str(Path(source.path).expanduser().resolve()).replace("\\", "/")
            forbidden = [r"/etc(/|$)", r"/proc(/|$)", r"/sys(/|$)", r"\.env$", r"\.key$", r"\.pem$", r"\.ssh(/|$)", r"\.aws(/|$)", r"\.config(/|$)"]
            import re
            for fb in forbidden:
                if re.search(fb, p):
                    raise ValueError(f"Source path matches forbidden pattern {fb}")


def _quick_relevance(text: str, query: str) -> float:
    tl = text.lower()
    ql = query.lower()
    words = ql.split()
    if not words:
        return 0.0
    hits = sum(1 for w in words if w in tl)
    return hits / len(words)


def _chunked(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]
