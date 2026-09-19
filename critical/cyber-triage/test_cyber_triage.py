from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_questions_match_policy_contract() -> None:
    assert_question_contract(DEMO.QUESTIONS, DEMO.SIGNALS)


def test_active_compromise_recommends_operator_containment() -> None:
    signals = JevSignals(
        choice="credential_attack", choice_confidence=0.91, score=3.6, score_confidence=0.87, noul=0.90
    )
    decision = DEMO.decide(signals)
    assert "await operator approval" in decision.action
    assert not decision.fallback


def test_uncertain_alert_preserves_evidence_for_human() -> None:
    signals = JevSignals(choice="unknown", choice_confidence=0.39, score=2.2, score_confidence=0.51, noul=0.57)
    assert DEMO.decide(signals) == DEMO.decide(signals)
    assert DEMO.decide(signals).fallback
