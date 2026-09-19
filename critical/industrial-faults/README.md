# Industrial Faults

A plant operator needs a rapid interpretation of noisy pump telemetry, but a model must never actuate machinery. Jev identifies a likely fault, scores severity, and estimates unsafe operation; fixed rules produce an operator-facing recommendation or a conservative inspection fallback.

```mermaid
flowchart LR
	state["State<br/>Pump telemetry"] --> jev["Jev"]
	jev --> typed["Typed result<br/>Choice + Score + Noul"]
	typed --> policy["Deterministic policy<br/>Operating envelope"]
	policy -->|Confident| action["Operator recommendation<br/>Monitor or controlled stop"]
	policy -->|Uncertain| fallback["Safe fallback<br/>Instrument inspection"]
```

```bash
uv run python critical/industrial-faults/demo.py
```