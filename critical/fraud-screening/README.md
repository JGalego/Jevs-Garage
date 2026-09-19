# Fraud Screening

A card processor needs a fast risk recommendation without letting a probabilistic model decline a payment. Jev scores the transaction and the deterministic policy either allows normal authorization, places a reversible hold for an analyst, or falls back when the signals are ambiguous.

```mermaid
flowchart LR
	state["State<br/>Transaction"] --> jev["Jev"]
	jev --> typed["Typed result<br/>Choice + Score + Noul"]
	typed --> policy["Deterministic policy<br/>Risk thresholds"]
	policy -->|Confident| action["Authorization path<br/>or reversible hold"]
	policy -->|Uncertain| fallback["Safe fallback<br/>Fraud analyst"]
```

```bash
uv run python critical/fraud-screening/demo.py
```