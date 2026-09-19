from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_questions_match_policy_contract() -> None:
    assert_question_contract(DEMO.QUESTIONS, DEMO.SIGNALS)


def test_red_flags_produce_emergency_guidance() -> None:
    signals = JevSignals(choice="emergency", choice_confidence=0.96, score=3.9, score_confidence=0.93, noul=0.98)
    decision = DEMO.decide(signals)
    assert "emergency-services guidance" in decision.action
    assert not decision.fallback


def test_uncertainty_routes_to_licensed_clinician() -> None:
    signals = JevSignals(choice="same_day", choice_confidence=0.48, score=2.7, score_confidence=0.55, noul=0.62)
    decision = DEMO.decide(signals)
    assert decision.fallback
    assert decision.owner == "licensed triage clinician"
