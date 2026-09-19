# Tiny Museum Curator

Three ordinary desk objects are enough for a very small exhibition if someone can find the thread. Jev types a curatorial theme, seriousness, and coherence, then a deterministic label cabinet supplies a title or falls back to a choose-your-own-theme display.

```mermaid
flowchart LR
    state["State<br/>Everyday objects"] --> jev["Jev"]
    jev --> typed["Typed result<br/>Choice + Score + Noul"]
    typed --> policy["Deterministic label cabinet"]
    policy -->|Confident| action["Exhibition title"]
    policy -->|Uncertain| fallback["Open theme cards"]
```

```bash
uv run python fun/tiny-museum-curator/demo.py
```