# Global Payment Incident Command

A payment platform is degrading across regions while a release and provider instability overlap, making a single-label diagnosis unsafe. Two Jev stages assess the incident and then challenge the proposed intervention; deterministic policy checks agreement, blast radius, evidence sufficiency, and change risk before producing an approval-gated recommendation.

```mermaid
flowchart LR
    snapshot["Immutable incident snapshot"] --> assess["Jev stage 1<br/>Failure + impact"]
    assess --> typed1["Typed situation signals"]
    typed1 --> enrich["Enriched intervention state<br/>Constraints + stage 1"]
    enrich --> challenge["Jev stage 2<br/>Action + change risk"]
    challenge --> typed2["Typed intervention signals"]
    typed2 --> gate["Deterministic policy v3.2"]
    gate -->|Agreement + confidence| approval["Dual-approval recommendation"]
    gate -->|Conflict or uncertainty| fallback["Freeze automation + incident commander"]
```

Production-shaped controls include an idempotency key, immutable state fingerprint, ordered audit events, dual approval, and a dry-run-only client. No rollback, failover, traffic shift, or customer communication is executed by this demo.

```bash
uv run python berserk/global-payment-incident/demo.py
```