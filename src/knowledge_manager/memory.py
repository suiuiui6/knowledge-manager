import json
import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from enum import IntEnum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from knowledge_manager.llm_clients import BaseLLMClient
from knowledge_manager.schemas import utc_now

logger = logging.getLogger("knowledge_manager.memory")


class ReviewGrade(IntEnum):
    AGAIN = 1
    HARD = 2
    GOOD = 3
    EASY = 4


class MemoryCard(BaseModel):
    id: str
    module_key: str
    module_title: str
    category: str
    front: str
    back: str
    source_field: str = "content.details"
    fsrs_state: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    last_review_at: Optional[datetime] = None
    next_review_at: Optional[datetime] = None
    review_count: int = 0
    total_grade_sum: int = 0


class MemoryStats(BaseModel):
    total_cards: int = 0
    due_today: int = 0
    due_this_week: int = 0
    avg_retention: float = 0.0
    streak_days: int = 0
    total_reviews: int = 0


CARD_GENERATION_PROMPT = """Generate a spaced repetition memory card from this knowledge module.

Module: {title} ({category})
Summary: {summary}

Content:
{content}

Rules:
1. FRONT = a scenario-based question that tests understanding, not just "What is X?"
2. BACK = concise answer (max 150 words, Chinese if module is in Chinese)
3. One card covers one key concept — pick the most important one
4. Focus on "our team's approach and reasons", not generic theory

Return ONLY JSON:
{{"front": "question", "back": "answer", "source_field": "content.details"}}"""


class FSRSScheduler:
    DEFAULT_WEIGHTS = [
        0.4072, 1.1829, 3.1262, 15.4722, 7.2102, 0.5316,
        1.0651, 0.0234, 1.616, 0.0304, 0.0611, 1.8455,
        0.172, 0.913, 2.6026, 0.3674, 0.7462, 0.9478, 0.0,
    ]

    def schedule(self, card: MemoryCard, grade: ReviewGrade, review_time: datetime | None = None) -> MemoryCard:
        review_time = review_time or datetime.now(timezone.utc)
        state = card.fsrs_state
        G = int(grade)

        stability = state.get("stability", 0.0)
        difficulty = state.get("difficulty", 0.3)
        reps = state.get("reps", 0)
        lapses = state.get("lapses", 0)

        if G == ReviewGrade.AGAIN:
            stability = self.DEFAULT_WEIGHTS[6]
            difficulty = min(1.0, difficulty + self.DEFAULT_WEIGHTS[4] * (G - 3))
            lapses += 1
            interval_days = 1.0 / 1440.0  # 1 minute
        elif reps == 0:
            # First review
            difficulty = max(0.01, min(1.0, difficulty + self.DEFAULT_WEIGHTS[4] * (G - 3)))
            base_intervals = {ReviewGrade.HARD: 0.5/24, ReviewGrade.GOOD: 1.0, ReviewGrade.EASY: 4.0}
            interval_days = base_intervals.get(grade, 1.0)
            stability = interval_days
        else:
            retrievability = (1 + (state.get("elapsed_days", 0) / (9 * max(stability, 0.01)))) ** -1
            difficulty = max(0.01, min(1.0, difficulty + self.DEFAULT_WEIGHTS[4] * (G - 3)))
            if G == ReviewGrade.HARD:
                stability = stability * 1.2
                interval_days = stability * 0.5
            elif G == ReviewGrade.GOOD:
                stability = stability * (1 + math.exp(self.DEFAULT_WEIGHTS[8]) * (11 - difficulty)
                                         * (stability ** -self.DEFAULT_WEIGHTS[9])
                                         * (math.exp(self.DEFAULT_WEIGHTS[10] * (1 - retrievability)) - 1))
                interval_days = stability
            else:  # EASY
                stability = stability * (1 + math.exp(self.DEFAULT_WEIGHTS[8]) * (11 - difficulty)
                                         * (stability ** -self.DEFAULT_WEIGHTS[9])
                                         * (math.exp(self.DEFAULT_WEIGHTS[10] * (1 - retrievability)) - 1))
                interval_days = stability * 1.5

        interval_days = max(0.0007, interval_days)
        reps += 1

        card.fsrs_state = {
            "stability": stability, "difficulty": difficulty,
            "elapsed_days": 0, "scheduled_days": interval_days,
            "reps": reps, "lapses": lapses,
            "last_review": review_time.isoformat(),
        }
        card.last_review_at = review_time
        card.next_review_at = review_time + timedelta(days=interval_days)
        card.review_count += 1
        card.total_grade_sum += G
        return card

    def get_due_cards(self, cards: list[MemoryCard], limit: int = 20) -> list[MemoryCard]:
        now = datetime.now(timezone.utc)
        due = [c for c in cards if c.next_review_at is None or c.next_review_at <= now]
        due.sort(key=lambda c: (
            c.next_review_at or now,
            -c.fsrs_state.get("difficulty", 0),
            c.fsrs_state.get("stability", 0),
        ))
        return due[:limit]


class CardGenerator:
    def __init__(self, llm_client: BaseLLMClient):
        self.llm = llm_client

    async def generate_cards(self, module, max_cards: int = 3) -> list[MemoryCard]:
        content_parts = []
        for field in ["overview", "details", "caveats"]:
            val = getattr(module.content, field, "")
            if val:
                content_parts.append(f"[{field}]\n{val[:500]}")
        content = "\n\n".join(content_parts)

        prompt = CARD_GENERATION_PROMPT.format(
            title=module.title, category=module.category,
            summary=module.summary, content=content,
        )

        cards = []
        for i in range(min(max_cards, 3)):
            try:
                response = await self.llm.complete(prompt)
                response = response.strip()
                if response.startswith("```"):
                    response = response.split("\n", 1)[1].rsplit("\n```", 1)[0]
                data = json.loads(response)
                card = MemoryCard(
                    id=f"{module.category}/{module.id}/card-{i}",
                    module_key=f"{module.category}/{module.id}",
                    module_title=module.title,
                    category=module.category,
                    front=data["front"],
                    back=data["back"],
                    source_field=data.get("source_field", "content.details"),
                )
                cards.append(card)
            except Exception as e:
                logger.debug("Card generation failed for %s: %s", module.id, e)
        return cards

    @staticmethod
    def select_modules(modules: list, max_modules: int = 50) -> list:
        published = [m for m in modules if m.metadata.status == "published"]
        high_conf = [m for m in published if m.metadata.confidence == "high"]
        candidates = high_conf if high_conf else published
        candidates.sort(key=lambda m: len(m.content.details), reverse=True)
        return candidates[:max_modules]


def load_cards(kb_path: Path) -> list[MemoryCard]:
    path = kb_path / ".memory" / "cards.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [MemoryCard.model_validate(c) for c in data]
    except Exception:
        return []


def save_cards(cards: list[MemoryCard], kb_path: Path) -> None:
    mem_dir = kb_path / ".memory"
    mem_dir.mkdir(exist_ok=True)
    (mem_dir / "cards.json").write_text(
        json.dumps([c.model_dump() for c in cards], indent=2, default=str),
        encoding="utf-8",
    )
