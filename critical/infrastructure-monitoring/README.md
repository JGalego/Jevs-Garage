# Infrastructure Monitoring

An on-call engineer needs a fast reading of a noisy production incident without allowing a model to deploy, roll back, or restart anything. Jev classifies the likely failure domain, impact, and outage state; deterministic policy recommends an operator-approved response or gathers more evidence.

```mermaid
flowchart LR
	state["State<br/>Production telemetry"] --> jev["Jev"]
	jev --> typed["Typed result<br/>Choice + Score + Noul"]
	typed --> policy["Deterministic policy<br/>Operations thresholds"]
	policy -->|Confident| action["Runbook recommendation<br/>Operator approval"]
	policy -->|Uncertain| fallback["Safe fallback<br/>Freeze and gather evidence"]
```

```bash
uv run python critical/infrastructure-monitoring/demo.py
```