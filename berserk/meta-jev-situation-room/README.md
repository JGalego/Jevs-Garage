# Meta-Jev Global Situation Room

Four live public-data pipelines fan out concurrently across earthquakes, severe weather, exploited vulnerabilities, and space weather. Their typed Jev outputs become inputs to two critic Jevs, then an arbiter Jev, then a counterfactual stability Jev; deterministic policy merges the whole evidence graph into one advisory posture or a safe fallback.

```mermaid
flowchart LR
    usgs["USGS earthquakes"] --> eq["Jev / seismic specialist"]
    nws["NWS alerts"] --> wx["Jev / weather specialist"]
    cisa["CISA KEV"] --> cyber["Jev / cyber specialist"]
    noaa["NOAA Kp"] --> space["Jev / space-weather specialist"]
    eq --> merge1["Typed evidence graph"]
    wx --> merge1
    cyber --> merge1
    space --> merge1
    merge1 --> calibration["Jev / calibration critic"]
    merge1 --> dependency["Jev / dependency critic"]
    calibration --> merge2["Meta-output merge"]
    dependency --> merge2
    merge2 --> arbiter["Jev / posture arbiter"]
    arbiter --> stability["Jev / counterfactual stability"]
    stability --> gate["Deterministic quorum + confidence policy"]
    gate -->|Robust| advisory["Approval-gated advisory posture"]
    gate -->|Fragile| fallback["Human situation lead"]
```

This is intentionally recursive: Jev outputs are serialized as explicitly probabilistic evidence, criticized by other Jevs, merged, adjudicated, and challenged again. Every source has a URL, retrieval timestamp, source timestamp, record count, and SHA-256 receipt; the gallery renders maps, bars, a line chart, and the pipeline confidence graph.

```bash
uv run python berserk/meta-jev-situation-room/demo.py
```
