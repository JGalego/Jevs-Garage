"""Make Jev earn a causal recommendation in a simulator, not win a scripted debate."""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any

from typesafe_sdk import Choice, Noul, Questions, Score, SystemOneResponse, TypeSafeClient

from jevs_garage.operations import (
    AuditEvent,
    ChartPoint,
    OperationRun,
    OperationStage,
    ProgressCallback,
    Visualization,
    render_operation,
    report_progress,
    state_fingerprint,
)
from jevs_garage.runtime import JevSignals, PolicyDecision, SignalNames, require_live_api_key, signals_from_response

TITLE = "Counterfactual City / The Road That Should Not Exist"
POLICY_VERSION = "counterfactual-city/v1.0"
MAX_CALLS = 23
MAX_WORKERS = 4
SIGNALS = SignalNames(choice="verdict", score="strength", noul="supported")
STATE = {
    "run_id": "COUNTERFACTUAL-CITY-001",
    "hidden_city": "city_a",
    "demand": 4000,
    "probe_budget": 1,
    "intervention_budget": 1,
    "call_budget": MAX_CALLS,
    "minimum_confidence": 0.72,
    "guardrails": {"simulation_only": True, "preserve_all_trips": True, "no_external_actions": True},
}
# Fixed hypotheses: the private selector is NEVER sent to Jev. Both cities have
# identical observed traffic at every allowed demand; only unused roads differ.
CITIES = {"city_a": 45.0, "city_b": 95.0}
SLOPE = 0.01
PROBES = {
    "repeat_baseline": {"cost": 0, "measurement": "Repeat the existing travel-time sensor."},
    "inspect_outer": {"cost": 1, "measurement": "Measure the fixed delay on an unused outer road."},
    "close_trial": {"cost": 3, "measurement": "Simulate temporarily closing the shortcut at full demand."},
}


@dataclass(frozen=True, slots=True)
class Intervention:
    key: str
    shortcut_open: bool
    capacity: float
    cost: int


INTERVENTIONS = tuple(
    Intervention(key, opened, capacity, cost + (0 if opened else 1))
    for capacity, cost, suffix in ((1.0, 0, ""), (1.25, 25, "_125"), (1.5, 50, "_150"), (2.0, 100, "_200"))
    for key, opened in ((f"keep{suffix}", True), (f"close{suffix}", False))
)


def questions(instruction: str, choices: dict[str, str]) -> Questions:
    return {
        "verdict": Choice(instructions=instruction, criteria=choices),
        "strength": Score(
            instructions="Score the evidential strength of your verdict, not its desirability.",
            criteria=["unsupported", "weak", "mixed", "strong", "decisive"],
        ),
        "supported": Noul(
            instructions="Is this verdict justified by the supplied evidence, without assuming hidden facts?",
            criteria={"true": "Evidence justifies this verdict.", "false": "A missing fact could reverse it."},
        ),
    }


IDENTIFY_QUESTIONS = questions(
    "Which city is identified by the measurements? Hypotheses are not observations. "
    "Choose unresolved if both cities fit, regardless of narrative plausibility.",
    {"city_a": "Only city A fits.", "city_b": "Only city B fits.", "unresolved": "Both or neither fit."},
)
PROBE_QUESTIONS = questions(
    "Choose the cheapest authorized experiment that distinguishes the remaining hypotheses. "
    "Repetition is not new causal evidence. Do not choose a probe over budget.",
    {**{key: value["measurement"] for key, value in PROBES.items()}, "defer": "No useful probe is justified."},
)
FORECAST_QUESTIONS = questions(
    "Before seeing the oracle, predict the direction of equilibrium travel time versus this city's baseline. "
    "Drivers selfishly choose minimum-latency routes; adding choices can change everyone's route.",
    {"faster": "Latency decreases.", "same": "Latency is unchanged.", "slower": "Latency increases."},
)
REVIEW_QUESTIONS = questions(
    "Audit only the assigned review scope. Uphold means the deterministic candidate is justified; "
    "model forecasts are fallible judgments, not measurements. Surface unsupported identification or bad constraints.",
    {
        "uphold": "Candidate survives this review.",
        "veto": "A concrete defect blocks it.",
        "defer": "Insufficient evidence.",
    },
)
DECISION_QUESTIONS = questions(
    "Choose the cheapest minimum-worst-case-latency intervention among budget-feasible candidates "
    "in the surviving cities, only if identification and both reviews support it. Otherwise defer. "
    "This is a synthetic equilibrium exercise, never authority over actual roads.",
    {**{item.key: str(asdict(item)) for item in INTERVENTIONS}, "defer": "Hold for human review."},
)
QUESTION_SETS = {
    "blind": IDENTIFY_QUESTIONS,
    "experiment": PROBE_QUESTIONS,
    "posterior": IDENTIFY_QUESTIONS,
    **{f"forecast-{city}-{item.key}": FORECAST_QUESTIONS for city in CITIES for item in INTERVENTIONS},
    "causal-critic": REVIEW_QUESTIONS,
    "safety-critic": REVIEW_QUESTIONS,
    "recommendation": DECISION_QUESTIONS,
    "order-challenge": DECISION_QUESTIONS,
}
PROGRESS_STEPS = (
    ("twins", "Construct observational twins"),
    *((key, key.replace("-", " ").title()) for key in QUESTION_SETS),
    ("oracle", "Unseal exact counterfactuals"),
    ("policy", "Certificate and deterministic policy"),
)


@dataclass(frozen=True, slots=True)
class Equilibrium:
    travel_minutes: float
    upper_flow: float
    lower_flow: float
    shortcut_flow: float
    route_minutes: tuple[float, float, float | None]


def equilibrium(demand: float, fixed_delay: float, intervention: Intervention) -> Equilibrium:
    """Exact symmetric Wardrop equilibrium; no iterative or model-based solver.

    Routes: S-A-T, S-B-T, S-A-B-T. S-A and B-T cost slope*flow;
    A-T and S-B cost fixed_delay. A-B is a zero-delay directed shortcut.
    Capacity divides the slope of BOTH congestible edges, not the fixed delays.
    """
    if not math.isfinite(demand) or demand <= 0 or not math.isfinite(fixed_delay) or fixed_delay <= 0:
        raise ValueError("Demand and fixed delay must be positive and finite")
    if not math.isfinite(intervention.capacity) or intervention.capacity <= 0:
        raise ValueError("Capacity must be positive and finite")
    slope = SLOPE / intervention.capacity
    shortcut = max(0.0, min(demand, 2 * fixed_delay / slope - demand)) if intervention.shortcut_open else 0.0
    outer = (demand - shortcut) / 2
    outer_time = slope * (outer + shortcut) + fixed_delay
    shortcut_time = slope * (demand + shortcut) if intervention.shortcut_open else None
    travel = (2 * outer * outer_time + shortcut * (shortcut_time or 0)) / demand
    return Equilibrium(travel, outer, outer, shortcut, (outer_time, outer_time, shortcut_time))


def validate_state(state: dict[str, Any]) -> list[str]:
    """Also validate direct CLI/library calls, not just the gallery's shape check."""
    errors: list[str] = []
    if set(state) != set(STATE):
        return ["$: fields must match the canonical state"]
    if not isinstance(state["run_id"], str) or not 1 <= len(state["run_id"]) <= 100:
        errors.append("$.run_id: must contain 1 to 100 characters")
    if state["hidden_city"] not in tuple(CITIES):
        errors.append("$.hidden_city: must be city_a or city_b")
    for field, lower, upper in (
        ("demand", 1000, 4500),
        ("probe_budget", 0, 3),
        ("intervention_budget", 0, 101),
        ("call_budget", MAX_CALLS, MAX_CALLS),
    ):
        value = state[field]
        if type(value) is not int or not lower <= value <= upper:
            errors.append(f"$.{field}: must be an integer between {lower} and {upper}")
    confidence = state["minimum_confidence"]
    if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0.5 <= confidence <= 0.95:
        errors.append("$.minimum_confidence: must be finite and between 0.5 and 0.95")
    guards = state["guardrails"]
    if not isinstance(guards, dict) or guards != STATE["guardrails"] or any(v is not True for v in guards.values()):
        errors.append("$.guardrails: all canonical simulation guardrails must remain true")
    return errors


def observation(city: str, demand: int) -> dict[str, float]:
    result = equilibrium(demand, CITIES[city], INTERVENTIONS[0])
    # Do not expose unused-route times, hypothesis labels, or the private selector.
    return {"travel_minutes": result.travel_minutes, "shortcut_flow": result.shortcut_flow}


def probe_value(city: str, demand: int, probe: str) -> float:
    if probe == "inspect_outer":
        return CITIES[city]
    if probe == "close_trial":
        return equilibrium(demand, CITIES[city], INTERVENTIONS[1]).travel_minutes
    if probe == "repeat_baseline":
        return observation(city, demand)["travel_minutes"]
    raise ValueError(f"Unknown probe: {probe}")


def surviving_cities(demand: int, probe: str, measured: float | None) -> tuple[str, ...]:
    if measured is None:
        return tuple(CITIES)
    return tuple(city for city in CITIES if math.isclose(probe_value(city, demand, probe), measured, abs_tol=1e-9))


def direction(before: float, after: float) -> str:
    return "same" if math.isclose(before, after, abs_tol=1e-9) else "faster" if after < before else "slower"


def oracle_table(demand: int) -> list[dict[str, Any]]:
    return [
        {
            "city": city,
            "intervention": asdict(item),
            "equilibrium": asdict(result),
            "direction": direction(observation(city, demand)["travel_minutes"], result.travel_minutes),
        }
        for city, fixed in CITIES.items()
        for item in INTERVENTIONS
        for result in (equilibrium(demand, fixed, item),)
    ]


def best_intervention(demand: int, cities: tuple[str, ...], budget: int) -> Intervention:
    """Minimax travel time, then cost, then stable key. No model chooses the optimum."""
    if not cities:
        raise ValueError("No consistent city; cannot certify an intervention")
    return min(
        (item for item in INTERVENTIONS if item.cost <= budget),
        key=lambda item: (
            round(max(equilibrium(demand, CITIES[city], item).travel_minutes for city in cities), 9),
            item.cost,
            item.key,
        ),
    )


def decide(
    *,
    candidate: Intervention,
    survivors: tuple[str, ...],
    posterior: JevSignals,
    critics: tuple[JevSignals, ...],
    recommendation: JevSignals,
    challenge: JevSignals,
    minimum_confidence: float,
    selected_forecast_correct: bool,
    calls_used: int,
    call_budget: int,
) -> PolicyDecision:
    confidence = min(signal.confidence for signal in (posterior, *critics, recommendation, challenge))
    reason = ""
    if calls_used > call_budget:
        reason = "The hard call budget was breached."
    elif len(survivors) != 1 or posterior.choice != survivors[0]:
        reason = "Observations do not uniquely identify a city, or Jev's posterior contradicts the measurement."
    elif confidence < minimum_confidence:
        reason = "A required judgment is below the configured confidence floor."
    elif any(signal.noul < 0.8 for signal in (posterior, recommendation, challenge)):
        reason = "Identification or recommendation lacks positive evidential support."
    elif len(critics) != 2 or any(critic.choice != "uphold" or critic.noul < 0.8 for critic in critics):
        reason = "The causal or safety critic did not uphold the candidate."
    elif not selected_forecast_correct:
        reason = "Jev's sealed forecast for the selected city/intervention failed the exact oracle."
    elif recommendation.choice != challenge.choice:
        reason = "Reordering identical evidence changed Jev's recommendation."
    elif recommendation.choice != candidate.key:
        reason = "Jev's recommendation does not match the budget-feasible minimax certificate."
    if reason:
        return PolicyDecision(
            action="Hold the simulated intervention and send the complete counterfactual trace to a human reviewer.",
            reason=reason,
            confidence=confidence,
            fallback=True,
            owner="simulation experiment lead",
        )
    return PolicyDecision(
        action=f"Recommend {candidate.key} inside the simulator only; attach the exact equilibrium certificate.",
        reason="Measured identification, sealed forecast, two critics, order challenge, and minimax certificate agree.",
        confidence=confidence,
        fallback=False,
        owner="simulation experiment lead",
    )


def _model_call(key: str, payload: dict[str, Any], on_progress: ProgressCallback | None) -> OperationStage:
    label = key.replace("-", " ").title()
    report_progress(on_progress, key, label, "running")
    try:
        with TypeSafeClient(timeout=30) as client:
            response: SystemOneResponse = client.system_one(state=payload, questions=QUESTION_SETS[key])
    except Exception as error:
        report_progress(on_progress, key, label, "failed", type(error).__name__)
        raise
    report_progress(on_progress, key, label, "completed", f"model={response.model}")
    return OperationStage(key, label, QUESTION_SETS[key], response)


class Council:
    """Reserve attempted calls before dispatch; append concurrent results in stable order."""

    def __init__(self, budget: int, on_progress: ProgressCallback | None) -> None:
        self.budget = budget
        self.on_progress = on_progress
        self.calls = 0
        self.stages: list[OperationStage] = []
        self.audit: list[AuditEvent] = []

    def record(self, event: str, detail: str) -> None:
        self.audit.append(AuditEvent(len(self.audit) + 1, event, detail))

    def batch(self, requests: dict[str, dict[str, Any]]) -> dict[str, JevSignals]:
        if self.calls + len(requests) > self.budget:
            raise RuntimeError("Hard Jev call budget exhausted before dispatch")
        self.calls += len(requests)
        for key, payload in requests.items():
            self.record("model.input.sealed", f"stage={key} fingerprint={state_fingerprint(payload)}")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="counterfactual") as pool:
            futures = [pool.submit(_model_call, key, payload, self.on_progress) for key, payload in requests.items()]
            stages = [future.result() for future in futures]
        self.stages.extend(stages)
        return {stage.key: signals_from_response(stage.response, SIGNALS) for stage in stages}

    def ask(self, key: str, payload: dict[str, Any]) -> JevSignals:
        return self.batch({key: payload})[key]


def public_context(demand: int) -> dict[str, Any]:
    return {
        "environment": "Synthetic, noiseless, static traffic equilibrium. Not a real traffic-control system.",
        "demand": demand,
        "network": {
            "routes": ["S-A-T", "S-B-T", "S-A-B-T"],
            "S-A_and_B-T": "Each costs 0.01 * total edge flow / capacity minutes.",
            "A-T_and_S-B": "Each costs the city's fixed delay, independent of flow.",
            "A-B": "Directed zero-delay shortcut, unless closed.",
            "equilibrium": "All used routes have equal minimum latency; unused routes cannot be faster.",
            "capacity": "Multiplier on BOTH congestible roads; every trip must still be served.",
        },
        "hypotheses": [{"city": city, "fixed_delay_minutes": delay} for city, delay in CITIES.items()],
        "observation": observation("city_a", demand),
        "trust_boundary": "Hypotheses and model outputs are not measurements. No hidden selector is supplied.",
    }


def _visualizations(
    demand: int,
    rows: list[dict[str, Any]],
    forecasts: dict[str, JevSignals],
    stages: list[OperationStage],
    blind: JevSignals,
    posterior: JevSignals,
) -> tuple[Visualization, ...]:
    latency = Visualization(
        kind="line",
        title="Two identical presents. Opposite futures. / exact simulated minutes",
        x_label="intervention index (0 keep / 1 close / then capacity pairs)",
        y_label="equilibrium travel minutes",
        points=tuple(
            ChartPoint(
                label=f"{city}/{item.key}",
                value=equilibrium(demand, fixed, item).travel_minutes,
                x=float(index),
                series=city,
                detail=f"cost={item.cost}; capacity={item.capacity}; shortcut_open={item.shortcut_open}",
            )
            for city, fixed in CITIES.items()
            for index, item in enumerate(INTERVENTIONS)
        ),
    )
    scoreboard = Visualization(
        kind="bar",
        title="Sealed forecasts / 1 correct, 0 wrong (not a calibration estimate)",
        points=tuple(
            ChartPoint(
                label=f"{row['city']}/{row['intervention']['key']}",
                value=float(forecast.choice == row["direction"]),
                series=row["city"],
                detail=f"Jev={forecast.choice}; oracle={row['direction']}; certainty={forecast.confidence:.0%}",
            )
            for row in rows
            for forecast in (forecasts[f"forecast-{row['city']}-{row['intervention']['key']}"],)
        ),
    )
    identification = Visualization(
        kind="bar",
        title="Before / after the chosen experiment (certainty is not correctness)",
        points=tuple(
            ChartPoint(label=label, value=signal.confidence, detail=f"identified={signal.choice}")
            for label, signal in (("before measurement", blind), ("after measurement", posterior))
        ),
    )
    graph = Visualization(
        kind="pipeline",
        title="23 live Jev judgments / 16 sealed futures / one deterministic gate",
        points=tuple(
            ChartPoint(
                label=stage.key.removeprefix("forecast-"),
                value=signals_from_response(stage.response, SIGNALS).confidence,
                x=float(
                    3 + ("city_b" in stage.key)
                    if stage.key.startswith("forecast-")
                    else index
                    if index < 3
                    else index - 14
                ),
                y=float((index - 3) % 8) if stage.key.startswith("forecast-") else 3.5,
                series="city_b" if "city_b" in stage.key else "judgment",
                detail=signals_from_response(stage.response, SIGNALS).choice,
            )
            for index, stage in enumerate(stages)
        ),
    )
    return latency, scoreboard, identification, graph


def execute(
    state: dict[str, Any] | None = None,
    on_progress: ProgressCallback | None = None,
) -> OperationRun:
    config = deepcopy(STATE if state is None else state)
    errors = validate_state(config)
    if errors:
        raise ValueError("; ".join(errors))
    require_live_api_key()
    council = Council(config["call_budget"], on_progress)
    fingerprint = state_fingerprint(config)
    council.record("run.accepted", f"fingerprint={fingerprint}; simulator=exact-symmetric-wardrop/v1")
    report_progress(on_progress, "twins", "Construct observational twins", "running")
    context = public_context(config["demand"])
    council.record("twins.constructed", f"same observations; hypothesis fingerprint={state_fingerprint(context)}")
    report_progress(
        on_progress, "twins", "Construct observational twins", "completed", "two indistinguishable baselines"
    )
    blind = council.ask("blind", context)
    experiment = council.ask("experiment", {**context, "probe_menu": PROBES, "probe_budget": config["probe_budget"]})
    probe = experiment.choice
    authorized = probe in PROBES and PROBES[probe]["cost"] <= config["probe_budget"]
    measured = probe_value(config["hidden_city"], config["demand"], probe) if authorized else None
    survivors = surviving_cities(config["demand"], probe, measured)
    measurement = {"probe": probe, "authorized": authorized, "measured_minutes": measured}
    council.record("probe.measured" if authorized else "probe.blocked", str(measurement))
    council.record("hypotheses.filtered", f"survivors={survivors}")
    posterior = council.ask("posterior", {**context, "measurement": measurement})

    # Every forecast is sealed before constructing or revealing oracle outcomes.
    forecasts = council.batch(
        {
            f"forecast-{city}-{item.key}": {
                **context,
                "conditional_city": city,
                "intervention": asdict(item),
                "task": "Assume this hypothesis for this forecast only; predict before the oracle is revealed.",
            }
            for city in CITIES
            for item in INTERVENTIONS
        }
    )
    council.record("forecasts.sealed", f"count={len(forecasts)}; no oracle outputs supplied to forecasters")
    report_progress(on_progress, "oracle", "Unseal exact counterfactuals", "running")
    rows = oracle_table(config["demand"])
    candidate = best_intervention(config["demand"], survivors, config["intervention_budget"])
    scored = [
        {
            **row,
            "forecast": asdict(forecasts[f"forecast-{row['city']}-{row['intervention']['key']}"]),
            "correct": forecasts[f"forecast-{row['city']}-{row['intervention']['key']}"].choice == row["direction"],
        }
        for row in rows
    ]
    correct = sum(row["correct"] for row in scored)
    council.record("oracle.unsealed", f"forecast_accuracy={correct}/16; table={state_fingerprint({'rows': rows})}")
    for row in scored:
        council.record(
            "forecast.scored",
            f"{row['city']}/{row['intervention']['key']}: predicted={row['forecast']['choice']} "
            f"actual={row['direction']} minutes={row['equilibrium']['travel_minutes']:.3f} correct={row['correct']}",
        )
    report_progress(
        on_progress, "oracle", "Unseal exact counterfactuals", "completed", f"forecasts correct={correct}/16"
    )
    evidence = {
        **context,
        "measurement": measurement,
        "surviving_cities": survivors,
        "posterior": asdict(posterior),
        "intervention_budget": config["intervention_budget"],
        "counterfactuals": scored,
        "deterministic_candidate": asdict(candidate),
        "limitations": "Exact only inside this closed, noiseless two-hypothesis simulator. Not real-world causality.",
    }
    critics = council.batch(
        {
            "causal-critic": {
                **evidence,
                "scope": "Check identifiability, observational twins, selected forecast, and causal overclaiming.",
            },
            "safety-critic": {
                **evidence,
                "scope": "Check budget, preserved trips, minimum worst-case latency, and simulation-only authority.",
            },
        }
    )
    reviewed = {**evidence, "reviews": {key: asdict(value) for key, value in critics.items()}}
    recommendation = council.ask("recommendation", reviewed)
    # Same facts/questions, different order; the first recommendation is withheld.
    reordered = {
        **reviewed,
        "hypotheses": list(reversed(reviewed["hypotheses"])),
        "counterfactuals": list(reversed(scored)),
    }
    challenge = council.ask("order-challenge", reordered)
    council.record("order.checked", f"first={recommendation.choice}; reordered={challenge.choice}")
    selected_correct = all(
        row["correct"] for row in scored if row["city"] in survivors and row["intervention"]["key"] == candidate.key
    )
    report_progress(on_progress, "policy", "Certificate and deterministic policy", "running")
    decision = decide(
        candidate=candidate,
        survivors=survivors,
        posterior=posterior,
        critics=tuple(critics.values()),
        recommendation=recommendation,
        challenge=challenge,
        minimum_confidence=config["minimum_confidence"],
        selected_forecast_correct=selected_correct,
        calls_used=council.calls,
        call_budget=config["call_budget"],
    )
    certificate = {
        "candidate": asdict(candidate),
        "survivors": survivors,
        "worst_case_minutes": max(
            equilibrium(config["demand"], CITIES[city], candidate).travel_minutes for city in survivors
        ),
    }
    council.record("certificate.computed", str(certificate))
    council.record("policy.evaluated", f"fallback={decision.fallback}; calls={council.calls}/{council.budget}")
    council.record("execution.blocked", "Only simulated measurements; no road, notification, or external state changed")
    report_progress(
        on_progress, "policy", "Certificate and deterministic policy", "completed", f"fallback={decision.fallback}"
    )
    return OperationRun(
        correlation_id=config["run_id"],
        policy_version=POLICY_VERSION,
        state_fingerprint=fingerprint,
        stages=tuple(council.stages),
        decision=decision,
        controls=(
            "Synthetic traffic, real Jev calls. No canned model answers and no real traffic authority.",
            "The private city selector never enters a Jev request; only the authorized measurement can distinguish it.",
            "23 stage calls maximum, four workers, 30-second SDK timeout per call; no orchestration retries.",
            "All 16 forecasts are sealed before exact outcomes are supplied; mistakes remain visible.",
            "The oracle is exact only for the stated symmetric, static, noiseless Wardrop model.",
            "All trips are preserved; construction costs and probe authorization are enforced outside Jev.",
            "Two critics and an order-invariance check can veto, never override, the deterministic certificate.",
            "No identification, disagreement, low confidence, or a wrong selected forecast means human review.",
        ),
        audit=tuple(council.audit),
        visualizations=_visualizations(config["demand"], rows, forecasts, council.stages, blind, posterior),
    )


def main() -> None:
    render_operation(title=TITLE, state=STATE, run=execute())


if __name__ == "__main__":
    main()
