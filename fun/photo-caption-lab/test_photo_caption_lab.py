from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_questions_match_policy_contract() -> None:
    assert_question_contract(DEMO.QUESTIONS, DEMO.SIGNALS)


def test_dry_photo_gets_dry_caption() -> None:
    signals = JevSignals(choice="dry", choice_confidence=0.89, score=2.1, score_confidence=0.76, noul=0.12)
    decision = DEMO.decide(signals)
    assert "Table for one" in decision.action
    assert not decision.fallback


def test_uncertain_tone_gets_plain_caption() -> None:
    signals = JevSignals(choice="observational", choice_confidence=0.29, score=2.0, score_confidence=0.41, noul=0.49)
    assert DEMO.decide(signals).fallback
