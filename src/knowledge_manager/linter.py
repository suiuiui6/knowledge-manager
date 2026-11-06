import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from knowledge_manager.llm_clients import BaseLLMClient
from knowledge_manager.schemas import (
    Contradiction,
    ContradictionEvidence,
    ContradictionType,
    Module,
    Severity,
)

logger = logging.getLogger("knowledge_manager.linter")

PAIR_FILTERS = {
    "same_category": lambda a, b: a.category == b.category,
    "shared_tags": lambda a, b: bool(set(a.metadata.tags) & set(b.metadata.tags)),
    "mutual_reference": lambda a, b: (
        f"{b.category}/{b.id}" in a.metadata.related_modules
        or f"{a.category}/{a.id}" in b.metadata.related_modules
    ),
    "title_overlap_keywords": lambda a, b: _title_keyword_overlap(a, b) > 0.5,
}

CONTRADICTION_PROMPT = """Check if these two knowledge modules contradict each other.

Module A ({module_a_key}):
  Title: {module_a_title}
  Summary: {module_a_summary}
  Overview: {module_a_overview}
  Details: {module_a_details}

Module B ({module_b_key}):
  Title: {module_b_title}
  Summary: {module_b_summary}
  Overview: {module_b_overview}
  Details: {module_b_details}

Check these dimensions:
1. FACT: Same fact/parameter has different values
2. DECISION: Architecture/tech decisions conflict
3. TIMELINE: One says done, other implies still in progress
4. TERMINOLOGY: Same thing called different names
5. STALE_REFERENCE: A references deprecated/archived B

If no contradiction, return {"contradiction": false}
If contradiction, return a JSON object with:
  "contradiction": true,
  "type": "fact|decision|timeline|terminology|stale_ref",
  "severity": "error|warning|info",
  "description": "1-2 sentence description (Chinese)",
  "evidence_a": "excerpt from module A",
  "evidence_b": "excerpt from module B",
  "suggestion": "how to fix (Chinese)",
  "auto_fixable": true/false,
  "auto_fix_description": "what auto-fix would do"

IMPORTANT:
- "Chose X" and "considered Y" is NOT a contradiction
- If they describe different time periods or contexts, mark as info
- Don't over-flag: only mark as error when genuinely conflicting"""


def _title_keyword_overlap(a: Module, b: Module) -> float:
    a_words = set(a.title.lower().split())
    b_words = set(b.title.lower().split())
    if not a_words or not b_words:
        return 0.0
    intersection = a_words & b_words
    return len(intersection) / min(len(a_words), len(b_words))


class DeepLinter:
    def __init__(self, kb_path: Path, llm_client: Optional[BaseLLMClient] = None):
        self.kb_path = kb_path
        self.llm = llm_client

    def lint_all(self, mode: str = "quick") -> list[Contradiction]:
        from knowledge_manager.storage import list_modules, load_index

        modules = list_modules(self.kb_path)
        index = load_index(self.kb_path)

        structural_issues = self._structural_check(modules, index)

        if mode == "deep" and self.llm:
            candidates = self._generate_candidates(modules)
            semantic_issues = asyncio.run(self._semantic_check(candidates))
        else:
            semantic_issues = []

        all_issues = structural_issues + semantic_issues
        all_issues.sort(key=lambda c: (
            {"error": 0, "warning": 1, "info": 2}.get(c.severity.value if hasattr(c.severity, 'value') else str(c.severity), 1),
            -len(c.modules),
        ))
        return all_issues

    def _generate_candidates(self, modules: list[Module]) -> list[tuple[Module, Module]]:
        pairs = set()
        for i, a in enumerate(modules):
            for j, b in enumerate(modules):
                if i >= j:
                    continue
                key = (f"{a.category}/{a.id}", f"{b.category}/{b.id}")
                if (PAIR_FILTERS["same_category"](a, b)
                    or PAIR_FILTERS["shared_tags"](a, b)
                    or PAIR_FILTERS["mutual_reference"](a, b)
                    or PAIR_FILTERS["title_overlap_keywords"](a, b)):
                    pairs.add(key)

        module_map = {f"{m.category}/{m.id}": m for m in modules}
        return [
            (module_map[a_key], module_map[b_key])
            for a_key, b_key in pairs
            if a_key in module_map and b_key in module_map
        ]

    def _structural_check(self, modules: list[Module], index) -> list[Contradiction]:
        issues = []
        module_status = {f"{m.category}/{m.id}": m.metadata.status for m in modules}
        module_keys_set = set(module_status.keys())

        for module in modules:
            module_key = f"{module.category}/{module.id}"

            for ref in module.metadata.related_modules:
                if ref in module_status and module_status[ref] in ("deprecated", "archived"):
                    issues.append(Contradiction(
                        id=str(uuid.uuid4()),
                        type=ContradictionType.STALE_REFERENCE,
                        severity=Severity.WARNING,
                        modules=[module_key, ref],
                        description=f"Module references {module_status[ref]} module: {ref}",
                        evidence=[ContradictionEvidence(
                            module_key=module_key,
                            field="metadata.related_modules",
                            excerpt=ref,
                            claim=f"References {ref}",
                        )],
                        suggestion=f"Update reference or remove from related_modules",
                        auto_fixable=True,
                        auto_fix_description=f"Remove {ref} from related_modules of {module_key}",
                    ))

                if ref not in module_keys_set:
                    issues.append(Contradiction(
                        id=str(uuid.uuid4()),
                        type=ContradictionType.STALE_REFERENCE,
                        severity=Severity.ERROR,
                        modules=[module_key],
                        description=f"References non-existent module: {ref}",
                        evidence=[ContradictionEvidence(
                            module_key=module_key,
                            field="metadata.related_modules",
                            excerpt=ref,
                            claim=f"References missing module {ref}",
                        )],
                        suggestion="Check for typos or create the missing module",
                        auto_fixable=False,
                    ))

            if module.metadata.expires_at:
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                exp = module.metadata.expires_at
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if now >= exp and module.metadata.status == "published":
                    issues.append(Contradiction(
                        id=str(uuid.uuid4()),
                        type=ContradictionType.FACT,
                        severity=Severity.WARNING,
                        modules=[module_key],
                        description=f"Module expired but still published",
                        suggestion="Archive or update the module",
                        auto_fixable=True,
                        auto_fix_description="Mark as deprecated",
                    ))

        # Orphan detection
        all_keys = set(module_keys_set)
        referenced = set()
        for m in modules:
            for ref in m.metadata.related_modules:
                referenced.add(ref)
        for key in all_keys:
            if key not in referenced and key not in [f"{m.category}/{m.id}" for m in modules
                                                     if m.metadata.related_modules]:
                pass  # Skip: having no references is normal for new modules

        return issues

    async def _semantic_check(self, candidates: list[tuple[Module, Module]]) -> list[Contradiction]:
        if not self.llm:
            return []

        all_issues = []
        for batch in _chunked(candidates, 10):
            tasks = [self._compare_pair(a, b) for a, b in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in batch_results:
                if isinstance(result, Contradiction):
                    all_issues.append(result)

        return all_issues

    async def _compare_pair(self, a: Module, b: Module) -> Optional[Contradiction]:
        prompt = CONTRADICTION_PROMPT.format(
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

        try:
            response = await self.llm.complete(prompt)
            response = response.strip()
            if response.startswith("```"):
                response = response.split("\n", 1)[1].rsplit("\n```", 1)[0]
            data = json.loads(response)
        except Exception:
            return None

        if not data.get("contradiction"):
            return None

        return Contradiction(
            id=str(uuid.uuid4()),
            type=ContradictionType(data.get("type", "fact")),
            severity=Severity(data.get("severity", "info")),
            modules=[f"{a.category}/{a.id}", f"{b.category}/{b.id}"],
            description=data.get("description", ""),
            evidence=[
                ContradictionEvidence(
                    module_key=f"{a.category}/{a.id}",
                    excerpt=data.get("evidence_a", ""),
                ),
                ContradictionEvidence(
                    module_key=f"{b.category}/{b.id}",
                    excerpt=data.get("evidence_b", ""),
                ),
            ],
            suggestion=data.get("suggestion", ""),
            auto_fixable=data.get("auto_fixable", False),
            auto_fix_description=data.get("auto_fix_description", ""),
        )


def _chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]
