#!/bin/sh
# Build the invented example family with the current engine, in a scratch folder. Usage: tools/build_example.sh [outdir]
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${1:-$(mktemp -d)}
mkdir -p "$OUT/game" "$OUT/private"
cp "$ROOT/game/build.py" "$ROOT/game/history.py" "$ROOT/game/template.html" "$ROOT/game/fonts.css" "$OUT/game/"
cp "$ROOT/game/example/world.json" "$OUT/game/"
cp -r "$ROOT/game/example/issues" "$OUT/"
[ -d "$ROOT/game/example/decisions" ] && cp -r "$ROOT/game/example/decisions" "$OUT/"
mkdir -p "$OUT/decisions"
[ -f "$ROOT/private/canaries.txt" ] && cp "$ROOT/private/canaries.txt" "$OUT/private/"
cd "$OUT" && python3 game/build.py --check
echo "page: $OUT/game/dist/two-shores.html"
