from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_questions_match_policy_contract() -> None:
    assert_question_contract(DEMO.QUESTIONS, DEMO.SIGNALS)


def test_major_outage_recommends_operator_approved_revert() -> None:
    signals = JevSignals(choice="database", choice_confidence=0.92, score=3.4, score_confidence=0.86, noul=0.94)
    decision = DEMO.decide(signals)
    assert "for approval" in decision.action
    assert not decision.fallback


def test_unknown_domain_freezes_automation() -> None:
    signals = JevSignals(choice="unknown", choice_confidence=0.36, score=2.4, score_confidence=0.50, noul=0.61)
    decision = DEMO.decide(signals)
    assert decision.fallback
    assert decision.action.startswith("Freeze automated remediation")
