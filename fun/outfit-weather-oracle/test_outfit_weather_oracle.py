from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_questions_match_policy_contract() -> None:
    assert_question_contract(DEMO.QUESTIONS, DEMO.SIGNALS)


def test_wet_breezy_day_uses_yellow_shell() -> None:
    signals = JevSignals(choice="shell", choice_confidence=0.88, score=2.2, score_confidence=0.78, noul=0.87)
    decision = DEMO.decide(signals)
    assert "yellow shell" in decision.action
    assert "waterproof shoes" in decision.action


def test_uncertain_forecast_uses_packable_fallback() -> None:
    signals = JevSignals(choice="overshirt", choice_confidence=0.30, score=1.9, score_confidence=0.42, noul=0.54)
    assert DEMO.decide(signals).fallback
