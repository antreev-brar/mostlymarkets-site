"""Refresh market data on the right schedule for the time of day (New York time). Called every run of data.yml.

- quotes + markets: every run
- earnings calendar: at the 06:xx, 12:xx, 17:xx and 20:xx runs (and when missing)
- daily price history: once a day after 18:00
- SEC fundamentals: once a day after 05:00 for companies that reported in the last 45 days; all of them on Sundays
- FOMC dates: on Sundays
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import marketdata as md  # noqa: E402

MARK = md.DATA / "quotes" / "refresh_marks.json"


def marks() -> dict:
    return json.loads(MARK.read_text()) if MARK.exists() else {}


def done_today(key: str) -> bool:
    return marks().get(key) == md.now_et().date().isoformat()


def mark(key: str) -> None:
    m = marks()
    m[key] = md.now_et().date().isoformat()
    MARK.parent.mkdir(parents=True, exist_ok=True)
    MARK.write_text(json.dumps(m))


def run(cmd: list[str]) -> None:
    print("$", " ".join(cmd), flush=True)
    subprocess.run([sys.executable, *cmd], cwd=md.ROOT, check=False)


def fomc() -> None:
    s = md.get("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", accept="text/html").decode("utf-8", "ignore")
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))
    months = {m: i + 1 for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                               "September", "October", "November", "December"])}
    by = {}
    y0 = md.now_et().year
    for y in (y0, y0 + 1):
        i = t.find(f"{y} FOMC Meetings")
        if i < 0:
            continue
        j = t.find(f"{y - 1} FOMC Meetings", i)
        seg = t[i:j if j > 0 else i + 6000]
        for m, _d1, d2 in re.findall(r"(January|February|March|April|May|June|July|August|September|October|November|December)"
                                     r"(?:/\w+)? (\d{1,2})-(\d{1,2})", seg):
            key = f"{y}-{months[m]:02d}"
            by[key] = max(by.get(key, ""), f"{key}-{int(d2):02d}")
    if by:
        (md.DATA / "calendar" / "fomc.json").write_text(json.dumps(sorted(by.values())))


def main() -> None:
    now = md.now_et()
    run(["pipeline/marketdata.py", "quotes"])
    cal_missing = not (md.DATA / "calendar" / f"{now.date().isoformat()}.json").exists()
    if cal_missing or (now.hour in (6, 12, 17, 20) and now.minute < 15) or not done_today("calendar"):
        run(["pipeline/marketdata.py", "calendar", "--days", "14"])
        mark("calendar")
    stale = False
    try:
        bars = md.read_prices("AAPL", with_today=False)
        prev = now.date() - dt.timedelta(days=1)
        while prev.weekday() >= 5:
            prev -= dt.timedelta(days=1)
        stale = bool(bars) and bars[-1]["date"] < prev.isoformat() and now.hour >= 6
    except Exception:  # noqa: BLE001
        pass
    if (stale or (now.hour >= 18 and now.weekday() < 5)) and not done_today("history"):
        run(["pipeline/marketdata.py", "history"])
        mark("history")
    if now.hour >= 5 and not done_today("fundamentals") and (md.ROOT / "pipeline/fundamentals.py").exists():
        if now.weekday() == 6:
            run(["pipeline/fundamentals.py"])
        else:
            recent = set()
            for f in (md.DATA / "calendar").glob("20*.json"):
                d = dt.date.fromisoformat(f.stem)
                if 0 <= (now.date() - d).days <= 45:
                    recent.update(r["ticker"] for r in json.loads(f.read_text()))
            if recent:
                run(["pipeline/fundamentals.py", *sorted(recent)])
        mark("fundamentals")
    if now.weekday() == 6 and not done_today("fomc"):
        try:
            fomc()
        except Exception as e:  # noqa: BLE001
            print("fomc refresh failed:", e)
        mark("fomc")


if __name__ == "__main__":
    main()
