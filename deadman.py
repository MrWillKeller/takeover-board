#!/usr/bin/env python3
"""deadman.py — dead-man switch for the Scout/GEMHUNT station.

publish.sh (mac-mini, or the MacBook standby) force-pushes the boards to the
gh-pages branch every 20 minutes. That push is the station's heartbeat: if the
branch stops moving, nobody is publishing — the active host is down, asleep,
off-network, on a dead battery, or publish.sh itself is failing. This script
runs on GitHub's infrastructure (see .github/workflows/deadman.yml), i.e. off
both Macs, so it keeps working when they do not.

Decision (pure, unit-tested in test_deadman.py):
  fresh -> stale        : one alert when age crosses THRESHOLD_MIN
  stale, still silent   : one reminder every REPEAT_MIN
  stale -> fresh        : one "recovered" message
State lives in state.json on the `deadman-state` branch, written through the
Contents API (GITHUB_TOKEN cannot write repository variables — HTTP 403 even
with actions:write — but can write file contents with contents:write). Only
transitions commit, so the branch grows by a few commits per outage.

Tick watchdog (decide_tick, also unit-tested): GitHub drops most of this workflow's own
"*/10" schedule runs (observed 2-5 h apart, 2026-09-16), so a Cloudflare cron fires
workflow_dispatch every 10 min instead. If that tick dies (PAT expired, worker gone)
the switch would silently fall back to the slow cadence — so on each schedule
(backstop) run, once a dispatch run has ever been seen, the age of the newest
workflow_dispatch run is checked and a ⚠️ is posted (once per TICK_REPEAT_MIN)
when it exceeds TICK_STALE_MIN; the next dispatch run posts ✅. Needs actions:read.

Env: GITHUB_TOKEN, GITHUB_REPOSITORY (owner/repo), TG_BOT_TOKEN, TG_CHAT_ID.
Optional: THRESHOLD_MIN (50), REPEAT_MIN (360), BRANCH (gh-pages), STATE_BRANCH (deadman-state),
TICK_STALE_MIN (60), TICK_REPEAT_MIN (1440), GITHUB_EVENT_NAME (set by Actions),
DRY_RUN=1 (print instead of send/write), NOW_OVERRIDE / LAST_OVERRIDE (ISO
timestamps, for local testing), TEST_LABEL=1 (prefix messages with "[TEST] ").
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def decide(age_min, state, since_alert_min, threshold, repeat):
    """Return (new_state, action) where action in {None, 'alert', 'remind', 'recovered'}."""
    stale_now = age_min > threshold
    was_stale = state == "stale"
    if stale_now and not was_stale:
        return "stale", "alert"
    if stale_now and was_stale:
        if since_alert_min is not None and since_alert_min >= repeat:
            return "stale", "remind"
        return "stale", None
    if not stale_now and was_stale:
        return "fresh", "recovered"
    return "fresh", None


def decide_tick(event, tick_seen, dispatch_age_min, since_tick_alert_min, stale_after, repeat):
    """Return (tick_seen, action) where action in {None, 'tick_alert', 'tick_recovered'}.

    event: GITHUB_EVENT_NAME ('workflow_dispatch' = the Cloudflare tick, 'schedule' = backstop).
    Self-arming: never alerts until one dispatch run has been seen. Unknown age (API
    failure) is not an alert."""
    if event == "workflow_dispatch":
        return True, ("tick_recovered" if since_tick_alert_min is not None else None)
    if not tick_seen or dispatch_age_min is None or dispatch_age_min <= stale_after:
        return tick_seen, None
    if since_tick_alert_min is None or since_tick_alert_min >= repeat:
        return True, "tick_alert"
    return True, None


# --- I/O -------------------------------------------------------------------

def env(name, default=None):
    v = os.environ.get(name, default)
    if v is None:
        sys.exit(f"missing env {name}")
    return v


def gh(method, path, token, body=None):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "takeover-board-deadman",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, None


def get_state(repo, token, state_branch):
    """Return (state_dict, blob_sha_or_None) from state.json on the state branch."""
    status, data = gh("GET", f"/repos/{repo}/contents/state.json?ref={state_branch}", token)
    if status != 200 or not data:
        return {}, None
    import base64
    try:
        return json.loads(base64.b64decode(data["content"])), data["sha"]
    except (ValueError, KeyError):
        return {}, data.get("sha")


def put_state(repo, token, state_branch, state, sha, dry):
    if dry:
        print(f"[dry-run] write state.json on {state_branch}: {json.dumps(state)}")
        return
    import base64
    body = {
        "message": f"deadman: {state.get('state')} @ {state.get('updated')}",
        "content": base64.b64encode((json.dumps(state, indent=1) + "\n").encode()).decode(),
        "branch": state_branch,
    }
    if sha:
        body["sha"] = sha
    status, _ = gh("PUT", f"/repos/{repo}/contents/state.json", token, body)
    if status not in (200, 201):
        sys.exit(f"could not write state.json on {state_branch}: HTTP {status}")


def newest_dispatch_age_min(repo, token, now):
    """Minutes since the newest workflow_dispatch run of deadman.yml, or None if unknown."""
    status, data = gh("GET", f"/repos/{repo}/actions/workflows/deadman.yml/runs?event=workflow_dispatch&per_page=1", token)
    try:
        created = data["workflow_runs"][0]["created_at"]
    except (TypeError, KeyError, IndexError):
        return None
    return (now - parse_iso(created)).total_seconds() / 60


def send_telegram(bot, chat, text, dry):
    if dry:
        print("[dry-run] telegram:\n" + text)
        return
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{bot}/sendMessage", data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.loads(r.read())
    if not body.get("ok"):
        sys.exit(f"telegram refused: {body}")


def parse_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def fmt_dur(minutes):
    m = int(round(minutes))
    return f"{m // 60} h {m % 60:02d} min" if m >= 60 else f"{m} min"


def main():
    dry = os.environ.get("DRY_RUN") == "1"
    repo = env("GITHUB_REPOSITORY")
    token = env("GITHUB_TOKEN")
    bot = env("TG_BOT_TOKEN", "" if dry else None)
    chat = env("TG_CHAT_ID", "" if dry else None)
    branch = os.environ.get("BRANCH", "gh-pages")
    threshold = float(os.environ.get("THRESHOLD_MIN", "50"))
    repeat = float(os.environ.get("REPEAT_MIN", "360"))
    label = "[TEST] " if os.environ.get("TEST_LABEL") == "1" else ""

    now = parse_iso(os.environ["NOW_OVERRIDE"]) if os.environ.get("NOW_OVERRIDE") else datetime.now(timezone.utc)
    if os.environ.get("LAST_OVERRIDE"):
        last = parse_iso(os.environ["LAST_OVERRIDE"])
    else:
        status, data = gh("GET", f"/repos/{repo}/branches/{branch}", token)
        if status != 200 or not data:
            sys.exit(f"branch lookup failed: HTTP {status}")
        last = parse_iso(data["commit"]["commit"]["committer"]["date"])
    age_min = (now - last).total_seconds() / 60

    state_branch = os.environ.get("STATE_BRANCH", "deadman-state")
    st, sha = get_state(repo, token, state_branch)
    state = st.get("state", "")
    last_alert = st.get("last_alert_ts")
    stale_since = st.get("stale_since", "")
    since_alert_min = (now.timestamp() - float(last_alert)) / 60 if last_alert else None

    new_state, action = decide(age_min, state, since_alert_min, threshold, repeat)
    last_s = last.strftime("%Y-%m-%d %H:%MZ")
    print(f"branch={branch} last={last_s} age={age_min:.1f}min state={state or '(unset)'}->{new_state} action={action}")

    if action in ("alert", "remind"):
        head = label + "🚨 Scout/GEMHUNT dead-man" + (" — still silent" if action == "remind" else "")
        send_telegram(bot, chat, (
            f"{head}\n\n"
            f"Boards not published for {fmt_dur(age_min)} (last gh-pages push {last_s}, expected every 20 min).\n\n"
            "Nobody is publishing: the active host (mac-mini, or the MacBook standby) is down, asleep, "
            "off-network, out of battery — or publish.sh is failing.\n"
            "Check: MacBook lid/battery/Wi-Fi, the mini's Tailscale, then the publish log.\n"
            f"Reminder every {fmt_dur(repeat)} while silent."), dry)
        st["last_alert_ts"] = int(now.timestamp())
        if action == "alert":
            st["stale_since"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    elif action == "recovered":
        silent = f" Silent for {fmt_dur((now - parse_iso(stale_since)).total_seconds() / 60)}." if stale_since else ""
        send_telegram(bot, chat, f"{label}✅ Scout/GEMHUNT dead-man — boards publishing again (last push {last_s}, {fmt_dur(age_min)} ago).{silent}", dry)
    # Tick watchdog — is the Cloudflare workflow_dispatch tick still arriving?
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    tick_seen = bool(st.get("tick_seen"))
    tick_alert = st.get("tick_alert_ts")
    since_tick_alert_min = (now.timestamp() - float(tick_alert)) / 60 if tick_alert else None
    dispatch_age = newest_dispatch_age_min(repo, token, now) if (event == "schedule" and tick_seen) else None
    tick_seen_new, tick_action = decide_tick(
        event, tick_seen, dispatch_age, since_tick_alert_min,
        float(os.environ.get("TICK_STALE_MIN", "60")), float(os.environ.get("TICK_REPEAT_MIN", "1440")))
    print(f"event={event or '(unset)'} tick_seen={tick_seen}->{tick_seen_new} dispatch_age={'?' if dispatch_age is None else f'{dispatch_age:.1f}min'} tick_action={tick_action}")
    if tick_action == "tick_alert":
        send_telegram(bot, chat, (
            f"{label}⚠️ Scout/GEMHUNT dead-man tick stopped\n\n"
            f"No workflow_dispatch run for {fmt_dur(dispatch_age)} — the Cloudflare cron (deadman-tick) is not firing, "
            "so this switch is back on GitHub's own schedule (runs every 2-5 h, not 10 min).\n"
            "Check: PAT expired/revoked (GH_PAT secret), worker deleted, workflow renamed. "
            "~/cf-workers/deadman-tick/DEPLOY.md"), dry)
        st["tick_alert_ts"] = int(now.timestamp())
    elif tick_action == "tick_recovered":
        send_telegram(bot, chat, f"{label}✅ Scout/GEMHUNT dead-man tick back (workflow_dispatch runs again).", dry)
        st.pop("tick_alert_ts", None)

    if action is not None or new_state != state or tick_action is not None or tick_seen_new != tick_seen:
        st["state"] = new_state
        st["tick_seen"] = tick_seen_new
        st["updated"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        put_state(repo, token, state_branch, st, sha, dry)


if __name__ == "__main__":
    main()
