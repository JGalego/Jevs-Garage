# Medical Routing

A virtual intake desk must route symptoms quickly without pretending to diagnose or replacing a clinician. Jev estimates route, urgency, and red-flag probability; deterministic policy presents conservative guidance or hands uncertain cases to a licensed professional.

```mermaid
flowchart LR
	state["State<br/>Reported symptoms"] --> jev["Jev"]
	jev --> typed["Typed result<br/>Choice + Score + Noul"]
	typed --> policy["Deterministic policy<br/>Clinical routing rules"]
	policy -->|Confident| action["Care guidance<br/>No diagnosis"]
	policy -->|Uncertain| fallback["Safe fallback<br/>Licensed clinician"]
```

```bash
uv run python critical/medical-routing/demo.py
```