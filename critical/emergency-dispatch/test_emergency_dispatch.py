from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_questions_match_policy_contract() -> None:
    assert_question_contract(DEMO.QUESTIONS, DEMO.SIGNALS)


def test_life_threat_is_presented_to_dispatcher() -> None:
    signals = JevSignals(choice="structure_fire", choice_confidence=0.97, score=3.9, score_confidence=0.94, noul=0.99)
    decision = DEMO.decide(signals)
    assert "do not auto-dispatch" in decision.action
    assert not decision.fallback


def test_uncertain_call_stays_with_human() -> None:
    signals = JevSignals(choice="unknown", choice_confidence=0.41, score=2.8, score_confidence=0.53, noul=0.64)
    decision = DEMO.decide(signals)
    assert decision.fallback
    assert decision.owner == "certified dispatcher"
