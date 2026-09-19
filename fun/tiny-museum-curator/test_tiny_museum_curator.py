from pathlib import Path

from tests.support import assert_model_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))


def test_fixture_matches_model_contract() -> None:
    assert_model_contract(DEMO.QUESTIONS, DEMO.evaluate())


def test_memory_objects_get_exhibition_title() -> None:
    decision = DEMO.decide(DEMO.evaluate())
    assert "Small Evidence" in decision.action
    assert not decision.fallback


def test_incoherent_objects_get_open_themes() -> None:
    assert DEMO.decide(DEMO.evaluate(scenario="uncertain")).fallback
