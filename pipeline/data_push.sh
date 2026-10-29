#!/usr/bin/env bash
# Publish ./data/{prices,quotes,calendar,fundamentals} to the `data` branch as one orphan commit (no history growth).
set -euo pipefail
cd "$(dirname "$0")/.."
export GIT_INDEX_FILE="$(mktemp -u)"
git read-tree --empty
git add -f data/prices data/quotes data/calendar data/fundamentals 2>/dev/null || git add -f data/prices data/quotes data/calendar
tree=$(git write-tree)
commit=$(git -c user.name="mm-data" -c user.email="data@mostlymarkets.org" commit-tree "$tree" -m "data $(TZ=America/New_York date '+%Y-%m-%d %H:%M ET')")
git push -f origin "$commit:refs/heads/data"
rm -f "$GIT_INDEX_FILE"
echo "data: pushed $commit"
