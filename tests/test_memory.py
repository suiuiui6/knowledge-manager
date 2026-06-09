import pytest
from datetime import datetime, timedelta, timezone

from knowledge_manager.memory import (
    FSRSScheduler, CardGenerator, MemoryCard, ReviewGrade,
    load_cards, save_cards, CARD_GENERATION_PROMPT,
)


class TestFSRSScheduler:
    @pytest.fixture
    def scheduler(self):
        return FSRSScheduler()

    @pytest.fixture
    def new_card(self):
        return MemoryCard(
            id="test/card-0", module_key="test/mod", module_title="Test",
            category="test", front="Q?", back="A.",
        )

    def test_first_review_good(self, scheduler, new_card):
        card = scheduler.schedule(new_card, ReviewGrade.GOOD)
        assert card.review_count == 1
        assert card.next_review_at is not None
        assert (card.next_review_at - card.last_review_at).days >= 0

    def test_first_review_again(self, scheduler, new_card):
        card = scheduler.schedule(new_card, ReviewGrade.AGAIN)
        assert card.fsrs_state["lapses"] == 1
        assert card.next_review_at > card.last_review_at

    def test_first_review_easy(self, scheduler, new_card):
        card = scheduler.schedule(new_card, ReviewGrade.EASY)
        assert card.fsrs_state["reps"] == 1
        interval = (card.next_review_at - card.last_review_at).total_seconds() / 86400
        assert interval >= 3.5

    def test_multiple_reviews(self, scheduler, new_card):
        card = scheduler.schedule(new_card, ReviewGrade.GOOD)
        card = scheduler.schedule(card, ReviewGrade.GOOD)
        assert card.review_count == 2
        assert card.fsrs_state["stability"] > 0

    def test_get_due_cards(self, scheduler):
        now = datetime.now(timezone.utc)
        cards = [
            MemoryCard(id="c1", module_key="m1", module_title="M1", category="t",
                       front="q1", back="a1", next_review_at=now - timedelta(days=1)),
            MemoryCard(id="c2", module_key="m2", module_title="M2", category="t",
                       front="q2", back="a2", next_review_at=now + timedelta(days=7)),
        ]
        due = scheduler.get_due_cards(cards)
        assert len(due) == 1
        assert due[0].id == "c1"


class TestCardPersistence:
    def test_save_and_load(self, tmp_path):
        kb = tmp_path / "test_kb"
        kb.mkdir()
        cards = [
            MemoryCard(id="test/card-0", module_key="test/mod", module_title="T",
                       category="test", front="Q", back="A"),
        ]
        save_cards(cards, kb)
        loaded = load_cards(kb)
        assert len(loaded) == 1
        assert loaded[0].front == "Q"

    def test_load_empty(self, tmp_path):
        kb = tmp_path / "empty"
        kb.mkdir()
        cards = load_cards(kb)
        assert cards == []


class TestReviewGrade:
    def test_grade_values(self):
        assert ReviewGrade.AGAIN == 1
        assert ReviewGrade.HARD == 2
        assert ReviewGrade.GOOD == 3
        assert ReviewGrade.EASY == 4
