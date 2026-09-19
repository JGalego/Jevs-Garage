from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_questions_match_policy_contract() -> None:
    assert_question_contract(DEMO.QUESTIONS, DEMO.SIGNALS)


def test_memory_objects_get_exhibition_title() -> None:
    signals = JevSignals(choice="memory", choice_confidence=0.82, score=2.6, score_confidence=0.76, noul=0.86)
    decision = DEMO.decide(signals)
    assert "Small Evidence" in decision.action
    assert not decision.fallback


def test_incoherent_objects_get_open_themes() -> None:
    signals = JevSignals(choice="mystery", choice_confidence=0.28, score=2.0, score_confidence=0.41, noul=0.54)
    assert DEMO.decide(signals).fallback
