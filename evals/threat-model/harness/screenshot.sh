#!/usr/bin/env bash
# Capture results.html as PNGs, light and dark.
#
#   ./harness/screenshot.sh            # ./results.html -> docs/results-{light,dark}.png
#   CHROME=/path/to/chrome ./harness/screenshot.sh path.html
#
# The window height is read out of the rendered page — it publishes its own height on
# <html data-page-height> — rather than guessed, so a capture never clips the footer or
# leaves a band of empty plane under it.
set -euo pipefail

CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
if [ ! -x "$CHROME" ]; then
  for c in "$(command -v google-chrome || true)" "$(command -v chromium || true)" \
           "$(command -v chromium-browser || true)"; do
    [ -n "$c" ] && [ -x "$c" ] && CHROME="$c" && break
  done
fi
[ -x "$CHROME" ] || { echo "no Chrome found — set CHROME=/path/to/chrome" >&2; exit 1; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PAGE="${1:-$ROOT/results.html}"
OUT="$ROOT/docs"
WIDTH=1120
mkdir -p "$OUT"

measure() {
  "$CHROME" --headless=new --disable-gpu --window-size="$WIDTH,1200" \
    --virtual-time-budget=3000 --dump-dom "file://$PAGE?theme=$1" 2>/dev/null \
    | grep -o 'data-page-height="[0-9]*"' | head -1 | tr -dc '0-9'
}

for theme in light dark; do
  height="$(measure "$theme")"
  height="${height:-2600}"
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars \
    --force-device-scale-factor=2 --window-size="$WIDTH,$height" \
    --virtual-time-budget=3000 \
    --screenshot="$OUT/results-$theme.png" "file://$PAGE?theme=$theme" 2>&1 | tail -1
  echo "  $theme: ${WIDTH}x${height} css (2x)"
done
