# takeover-board

Static, auto-published Roblox screening boards. Two pages, both self-contained HTML with no build step:

- `gemhunt.html` — GEMHUNT board: young/small games ranked by engagement. Regenerated on the mac-mini every 15 min.
- `ratio.html` — CCU / lifetime-visits leaderboard over Scout's rotrends pool. Regenerated hourly.

`ratio-gen.py` renders `ratio.html` from the newest full `scrape-history` snapshot.
`publish.sh` copies the current pages out of the station and force-pushes a single-commit
`gh-pages` branch, so the repo never accumulates history.

No credentials, tokens, or hostnames are committed here. Data originates from Roblox's public game API.
