"""Turn market events into queued story assignments for the writer.

Runs every 15 minutes on market days (GitHub Actions, `.github/workflows/data.yml`) after the quotes refresh.
Deterministic: no LLM. Each event becomes events/queue/<id>.json with a data pack the writer uses offline.

  python3 pipeline/detect.py            # detect and queue
  python3 pipeline/detect.py --dry      # print what would be queued
  python3 pipeline/detect.py --at 2026-10-29T16:30   # pretend it's that New York time (testing)
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import marketdata as md  # noqa: E402
from facts import facts  # noqa: E402

ROOT = md.ROOT
EV = ROOT / "events"
QUEUE, DONE, PACKS = EV / "queue", EV / "done", EV / "packs"
SEEN = EV / "seen.json"
ET = md.ET

HOLIDAYS = {"2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
            "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24"}
EARLY_CLOSE = {"2026-11-27": dt.time(13, 0), "2026-12-24": dt.time(13, 0)}

# Second share classes: we write about the main line only.
DUP_CLASS = {"GOOG", "FOX", "NWS", "BF.B"}
# How many stories of each kind a day can take, and the size of company we write about.
DAILY_CAP = {"why-it-moved": 10, "basket": 2, "earnings-recap": 14, "earnings-preview": 8, "after-hours": 1}
MIN_CAP_RECAP = 20e9
MIN_CAP_PREVIEW = 40e9
LIST_THEMES = [
    ("cash-machines", "Cash Machines", "free-cash-flow margin over the last 12 months", "fcf_margin_pct"),
    ("fast-growers", "Fast Growers", "revenue growth over the last 12 months", "revenue_growth_yoy_pct"),
    ("beaten-down-quality", "Beaten-Down Quality", "distance below the 52-week high, among profitable companies", "off_high"),
    ("ai-infrastructure", "AI Infrastructure", "revenue growth among chip, networking, power and data-center names", "revenue_growth_yoy_pct"),
    ("dividend-payers", "Dividend Payers", "dividend yield, with free cash flow covering the payout", "dividend_yield"),
    ("momentum", "Momentum", "six-month price return", "ret_6m"),
    ("profitable-small-caps", "Under-the-Radar", "operating margin among companies worth $5-30 billion", "operating_margin_pct"),
]


def is_trading_day(d: dt.date) -> bool:
    return d.weekday() < 5 and d.isoformat() not in HOLIDAYS


def prev_trading_day(d: dt.date) -> dt.date:
    d -= dt.timedelta(days=1)
    while not is_trading_day(d):
        d -= dt.timedelta(days=1)
    return d


def next_trading_day(d: dt.date) -> dt.date:
    d += dt.timedelta(days=1)
    while not is_trading_day(d):
        d += dt.timedelta(days=1)
    return d


def close_time(d: dt.date) -> dt.time:
    return EARLY_CLOSE.get(d.isoformat(), dt.time(16, 0))


def cap_of(q: dict | None) -> float:
    if not q:
        return 0
    m = re.match(r"([\d.]+)\s*([TBMK]?)", str(q.get("mktcap") or ""))
    return float(m.group(1)) * {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3, "": 1}[m.group(2)] if m else 0


class Detector:
    def __init__(self, now: dt.datetime, dry: bool = False):
        self.now, self.dry = now, dry
        self.today = now.date()
        self.univ = md.universe_map()
        qd = json.loads((md.DATA / "quotes/latest.json").read_text())
        self.quotes = qd["quotes"]
        self.quotes_asof = qd.get("asof")
        mp = md.DATA / "quotes/markets.json"
        self.markets = json.loads(mp.read_text())["markets"] if mp.exists() else {}
        self.seen = json.loads(SEEN.read_text()) if SEEN.exists() else {}
        self.new: list[dict] = []
        self.cal = {}
        for f in (md.DATA / "calendar").glob("*.json"):
            if re.match(r"\d{4}-\d{2}-\d{2}$", f.stem):
                self.cal[f.stem] = json.loads(f.read_text())
        self.stories = self._stories()

    # ------------------------------------------------------------- helpers
    def _stories(self):
        out = []
        for p in sorted((ROOT / "content/articles").glob("*.md")):
            text = p.read_text()
            m = re.search(r'^title\s*=\s*"(.*)"\s*$', text, re.M)
            t = re.search(r'^tickers\s*=\s*\[(.*?)\]', text, re.M)
            ty = re.search(r'^type\s*=\s*"(.*?)"', text, re.M)
            d, slug = p.name[:10], p.name[11:-3]
            path = f"/daily/{d}/" if ty and ty.group(1) == "daily" else f"/news/{d}/{slug}/"
            out.append({"path": path, "date": d, "title": m.group(1) if m else slug,
                        "type": ty.group(1) if ty else "", "tickers": re.findall(r'"([A-Z.]+)"', t.group(1)) if t else []})
        return out

    def stories_for(self, t: str, n: int = 5):
        return [s for s in self.stories if t in s["tickers"]][-n:][::-1]

    def count_today(self, kind: str) -> int:
        day = self.today.isoformat()
        return sum(1 for k, v in self.seen.items() if v.get("kind") == kind and v.get("day") == day)

    def facts(self, t: str):
        try:
            f = facts(t)
            f.pop("sentences", None)
            from facts import sentence_pack
            f["sentences"] = sentence_pack(facts(t))
            return f
        except SystemExit:
            return None

    def quote(self, t: str):
        q = self.quotes.get(t)
        return {k: q.get(k) for k in ("price", "change_pct", "prev_close", "time", "mktcap", "pe", "fpe", "yr_high",
                                      "yr_low", "ext")} if q else None

    def written(self, story_type: str, tickers: list[str], since: str) -> bool:
        """True when a story of this type about this ticker (or, with no ticker, of this type) exists since a date."""
        for s in self.stories:
            if s["type"] != story_type or s["date"] < since:
                continue
            if not tickers or (s["tickers"] and s["tickers"][0] == tickers[0]):
                return True
        return False

    def add(self, eid: str, kind: str, story_type: str, priority: int, expires: dt.datetime, tickers: list[str],
            hint: str, instructions: str, pack: dict):
        if eid in self.seen or (QUEUE / f"{eid}.json").exists():
            return False
        if any(t in DUP_CLASS for t in tickers[:1]):
            return False
        since = (self.today if kind in ("market-wrap", "movers", "list", "macro-check", "fomc", "week-ahead", "basket", "daily")
                 else prev_trading_day(self.today)).isoformat()
        if kind != "basket" and not eid.startswith("daily-weekend") and self.written(story_type, tickers, since):
            self.seen[eid] = {"kind": kind, "day": self.today.isoformat(), "created": self.now.isoformat(timespec="seconds"),
                              "outcome": "already-written"}
            return False
        ev = {"id": eid, "kind": kind, "story_type": story_type, "priority": priority,
              "created": self.now.isoformat(timespec="seconds"), "expires": expires.isoformat(timespec="seconds"),
              "tickers": tickers, "headline_hint": hint, "instructions": instructions,
              "quotes_asof": self.quotes_asof, "pack": pack}
        self.new.append(ev)
        self.seen[eid] = {"kind": kind, "day": self.today.isoformat(), "created": ev["created"]}
        return True

    def at(self, h: int, m: int = 0) -> dt.datetime:
        return dt.datetime.combine(self.today, dt.time(h, m), tzinfo=ET)

    # ------------------------------------------------------------- rules
    def rule_moves(self):
        """A stock moved a lot in the regular session (or after hours) on something other than its own results."""
        if not is_trading_day(self.today):
            return
        t_open = self.at(9, 50)
        reg = t_open <= self.now <= self.at(16, 45)
        reported = self.reported_tickers()
        cands = []
        for t, q in self.quotes.items():
            if t not in self.univ or q.get("change_pct") is None:
                continue
            qt = q.get("time") or ""
            if not qt.startswith(self.today.isoformat()):
                continue  # stale quote (holiday or halted)
            cap = cap_of(q)
            chg = q["change_pct"]
            sp = "S&P 500" in self.univ[t].get("index", [])
            thr = 4.0 if cap >= 2e11 else 5.0 if (sp or cap >= 1e10) else 8.0
            if cap < 2e9:
                continue
            if reg and abs(chg) >= thr:
                cands.append((t, chg, cap, "regular"))
            ext = q.get("ext") or {}
            if (self.now >= self.at(16, 30) and ext.get("change_pct") is not None and abs(ext["change_pct"]) >= 8
                    and cap >= 1e10 and t not in reported):
                cands.append((t, ext["change_pct"], cap, "after-hours"))
        # baskets: 3+ names in one industry moving 4%+ the same way in the regular session
        groups = defaultdict(list)
        for t, chg, cap, sess in cands:
            if sess == "regular" and t not in reported:
                groups[(self.univ[t]["industry"], chg > 0)].append((t, chg, cap))
        in_basket = set()
        for (ind, up), items in groups.items():
            if len(items) >= 3 and self.count_today("basket") < DAILY_CAP["basket"]:
                items.sort(key=lambda x: -abs(x[1]))
                ts = [x[0] for x in items[:5]]
                eid = f"basket-{re.sub(r'[^a-z0-9]+', '-', ind.lower())}-{'up' if up else 'down'}-{self.today}"
                if self.add(eid, "basket", "why-it-moved", 60, self.at(23, 59), ts,
                            f"{', '.join(ts[:3])} shares {'jump' if up else 'slide'}: what happened",
                            "Basket story: one shared cause for several stocks in the same industry. Confirm the cause in two "
                            "outlets; if each stock moved for its own reason, write single stories for the two biggest instead.",
                            {"industry": ind, "quotes": {t: self.quote(t) for t in ts}, "facts": {ts[0]: self.facts(ts[0])}}):
                    pass
                in_basket.update(t for t, chg, cap in items if abs(chg) < 9)
        cands.sort(key=lambda x: -(abs(x[1]) * (1 + min(x[2], 1e12) / 2e11)))
        for t, chg, cap, sess in cands:
            if t in in_basket or (t in reported and sess == "regular" and self.has_recap(t)):
                continue
            kind = "after-hours" if sess == "after-hours" else "why-it-moved"
            if self.count_today("why-it-moved") >= DAILY_CAP["why-it-moved"]:
                break
            eid = f"move-{t}-{self.today}" + ("-ah" if sess == "after-hours" else "")
            if f"move-{t}-{self.today}" in self.seen and sess == "after-hours":
                continue
            pri = int(min(95, 45 + abs(chg) * 2.5 + (15 if cap > 2e11 else 8 if cap > 5e10 else 0)))
            name = self.univ[t]["name"]
            self.add(eid, kind, "why-it-moved", pri, dt.datetime.combine(next_trading_day(self.today), dt.time(12, 0), tzinfo=ET),
                     [t], f"Why {name} ({t}) stock is {'up' if chg > 0 else 'down'} today",
                     ("The move is happening now. Use the latest quote; if the session has closed by the time you write, "
                      "use the close and say so." if sess == "regular" else
                      "After-hours move: say it's after hours and give the time of the quote.")
                     + (" The company reported results today or last night: make the results the cause, and link the recap if one exists."
                        if t in reported else ""),
                     {"session": sess, "quote": self.quote(t), "facts": self.facts(t), "sector": self.univ[t]["sector"],
                      "industry": self.univ[t]["industry"], "recent_stories": self.stories_for(t)})

    def reported_tickers(self) -> set[str]:
        out = set()
        for r in self.cal.get(self.today.isoformat(), []):
            if r["time"] == "bmo" or (r["time"] == "amc" and self.now.time() >= dt.time(16, 0)) or r["time"] == "unknown":
                out.add(r["ticker"])
        for r in self.cal.get(prev_trading_day(self.today).isoformat(), []):
            if r["time"] in ("amc", "unknown"):
                out.add(r["ticker"])
        return out

    def has_recap(self, t: str) -> bool:
        return any(k.startswith(f"recap-{t}-") and v.get("day") >= prev_trading_day(self.today).isoformat()
                   for k, v in self.seen.items())

    def rule_recaps(self):
        """A big company's results are out: 8-K Item 2.02 at the SEC, or past the release time on the calendar."""
        if not is_trading_day(self.today) and self.today.weekday() != 6:
            return
        rows = []
        for day in (self.today.isoformat(), prev_trading_day(self.today).isoformat()):
            for r in self.cal.get(day, []):
                q = self.quotes.get(r["ticker"])
                if cap_of(q) >= MIN_CAP_RECAP:
                    rows.append((day, r))
        if not rows:
            return
        try:
            from edgar import current_8k, release_text
            filings = [f for f in current_8k() if "2.02" in f["items"]]
        except Exception as e:  # noqa: BLE001
            print("edgar unavailable:", e)
            filings, release_text = [], None
        by_cik = {f["cik"]: f for f in filings}
        rows.sort(key=lambda x: -cap_of(self.quotes.get(x[1]["ticker"])))
        for day, r in rows:
            t = r["ticker"]
            eid = f"recap-{t}-{day}"
            if eid in self.seen or self.count_today("earnings-recap") >= DAILY_CAP["earnings-recap"]:
                continue
            if t in DUP_CLASS or self.written("earnings-recap", [t], day):
                self.seen.setdefault(eid, {"kind": "earnings-recap", "day": self.today.isoformat(),
                                           "created": self.now.isoformat(timespec="seconds"), "outcome": "already-written"})
                continue
            u = self.univ.get(t, {})
            f = by_cik.get(str(u.get("cik", "")).zfill(10))
            due = (day < self.today.isoformat() or (r["time"] == "bmo" and self.now.time() >= dt.time(8, 0))
                   or (r["time"] == "amc" and self.now.time() >= dt.time(17, 0)))
            if not f and not due:
                continue
            pack = {"calendar": r, "quote": self.quote(t), "facts": self.facts(t), "sector": u.get("sector"),
                    "industry": u.get("industry"), "recent_stories": self.stories_for(t)}
            if f:
                pack["sec_filing"] = f["index"]
                if release_text and not self.dry:
                    text, url = release_text(f)
                    if text:
                        PACKS.mkdir(parents=True, exist_ok=True)
                        (PACKS / f"{eid}.txt").write_text(text)
                        pack["release_text"] = f"events/packs/{eid}.txt"
                        pack["release_url"] = url
            cap = cap_of(self.quotes.get(t))
            pri = int(min(98, 62 + (20 if cap > 5e11 else 12 if cap > 1e11 else 5)))
            exp = dt.datetime.combine(next_trading_day(dt.date.fromisoformat(day)), dt.time(20, 0), tzinfo=ET)
            self.add(eid, "earnings-recap", "earnings-recap", pri, exp, [t],
                     f"{u.get('name', t)} ({t}) {r.get('quarter') or ''} results vs estimates",
                     "Recap: lead with revenue and EPS against consensus (name the provider), the 1-3 numbers investors watch "
                     "for this company, guidance, and the stock's reaction with its session. Use release_text as the primary "
                     "source when present.", pack)

    def rule_previews(self):
        """Tomorrow's biggest reporters, the evening before (Friday and Sunday evenings cover Monday)."""
        if self.now.time() < dt.time(17, 30):
            return
        if not (is_trading_day(self.today) or self.today.weekday() == 6):
            return
        nxt = next_trading_day(self.today)
        if self.today.weekday() == 4:
            return  # Monday's previews go out on Sunday evening
        rows = [r for r in self.cal.get(nxt.isoformat(), []) if cap_of(self.quotes.get(r["ticker"])) >= MIN_CAP_PREVIEW]
        rows.sort(key=lambda r: -cap_of(self.quotes.get(r["ticker"])))
        for r in rows[:DAILY_CAP["earnings-preview"]]:
            t = r["ticker"]
            u = self.univ[t]
            when = {"bmo": "before the open", "amc": "after the close"}.get(r["time"], "")
            self.add(f"preview-{t}-{nxt}", "earnings-preview", "earnings-preview", 40,
                     dt.datetime.combine(nxt, dt.time(9, 0) if r["time"] == "bmo" else dt.time(15, 30), tzinfo=ET), [t],
                     f"What to expect from {u['name']}'s ({t}) earnings", f"Reports {nxt:%A} {when}. Consensus EPS is in the calendar row.",
                     {"calendar": r, "report_date": nxt.isoformat(), "quote": self.quote(t), "facts": self.facts(t),
                      "recent_stories": self.stories_for(t), "last_recap": [s for s in self.stories_for(t, 20) if s["type"] == "earnings-recap"][:1]})

    def edition_pack(self, since: dt.date, session: dt.date) -> dict:
        """What the Daily is written from: the markets, the session's biggest moves, our stories since the last
        edition, and today's earnings calendar."""
        today_cal = sorted(self.cal.get(self.today.isoformat(), []), key=lambda r: -cap_of(self.quotes.get(r["ticker"])))[:10]
        return {"markets": self.markets, "session": session.isoformat(), "moves": self.session_moves(session),
                "stories_since": [{"title": x["title"], "path": x["path"], "type": x["type"], "date": x["date"]}
                                  for x in self.stories if x["date"] >= since.isoformat()][:40],
                "reporting_today": [{"ticker": r["ticker"], "time": r["time"], "eps_forecast": r["eps_forecast"]} for r in today_cal]}

    def rule_edition(self):
        """The Daily: a morning edition before every session, and a weekend edition after Friday's close."""
        d = self.today
        if is_trading_day(d) and self.now.time() >= dt.time(5, 30) and d.weekday() != 0:
            prev = prev_trading_day(d)
            self.add(f"daily-{d}", "daily", "daily", 96, self.at(10, 30), [],
                     "Mostly Markets Daily: <the one story behind yesterday's market>",
                     f"The morning edition before the open on {d:%A %d %B}. Tell the story of the last session ({prev:%A %d %B}) "
                     "and set up today: a narrative lede, then a thread of 6 to 8 takes, each one claim with one chart or stat "
                     "block, then What's next (today's reporters and data) and The numbers. Follow the daily template in "
                     "docs/STYLE.md. Write a cover_brief.",
                     self.edition_pack(prev, prev))
        if d.weekday() == 0 and is_trading_day(d) and self.now.time() >= dt.time(5, 30):
            self.add(f"daily-{d}", "daily", "daily", 96, self.at(10, 30), [],
                     "Mostly Markets Daily: <the week's big test>",
                     "The Monday edition. Weekend news that moves stocks today, then the thread: 6 to 8 takes on what this "
                     "week will decide (the big reporters, the data, the Fed), each with one chart or stat block. "
                     "Follow the daily template in docs/STYLE.md. Write a cover_brief.",
                     self.edition_pack(d - dt.timedelta(days=3), prev_trading_day(d)))
        if d.weekday() == 4 and is_trading_day(d) and self.now.time() >= dt.time(19, 30):
            monday = d - dt.timedelta(days=d.weekday())
            self.add(f"daily-weekend-{d}", "daily", "daily", 90, dt.datetime.combine(d + dt.timedelta(days=1), dt.time(23, 59), tzinfo=ET), [],
                     "Mostly Markets Daily, weekend edition: <the week in eight charts>",
                     "The weekend edition: the week's story in a narrative lede, then a thread of 7 or 8 takes (one chart or "
                     "stat block each; use moves charts from Friday a week ago to this Friday), What's next for next week, "
                     "and The numbers. Follow the daily template in docs/STYLE.md. Write a cover_brief.",
                     {**self.edition_pack(monday - dt.timedelta(days=3), d), "week_moves": self.week_moves()})

    def rule_daily(self):
        d = self.today
        if is_trading_day(d):
            ct = close_time(d)
            if self.now.time() >= (dt.datetime.combine(d, ct) + dt.timedelta(minutes=15)).time():
                todays = [s for s in self.stories if s["date"] == d.isoformat()]
                self.add(f"wrap-{d}", "market-wrap", "market-wrap", 85, self.at(23, 59), [],
                         "Stock Market Today: <the story of the day>",
                         "The close. Use pack.markets for the numbers table. Link today's stories where they fit.",
                         {"markets": self.markets, "top_moves": self.top_moves(10), "todays_stories": todays,
                          "reporting_after_close": [r["ticker"] for r in self.cal.get(d.isoformat(), []) if r["time"] == "amc"][:12]})
            if self.now.time() >= dt.time(8, 50):
                self.add(f"macro-{d}", "macro-check", "macro", 45, self.at(13, 0), [],
                         "Only if a top-tier economic release came out this morning",
                         "Check whether CPI, PPI, the jobs report, GDP, PCE, retail sales or JOLTS came out today at 8:30 or 10:00. "
                         "If one did, write a macro story (number vs expectations, what moved, what's next). If not, skip this event.",
                         {"markets": self.markets})
            if self.now.time() >= dt.time(9, 0) and d.weekday() in (1, 2, 3, 4):
                prev = prev_trading_day(d)
                self.add(f"movers-{prev}", "movers", "movers", 55, self.at(12, 0), [],
                         f"Stocks Making the Biggest Moves Yesterday",
                         f"Yesterday ({prev:%A %d %B})'s five biggest moves among companies worth $10bn+, one paragraph each. "
                         "Link each to our story about it when one exists.",
                         {"session": prev.isoformat(), "moves": self.session_moves(prev)})
            if d.weekday() == 4 and self.now.time() >= dt.time(16, 40):
                self.add(f"movers-week-{d}", "movers", "movers", 50, self.at(23, 59), [],
                         "Stocks Making the Biggest Moves This Week", "The week's five biggest moves, Monday open to Friday close.",
                         {"week_ending": d.isoformat(), "moves": self.week_moves()})
            if d.weekday() in (1, 3) and self.now.time() >= dt.time(11, 30):
                recent = " ".join(x["title"].lower() for x in self.stories
                                  if x["type"] == "list" and x["date"] >= (d - dt.timedelta(days=21)).isoformat())
                fresh = [th for th in LIST_THEMES if th[1].lower() not in recent]
                k = (d.toordinal() // 2) % len(fresh or LIST_THEMES)
                theme = (fresh or LIST_THEMES)[k]
                self.add(f"list-{d}", "list", "list", 30, self.at(23, 59), [],
                         f"3 {theme[1]} Stocks We Love and 1 We Hate",
                         f"Theme: {theme[1]}, screened on {theme[2]}. Pick 3 to love and 1 to hate from pack.candidates; "
                         "every reason must rest on a dated number from data/fundamentals or the latest results.",
                         {"theme": theme[0], "screen": theme[2], "candidates": self.screen(theme)})
        fomc = self.fomc_today()
        if fomc and self.now.time() >= dt.time(14, 5):
            self.add(f"fomc-{d}", "fomc", "macro", 92, self.at(23, 59), [],
                     "The Fed's decision", "The statement came out at 2 p.m. ET and the chair speaks at 2:30. Decision, vote, "
                     "dissents, the statement's changes, the press conference's key quotes, market reaction.",
                     {"markets": self.markets})
        if d.weekday() == 6 and self.now.time() >= dt.time(12, 0):
            nxt = next_trading_day(d)
            week = []
            for k in range(5):
                day = nxt + dt.timedelta(days=k)
                rows = sorted(self.cal.get(day.isoformat(), []), key=lambda r: -cap_of(self.quotes.get(r["ticker"])))[:8]
                week.append({"date": day.isoformat(), "reporters": [{"ticker": r["ticker"], "time": r["time"],
                                                                     "eps_forecast": r["eps_forecast"]} for r in rows]})
            self.add(f"weekahead-{d}", "week-ahead", "analysis", 40, dt.datetime.combine(nxt, dt.time(9, 0), tzinfo=ET), [],
                     "The Week Ahead: <the big tests for stocks>", "Day by day: the big reporters and the economic calendar.",
                     {"week": week})

    def fomc_today(self) -> bool:
        p = md.DATA / "calendar/fomc.json"
        return p.exists() and self.today.isoformat() in json.loads(p.read_text())

    def top_moves(self, n: int):
        rows = [(t, q["change_pct"], cap_of(q)) for t, q in self.quotes.items()
                if q.get("change_pct") is not None and cap_of(q) >= 1e10 and (q.get("time") or "").startswith(self.today.isoformat())]
        rows.sort(key=lambda x: x[1])
        pick = rows[:n] + rows[::-1][:n]
        return [{"ticker": t, "name": self.univ.get(t, {}).get("name", t), "change_pct": c, "price": self.quotes[t]["price"]}
                for t, c, _ in pick]

    def session_moves(self, day: dt.date):
        out = []
        for t, u in self.univ.items():
            if cap_of(self.quotes.get(t)) < 1e10:
                continue
            bars = [b for b in md.read_prices(t) if b["date"] <= day.isoformat()]
            if len(bars) < 2 or bars[-1]["date"] != day.isoformat():
                continue
            out.append({"ticker": t, "name": u["name"], "close": bars[-1]["close"],
                        "change_pct": round((bars[-1]["close"] / bars[-2]["close"] - 1) * 100, 2)})
        out.sort(key=lambda x: -abs(x["change_pct"]))
        for m in out[:12]:
            m["our_stories"] = [s["path"] for s in self.stories_for(m["ticker"], 3) if s["date"] >= day.isoformat()]
        return out[:12]

    def week_moves(self):
        monday = self.today - dt.timedelta(days=self.today.weekday())
        out = []
        for t, u in self.univ.items():
            if cap_of(self.quotes.get(t)) < 1e10:
                continue
            bars = md.read_prices(t)
            before = [b for b in bars if b["date"] < monday.isoformat()]
            if not before or not bars:
                continue
            out.append({"ticker": t, "name": u["name"], "close": bars[-1]["close"],
                        "change_pct": round((bars[-1]["close"] / before[-1]["close"] - 1) * 100, 2)})
        out.sort(key=lambda x: -abs(x["change_pct"]))
        return out[:12]

    def screen(self, theme):
        key = theme[3]
        rows = []
        for t, u in self.univ.items():
            q = self.quotes.get(t) or {}
            fp = md.DATA / "fundamentals" / f"{t.replace('.', '-')}.json"
            ttm = json.loads(fp.read_text()).get("ttm", {}) if fp.exists() else {}
            cap = cap_of(q)
            if cap < 5e9:
                continue
            if theme[0] == "ai-infrastructure" and not re.search(r"Semiconductor|Electronic|Communications Equipment|Internet Services|Heavy Electrical|Electrical Components|Technology Hardware", u["industry"]):
                continue
            if theme[0] == "profitable-small-caps" and not (5e9 <= cap <= 3e10):
                continue
            bars = md.read_prices(t)
            if len(bars) < 130:
                continue
            hi = max(b["close"] for b in bars[-252:])
            v = {"fcf_margin_pct": ttm.get("fcf_margin_pct"), "revenue_growth_yoy_pct": ttm.get("revenue_growth_yoy_pct"),
                 "operating_margin_pct": ttm.get("operating_margin_pct"), "dividend_yield": q.get("dividend_yield"),
                 "off_high": round((1 - bars[-1]["close"] / hi) * 100, 1) if (ttm.get("operating_margin_pct") or 0) > 10 else None,
                 "ret_6m": round((bars[-1]["close"] / bars[-127]["close"] - 1) * 100, 1)}.get(key)
            if v is None:
                continue
            rows.append({"ticker": t, "name": u["name"], "industry": u["industry"], "metric": v, "price": q.get("price"),
                         "pe": q.get("pe"), "ttm": ttm})
        rows.sort(key=lambda r: -r["metric"])
        return rows[:12] + rows[-4:]

    # ------------------------------------------------------------- run
    def run(self):
        for rule in (self.rule_recaps, self.rule_moves, self.rule_previews, self.rule_edition, self.rule_daily):
            try:
                rule()
            except Exception as e:  # noqa: BLE001
                print(f"rule {rule.__name__} failed: {e}")
        self.expire()
        if self.dry:
            for e in self.new:
                print(f"{e['priority']:>3} {e['id']:<40} {e['headline_hint']}")
            return self.new
        QUEUE.mkdir(parents=True, exist_ok=True)
        for e in self.new:
            (QUEUE / f"{e['id']}.json").write_text(json.dumps(e, indent=1, default=str))
        cutoff = (self.today - dt.timedelta(days=21)).isoformat()
        self.seen = {k: v for k, v in self.seen.items() if v.get("day", "9999") >= cutoff}
        SEEN.write_text(json.dumps(self.seen, indent=0, sort_keys=True))
        print(f"queued {len(self.new)}: " + ", ".join(e["id"] for e in self.new))
        return self.new

    def expire(self):
        if self.dry:
            return
        for p in QUEUE.glob("*.json"):
            e = json.loads(p.read_text())
            if dt.datetime.fromisoformat(e["expires"]) < self.now:
                DONE.mkdir(parents=True, exist_ok=True)
                e["outcome"] = "expired"
                (DONE / p.name).write_text(json.dumps(e, indent=1))
                p.unlink()


def main(argv):
    dry = "--dry" in argv
    now = md.now_et()
    if "--at" in argv:
        now = dt.datetime.fromisoformat(argv[argv.index("--at") + 1]).replace(tzinfo=ET)
    new = Detector(now, dry).run()
    top = max([e["priority"] for e in new] or [0])
    # For the workflow: whether to wake the writer now rather than wait for its next scheduled run.
    out = Path(__import__("os").environ.get("GITHUB_OUTPUT", "/dev/null"))
    with out.open("a") as f:
        f.write(f"queued={len(new)}\nwake={'true' if top >= 70 else 'false'}\n")


if __name__ == "__main__":
    main(sys.argv[1:])
