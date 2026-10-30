"""Market data for Mostly Markets: price history, live quotes, the earnings calendar and SEC lookups.

Standard library only, so it runs the same on the Mac, in GitHub Actions and in a cloud routine.

  python3 pipeline/marketdata.py history [TICKER ...]   # incremental daily bars -> data/prices/<T>.csv
  python3 pipeline/marketdata.py quotes                 # live quotes for the universe -> data/quotes/latest.json
  python3 pipeline/marketdata.py calendar [--days 14]   # earnings calendar -> data/calendar/<date>.json
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ET = ZoneInfo("America/New_York")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
SEC_UA = "Mostly Markets research desk admin@mostlymarkets.org"


def get(url: str, ua: str = UA, accept: str = "application/json", tries: int = 3, timeout: int = 25) -> bytes:
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": accept,
                                                       "Accept-Language": "en-US,en;q=0.9"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - network errors of every kind get a retry
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"GET failed after {tries} tries: {url}: {last}")


def get_json(url: str, **kw):
    return json.loads(get(url, **kw))


def now_et() -> dt.datetime:
    return dt.datetime.now(tz=ET)


# ---------------------------------------------------------------- universe

def universe() -> list[dict]:
    return json.loads((DATA / "universe" / "universe.json").read_text())


def universe_map() -> dict[str, dict]:
    return {u["ticker"]: u for u in universe()}


# ---------------------------------------------------------------- history (Nasdaq, daily)

def _num(s):
    if s in (None, "", "N/A", "--"):
        return None
    try:
        return float(str(s).replace("$", "").replace(",", "").replace("%", "").strip())
    except ValueError:
        return 0.0 if str(s).strip().upper() == "UNCH" else None


def nasdaq_symbol(t: str) -> str:
    return t.replace(".", "%25sl%25") if "." in t else t


def nasdaq_history(ticker: str, start: dt.date, end: dt.date) -> list[list]:
    """Daily bars, oldest first: [date, open, high, low, close, volume]."""
    url = (f"https://api.nasdaq.com/api/quote/{nasdaq_symbol(ticker)}/historical?assetclass=stocks"
           f"&fromdate={start.isoformat()}&todate={end.isoformat()}&limit=9999")
    d = get_json(url)
    rows = (((d or {}).get("data") or {}).get("tradesTable") or {}).get("rows") or []
    out = []
    for r in rows:
        m, dd, y = r["date"].split("/")
        out.append([f"{y}-{m}-{dd}", _num(r["open"]), _num(r["high"]), _num(r["low"]), _num(r["close"]),
                    int(_num(r["volume"]) or 0)])
    out.sort(key=lambda x: x[0])
    return out


def price_path(t: str) -> Path:
    return DATA / "prices" / f"{t.replace('.', '-')}.csv"


_QUOTES = None


def quote_time(q: dict) -> dt.datetime | None:
    """A quote's time in New York. CNBC sends a bare date before the open; that means that day's close."""
    t = (q or {}).get("time")
    if not t:
        return None
    if len(t) == 10:
        return dt.datetime.combine(dt.date.fromisoformat(t), dt.time(16, 0), tzinfo=ET)
    t = re.sub(r"([+-]\d\d)(\d\d)$", r"\1:\2", t)
    d = dt.datetime.fromisoformat(t)
    return (d if d.tzinfo else d.replace(tzinfo=ET)).astimezone(ET)
_ADJ = DATA / "universe" / "adjustments.json"
ADJUSTMENTS = json.loads(_ADJ.read_text()) if _ADJ.exists() else {}


def latest_quotes() -> dict:
    global _QUOTES
    if _QUOTES is None:
        p = DATA / "quotes" / "latest.json"
        _QUOTES = json.loads(p.read_text()) if p.exists() else {"quotes": {}}
    return _QUOTES


def read_prices(t: str, with_today: bool = True) -> list[dict]:
    """Daily bars from data/prices/<T>.csv. When the history feed hasn't posted the latest finished session yet,
    the regular-session close from data/quotes/latest.json is appended as that day's bar."""
    p = price_path(t)
    if not p.exists():
        return []
    with p.open() as f:
        bars = [{"date": r["date"], "open": float(r["open"] or 0), "high": float(r["high"] or 0),
                 "low": float(r["low"] or 0), "close": float(r["close"]), "volume": int(r["volume"] or 0)}
                for r in csv.DictReader(f) if r["close"]]
    # Corporate actions the feed doesn't adjust for (spin-offs): scale earlier prices by the factor.
    for adj in ADJUSTMENTS.get(t, []):
        for b in bars:
            if b["date"] < adj["date"]:
                for k in ("open", "high", "low", "close"):
                    b[k] = round(b[k] * adj["factor"], 4)
    if with_today and bars:
        q = latest_quotes()["quotes"].get(t)
        if q and q.get("time") and q.get("price"):
            qd = quote_time(q)
            closed = qd.time() >= dt.time(16, 0) or (q.get("status") or "").upper() in ("POST_MKT", "CLOSED")
            if qd.date().isoformat() > bars[-1]["date"] and closed and q.get("prev_close"):
                if abs(q["prev_close"] / bars[-1]["close"] - 1) < 0.002:  # the quote follows our last bar
                    bars.append({"date": qd.date().isoformat(), "open": q.get("open") or 0, "high": q.get("high") or 0,
                                 "low": q.get("low") or 0, "close": q["price"], "volume": q.get("volume") or 0,
                                 "from_quote": True})
    return bars


def update_history(t: str, years: int = 5) -> int:
    """Fetch new bars and merge them into data/prices/<T>.csv. Returns the number of rows written."""
    p = price_path(t)
    old = {r["date"]: [r["date"], r["open"], r["high"], r["low"], r["close"], r["volume"]]
           for r in read_prices(t, with_today=False)}
    today = now_et().date()
    start = (max(old) and dt.date.fromisoformat(max(old)) - dt.timedelta(days=10)) if old else today - dt.timedelta(days=365 * years + 7)
    new = nasdaq_history(t, start, today)
    # Today's bar during the session is partial; keep it only after the close.
    if new and new[-1][0] == today.isoformat() and now_et().time() < dt.time(16, 10):
        new = new[:-1]
    for r in new:
        if r[4] is not None:
            old[r[0]] = r
    rows = [old[k] for k in sorted(old)]
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "open", "high", "low", "close", "volume"])
        for r in rows:
            w.writerow([r[0]] + [("" if v is None else (round(v, 4) if isinstance(v, float) else v)) for v in r[1:]])
    return len(rows)


# ---------------------------------------------------------------- live quotes (CNBC)

def cnbc_symbol(t: str) -> str:
    return t  # CNBC accepts BRK.B style


def cnbc_quotes(tickers: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(tickers), 40):
        chunk = tickers[i:i + 40]
        url = ("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols="
               + urllib.parse.quote("|".join(cnbc_symbol(t) for t in chunk))
               + "&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json&events=1")
        try:
            d = get_json(url)
        except RuntimeError as e:
            print("quotes chunk failed:", e, file=sys.stderr)
            continue
        q = (d.get("FormattedQuoteResult") or {}).get("FormattedQuote") or []
        if isinstance(q, dict):
            q = [q]
        for x in q:
            sym = x.get("symbol")
            if not sym or _num(x.get("last")) is None:
                continue
            ext = x.get("ExtendedMktQuote") or {}
            out[sym] = {
                "price": _num(x.get("last")),
                "change": _num(x.get("change")),
                "change_pct": _num((x.get("change_pct") or "").replace("%", "")),
                "prev_close": _num(x.get("previous_day_closing")),
                "open": _num(x.get("open")),
                "high": _num(x.get("high")),
                "low": _num(x.get("low")),
                "volume": int(_num(x.get("volume")) or 0),
                "time": x.get("last_time"),
                "mktcap": x.get("mktcapView"),
                "pe": _num(x.get("pe")),
                "fpe": _num(x.get("fpe")),
                "yr_high": _num(x.get("yrhiprice")),
                "yr_low": _num(x.get("yrloprice")),
                "dividend_yield": _num((x.get("dividendyield") or "").replace("%", "")),
                "ext": ({"session": ext.get("type"), "price": _num(ext.get("last")),
                         "change_pct": _num((ext.get("change_pct") or "").replace("%", "")),
                         "time": ext.get("last_time")} if ext.get("last") else None),
                "status": x.get("curmktstatus"),
            }
        time.sleep(0.4)
    return out


MARKETS = {".SPX": "S&P 500", ".IXIC": "Nasdaq Composite", ".DJI": "Dow Jones Industrial Average",
           ".RUT": "Russell 2000", ".VIX": "VIX", "US10Y": "10-year Treasury yield", "US2Y": "2-year Treasury yield",
           "@CL.1": "WTI crude oil", "@LCO.1": "Brent crude oil", "@GC.1": "Gold", "BTC.CM=": "Bitcoin",
           ".DXY": "US dollar index"}


def write_quotes() -> Path:
    tickers = [u["ticker"] for u in universe()]
    q = cnbc_quotes(tickers)
    if len(q) < len(tickers) * 0.98:  # retry the stragglers once
        q.update(cnbc_quotes([t for t in tickers if t not in q]))
    p = DATA / "quotes" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"asof": now_et().isoformat(timespec="seconds"), "quotes": q}, separators=(",", ":")))
    m = cnbc_quotes(list(MARKETS))
    for k, v in m.items():
        v["name"] = MARKETS.get(k, k)
    (DATA / "quotes" / "markets.json").write_text(json.dumps({"asof": now_et().isoformat(timespec="seconds"),
                                                             "markets": m}, indent=0))
    return p


# ---------------------------------------------------------------- earnings calendar (Nasdaq)

def nasdaq_earnings(day: dt.date) -> list[dict]:
    d = get_json(f"https://api.nasdaq.com/api/calendar/earnings?date={day.isoformat()}")
    rows = ((d or {}).get("data") or {}).get("rows") or []
    out = []
    for r in rows:
        t = (r.get("symbol") or "").strip()
        out.append({
            "ticker": t,
            "name": r.get("name"),
            "time": {"time-pre-market": "bmo", "time-after-hours": "amc"}.get(r.get("time"), "unknown"),
            "quarter": r.get("fiscalQuarterEnding"),
            "eps_forecast": _num(r.get("epsForecast")),
            "n_estimates": int(_num(r.get("noOfEsts")) or 0),
            "eps_last_year": _num(r.get("lastYearEPS")),
            "last_year_date": r.get("lastYearRptDt"),
            "eps_actual": _num(r.get("eps")),
            "surprise_pct": _num(r.get("surprise")),
            "mktcap": _num(r.get("marketCap")),
        })
    return out


def write_calendar(days: int = 14, back: int = 3) -> list[Path]:
    paths = []
    today = now_et().date()
    univ = universe_map()
    for k in range(-back, days + 1):
        day = today + dt.timedelta(days=k)
        if day.weekday() >= 5:
            continue
        try:
            rows = nasdaq_earnings(day)
        except RuntimeError as e:
            print("calendar failed", day, e, file=sys.stderr)
            continue
        rows = [r for r in rows if r["ticker"] in univ]
        p = DATA / "calendar" / f"{day.isoformat()}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rows, indent=0))
        paths.append(p)
        time.sleep(0.3)
    return paths


# ---------------------------------------------------------------- SEC

def sec_get_json(url: str):
    return get_json(url, ua=SEC_UA)


def sec_ticker_map() -> dict[str, dict]:
    d = sec_get_json("https://www.sec.gov/files/company_tickers.json")
    return {v["ticker"].upper(): {"cik": str(v["cik_str"]).zfill(10), "name": v["title"]} for v in d.values()}


# ---------------------------------------------------------------- CLI

def main(argv: list[str]) -> None:
    if not argv:
        print(__doc__)
        return
    cmd, rest = argv[0], argv[1:]
    if cmd == "history":
        tickers = rest or [u["ticker"] for u in universe()]
        workers = int(os.environ.get("MM_WORKERS", "4"))

        def one(t):
            try:
                n = update_history(t)
                return t, n, None
            except Exception as e:  # noqa: BLE001
                return t, 0, str(e)[:160]
        bad = []
        with ThreadPoolExecutor(workers) as ex:
            for t, n, err in ex.map(one, tickers):
                if err or n == 0:
                    bad.append((t, err))
        print(f"history: {len(tickers) - len(bad)}/{len(tickers)} ok")
        for t, e in bad:
            print("  failed", t, e)
    elif cmd == "quotes":
        p = write_quotes()
        print("quotes ->", p, len(json.loads(p.read_text())["quotes"]))
    elif cmd == "calendar":
        days = int(rest[rest.index("--days") + 1]) if "--days" in rest else 14
        ps = write_calendar(days)
        print("calendar ->", len(ps), "days")
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
