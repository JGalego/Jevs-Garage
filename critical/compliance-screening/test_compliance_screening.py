from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_questions_match_policy_contract() -> None:
    assert_question_contract(DEMO.QUESTIONS, DEMO.SIGNALS)


def test_likely_match_recommends_compliance_hold() -> None:
    signals = JevSignals(choice="sanctions", choice_confidence=0.88, score=3.3, score_confidence=0.84, noul=0.94)
    decision = DEMO.decide(signals)
    assert "pending analyst adjudication" in decision.action
    assert not decision.fallback


def test_ambiguous_match_gets_enhanced_review() -> None:
    signals = JevSignals(choice="sanctions", choice_confidence=0.45, score=2.2, score_confidence=0.49, noul=0.55)
    decision = DEMO.decide(signals)
    assert decision.fallback
    assert decision.owner == "compliance analyst"
