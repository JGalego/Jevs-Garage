# Cyber Triage

A security operations center needs to sort noisy endpoint alerts without letting a classifier isolate machines on its own. Jev estimates incident class, severity, and compromise probability; policy turns strong agreement into an operator recommendation and routes ambiguity to an analyst.

`state -> Jev -> Choice + Score + Noul -> SOC policy -> recommendation or analyst fallback`

```bash
uv run python critical/cyber-triage/demo.py
uv run python critical/cyber-triage/demo.py --scenario uncertain
uv run python critical/cyber-triage/demo.py --live
```