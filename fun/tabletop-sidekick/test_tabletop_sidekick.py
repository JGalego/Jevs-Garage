from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_questions_match_policy_contract() -> None:
    assert_question_contract(DEMO.QUESTIONS, DEMO.SIGNALS)


def test_party_gap_selects_scout() -> None:
    signals = JevSignals(choice="scout", choice_confidence=0.86, score=2.5, score_confidence=0.78, noul=0.90)
    decision = DEMO.decide(signals)
    assert "Mira Quickstep" in decision.action
    assert not decision.fallback


def test_ambiguous_party_gets_table_vote() -> None:
    signals = JevSignals(choice="trickster", choice_confidence=0.28, score=2.1, score_confidence=0.42, noul=0.54)
    assert DEMO.decide(signals).fallback
