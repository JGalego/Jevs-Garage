# Safety Guardrails

An assistant has drafted a response that may cross an operational safety boundary, but a probabilistic classifier must not become the final authority. Jev labels the response mode, scores harm, and estimates a policy violation; deterministic rules then release, transform, withhold, or escalate it.

`state -> Jev -> Choice + Score + Noul -> release policy -> safe response or review fallback`

```bash
uv run python critical/safety-guardrails/demo.py
uv run python critical/safety-guardrails/demo.py --scenario uncertain
uv run python critical/safety-guardrails/demo.py --live
```