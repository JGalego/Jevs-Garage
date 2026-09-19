from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_questions_match_policy_contract() -> None:
    assert_question_contract(DEMO.QUESTIONS, DEMO.SIGNALS)


def test_focus_context_selects_instrumental_circuit() -> None:
    signals = JevSignals(choice="focus", choice_confidence=0.90, score=2.4, score_confidence=0.81, noul=0.92)
    decision = DEMO.decide(signals)
    assert "focus circuit" in decision.action
    assert "instrumental" in decision.action


def test_unclear_vibe_offers_samplers() -> None:
    signals = JevSignals(choice="lift", choice_confidence=0.29, score=2.0, score_confidence=0.41, noul=0.50)
    assert DEMO.decide(signals).fallback
