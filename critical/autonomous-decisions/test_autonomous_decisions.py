from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_questions_match_policy_contract() -> None:
    assert_question_contract(DEMO.QUESTIONS, DEMO.SIGNALS)


def test_obstacle_crosses_stop_boundary() -> None:
    signals = JevSignals(choice="stop", choice_confidence=0.94, score=3.5, score_confidence=0.91, noul=0.95)
    decision = DEMO.decide(signals)
    assert "controlled stop" in decision.action
    assert not decision.fallback


def test_sensor_uncertainty_requests_takeover() -> None:
    signals = JevSignals(choice="slow", choice_confidence=0.43, score=2.3, score_confidence=0.52, noul=0.51)
    decision = DEMO.decide(signals)
    assert decision.fallback
    assert "human takeover" in decision.action
