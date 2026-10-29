#!/usr/bin/env bash
# Fetch the market data (prices, quotes, calendar, fundamentals) from the `data` branch into ./data.
# The data lives on its own branch, force-pushed as a single commit, so main's history stays small.
set -euo pipefail
cd "$(dirname "$0")/.."
if git fetch --depth=1 origin data 2>/dev/null; then
  git archive FETCH_HEAD data | tar -x
  echo "data: pulled $(git log -1 --format=%s FETCH_HEAD)"
else
  echo "data: no data branch yet"
fi
