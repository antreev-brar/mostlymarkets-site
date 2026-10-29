"""The biggest close-to-close moves in the universe on a date.

  python3 pipeline/movers.py 2026-10-28            # top 12 up and down
  python3 pipeline/movers.py 2026-10-28 --n 20 --sp500
  python3 pipeline/movers.py --week 2026-10-30     # Monday-to-date moves for the week containing that date
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from marketdata import read_prices, universe  # noqa: E402


def day_moves(date: str, sp500_only: bool = False) -> list[dict]:
    out = []
    for u in universe():
        if sp500_only and "S&P 500" not in u.get("index", []):
            continue
        bars = read_prices(u["ticker"])
        idx = next((i for i, b in enumerate(bars) if b["date"] == date), None)
        if not idx:
            continue
        prev, cur = bars[idx - 1], bars[idx]
        out.append({"ticker": u["ticker"], "name": u["name"], "sector": u["sector"], "close": round(cur["close"], 2),
                    "change_pct": round((cur["close"] / prev["close"] - 1) * 100, 2),
                    "volume_x": round(cur["volume"] / max(1, sum(b["volume"] for b in bars[max(0, idx - 20):idx]) / 20), 2)})
    return out


def week_moves(date: str, sp500_only: bool = False) -> list[dict]:
    d = dt.date.fromisoformat(date)
    monday = d - dt.timedelta(days=d.weekday())
    out = []
    for u in universe():
        if sp500_only and "S&P 500" not in u.get("index", []):
            continue
        bars = [b for b in read_prices(u["ticker"]) if b["date"] <= date]
        before = [b for b in bars if b["date"] < monday.isoformat()]
        if not before or not bars:
            continue
        out.append({"ticker": u["ticker"], "name": u["name"], "sector": u["sector"], "close": round(bars[-1]["close"], 2),
                    "change_pct": round((bars[-1]["close"] / before[-1]["close"] - 1) * 100, 2)})
    return out


def main(argv: list[str]) -> None:
    n = int(argv[argv.index("--n") + 1]) if "--n" in argv else 12
    sp = "--sp500" in argv
    if "--week" in argv:
        moves = week_moves(argv[argv.index("--week") + 1], sp)
    else:
        moves = day_moves([a for a in argv if a[:2] == "20"][0], sp)
    moves.sort(key=lambda m: m["change_pct"])
    print(json.dumps({"up": moves[::-1][:n], "down": moves[:n], "count": len(moves)}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
