# Emergency Dispatch

A call center needs a fast incident summary while certified dispatchers retain control of every resource assignment. Jev types the incident, estimates priority and immediate danger, then deterministic policy presents a recommendation or keeps the caller with a human when confidence is weak.

```mermaid
flowchart LR
	state["State<br/>Emergency call"] --> jev["Jev"]
	jev --> typed["Typed result<br/>Choice + Score + Noul"]
	typed --> policy["Deterministic policy<br/>Dispatch protocol"]
	policy -->|Confident| action["Priority recommendation<br/>Human approval required"]
	policy -->|Uncertain| fallback["Safe fallback<br/>Certified dispatcher"]
```

```bash
uv run python critical/emergency-dispatch/demo.py
```