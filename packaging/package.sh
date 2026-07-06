#!/bin/bash
# Build a clean, sendable client package (zip) the client unzips and runs.
#
# Source comes from `git archive HEAD` — so ONLY committed files are included:
# no .env, no scans, no videos, no node_modules/__pycache__ (all gitignored or
# untracked). Then we drop in the client .env template, the Start/Stop
# launchers, and the README. Run from the repo root:  bash packaging/package.sh
set -euo pipefail
cd "$(dirname "$0")/.."

NAME="agilink-fiches-test"
OUT="dist"
rm -rf "$OUT/$NAME" "$OUT/$NAME.zip"
mkdir -p "$OUT/$NAME"

echo "→ exporting committed source (clean: no secrets/scans/caches)…"
git archive --format=tar HEAD | tar -x -C "$OUT/$NAME"

echo "→ adding client launchers, .env template, README…"
cp packaging/env.package              "$OUT/$NAME/.env"
cp packaging/start-windows.bat        "$OUT/$NAME/"
cp packaging/start-mac.command        "$OUT/$NAME/"
cp packaging/start-linux.sh           "$OUT/$NAME/"
cp packaging/stop-windows.bat         "$OUT/$NAME/"
cp packaging/stop-mac.command         "$OUT/$NAME/"
cp packaging/stop.sh                  "$OUT/$NAME/"
cp packaging/reset-all-data.sh        "$OUT/$NAME/"
cp packaging/README-CLIENT.txt        "$OUT/$NAME/README.txt"
chmod +x "$OUT/$NAME"/*.command "$OUT/$NAME"/*.sh 2>/dev/null || true

# The packaging/ dir and dev-only bits aren't needed by the client — trim them.
rm -rf "$OUT/$NAME/packaging" "$OUT/$NAME/HANDOFF.md" "$OUT/$NAME/worker/accuracy_eval.py" 2>/dev/null || true

# Safety net: make sure nothing sensitive slipped in.
if find "$OUT/$NAME" -type f \( -iname '*.mp4' -o -iname 'Test_file_*.pdf' \) | grep -q .; then
  echo "!! sensitive file detected in package — aborting"; exit 1
fi
if grep -rqi "sk-or-v1-[a-z0-9]" "$OUT/$NAME/.env" 2>/dev/null; then
  echo "!! a real API key is present in .env — aborting (use the placeholder)"; exit 1
fi

echo "→ zipping…"
( cd "$OUT" && zip -rq "$NAME.zip" "$NAME" )
SIZE=$(du -h "$OUT/$NAME.zip" | cut -f1)
echo "✅ Package ready:  $OUT/$NAME.zip  ($SIZE)"
echo "   Send that zip to the client. They: unzip → edit .env → double-click Start."
