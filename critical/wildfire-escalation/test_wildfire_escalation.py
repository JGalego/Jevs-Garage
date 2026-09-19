from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_questions_match_policy_contract() -> None:
    assert_question_contract(DEMO.QUESTIONS, DEMO.SIGNALS)


def test_extreme_spread_recommends_authorized_warning_review() -> None:
    signals = JevSignals(choice="extreme", choice_confidence=0.91, score=3.8, score_confidence=0.90, noul=0.94)
    decision = DEMO.decide(signals)
    assert "authorized incident command" in decision.action
    assert not decision.fallback


def test_uncertain_spread_goes_to_incident_commander() -> None:
    signals = JevSignals(choice="surface", choice_confidence=0.41, score=2.5, score_confidence=0.51, noul=0.59)
    decision = DEMO.decide(signals)
    assert decision.fallback
    assert decision.owner == "incident commander"
