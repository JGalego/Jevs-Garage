from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_questions_match_policy_contract() -> None:
    assert_question_contract(DEMO.QUESTIONS, DEMO.SIGNALS)


def test_craving_maps_to_miso_popcorn() -> None:
    signals = JevSignals(choice="savory", choice_confidence=0.87, score=2.8, score_confidence=0.82, noul=0.86)
    decision = DEMO.decide(signals)
    assert "miso-lime popcorn" in decision.action
    assert not decision.fallback


def test_indecisive_craving_gets_tasting_flight() -> None:
    signals = JevSignals(choice="tangy", choice_confidence=0.31, score=2.0, score_confidence=0.43, noul=0.52)
    decision = DEMO.decide(signals)
    assert decision.fallback
    assert "tasting flight" in decision.action
