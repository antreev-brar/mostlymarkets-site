"""Price facts for a stock as of a date, from data/prices/<T>.csv. Writers quote these numbers instead of computing their own.

  python3 pipeline/facts.py AMZN                     # as of the latest bar
  python3 pipeline/facts.py AMZN --asof 2026-10-28   # as of that session's close
  python3 pipeline/facts.py AMZN MSFT --brief        # one line per stock

Every figure is a close-to-close move on daily closes (Nasdaq). "Sessions" are trading days.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from marketdata import read_prices, universe_map  # noqa: E402


def pct(a: float, b: float) -> float:
    return round((a / b - 1) * 100, 2)


def human_date(d: str) -> str:
    x = dt.date.fromisoformat(d)
    return f"{x.day} {x.strftime('%B')} {x.year}"


def facts(ticker: str, asof: str | None = None) -> dict:
    bars = read_prices(ticker)
    if not bars:
        raise SystemExit(f"no price file for {ticker}; run: python3 pipeline/marketdata.py history {ticker}")
    if asof:
        bars = [b for b in bars if b["date"] <= asof]
    if len(bars) < 30:
        raise SystemExit(f"{ticker}: not enough history")
    last, prev = bars[-1], bars[-2]
    closes = [b["close"] for b in bars]
    rets = [(bars[i]["date"], pct(closes[i], closes[i - 1])) for i in range(1, len(bars))]
    year = rets[-252:]
    move = rets[-1][1]
    big = [r for r in year if abs(r[1]) >= 5]
    same_dir = [r for r in rets[:-1] if (r[1] <= move if move < 0 else r[1] >= move)]
    last_bigger = same_dir[-1] if same_dir else None
    window = bars[-252:]
    hi = max(window, key=lambda b: b["close"])
    lo = min(window, key=lambda b: b["close"])
    y = last["date"][:4]
    prior_year = [b for b in bars if b["date"] < f"{y}-01-01"]
    ytd = pct(last["close"], prior_year[-1]["close"]) if prior_year else None

    def back(n):
        return pct(last["close"], closes[-1 - n]) if len(closes) > n else None

    five = [b for b in bars if b["date"] <= str(int(y) - 5) + last["date"][4:]]
    vols = [b["volume"] for b in bars[-21:-1] if b["volume"]]
    avgvol = sum(vols) / len(vols) if vols else 0
    u = universe_map().get(ticker, {})
    out = {
        "ticker": ticker,
        "name": u.get("name", ticker),
        "date": last["date"],
        "close": round(last["close"], 2),
        "prev_close": round(prev["close"], 2),
        "change_pct": move,
        "moves_over_5pct_last_year": len(big),
        "sessions_in_year": len(year),
        "biggest_move_rank_in_year": 1 + sum(1 for r in year if abs(r[1]) > abs(move)),
        "last_move_at_least_this_big_same_direction": (
            {"date": last_bigger[0], "change_pct": last_bigger[1]} if last_bigger else None),
        "ytd_pct": ytd,
        "return_1m_pct": back(21),
        "return_6m_pct": back(126),
        "return_1y_pct": back(252),
        "high_52w": {"close": round(hi["close"], 2), "date": hi["date"]},
        "low_52w": {"close": round(lo["close"], 2), "date": lo["date"]},
        "pct_below_52w_high": round((1 - last["close"] / hi["close"]) * 100, 2),
        "thousand_dollars_5y_ago_now": round(1000 * last["close"] / five[-1]["close"]) if five else None,
        "five_years_ago_date": five[-1]["date"] if five else None,
        "volume": last["volume"],
        "volume_vs_20d_avg": round(last["volume"] / avgvol, 2) if avgvol else None,
    }
    return out


def sentence_pack(f: dict) -> list[str]:
    """Ready-made, checkable sentences for the "What the market is telling us" section."""
    s = []
    s.append(f"{f['name']}'s shares moved 5% or more on {f['moves_over_5pct_last_year']} of the last "
             f"{f['sessions_in_year']} sessions.")
    lb = f["last_move_at_least_this_big_same_direction"]
    if lb:
        s.append(f"The last move at least this big in the same direction was on {human_date(lb['date'])}, "
                 f"when the stock {'rose' if lb['change_pct'] > 0 else 'fell'} {abs(lb['change_pct']):.1f}%.")
    if f["ytd_pct"] is not None:
        s.append(f"The stock is {'up' if f['ytd_pct'] >= 0 else 'down'} {abs(f['ytd_pct']):.1f}% this year, and at "
                 f"${f['close']:,.2f} it sits {f['pct_below_52w_high']:.1f}% below its 52-week closing high of "
                 f"${f['high_52w']['close']:,.2f} from {human_date(f['high_52w']['date'])}.")
    if f["thousand_dollars_5y_ago_now"]:
        s.append(f"$1,000 invested in {f['name']} five years ago would be worth "
                 f"${f['thousand_dollars_5y_ago_now']:,} today.")
    return s


def main(argv: list[str]) -> None:
    asof = None
    if "--asof" in argv:
        i = argv.index("--asof")
        asof = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    brief = "--brief" in argv
    tickers = [a for a in argv if not a.startswith("--")]
    for t in tickers:
        f = facts(t, asof)
        if brief:
            print(f"{t}: {f['date']} close ${f['close']:,.2f} ({f['change_pct']:+.2f}%), "
                  f"YTD {f['ytd_pct']:+.1f}%, 1M {f['return_1m_pct']:+.1f}%")
        else:
            f["sentences"] = sentence_pack(f)
            print(json.dumps(f, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
