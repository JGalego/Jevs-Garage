# Playlist Pilot

A commute mood is messy; a playlist switch does not have to be. Jev turns context into mood, energy, and lyric preference, then a fixed set of playlist recipes chooses a queue or offers a mixed sampler when the vibe is unclear.

```mermaid
flowchart LR
	state["State<br/>Moment + listening note"] --> jev["Jev"]
	jev --> typed["Typed result<br/>Choice + Score + Noul"]
	typed --> policy["Deterministic playlist recipe"]
	policy -->|Confident| action["Playlist queue"]
	policy -->|Uncertain| fallback["Mood samplers"]
```

```bash
uv run python fun/playlist-pilot/demo.py
```