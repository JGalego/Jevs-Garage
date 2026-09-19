from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_questions_match_policy_contract() -> None:
    assert_question_contract(DEMO.QUESTIONS, DEMO.SIGNALS)


def test_temperature_excursion_recommends_quarantine() -> None:
    signals = JevSignals(
        choice="temperature_abuse", choice_confidence=0.94, score=3.4, score_confidence=0.86, noul=0.93
    )
    decision = DEMO.decide(signals)
    assert "quarantining" in decision.action
    assert not decision.fallback


def test_sensor_uncertainty_routes_to_lab_review() -> None:
    signals = JevSignals(choice="sensor_fault", choice_confidence=0.41, score=2.3, score_confidence=0.50, noul=0.57)
    decision = DEMO.decide(signals)
    assert decision.fallback
    assert "lab review" in decision.action
