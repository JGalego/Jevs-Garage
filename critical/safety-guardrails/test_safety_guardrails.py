from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_questions_match_policy_contract() -> None:
    assert_question_contract(DEMO.QUESTIONS, DEMO.SIGNALS)


def test_unsafe_draft_is_suppressed_by_policy() -> None:
    signals = JevSignals(choice="refuse", choice_confidence=0.93, score=3.6, score_confidence=0.88, noul=0.96)
    decision = DEMO.decide(signals)
    assert decision.action.startswith("Suppress the draft")
    assert not decision.fallback


def test_ambiguous_draft_is_withheld_for_review() -> None:
    signals = JevSignals(choice="transform_safe", choice_confidence=0.42, score=2.4, score_confidence=0.49, noul=0.58)
    decision = DEMO.decide(signals)
    assert decision.fallback
    assert "review" in decision.action.lower()
