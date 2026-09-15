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

Env: GITHUB_TOKEN, GITHUB_REPOSITORY (owner/repo), TG_BOT_TOKEN, TG_CHAT_ID.
Optional: THRESHOLD_MIN (50), REPEAT_MIN (360), BRANCH (gh-pages), STATE_BRANCH (deadman-state),
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
    if action is not None or new_state != state:
        st["state"] = new_state
        st["updated"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        put_state(repo, token, state_branch, st, sha, dry)


if __name__ == "__main__":
    main()
