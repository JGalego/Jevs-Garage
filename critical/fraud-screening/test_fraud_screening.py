from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_questions_match_policy_contract() -> None:
    assert_question_contract(DEMO.QUESTIONS, DEMO.SIGNALS)


def test_high_risk_transaction_gets_reversible_hold() -> None:
    signals = JevSignals(choice="high", choice_confidence=0.89, score=3.7, score_confidence=0.88, noul=0.88)
    decision = DEMO.decide(signals)
    assert decision.action.startswith("Place a reversible authorization hold")
    assert not decision.fallback


def test_uncertain_transaction_uses_safe_fallback() -> None:
    signals = JevSignals(choice="medium", choice_confidence=0.46, score=2.1, score_confidence=0.52, noul=0.54)
    first = DEMO.decide(signals)
    second = DEMO.decide(signals)
    assert first == second
    assert first.fallback
    assert "review" in first.action.lower()
