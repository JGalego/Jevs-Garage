# AI Output Verification

A report-writing assistant has produced a confident factual claim that may disagree with its cited evidence. Jev evaluates support, reliability, and citation agreement; deterministic publication rules either release the sentence, hold it, or request a human fact check.

```mermaid
flowchart LR
	state["State<br/>Claim + evidence"] --> jev["Jev"]
	jev --> typed["Typed result<br/>Choice + Score + Noul"]
	typed --> policy["Deterministic policy<br/>Publication rules"]
	policy -->|Confident| action["Verify or block<br/>the claim"]
	policy -->|Uncertain| fallback["Safe fallback<br/>Human fact check"]
```

```bash
uv run python critical/ai-output-verification/demo.py
```