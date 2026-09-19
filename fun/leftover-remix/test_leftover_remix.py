from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_questions_match_policy_contract() -> None:
    assert_question_contract(DEMO.QUESTIONS, DEMO.SIGNALS)


def test_potatoes_become_crispy_hash() -> None:
    signals = JevSignals(choice="hash", choice_confidence=0.86, score=1.7, score_confidence=0.77, noul=0.89)
    decision = DEMO.decide(signals)
    assert "Crisp the potatoes" in decision.action
    assert not decision.fallback


def test_uncertain_remix_becomes_snack_plate() -> None:
    signals = JevSignals(choice="frittata", choice_confidence=0.29, score=1.9, score_confidence=0.41, noul=0.51)
    assert DEMO.decide(signals).fallback
