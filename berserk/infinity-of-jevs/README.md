# Infinity of Jevs

A recursive council repeatedly fans one live USGS earthquake feed through hazard, exposure, skeptic, and counterfactual Jevs, then feeds all four typed outputs into a merger Jev. Each merged result becomes evidence for the next round until deterministic code detects convergence, an A-B-A cycle, or the hard round and call budgets; a final auditor Jev challenges whatever survives.

```mermaid
flowchart LR
    source["Live USGS feed"] --> r1a["Round 1<br/>4 Jevs in parallel"]
    r1a --> r1m["Merger Jev"]
    r1m --> check1{"Converged<br/>or cycle?"}
    check1 -->|No| r2a["Round 2<br/>4 Jevs + prior output"]
    r2a --> r2m["Merger Jev"]
    r2m --> check2{"Converged<br/>or cycle?"}
    check2 -->|No| rn["Repeat within hard bound"]
    check1 -->|Yes| audit["Final auditor Jev"]
    check2 -->|Yes| audit
    rn --> audit
    audit --> policy["Deterministic policy"]
    policy -->|Robust| result["Approval-gated advisory"]
    policy -->|Fragile / cyclic| fallback["Human adjudication"]
```

The infinity is conceptual, never literal: defaults permit at most three rounds and sixteen Jev calls. Earlier outputs are marked as probabilistic evidence rather than independent facts, cycles and convergence are detected outside the model, unused rounds appear as skipped in the live tracker, and no external action is available.

```bash
uv run python berserk/infinity-of-jevs/demo.py
```
