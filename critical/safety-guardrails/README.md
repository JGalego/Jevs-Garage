# Safety Guardrails

An assistant has drafted a response that may cross an operational safety boundary, but a probabilistic classifier must not become the final authority. Jev labels the response mode, scores harm, and estimates a policy violation; deterministic rules then release, transform, withhold, or escalate it.

```mermaid
flowchart LR
	state["State<br/>Draft response"] --> jev["Jev"]
	jev --> typed["Typed result<br/>Choice + Score + Noul"]
	typed --> policy["Deterministic policy<br/>Release rules"]
	policy -->|Confident| action["Release, transform,<br/>or suppress"]
	policy -->|Uncertain| fallback["Safe fallback<br/>Safety reviewer"]
```

```bash
uv run python critical/safety-guardrails/demo.py
```