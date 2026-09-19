"""Offline simulator and policy tests; no fabricated SDK responses or live calls."""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from jevs_garage.operations import AuditEvent, OperationStage, ProgressCallback, ProgressEvent, state_fingerprint
from jevs_garage.runtime import JevSignals
from tests.support import assert_question_contract, load_demo

DEMO = load_demo(Path(__file__).with_name("demo.py"))
ROLES = ("posterior", "causal-critic", "safety-critic", "recommendation", "challenge")
INTEGER_RANGES = (
    ("demand", 1000, 4500),
    ("probe_budget", 0, 3),
    ("intervention_budget", 0, 101),
    ("call_budget", 23, 23),
)


def signal(choice: str, *, confidence: float = 0.90, noul: float = 0.99) -> JevSignals:
    return JevSignals(
        choice=choice,
        choice_confidence=confidence,
        score=4.0,
        score_confidence=confidence,
        noul=noul,
    )


def policy_inputs(**overrides: Any) -> dict[str, Any]:
    return {
        "candidate": DEMO.INTERVENTIONS[1],
        "survivors": ("city_a",),
        "posterior": signal("city_a"),
        "critics": (signal("uphold"), signal("uphold")),
        "recommendation": signal("close"),
        "challenge": signal("close"),
        "minimum_confidence": 0.72,
        "selected_forecast_correct": True,
        "calls_used": 23,
        "call_budget": 23,
        **overrides,
    }


def replace_judgment(inputs: dict[str, Any], role: str, **changes: Any) -> None:
    if role in ("causal-critic", "safety-critic"):
        critics = list(inputs["critics"])
        index = ("causal-critic", "safety-critic").index(role)
        critics[index] = replace(critics[index], **changes)
        inputs["critics"] = tuple(critics)
    else:
        inputs[role] = replace(inputs[role], **changes)


@pytest.fixture(autouse=True)
def forbid_live_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Offline tests must not dispatch a model call or access live credentials")

    monkeypatch.setattr(DEMO, "require_live_api_key", forbidden)
    monkeypatch.setattr(DEMO, "TypeSafeClient", forbidden)
    monkeypatch.setattr(DEMO, "_model_call", forbidden)


def test_all_23_questions_have_typed_contracts_and_unique_progress_keys() -> None:
    expected = {
        "blind",
        "experiment",
        "posterior",
        "causal-critic",
        "safety-critic",
        "recommendation",
        "order-challenge",
        *(f"forecast-{city}-{item.key}" for city in DEMO.CITIES for item in DEMO.INTERVENTIONS),
    }
    assert DEMO.MAX_CALLS == len(DEMO.QUESTION_SETS) == len(expected) == 23
    assert set(DEMO.QUESTION_SETS) == expected
    assert DEMO.MAX_WORKERS == 4
    for questions in DEMO.QUESTION_SETS.values():
        assert_question_contract(questions, DEMO.SIGNALS)
    keys = [key for key, _ in DEMO.PROGRESS_STEPS]
    assert len(keys) == len(set(keys)) == 26
    assert set(keys) == expected | {"twins", "oracle", "policy"}
    assert all(label for _, label in DEMO.PROGRESS_STEPS)
    assert DEMO.QUESTION_SETS["recommendation"] == DEMO.QUESTION_SETS["order-challenge"]


def test_question_choices_match_the_authorized_domains() -> None:
    for key, questions in DEMO.QUESTION_SETS.items():
        if key in {"blind", "posterior"}:
            expected = {"city_a", "city_b", "unresolved"}
        elif key == "experiment":
            expected = {*DEMO.PROBES, "defer"}
        elif key.startswith("forecast-"):
            expected = {"faster", "same", "slower"}
        elif key.endswith("critic"):
            expected = {"uphold", "veto", "defer"}
        else:
            expected = {*(item.key for item in DEMO.INTERVENTIONS), "defer"}
        assert set(questions["verdict"].criteria) == expected


@pytest.mark.parametrize(
    ("demand", "fixed", "capacity", "opened", "flows", "routes", "travel"),
    [
        (4000, 45, 1, True, (0, 0, 4000), (85, 85, 80), 80),
        (4000, 95, 1, True, (0, 0, 4000), (135, 135, 80), 80),
        (4000, 45, 1, False, (2000, 2000, 0), (65, 65, None), 65),
        (4000, 95, 1, False, (2000, 2000, 0), (115, 115, None), 115),
        (4000, 30, 1, True, (1000, 1000, 2000), (60, 60, 60), 60),
        (12000, 45, 2, True, (3000, 3000, 6000), (90, 90, 90), 90),
        (10000, 45, 1, True, (5000, 5000, 0), (95, 95, 100), 95),
        (4500, 45, 1, True, (0, 0, 4500), (90, 90, 90), 90),
        (9000, 45, 1, True, (4500, 4500, 0), (90, 90, 90), 90),
        (4000, 45, 2, True, (0, 0, 4000), (65, 65, 40), 40),
        (4000, 45, 2, False, (2000, 2000, 0), (55, 55, None), 55),
    ],
)
def test_exact_wardrop_examples(
    demand: float,
    fixed: float,
    capacity: float,
    opened: bool,
    flows: tuple[float, float, float],
    routes: tuple[float, float, float | None],
    travel: float,
) -> None:
    result = DEMO.equilibrium(demand, fixed, DEMO.Intervention("test", opened, capacity, 0))
    assert (result.upper_flow, result.lower_flow, result.shortcut_flow) == pytest.approx(flows)
    assert result.travel_minutes == pytest.approx(travel)
    for actual, expected in zip(result.route_minutes, routes, strict=True):
        if expected is None:
            assert actual is None
        else:
            assert actual == pytest.approx(expected)


@pytest.mark.parametrize("demand", [1.0, 1000, 2750, 4000, 4500, 6000, 9000, 25000])
@pytest.mark.parametrize("fixed", [5.0, 20.0, 30.0, 45.0, 95.0])
@pytest.mark.parametrize("capacity", [0.5, 1.0, 1.25, 1.5, 2.0])
@pytest.mark.parametrize("opened", [False, True])
def test_wardrop_conserves_flow_and_no_unused_route_is_faster(
    demand: float, fixed: float, capacity: float, opened: bool
) -> None:
    result = DEMO.equilibrium(demand, fixed, DEMO.Intervention("grid", opened, capacity, 0))
    upper, lower, shortcut = result.upper_flow, result.lower_flow, result.shortcut_flow
    assert all(math.isfinite(flow) and flow >= 0 for flow in (upper, lower, shortcut))
    assert upper + lower + shortcut == pytest.approx(demand)
    assert upper == pytest.approx(lower)
    # Independently reconstruct edge and route costs from the conserved path flows.
    sa = 0.01 * (upper + shortcut) / capacity
    bt = 0.01 * (lower + shortcut) / capacity
    expected_routes = (sa + fixed, fixed + bt, sa + bt if opened else None)
    total_minutes = 0.0
    for flow, actual, expected in zip((upper, lower, shortcut), result.route_minutes, expected_routes, strict=True):
        if expected is None:
            assert actual is None
            assert flow == 0
            continue
        assert actual == pytest.approx(expected)
        if flow > 1e-9:
            assert actual == pytest.approx(result.travel_minutes)
        else:
            assert actual >= result.travel_minutes - 1e-9
        total_minutes += flow * actual
    assert total_minutes / demand == pytest.approx(result.travel_minutes)


@pytest.mark.parametrize("capacity", [0.5, 1, 1.25, 1.5, 2])
@pytest.mark.parametrize("fixed", [20, 45, 95])
@pytest.mark.parametrize("ratio", [0.5, 1, 1.25, 1.75, 2, 3])
def test_shortcut_regimes_including_both_transition_boundaries(capacity: float, fixed: float, ratio: float) -> None:
    demand = ratio * fixed * capacity / 0.01
    result = DEMO.equilibrium(demand, fixed, DEMO.Intervention("regimes", True, capacity, 0))
    if ratio <= 1:
        assert result.shortcut_flow == pytest.approx(demand)
        assert result.travel_minutes == pytest.approx(2 * ratio * fixed)
    elif ratio < 2:
        assert 0 < result.shortcut_flow < demand
        assert result.travel_minutes == pytest.approx(2 * fixed)
        assert result.route_minutes == pytest.approx((2 * fixed,) * 3)
    else:
        assert result.shortcut_flow == pytest.approx(0)
        assert result.travel_minutes == pytest.approx(fixed * (1 + ratio / 2))


@pytest.mark.parametrize("field", ["demand", "fixed_delay", "capacity"])
@pytest.mark.parametrize("bad", [0, -1, math.nan, math.inf, -math.inf])
def test_equilibrium_rejects_nonpositive_and_nonfinite_parameters(field: str, bad: float) -> None:
    values = {"demand": 4000.0, "fixed_delay": 45.0, "capacity": 1.0, field: bad}
    intervention = DEMO.Intervention("invalid", True, values["capacity"], 0)
    with pytest.raises(ValueError, match="positive and finite"):
        DEMO.equilibrium(values["demand"], values["fixed_delay"], intervention)


@pytest.mark.parametrize("demand", [1000, 1001, 2000, 4000, 4499, 4500])
def test_observational_twins_match_including_allowed_demand_boundaries(demand: int) -> None:
    a, b = (DEMO.observation(city, demand) for city in ("city_a", "city_b"))
    assert a == b == {"travel_minutes": pytest.approx(0.02 * demand), "shortcut_flow": demand}
    assert DEMO.public_context(demand)["observation"] == a
    assert DEMO.surviving_cities(demand, "repeat_baseline", a["travel_minutes"]) == ("city_a", "city_b")


def test_default_braess_paradox_has_opposite_effects_in_the_two_cities() -> None:
    rows = {(row["city"], row["intervention"]["key"]): row for row in DEMO.oracle_table(4000)}
    assert len(rows) == 16
    for city, closed, direction in (("city_a", 65, "faster"), ("city_b", 115, "slower")):
        assert rows[city, "keep"]["equilibrium"]["travel_minutes"] == 80
        assert rows[city, "keep"]["direction"] == "same"
        assert rows[city, "close"]["equilibrium"]["travel_minutes"] == closed
        assert rows[city, "close"]["direction"] == direction


@pytest.mark.parametrize("demand", [1000, 4000, 4500])
@pytest.mark.parametrize("city", ["city_a", "city_b"])
@pytest.mark.parametrize("probe", ["inspect_outer", "close_trial"])
def test_informative_probes_separate_twins(demand: int, city: str, probe: str) -> None:
    measured = DEMO.probe_value(city, demand, probe)
    fixed = 45 if city == "city_a" else 95
    assert measured == pytest.approx(fixed if probe == "inspect_outer" else fixed + demand * 0.005)
    assert DEMO.surviving_cities(demand, probe, measured) == (city,)


def test_cheapest_separating_probe_and_missing_or_inconsistent_measurements() -> None:
    separating = [
        key for key in DEMO.PROBES if DEMO.probe_value("city_a", 4000, key) != DEMO.probe_value("city_b", 4000, key)
    ]
    assert min(separating, key=lambda key: DEMO.PROBES[key]["cost"]) == "inspect_outer"
    assert DEMO.PROBES["inspect_outer"]["cost"] == 1
    assert DEMO.PROBES["repeat_baseline"]["cost"] == 0
    assert DEMO.PROBES["close_trial"]["cost"] == 3
    assert DEMO.surviving_cities(4000, "defer", None) == ("city_a", "city_b")
    assert DEMO.surviving_cities(4000, "inspect_outer", 70) == ()
    with pytest.raises(ValueError, match="Unknown probe"):
        DEMO.probe_value("city_a", 4000, "invented")


@pytest.mark.parametrize(
    ("budget", "city_a_key", "robust_key"),
    [
        (0, "keep", "keep"),
        (1, "close", "keep"),
        (24, "close", "keep"),
        (25, "keep_125", "keep_125"),
        (26, "close_125", "keep_125"),
        (49, "close_125", "keep_125"),
        (50, "keep_150", "keep_150"),
        (51, "keep_150", "keep_150"),
        (99, "keep_150", "keep_150"),
        (100, "keep_200", "keep_200"),
        (101, "keep_200", "keep_200"),
    ],
)
def test_default_minimax_candidates_at_every_cost_boundary(budget: int, city_a_key: str, robust_key: str) -> None:
    assert DEMO.best_intervention(4000, ("city_a",), budget).key == city_a_key
    assert DEMO.best_intervention(4000, ("city_b",), budget).key == robust_key
    assert DEMO.best_intervention(4000, ("city_a", "city_b"), budget).key == robust_key
    assert DEMO.best_intervention(4000, ("city_b", "city_a"), budget).key == robust_key


@pytest.mark.parametrize("demand", [1000, 2750, 4000, 4500])
@pytest.mark.parametrize("cities", [("city_a",), ("city_b",), ("city_a", "city_b")])
def test_minimax_certificate_against_independent_piecewise_latency(demand: int, cities: tuple[str, ...]) -> None:
    def rank(item: Any) -> tuple[float, int, str]:
        q = 0.01 * demand / item.capacity
        latencies = []
        for city in cities:
            fixed = {"city_a": 45, "city_b": 95}[city]
            latency = q / 2 + fixed if not item.shortcut_open or q >= 2 * fixed else 2 * min(q, fixed)
            latencies.append(latency)
        return max(latencies), item.cost, item.key

    for budget in range(102):
        feasible = [item for item in DEMO.INTERVENTIONS if item.cost <= budget]
        chosen = DEMO.best_intervention(demand, cities, budget)
        assert chosen == min(feasible, key=rank), (demand, cities, budget)
        assert chosen.cost <= budget


def test_minimax_equal_latency_prefers_cheaper_intervention() -> None:
    # At this boundary keep_150 and close_150 both take 60 minutes; keep costs less.
    assert DEMO.best_intervention(4500, ("city_a",), 51).key == "keep_150"


def test_minimax_ties_prefer_cost_then_stable_key(monkeypatch: pytest.MonkeyPatch) -> None:
    options = tuple(DEMO.Intervention(key, True, 1, cost) for key, cost in (("z", 0), ("a", 0), ("0", 1)))
    monkeypatch.setattr(DEMO, "INTERVENTIONS", options)
    assert DEMO.best_intervention(4000, ("city_a", "city_b"), 1).key == "a"


def test_minimax_refuses_an_empty_hypothesis_set() -> None:
    with pytest.raises(ValueError, match="No consistent city"):
        DEMO.best_intervention(4000, (), 101)


@pytest.mark.parametrize(("field", "lower", "upper"), INTEGER_RANGES)
def test_integer_validation_accepts_only_inclusive_boundaries(field: str, lower: int, upper: int) -> None:
    for value in (lower, upper):
        assert DEMO.validate_state({**deepcopy(DEMO.STATE), field: value}) == []
    for value in (lower - 1, upper + 1):
        assert any(error.startswith(f"$.{field}:") for error in DEMO.validate_state({**DEMO.STATE, field: value}))


@pytest.mark.parametrize(("field", "lower", "upper"), INTEGER_RANGES)
@pytest.mark.parametrize("bad", [True, False, 1.0, "1", None, [], {}, math.nan, math.inf, -math.inf])
def test_integer_validation_rejects_malformed_values(field: str, lower: int, upper: int, bad: Any) -> None:
    assert DEMO.validate_state({**DEMO.STATE, field: bad}) == [
        f"$.{field}: must be an integer between {lower} and {upper}"
    ]


@pytest.mark.parametrize(("field", "lower", "upper"), INTEGER_RANGES)
def test_integer_validation_rejects_even_integral_floats(field: str, lower: int, upper: int) -> None:
    assert DEMO.validate_state({**DEMO.STATE, field: float(lower)})


@pytest.mark.parametrize("confidence", [0.5, 0.72, 0.95])
def test_confidence_validation_accepts_inclusive_range(confidence: float) -> None:
    assert DEMO.validate_state({**DEMO.STATE, "minimum_confidence": confidence}) == []


@pytest.mark.parametrize(
    "bad", [0.499999, 0.950001, 0, 1, True, False, "0.72", None, [], {}, math.nan, math.inf, -math.inf]
)
def test_confidence_validation_rejects_malformed_values(bad: Any) -> None:
    assert DEMO.validate_state({**DEMO.STATE, "minimum_confidence": bad}) == [
        "$.minimum_confidence: must be finite and between 0.5 and 0.95"
    ]


@pytest.mark.parametrize("run_id", ["x", "x" * 100])
@pytest.mark.parametrize("city", ["city_a", "city_b"])
def test_valid_identifiers(run_id: str, city: str) -> None:
    assert DEMO.validate_state({**DEMO.STATE, "run_id": run_id, "hidden_city": city}) == []


@pytest.mark.parametrize("bad", ["", "x" * 101, 123, True, None, [], {}])
def test_invalid_run_identifiers(bad: Any) -> None:
    assert DEMO.validate_state({**DEMO.STATE, "run_id": bad}) == ["$.run_id: must contain 1 to 100 characters"]


@pytest.mark.parametrize("bad", ["city_c", "CITY_A", "", True, 1, None, [], {}, math.nan])
def test_invalid_hidden_selectors(bad: Any) -> None:
    assert DEMO.validate_state({**DEMO.STATE, "hidden_city": bad}) == ["$.hidden_city: must be city_a or city_b"]


@pytest.mark.parametrize("guard", ["simulation_only", "preserve_all_trips", "no_external_actions"])
@pytest.mark.parametrize("bad", [False, 1, "true", None])
def test_each_guardrail_requires_literal_true(guard: str, bad: Any) -> None:
    state = deepcopy(DEMO.STATE)
    state["guardrails"][guard] = bad
    assert DEMO.validate_state(state) == ["$.guardrails: all canonical simulation guardrails must remain true"]


@pytest.mark.parametrize("guards", [None, True, [], {}, {"simulation_only": True}])
def test_guardrail_shape_is_canonical(guards: Any) -> None:
    assert DEMO.validate_state({**DEMO.STATE, "guardrails": guards})


def test_validation_rejects_extra_or_missing_fields_and_does_not_mutate_input() -> None:
    state = deepcopy(DEMO.STATE)
    original = deepcopy(state)
    assert DEMO.validate_state(state) == []
    assert state == original
    assert DEMO.validate_state({**state, "unexpected": True}) == ["$: fields must match the canonical state"]
    for field in state:
        assert DEMO.validate_state({key: value for key, value in state.items() if key != field}) == [
            "$: fields must match the canonical state"
        ]
    state["guardrails"]["unexpected"] = True
    assert DEMO.validate_state(state)


@pytest.mark.parametrize("city", ["city_a", "city_b"])
@pytest.mark.parametrize("calls_used", [22, 23])
def test_policy_positive_is_repeatable_simulation_only_and_budget_inclusive(city: str, calls_used: int) -> None:
    candidate = DEMO.best_intervention(4000, (city,), 1)
    inputs = policy_inputs(
        candidate=candidate,
        survivors=(city,),
        posterior=signal(city),
        recommendation=signal(candidate.key),
        challenge=signal(candidate.key),
        calls_used=calls_used,
    )
    decision = DEMO.decide(**inputs)
    assert decision == DEMO.decide(**inputs)
    assert not decision.fallback
    assert decision.confidence == pytest.approx(0.9)
    assert decision.action == (
        f"Recommend {candidate.key} inside the simulator only; attach the exact equilibrium certificate."
    )
    assert decision.owner == "simulation experiment lead"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"calls_used": 24}, "hard call budget"),
        ({"survivors": ()}, "uniquely identify"),
        ({"survivors": ("city_a", "city_b")}, "uniquely identify"),
        ({"posterior": signal("city_b")}, "posterior contradicts"),
        ({"posterior": signal("unresolved")}, "posterior contradicts"),
        ({"critics": ()}, "critic did not uphold"),
        ({"critics": (signal("uphold"),)}, "critic did not uphold"),
        ({"critics": (signal("uphold"),) * 3}, "critic did not uphold"),
        ({"selected_forecast_correct": False}, "sealed forecast"),
        ({"challenge": signal("keep")}, "Reordering identical evidence"),
        ({"recommendation": signal("keep")}, "Reordering identical evidence"),
        ({"recommendation": signal("keep"), "challenge": signal("keep")}, "minimax certificate"),
        ({"recommendation": signal("defer"), "challenge": signal("defer")}, "minimax certificate"),
    ],
)
def test_each_policy_veto(overrides: dict[str, Any], reason: str) -> None:
    decision = DEMO.decide(**policy_inputs(**overrides))
    assert decision.fallback
    assert reason.lower() in decision.reason.lower()
    assert "human reviewer" in decision.action
    assert decision.owner == "simulation experiment lead"


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("component", ["choice_confidence", "score_confidence", "noul"])
def test_each_required_judgment_enforces_confidence_floor(role: str, component: str) -> None:
    inputs = policy_inputs()
    value = math.nextafter(0.86 if component == "noul" else 0.72, 0.0)
    replace_judgment(inputs, role, **{component: value})
    decision = DEMO.decide(**inputs)
    assert decision.fallback
    assert "confidence floor" in decision.reason
    assert decision.confidence < 0.72


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("component", ["choice_confidence", "score_confidence", "noul"])
def test_confidence_floor_is_inclusive_for_every_judgment(role: str, component: str) -> None:
    inputs = policy_inputs(minimum_confidence=0.75)
    replace_judgment(inputs, role, **{component: 0.875 if component == "noul" else 0.75})
    decision = DEMO.decide(**inputs)
    assert not decision.fallback
    assert decision.confidence == 0.75


@pytest.mark.parametrize("role", ["causal-critic", "safety-critic"])
@pytest.mark.parametrize("choice", ["veto", "defer", "unknown"])
def test_both_critics_must_explicitly_uphold(role: str, choice: str) -> None:
    inputs = policy_inputs()
    replace_judgment(inputs, role, choice=choice)
    decision = DEMO.decide(**inputs)
    assert decision.fallback
    assert "critic did not uphold" in decision.reason


@pytest.mark.parametrize("role", ["causal-critic", "safety-critic"])
@pytest.mark.parametrize(("support", "fallback"), [(math.nextafter(0.8, 0), True), (0.8, False), (0.81, False)])
def test_critic_support_probability_boundary_is_separate_from_certainty(
    role: str, support: float, fallback: bool
) -> None:
    inputs = policy_inputs(minimum_confidence=0.5)
    replace_judgment(inputs, role, noul=support)
    decision = DEMO.decide(**inputs)
    assert decision.confidence >= 0.5
    assert decision.fallback is fallback
    if fallback:
        assert "critic did not uphold" in decision.reason


@pytest.mark.parametrize("role", ROLES)
def test_confidently_unsupported_required_judgment_must_veto(role: str) -> None:
    # Noul near zero is high certainty that the verdict is NOT supported.
    # Certainty alone must not authorize a recommendation. These are regression
    # assertions, deliberately not xfailed if the implementation omits this gate.
    inputs = policy_inputs()
    replace_judgment(inputs, role, noul=0.01)
    decision = DEMO.decide(**inputs)
    assert decision.confidence >= inputs["minimum_confidence"]
    assert decision.fallback, f"A confidently unsupported {role} must not authorize an intervention"


@pytest.mark.parametrize(("budget", "already_used", "requested"), [(0, 0, 1), (22, 0, 23), (23, 22, 2), (23, 23, 1)])
def test_council_rejects_entire_over_budget_batch_before_dispatch(
    budget: int, already_used: int, requested: int
) -> None:
    council = DEMO.Council(budget, None)
    council.calls = already_used
    council.record("existing", "must remain untouched")
    original_audit = list(council.audit)
    requests = {key: {"test": True} for key in list(DEMO.QUESTION_SETS)[:requested]}
    with pytest.raises(RuntimeError, match="Hard Jev call budget exhausted before dispatch"):
        council.batch(requests)
    assert council.calls == already_used
    assert council.stages == []
    assert council.audit == original_audit


def test_failed_attempt_consumes_reserved_call_and_cannot_retry_over_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    attempted = []

    def fail_call(key: str, payload: dict[str, Any], on_progress: ProgressCallback | None) -> Any:
        attempted.append(key)
        assert council.calls == 1
        raise LookupError("local dispatch failure, not a network request")

    monkeypatch.setattr(DEMO, "_model_call", fail_call)
    council = DEMO.Council(1, None)
    with pytest.raises(LookupError, match="local dispatch failure"):
        council.ask("blind", {"test": True})
    assert council.calls == 1
    assert council.stages == []
    assert len(council.audit) == 1
    assert council.audit[0].event == "model.input.sealed"
    with pytest.raises(RuntimeError, match="before dispatch"):
        council.ask("blind", {"test": True})
    assert attempted == ["blind"]


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("demand", True),
        ("demand", math.nan),
        ("call_budget", 22),
        ("call_budget", 24),
        ("probe_budget", -1),
        ("intervention_budget", 102),
        ("minimum_confidence", math.nan),
        ("hidden_city", "unknown"),
        ("guardrails", {}),
        ("run_id", ""),
    ],
)
def test_invalid_configuration_is_rejected_before_credentials_or_council(
    monkeypatch: pytest.MonkeyPatch, field: str, bad: Any
) -> None:
    def forbidden_council(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Invalid configuration must be rejected before constructing a Council")

    monkeypatch.setattr(DEMO, "Council", forbidden_council)
    with pytest.raises(ValueError, match=rf"\$\.{field}:"):
        DEMO.execute({**DEMO.STATE, field: bad})


class RecordingCouncil:
    """Test the orchestration boundary with plain signals, never SDK responses."""

    def __init__(self, budget: int, on_progress: ProgressCallback | None, probe: str) -> None:
        self.budget = budget
        self.on_progress = on_progress
        self.probe = probe
        self.calls = 0
        self.stages: list[OperationStage] = []
        self.audit: list[AuditEvent] = []
        self.inputs: dict[str, dict[str, Any]] = {}
        self.batches: list[tuple[str, ...]] = []

    def record(self, event: str, detail: str) -> None:
        self.audit.append(AuditEvent(len(self.audit) + 1, event, detail))

    def ask(self, key: str, payload: dict[str, Any]) -> JevSignals:
        return self.batch({key: payload})[key]

    def batch(self, requests: dict[str, dict[str, Any]]) -> dict[str, JevSignals]:
        assert self.calls + len(requests) <= self.budget
        assert not self.inputs.keys() & requests.keys()
        self.calls += len(requests)
        self.batches.append(tuple(requests))
        self.inputs.update(deepcopy(requests))
        answers = {}
        for key, payload in requests.items():
            if key == "blind":
                choice = "unresolved"
            elif key == "experiment":
                choice = self.probe
            elif key == "posterior":
                measured = payload["measurement"]["measured_minutes"]
                choice = {45: "city_a", 95: "city_b", 65: "city_a", 115: "city_b"}.get(measured, "unresolved")
            elif key.startswith("forecast-"):
                # Intentionally imperfect judgments: only the default selected
                # forecasts need agree. Wrong unselected futures remain visible.
                choice = "faster" if key == "forecast-city_a-close" else "same"
            elif key.endswith("critic"):
                choice = "uphold"
            else:
                choice = payload["deterministic_candidate"]["key"]
            answers[key] = signal(choice)
        return answers


@pytest.fixture
def recording_run(monkeypatch: pytest.MonkeyPatch) -> Any:
    councils: list[RecordingCouncil] = []
    probe = "inspect_outer"

    def council_factory(budget: int, on_progress: ProgressCallback | None) -> RecordingCouncil:
        council = RecordingCouncil(budget, on_progress, probe)
        councils.append(council)
        return council

    original_oracle = DEMO.oracle_table

    def checked_oracle(demand: int) -> list[dict[str, Any]]:
        council = councils[-1]
        assert council.calls == 19
        assert len([key for key in council.inputs if key.startswith("forecast-")]) == 16
        assert council.audit[-1].event == "forecasts.sealed"
        return original_oracle(demand)

    monkeypatch.setattr(DEMO, "require_live_api_key", lambda: None)
    monkeypatch.setattr(DEMO, "Council", council_factory)
    monkeypatch.setattr(DEMO, "oracle_table", checked_oracle)
    # OperationRun requires nonempty SDK stages. Capture its constructor fields
    # instead of forging responses or pretending to exercise the SDK renderer.
    monkeypatch.setattr(DEMO, "OperationRun", lambda **fields: SimpleNamespace(**fields))

    def run(
        state: dict[str, Any], selected_probe: str = "inspect_outer"
    ) -> tuple[Any, RecordingCouncil, list[ProgressEvent]]:
        nonlocal probe
        probe = selected_probe
        events: list[ProgressEvent] = []
        result = DEMO.execute(state, on_progress=events.append)
        return result, councils[-1], events

    return run


def nested_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for child in value.values() for key in nested_keys(child)}
    if isinstance(value, (list, tuple)):
        return {key for child in value for key in nested_keys(child)}
    return set()


def test_orchestration_hides_selector_seals_forecasts_and_preserves_input(recording_run: Any) -> None:
    canonical = deepcopy(DEMO.STATE)
    captured = []
    for city, selected in (("city_a", "close"), ("city_b", "keep")):
        state = {**deepcopy(DEMO.STATE), "hidden_city": city, "run_id": f"PRIVATE-SELECTOR-{city}"}
        original = deepcopy(state)
        result, council, events = recording_run(state)
        captured.append(council.inputs)
        assert state == original
        assert canonical == DEMO.STATE
        assert result.state_fingerprint == state_fingerprint(original)
        assert result.correlation_id == original["run_id"]
        assert not result.decision.fallback
        assert f"Recommend {selected} inside the simulator only" in result.decision.action
        assert council.calls == council.budget == 23
        assert list(council.inputs) == list(DEMO.QUESTION_SETS)
        assert [len(batch) for batch in council.batches] == [1, 1, 1, 16, 2, 1, 1]
        assert [event.sequence for event in result.audit] == list(range(1, len(result.audit) + 1))
        assert result.audit[-1].event == "execution.blocked"
        for payload in council.inputs.values():
            assert "hidden_city" not in nested_keys(payload)
            assert "run_id" not in nested_keys(payload)
            assert original["run_id"] not in repr(payload)
        for hypothetical_city in DEMO.CITIES:
            for intervention in DEMO.INTERVENTIONS:
                payload = council.inputs[f"forecast-{hypothetical_city}-{intervention.key}"]
                assert set(payload) == set(DEMO.public_context(4000)) | {"conditional_city", "intervention", "task"}
                assert payload["conditional_city"] == hypothetical_city
                assert payload["intervention"] == asdict(intervention)
                forbidden = {"counterfactuals", "direction", "route_minutes", "correct", "measurement"}
                assert not forbidden & nested_keys(payload)
                assert {key: payload[key] for key in DEMO.public_context(4000)} == DEMO.public_context(4000)
        assert [(event.key, event.status) for event in events] == [
            (key, status) for key in ("twins", "oracle", "policy") for status in ("running", "completed")
        ]
        # Bad unselected predictions must stay in the trace, not be replaced by the oracle.
        scored = council.inputs["recommendation"]["counterfactuals"]
        assert len(scored) == 16
        assert any(not row["correct"] for row in scored)
        assert all(row["correct"] == (row["forecast"]["choice"] == row["direction"]) for row in scored)
    a, b = captured
    for key in ("blind", "experiment", *(key for key in a if key.startswith("forecast-"))):
        assert a[key] == b[key]
    assert a["posterior"]["measurement"]["measured_minutes"] == 45
    assert b["posterior"]["measurement"]["measured_minutes"] == 95


def test_order_challenge_only_reorders_evidence_and_withholds_recommendation(recording_run: Any) -> None:
    _, council, _ = recording_run(deepcopy(DEMO.STATE))
    first = council.inputs["recommendation"]
    challenge = council.inputs["order-challenge"]
    assert challenge["hypotheses"] == list(reversed(first["hypotheses"]))
    assert challenge["counterfactuals"] == list(reversed(first["counterfactuals"]))
    normalized = {**challenge, "hypotheses": first["hypotheses"], "counterfactuals": first["counterfactuals"]}
    assert normalized == first
    assert not {"recommendation", "first_recommendation", "challenge"} & nested_keys(challenge)
    causal, safety = (council.inputs[key] for key in ("causal-critic", "safety-critic"))
    assert causal["scope"] != safety["scope"]
    assert {key: value for key, value in causal.items() if key != "scope"} == {
        key: value for key, value in safety.items() if key != "scope"
    }


@pytest.mark.parametrize(
    ("probe", "budget", "authorized", "measured"),
    [
        ("repeat_baseline", 0, True, 80),
        ("inspect_outer", 0, False, None),
        ("close_trial", 2, False, None),
        ("defer", 3, False, None),
        ("invented", 3, False, None),
    ],
)
def test_uninformative_or_unauthorized_probe_never_identifies_city(
    recording_run: Any,
    monkeypatch: pytest.MonkeyPatch,
    probe: str,
    budget: int,
    authorized: bool,
    measured: float | None,
) -> None:
    if not authorized:

        def forbidden_measurement(*args: Any, **kwargs: Any) -> Any:
            pytest.fail("An unauthorized probe must not access the private city")

        monkeypatch.setattr(DEMO, "probe_value", forbidden_measurement)
    result, council, _ = recording_run({**deepcopy(DEMO.STATE), "probe_budget": budget}, probe)
    assert council.inputs["posterior"]["measurement"] == {
        "probe": probe,
        "authorized": authorized,
        "measured_minutes": measured,
    }
    reviewed = council.inputs["recommendation"]
    assert reviewed["surviving_cities"] == ("city_a", "city_b")
    assert reviewed["deterministic_candidate"]["key"] == "keep"
    assert result.decision.fallback
    assert "uniquely identify" in result.decision.reason


def test_authorized_close_trial_uses_its_budget_boundary(recording_run: Any) -> None:
    result, council, _ = recording_run({**deepcopy(DEMO.STATE), "probe_budget": 3}, "close_trial")
    assert council.inputs["posterior"]["measurement"] == {
        "probe": "close_trial",
        "authorized": True,
        "measured_minutes": 65,
    }
    assert council.inputs["recommendation"]["surviving_cities"] == ("city_a",)
    assert not result.decision.fallback
