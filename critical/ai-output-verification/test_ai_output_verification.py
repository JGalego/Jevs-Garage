from pathlib import Path

from tests.support import assert_model_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_fixture_matches_model_contract() -> None:
    assert_model_contract(DEMO.QUESTIONS, DEMO.evaluate())


def test_contradicted_claim_is_blocked() -> None:
    decision = DEMO.decide(DEMO.evaluate())
    assert decision.action.startswith("Block publication")
    assert not decision.fallback


def test_insufficient_evidence_gets_fact_check() -> None:
    decision = DEMO.decide(DEMO.evaluate(scenario="uncertain"))
    assert decision.fallback
    assert decision.owner == "fact checker"
