from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_questions_match_policy_contract() -> None:
    assert_question_contract(DEMO.QUESTIONS, DEMO.SIGNALS)


def test_scifi_plant_gets_ripley() -> None:
    signals = JevSignals(choice="sci_fi", choice_confidence=0.84, score=2.8, score_confidence=0.79, noul=0.89)
    decision = DEMO.decide(signals)
    assert "Ripley" in decision.action
    assert not decision.fallback


def test_uncertain_style_gets_shortlist() -> None:
    signals = JevSignals(choice="botanical", choice_confidence=0.28, score=2.0, score_confidence=0.40, noul=0.53)
    assert DEMO.decide(signals).fallback
