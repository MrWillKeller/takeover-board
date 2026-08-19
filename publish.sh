#!/bin/bash
# publish.sh — push the current boards to GitHub Pages. Runs on the mac-mini from cron.
#
# Two things this script is careful about:
#
#   1. It COPIES ~/.openclaw/shared/gemhunt-dash/index.html. That file is load-bearing
#      input, not just output — gemhunt-fill.py:21 regex-parses its `const G=[...], M=`
#      literal every hour to build the server-fill shortlist. Moving, renaming or
#      rewriting it in place breaks the hourly sweep.
#
#   2. It force-pushes a single-commit orphan branch. The two pages total ~1.7 MB and
#      this runs 96x/day; keeping history would add ~163 MB/day and cross GitHub's 1 GB
#      soft repo limit within a week. Each publish replaces the branch outright, so the
#      remote stays at one snapshot.

set -euo pipefail

REPO_SSH="git@github.com:MrWillKeller/takeover-board.git"
STAGE="$HOME/.openclaw/shared/board-stage"
DASH="$HOME/.openclaw/shared/gemhunt-dash/index.html"
SRC="$HOME/.openclaw/scripts"
BRANCH="gh-pages"
LOCK="/tmp/takeover-board-publish.lock"

# Lockfile — a slow push must not overlap the next cron tick.
exec 9>"$LOCK"
flock -n 9 || { echo "$(date -u +%FT%TZ) publish already running, skipping"; exit 0; }

[ -f "$DASH" ] || { echo "FATAL: dashboard missing at $DASH"; exit 1; }

mkdir -p "$STAGE"
cd "$STAGE"

if [ ! -d .git ]; then
  git init -q
  git remote add origin "$REPO_SSH"
  git config user.email "theoricast@gmail.com"
  git config user.name "MrWillKeller"
  git config core.sshCommand "ssh -i $HOME/.ssh/takeover_board_deploy -o IdentitiesOnly=yes"
fi

# --- assemble ---------------------------------------------------------------
cp "$DASH" gemhunt.html                       # COPY. see note 1 above.
python3 "$SRC/ratio-gen.py" "$STAGE/ratio.html"
python3 "$SRC/inject-nav.py" "$STAGE/gemhunt.html"
cp "$SRC/board-index.html" index.html
printf 'User-agent: *\nDisallow: /\n' > robots.txt

# --- verify before publishing ----------------------------------------------
# Never push a truncated or empty board: a failed generator upstream would
# otherwise quietly replace a good page with a broken one.
for f in gemhunt.html ratio.html index.html; do
  [ -s "$f" ] || { echo "FATAL: $f is empty"; exit 1; }
done
GH_BYTES=$(wc -c < gemhunt.html)
RT_BYTES=$(wc -c < ratio.html)
[ "$GH_BYTES" -gt 200000 ] || { echo "FATAL: gemhunt.html only $GH_BYTES B — generator likely failed"; exit 1; }
[ "$RT_BYTES" -gt 200000 ] || { echo "FATAL: ratio.html only $RT_BYTES B — generator likely failed"; exit 1; }
grep -q 'const G=' gemhunt.html || { echo "FATAL: gemhunt.html has no data payload"; exit 1; }
grep -q 'const G=' ratio.html   || { echo "FATAL: ratio.html has no data payload"; exit 1; }

# Refuse to publish anything token-shaped, whatever changes upstream.
if grep -qE '[0-9]{8,10}:AA[A-Za-z0-9_-]{30,}|ROBLOSECURITY|sk-[A-Za-z0-9_-]{16,}|eyJ[A-Za-z0-9_-]{20,}' \
     gemhunt.html ratio.html index.html; then
  echo "FATAL: credential-shaped string found in output — refusing to publish"; exit 1
fi

# --- publish ----------------------------------------------------------------
git checkout -q --orphan tmp-publish 2>/dev/null || git checkout -q -B tmp-publish
git add -A gemhunt.html ratio.html index.html robots.txt
git commit -q -m "boards $(date -u +%FT%TZ)" || { echo "no change"; exit 0; }
git branch -qM "$BRANCH"
git push -q --force origin "$BRANCH"

# Keep the local stage from growing without bound.
git reflog expire --expire=now --all >/dev/null 2>&1 || true
git gc --prune=now -q >/dev/null 2>&1 || true

echo "$(date -u +%FT%TZ) published — gemhunt ${GH_BYTES}B, ratio ${RT_BYTES}B"
