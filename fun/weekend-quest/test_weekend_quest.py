from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_questions_match_policy_contract() -> None:
    assert_question_contract(DEMO.QUESTIONS, DEMO.SIGNALS)


def test_clear_day_selects_tram_wander() -> None:
    signals = JevSignals(choice="wandering", choice_confidence=0.81, score=2.4, score_confidence=0.76, noul=0.88)
    decision = DEMO.decide(signals)
    assert "next tram" in decision.action
    assert not decision.fallback


def test_ambiguous_day_gets_coin_flip() -> None:
    signals = JevSignals(choice="nature", choice_confidence=0.29, score=2.1, score_confidence=0.42, noul=0.52)
    assert DEMO.decide(signals).fallback
