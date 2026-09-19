from pathlib import Path

from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_questions_match_policy_contract() -> None:
    assert_question_contract(DEMO.QUESTIONS, DEMO.SIGNALS)


def test_contradicted_claim_is_blocked() -> None:
    signals = JevSignals(choice="contradicted", choice_confidence=0.97, score=0.4, score_confidence=0.92, noul=0.02)
    decision = DEMO.decide(signals)
    assert decision.action.startswith("Block publication")
    assert not decision.fallback


def test_insufficient_evidence_gets_fact_check() -> None:
    signals = JevSignals(choice="insufficient", choice_confidence=0.46, score=2.1, score_confidence=0.48, noul=0.53)
    decision = DEMO.decide(signals)
    assert decision.fallback
    assert decision.owner == "fact checker"
