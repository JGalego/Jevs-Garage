# Emergency Dispatch

A call center needs a fast incident summary while certified dispatchers retain control of every resource assignment. Jev types the incident, estimates priority and immediate danger, then deterministic policy presents a recommendation or keeps the caller with a human when confidence is weak.

`state -> Jev -> Choice + Score + Noul -> dispatch protocol -> human-approved recommendation or fallback`

```bash
uv run python critical/emergency-dispatch/demo.py
uv run python critical/emergency-dispatch/demo.py --scenario uncertain
uv run python critical/emergency-dispatch/demo.py --live
```