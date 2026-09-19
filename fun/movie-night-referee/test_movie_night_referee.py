from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_questions_match_policy_contract() -> None:
    assert_question_contract(DEMO.QUESTIONS, DEMO.SIGNALS)


def test_shared_preferences_pick_light_mystery() -> None:
    signals = JevSignals(choice="mystery", choice_confidence=0.78, score=2.3, score_confidence=0.75, noul=0.88)
    decision = DEMO.decide(signals)
    assert "mystery" in decision.action
    assert not decision.fallback


def test_split_group_gets_ranked_vote() -> None:
    signals = JevSignals(choice="comedy", choice_confidence=0.29, score=2.0, score_confidence=0.40, noul=0.51)
    decision = DEMO.decide(signals)
    assert decision.fallback
    assert "ranked vote" in decision.action
