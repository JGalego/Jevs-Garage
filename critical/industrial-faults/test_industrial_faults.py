from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_questions_match_policy_contract() -> None:
    assert_question_contract(DEMO.QUESTIONS, DEMO.SIGNALS)


def test_unsafe_pump_recommends_confirmed_shutdown() -> None:
    signals = JevSignals(choice="bearing_failure", choice_confidence=0.90, score=3.5, score_confidence=0.86, noul=0.93)
    decision = DEMO.decide(signals)
    assert "require operator confirmation" in decision.action
    assert not decision.fallback


def test_uncertain_sensor_state_requests_inspection() -> None:
    signals = JevSignals(choice="sensor_fault", choice_confidence=0.38, score=2.3, score_confidence=0.50, noul=0.56)
    decision = DEMO.decide(signals)
    assert decision.fallback
    assert decision.owner == "shift engineer"
