from pathlib import Path

from tests.support import assert_model_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_fixture_matches_model_contract() -> None:
    assert_model_contract(DEMO.QUESTIONS, DEMO.evaluate())


def test_party_gap_selects_scout() -> None:
    decision = DEMO.decide(DEMO.evaluate())
    assert "Mira Quickstep" in decision.action
    assert not decision.fallback


def test_ambiguous_party_gets_table_vote() -> None:
    assert DEMO.decide(DEMO.evaluate(scenario="uncertain")).fallback
