# Tabletop Sidekick

A one-shot party needs a final character who complements the table instead of stealing every scene. Jev types the missing role, chaos level, and team fit, then a deterministic character shelf supplies one sidekick or asks the group to choose when the read is uncertain.

```mermaid
flowchart LR
	state["State<br/>Party + adventure"] --> jev["Jev"]
	jev --> typed["Typed result<br/>Choice + Score + Noul"]
	typed --> policy["Deterministic character shelf"]
	policy -->|Confident| action["Sidekick card"]
	policy -->|Uncertain| fallback["Table vote"]
```

```bash
uv run python fun/tabletop-sidekick/demo.py
uv run python fun/tabletop-sidekick/demo.py --scenario uncertain
uv run python fun/tabletop-sidekick/demo.py --live
```