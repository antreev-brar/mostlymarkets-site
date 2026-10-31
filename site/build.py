"""Build mostlymarkets.org into dist/. Standard library only.

  python3 site/build.py                 # full build
  MM_BASE_PATH=/mostlymarkets-site/ python3 site/build.py   # when served from a sub-path (GitHub Pages preview)
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import math
import os
import re
import shutil
import sys
import time
import tomllib
from collections import defaultdict
from email.utils import format_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
DIST = Path(os.environ.get("MM_DIST") or ROOT / "dist")  # MM_DIST lets several writers render at once
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(SITE))
import charts as C  # noqa: E402
from marketdata import quote_time, read_prices  # noqa: E402
from md import Renderer  # noqa: E402

ET = ZoneInfo("America/New_York")
CFG = json.loads((SITE / "config.json").read_text())
BASE = os.environ.get("MM_BASE_PATH", CFG["base_path"])
if not BASE.endswith("/"):
    BASE += "/"
BASE_URL = os.environ.get("MM_BASE_URL", CFG["base_url"]).rstrip("/")
LAUNCHED = os.environ.get("MM_LAUNCHED", str(CFG["launched"])).lower() == "true"
NOW = dt.datetime.now(tz=ET)
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
         "November", "December"]
WD = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
TYPE_LABEL = {"daily": "The Daily", "market-wrap": "Markets", "why-it-moved": "Why it moved", "movers": "Big movers",
              "earnings-recap": "Earnings", "earnings-preview": "Earnings preview", "list": "Our picks",
              "macro": "Economy", "chart": "Chart", "analysis": "Analysis", "narrative": "The big story",
              "viewpoints": "Bulls vs bears", "breakdown": "Breakdown", "brief": "News"}
FILTERS = [("all", "All"), ("brief,why-it-moved,movers", "News & moves"),
           ("narrative,viewpoints,breakdown,analysis,chart", "Analysis"), ("earnings-recap,earnings-preview", "Earnings"),
           ("list", "Our picks"), ("daily,market-wrap,macro", "Markets"), ("mine", "My stocks")]


def esc(s) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def u(path: str) -> str:
    return BASE + path.lstrip("/")


def absu(path: str) -> str:
    return BASE_URL + "/" + path.lstrip("/")


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def tpath(t: str) -> str:
    return f"stocks/{t}/"


# ---------------------------------------------------------------------- formatting

def ampm(d: dt.datetime) -> str:
    h = d.hour % 12 or 12
    return f"{h}:{d.minute:02d} {'a.m.' if d.hour < 12 else 'p.m.'}"


def when(d: dt.datetime, with_year: bool = False) -> str:
    y = f" {d.year}" if with_year or d.year != NOW.year else ""
    return f"{d.day} {MON[d.month - 1]}{y}, {ampm(d)} ET"


def day_title(d: dt.date) -> str:
    return f"{WD[d.weekday()]}, {d.day} {MONTH[d.month - 1]}"


def money(v, digits=2) -> str:
    if v is None:
        return "–"
    return f"${v:,.{digits}f}"


def big_money(v) -> str:
    if v is None:
        return "–"
    a = abs(v)
    s = "−" if v < 0 else ""
    if a >= 1e12:
        return f"{s}${a / 1e12:.2f} trillion"
    if a >= 1e9:
        return f"{s}${a / 1e9:.1f} billion" if a < 1e11 else f"{s}${a / 1e9:.0f} billion"
    if a >= 1e6:
        return f"{s}${a / 1e6:.0f} million"
    return f"{s}${a:,.0f}"


def short_money(v) -> str:
    if v is None:
        return "–"
    a, s = abs(v), ("−" if v < 0 else "")
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if a >= div:
            return f"{s}${a / div:.2f}{suf}" if a / div < 100 else f"{s}${a / div:.0f}{suf}"
    return f"{s}${a:,.0f}"


def pct(v, digits=2, sign=True) -> str:
    if v is None:
        return "–"
    return f"{'+' if v > 0 and sign else '−' if v < 0 else ''}{abs(v):.{digits}f}%"


def tone(v) -> str:
    return "" if v is None else ("up" if v >= 0 else "down")


def parse_cap(s) -> float | None:
    if not s:
        return None
    m = re.match(r"([\d.]+)\s*([TBMK]?)", str(s))
    if not m:
        return None
    return float(m.group(1)) * {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3, "": 1}[m.group(2)]


# ---------------------------------------------------------------------- data

UNIV = json.loads((ROOT / "data/universe/universe.json").read_text())
UMAP = {x["ticker"]: x for x in UNIV}
AUTHORS = {a["id"]: a for a in json.loads((ROOT / "data/authors.json").read_text())}
COVERS = json.loads((SITE / "covers.json").read_text())
COVER_ALT: dict[str, str] = {}  # alt text for AI story covers (assets/covers/story/)
QPATH = ROOT / "data/quotes/latest.json"
QUOTES = json.loads(QPATH.read_text()) if QPATH.exists() else {"asof": None, "quotes": {}}
Q = QUOTES["quotes"]
for t, q in Q.items():
    q["cap"] = parse_cap(q.get("mktcap"))
MPATH = ROOT / "data/quotes/markets.json"
MKT = json.loads(MPATH.read_text()) if MPATH.exists() else {"asof": None, "markets": {}}


def _load_news() -> dict[str, dict]:
    """Aggregated headlines per ticker (pipeline/news.py): data/news/<T>.json, plus market.json under "_market"."""
    out = {}
    for f in (ROOT / "data/news").glob("*.json") if (ROOT / "data/news").exists() else []:
        if f.stem == "tweets":
            continue
        try:
            d = json.loads(f.read_text())
        except Exception:  # noqa: BLE001
            continue
        out["_market" if f.stem == "market" else (d.get("ticker") or f.stem)] = d
    return out


NEWS = _load_news()
TPATH_ = ROOT / "data/news/tweets.json"
TWEETS: dict = json.loads(TPATH_.read_text()) if TPATH_.exists() else {}

_PRICES: dict[str, list] = {}


def prices(t: str) -> list[dict]:
    if t not in _PRICES:
        _PRICES[t] = read_prices(t)
    return _PRICES[t]


def close_on(t: str, day: str):
    bars = [b for b in prices(t) if b["date"] <= day]
    if len(bars) < 2:
        return None
    return bars[-1], bars[-2]


def ret_since(t: str, days: int, end: str | None = None):
    bars = prices(t)
    if end:
        bars = [b for b in bars if b["date"] <= end]
    if len(bars) <= days:
        return None
    return (bars[-1]["close"] / bars[-1 - days]["close"] - 1) * 100


def ytd(t: str, end: str | None = None):
    bars = prices(t)
    if end:
        bars = [b for b in bars if b["date"] <= end]
    if not bars:
        return None
    y = bars[-1]["date"][:4]
    prior = [b for b in bars if b["date"] < f"{y}-01-01"]
    return (bars[-1]["close"] / prior[-1]["close"] - 1) * 100 if prior else None


FUND: dict[str, dict] = {}
for f in (ROOT / "data/fundamentals").glob("*.json"):
    try:
        d = json.loads(f.read_text())
        FUND[d.get("ticker") or f.stem.replace("-", ".")] = d
    except Exception:  # noqa: BLE001
        pass

CAL: dict[str, list] = {}
for f in sorted((ROOT / "data/calendar").glob("20*-*-*.json")):
    CAL[f.stem] = json.loads(f.read_text())


def next_earnings(t: str):
    """The next report that hasn't happened yet (today's counts until its release time)."""
    today = NOW.date().isoformat()
    for d in sorted(CAL):
        if d < today:
            continue
        for r in CAL[d]:
            if r["ticker"] != t:
                continue
            if d == today and (r["time"] == "bmo" and NOW.hour >= 9 or r["time"] == "amc" and NOW.hour >= 16
                               or r.get("eps_actual") is not None):
                continue
            return d, r
    return None


# ---------------------------------------------------------------------- articles

class Story:
    def __init__(self, path: Path):
        text = path.read_text()
        _, fm, body = text.split("+++", 2)
        self.fm = tomllib.loads(fm)
        self.body = body.strip()
        m = re.match(r"(\d{4}-\d{2}-\d{2})-(.+)\.md$", path.name)
        self.date, self.slug = m.group(1), m.group(2)
        self.type = self.fm["type"]
        self.path = f"daily/{self.date}/" if self.type == "daily" else f"news/{self.date}/{self.slug}/"
        self.title = self.fm["title"]
        self.dek = self.fm["dek"]
        self.type = self.fm["type"]
        self.pub = self.fm["published"].astimezone(ET)
        self.tickers = [t for t in self.fm.get("tickers", []) if t in UMAP]
        self.author = AUTHORS.get(self.fm.get("author"), {"name": "Mostly Markets", "role": ""})
        self.status = self.fm.get("status", "published")
        self.featured = bool(self.fm.get("featured"))
        self.themes = [str(x) for x in self.fm.get("themes", []) if x]
        self.moves = self._moves()
        self.cover = self._cover()
        self._rendered = None
        words = len(re.findall(r"\w+", re.sub(r"```.*?```", " ", self.body, flags=re.S)))
        self.minutes = max(1, round(words / 230))

    def _moves(self):
        out = []
        given = {m["ticker"]: m for m in self.fm.get("moves", []) if m.get("ticker") in UMAP}
        for t in [x for x in self.tickers if x not in ("GOOG", "FOX", "NWS") or x == self.tickers[0]][:4]:
            if given and t not in given:
                continue  # the story says which moves matter; don't mix in other sessions
            if t in given:
                m = given[t]
                asof = m.get("asof")
                day = (asof.astimezone(ET).date().isoformat() if isinstance(asof, dt.datetime) else
                       asof.isoformat() if isinstance(asof, dt.date) else None)
                out.append({"t": t, "p": m.get("price"), "c": m.get("change_pct"), "s": m.get("session", "close"), "d": day})
                continue
            c = close_on(t, self.date)
            if c and c[0]["date"] == self.date:
                out.append({"t": t, "p": c[0]["close"], "c": (c[0]["close"] / c[1]["close"] - 1) * 100, "s": "close",
                            "d": self.date})
        return out

    def _cover(self):
        keys = COVERS["covers"]
        if (ROOT / f"assets/covers/story/{self.slug}-800.webp").exists():  # AI art drawn for this story
            COVER_ALT[f"story/{self.slug}"] = self.fm.get("cover_alt") or "Illustration for this story"
            return f"story/{self.slug}"
        want = self.fm.get("cover")
        if want in keys:
            return want
        opts: list[str] = []
        if self.type in ("market-wrap", "macro", "chart", "movers", "list", "analysis") or not self.tickers:
            opts = COVERS["type"].get(self.type, ["markets-calm"])
        if not opts and self.tickers:
            info = UMAP[self.tickers[0]]
            for k, v in COVERS["industry"].items():
                if k.lower() in info["industry"].lower():
                    opts = v
                    break
            if not opts:
                opts = COVERS["sector"].get(info["sector"], ["markets-calm"])
        if self.type == "earnings-preview" and self.tickers:
            opts = opts or COVERS["type"]["earnings-preview"]
        h = int(hashlib.md5(self.slug.encode()).hexdigest(), 16)
        return opts[h % len(opts)] if opts else "markets-calm"

    def weight(self) -> float:
        base = {"daily": 7, "market-wrap": 6, "narrative": 6, "earnings-recap": 5, "macro": 5, "viewpoints": 5, "analysis": 4,
                "breakdown": 4, "why-it-moved": 3, "list": 3, "brief": 3, "earnings-preview": 2, "movers": 2,
                "chart": 1}.get(self.type, 2)
        mv = max([abs(m["c"]) for m in self.moves if m.get("c") is not None] or [0])
        cap = max([(Q.get(t) or {}).get("cap") or 0 for t in self.tickers] or [0])
        return base + min(mv, 15) / 3 + (2 if cap > 5e11 else 1 if cap > 1e11 else 0) + (6 if self.featured else 0)


STORIES: list[Story] = []
for p in sorted((ROOT / "content/articles").glob("*.md")):
    try:
        s = Story(p)
    except Exception as e:  # noqa: BLE001
        print("skip", p.name, e)
        continue
    if s.status == "draft" or s.pub > NOW + dt.timedelta(minutes=5):
        continue
    STORIES.append(s)
STORIES.sort(key=lambda s: s.pub, reverse=True)
BY_TICKER: dict[str, list[Story]] = defaultdict(list)
for s in STORIES:
    for t in s.tickers:
        BY_TICKER[t].append(s)
BY_PATH = {f"/{s.path}": s for s in STORIES}
DAILIES = [s for s in STORIES if s.type == "daily"]  # newest first
BY_THEME: dict[str, list[Story]] = defaultdict(list)  # running stories (STYLE.md, "Story log"), newest first
for s in STORIES:
    for th in s.themes:
        BY_THEME[th].append(s)


def running_story(s: Story):
    """The newest narrative that shares a theme with this story (not the story itself)."""
    cands = [x for th in s.themes for x in BY_THEME[th] if x.type == "narrative" and x is not s]
    return max(cands, key=lambda x: x.pub) if cands else None


def story_log(s: Story) -> str:
    """A narrative's dated log: every story on its themes, newest first."""
    seen, items = set(), []
    for x in sorted({id(x): x for th in s.themes for x in BY_THEME[th]}.values(), key=lambda x: x.pub, reverse=True):
        if x is s or id(x) in seen:
            continue
        seen.add(id(x))
        items.append(f'<li><span class="sl-d">{x.pub.day} {MON[x.pub.month - 1]}</span><a href="{u(x.path)}">{esc(x.title)}</a>'
                     f'<span class="sl-t">{TYPE_LABEL[x.type]} · {ago(x.pub, "ago q")}</span></li>')
    if not items:
        return ""
    return (f'<section class="slog"><h2>Story log</h2><p class="lede">Everything we\'ve published on this story, newest first. '
            f'This page grows as the story moves.</p><ol>{"".join(items[:30])}</ol></section>')
for i, s in enumerate(reversed(DAILIES)):
    s.edition = i + 1
    # A weekend edition published on a Friday evening shares its date with that morning's edition.
    if s.fm.get("edition") == "weekend" and any(x is not s and x.date == s.date for x in DAILIES):
        del BY_PATH[f"/{s.path}"]
        s.path = f"daily/{s.date}/weekend/"
        BY_PATH[f"/{s.path}"] = s

# ---------------------------------------------------------------------- page shell

ICON = {
    "search": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/></svg>',
    "theme": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z"/></svg>',
    "play": '<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.2-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5Z"/></svg>',
    "plus": '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
}
NAV = [("", "Feed"), ("daily/", "The Daily"), ("discover/", "Discover"), ("earnings/", "Earnings")]
STRIP = [(".SPX", "S&P 500"), (".IXIC", "Nasdaq"), (".DJI", "Dow"), (".RUT", "Russell 2000"), ("US10Y", "10-year"),
         ("@CL.1", "Oil"), ("@GC.1", "Gold"), ("BTC.CM=", "Bitcoin")]
sys.path.insert(0, str(ROOT / "pipeline"))
try:
    from detect import HOLIDAYS  # noqa: E402  (the market's closed days, for the open/closed label)
except Exception:  # noqa: BLE001
    HOLIDAYS = set()


def market_strip() -> str:
    """The thin line under the header on every page: market status (set live by app.js), the indexes, and how fresh
    the newest story is. It's what tells a reader the site is current."""
    cells = []
    for k, lab in STRIP:
        m = MKT["markets"].get(k) or {}
        if m.get("price") is None:
            continue
        if k == "US10Y":
            v = f'{m["price"]:.2f}%'
            cells.append(f'<span class="ms-i"><b>{lab}</b> <span data-mk="{k}" data-k="lvl">{v}</span></span>')
            continue
        c = m.get("change_pct")
        cells.append(f'<span class="ms-i"><b>{lab}</b> <span class="{tone(c)}" data-mk="{k}" data-k="chg">'
                     f'{"▲" if (c or 0) >= 0 else "▼"} {abs(c or 0):.2f}%</span></span>')
    newest = STORIES[0] if STORIES else None
    last = (f'<a class="ms-new" href="{u(newest.path)}">Newest story <time datetime="{newest.pub.isoformat()}" data-rel>'
            f'{esc(when(newest.pub))}</time></a>') if newest else ""
    return (f'<div class="mstrip" data-hol="{" ".join(sorted(HOLIDAYS))}"><div class="wrap"><span class="ms-st" data-mstatus>'
            f'<i></i><span>Markets</span></span><div class="ms-row">{"".join(cells)}</div>{last}</div></div>')


def page(path: str, title: str, body: str, desc: str = "", image: str | None = None, active: str = "",
         og_type: str = "website", extra_head: str = "") -> str:
    full_title = title if title.endswith(CFG["name"]) else f"{title} | {CFG['name']}"
    desc = desc or CFG["tagline"]
    img = absu(image) if image else absu("static/og.jpg")
    robots = "" if LAUNCHED else '<meta name="robots" content="noindex, nofollow">'
    nav = "".join(f'<a href="{u(p)}"{" aria-current=page" if active == p else ""}>{n}</a>' for p, n in NAV)
    fonts = ("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Source+Serif+4:ital,opsz,wght@"
             "0,8..60,400..700;1,8..60,400&display=swap")
    return f"""<!doctype html>
<html lang="en" data-base="{BASE}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(desc)}">
{robots}
<link rel="canonical" href="{absu(path)}">
<meta property="og:site_name" content="{CFG['name']}">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{absu(path)}">
<meta property="og:image" content="{img}">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0b1020" media="(prefers-color-scheme: dark)">
<link rel="icon" href="{u('static/favicon.svg')}" type="image/svg+xml">
<link rel="alternate" type="application/rss+xml" title="{CFG['name']}" href="{u('feed.xml')}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{fonts}">
<link rel="stylesheet" href="{u('static/style.css')}?v={ASSET_V}">
<script>try{{var t=localStorage.getItem("mm-theme");if(t)document.documentElement.setAttribute("data-theme",JSON.parse(t))}}catch(e){{}}</script>
{extra_head}
</head>
<body>
<header class="hd">
 <div class="wrap">
  <a class="wm" href="{u('')}" aria-label="Mostly Markets, home">Mostly <span>Markets</span></a>
  <nav class="nav" aria-label="Main">{nav}</nav>
  <div class="hd-r">
   <button class="ib" type="button" data-search aria-label="Search">{ICON['search']}</button>
   <button class="ib" type="button" data-theme-toggle aria-label="Switch light or dark theme">{ICON['theme']}</button>
   <a class="btn" href="{CFG['subscribe']}">Subscribe</a>
  </div>
 </div>
 <nav class="nav2" aria-label="Sections">{nav}</nav>
</header>
{market_strip()}
<main>
{body}
</main>
<footer class="ft">
 <div class="wrap">
  <div><a class="wm" href="{u('')}">Mostly <span>Markets</span></a><p>{esc(CFG['tagline'])} New stories through every market day, analysis at the weekend, and a free newsletter.</p></div>
  <nav aria-label="Footer"><a href="{u('')}">Feed</a><a href="{u('daily/')}">The Daily</a><a href="{u('discover/')}">Discover</a><a href="{u('earnings/')}">Earnings</a><a href="{u('stocks/')}">All stocks</a><a href="{CFG['substack']}">Newsletter</a><a href="{CFG['instagram']}">Instagram</a><a href="{u('about/')}">About</a><a href="{u('feed.xml')}">RSS</a></nav>
  <div><p>Mostly Markets is for information and education only. It is not investment advice, and nothing here is a recommendation to buy or sell any security.</p><p>Our writers publish under pen names. Prices from Nasdaq and CNBC, financials from SEC filings, headlines link to their publishers.</p></div>
 </div>
</footer>
<div class="srch" role="dialog" aria-label="Search"><div class="bx"><input type="search" placeholder="Search stocks and stories" aria-label="Search"><div class="res"></div></div></div>
<script src="{u('static/app.js')}?v={ASSET_V}" defer></script>
</body>
</html>"""


def write(path: str, content: str):
    p = DIST / path
    if path.endswith("/") or path == "":
        p = p / "index.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


# ---------------------------------------------------------------------- components

LOGOS = {p.stem for p in (ROOT / "assets/logos").glob("*.png")} if (ROOT / "assets/logos").exists() else set()
MARKET_ICON = ('<svg viewBox="0 0 24 24" width="55%" height="55%" fill="none" stroke="currentColor" stroke-width="2" '
               'stroke-linecap="round" stroke-linejoin="round" style="color:var(--accent)"><path d="M3 17l5-5 4 4 8-9"/><path d="M15 7h5v5"/></svg>')


def logo(t: str | None, size: int = 36) -> str:
    """A company logo in a white circle; a monogram when we have no logo; a market icon for no ticker."""
    st = f' style="--s:{size}px"'
    if not t:
        return f'<span class="lg"{st} aria-hidden="true">{MARKET_ICON}</span>'
    if t in LOGOS:
        return f'<span class="lg"{st}><img src="{u(f"static/logos/{t}.png")}" alt="" loading="lazy" decoding="async"></span>'
    return f'<span class="lg"{st} aria-hidden="true"><b>{esc(t[:4])}</b></span>'


def logos(ts: list[str], size: int = 36, limit: int = 3) -> str:
    if not ts:
        return f'<span class="lgs" style="--s:{size}px">{logo(None, size)}</span>'
    return f'<span class="lgs" style="--s:{size}px">' + "".join(logo(t, size) for t in ts[:limit]) + "</span>"


def chip(m: dict) -> str:
    s = m.get("s")
    tag = {"after-hours": "AH", "pre-market": "PM"}.get(s, "")
    c = m.get("c")
    if c is None:
        return f'<span class="pc"><b>{m["t"]}</b></span>'
    return (f'<span class="pc {tone(c)}"><b>{m["t"]}</b><i>{"▲" if c >= 0 else "▼"} {abs(c):.1f}%</i>'
            f'{f"<small>{tag}</small>" if tag else ""}</span>')


def chips(s: Story, limit=3) -> str:
    if not s.moves:
        return ""
    extra = len(s.moves) - limit
    return '<span class="pcs">' + "".join(chip(m) for m in s.moves[:limit]) + (
        f'<span class="pc">+{extra}</span>' if extra > 0 and limit > 1 else "") + "</span>"


def cover_img(key: str, size: int, cls: str = "", lazy=True, alt=True) -> str:
    a = esc(COVERS["covers"].get(key, {}).get("alt", "") or COVER_ALT.get(key, "")) if alt else ""
    srcset = ""
    if size == 1600:
        srcset = f' srcset="{u(f"static/covers/{key}-800.webp")} 800w, {u(f"static/covers/{key}-1600.webp")} 1600w" sizes="(max-width: 760px) 100vw, 680px"'
    return (f'<img src="{u(f"static/covers/{key}-{size}.webp")}"{srcset} alt="{a}"'
            f'{" loading=lazy decoding=async" if lazy else ""} class="{cls}">')


def time_tag(s: Story, rel=True) -> str:
    return f'<time datetime="{s.pub.isoformat()}"{" data-rel" if rel else ""}>{esc(ampm(s.pub))} ET</time>'


def ago(d: dt.datetime, cls: str = "ago") -> str:
    """A timestamp that app.js turns into "12 min ago", "3h ago", "Yesterday" and keeps ticking."""
    fb = f"{WD[d.weekday()][:3]} {d.day} {MON[d.month - 1]}, {ampm(d)}"
    return f'<time class="{cls}" datetime="{d.isoformat()}" data-rel>{esc(fb)}</time>'


def fresh(s: Story) -> str:
    """Attributes app.js reads to mark a card New (published in the last few hours) or unseen since the last visit."""
    return f' data-pub="{s.pub.isoformat()}"'


NEWB = '<span class="newb">New</span>'

# ---------------------------------------------------------------------- picture for every card: a chart, never stock art

_TM_CACHE: dict[str, str] = {}


def thumb_spark(t: str, end: str, tone_: str | None = None, w: int = 320, h: int = 200, n: int = 44) -> str:
    """A small area chart of a stock's last two months of closes, ending on the story's day. The last point is the news."""
    bars = [b for b in prices(t) if b["date"] <= end][-n:]
    if len(bars) < 5:
        return ""
    vals = [b["close"] for b in bars]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.12 or 1
    lo, hi = lo - pad, hi + pad
    top, bot = h * 0.30, h * 0.94
    pts = [(w * i / (len(vals) - 1), bot - (bot - top) * (v - lo) / (hi - lo)) for i, v in enumerate(vals)]
    line = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = line + f" L{w},{h} L0,{h} Z"
    tn = tone_ or ("up" if vals[-1] >= vals[0] else "down")
    x, y = pts[-1]
    return (f'<svg class="tsp {tn}" viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">'
            f'<path class="a" d="{area}"/><path class="l" d="{line}" vector-effect="non-scaling-stroke"/></svg>'
            f'<i class="tdot {tn}" style="left:{x / w * 100:.1f}%;top:{y / h * 100:.1f}%"></i>')


def thumb_map(day: str, w: int = 320, h: int = 200, n: int = 48) -> str:
    """The day's market map in miniature: the biggest S&P 500 companies sized by value, coloured by the move."""
    if day in _TM_CACHE:
        return _TM_CACHE[day]
    mv = sorted(day_moves(day), key=lambda m: -m["cap"])[:n]
    if not mv:
        return ""
    tot = sum(m["cap"] for m in mv)
    rects = C.squarify([m["cap"] / tot * w * h for m in mv], 0, 0, w, h)
    cells = "".join(f'<rect x="{x + .6:.1f}" y="{y + .6:.1f}" width="{max(0, rw - 1.2):.1f}" height="{max(0, rh - 1.2):.1f}" '
                    f'rx="2" fill="{C.heat(m["v"])}"/>' for m, (x, y, rw, rh) in zip(mv, rects))
    _TM_CACHE[day] = f'<svg class="tmm" viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">{cells}</svg>'
    return _TM_CACHE[day]


def thumb(s: Story) -> str:
    """The card picture: the stock's recent line with the story's day as the last point, its logo on top; or, for
    market-wide stories, that day's market map."""
    if s.tickers and prices(s.tickers[0]):
        mv = next((m for m in s.moves if m["t"] == s.tickers[0] and m.get("c") is not None), None)
        sp = thumb_spark(s.tickers[0], s.date, tone(mv["c"]) if mv else None)
        if sp:
            return f'<div class="th tch">{sp}<span class="th-lg">{logos(s.tickers, 30)}</span></div>'
    day = last_trading_day(s.date)
    return f'<div class="th tmap-th">{thumb_map(day)}</div>'


def row(s: Story) -> str:
    """A river card: when (prominent), what kind, headline, two-line dek, the price tag, and the chart picture."""
    return (f'<article class="card" data-type="{s.type}" data-tickers="{" ".join(s.tickers)}"{fresh(s)}>'
            f'<a class="cover-link" href="{u(s.path)}" aria-label="{esc(s.title)}"></a><div>'
            f'<div class="c-top">{NEWB}{ago(s.pub)}<span class="tag">{TYPE_LABEL[s.type]}</span></div>'
            f'<h3>{esc(s.title)}</h3><p class="dk">{esc(s.dek)}</p>'
            f'<div class="c-ft">{chips(s, 2)}</div></div>'
            f'{thumb(s)}</article>')


def mini(s: Story, show_thumb: bool = True) -> str:
    """A compact headline row for top-story lists and side rails: time, kind, headline."""
    th = thumb(s) if show_thumb else ""
    return (f'<article class="mini{" nt" if not show_thumb else ""}"{fresh(s)}><a class="cover-link" href="{u(s.path)}" aria-label="{esc(s.title)}"></a>'
            f'{th}<div class="mi-tx"><div class="mi-k">{NEWB}{ago(s.pub)}<span>{TYPE_LABEL[s.type]}</span></div>'
            f'<h3>{esc(s.title)}</h3></div></article>')


def news_items(t: str | None, n: int = 6, since_days: int = 10) -> list[dict]:
    """Aggregated outside headlines (pipeline/news.py) for a ticker, or the market's when t is None. Newest first."""
    d = NEWS.get(t or "_market") or {}
    out = []
    cutoff = NOW - dt.timedelta(days=since_days)
    for it in d.get("items", []):
        try:
            when_ = dt.datetime.fromisoformat(it["published"]).astimezone(ET)
        except Exception:  # noqa: BLE001
            continue
        if when_ < cutoff or when_ > NOW + dt.timedelta(minutes=5):
            continue
        out.append({**it, "dt": when_})
    out.sort(key=lambda x: x["dt"], reverse=True)
    return out[:n]


def news_row(it: dict) -> str:
    also = f' <span class="nw-also">+{len(it["also"])}</span>' if it.get("also") else ""
    return (f'<li class="nw"><a href="{esc(it["url"])}" target="_blank" rel="noopener nofollow">{esc(it["title"])}</a>'
            f'<span class="nw-m">{esc(it.get("source") or "")}{also} · {ago(it["dt"], "ago q")}</span></li>')


def mini_rows(stories: list[Story]) -> str:
    out = []
    last_day = None
    for s in stories:
        d = s.pub.date()
        if d != last_day:
            out.append(f'<div class="day" data-day="{d.isoformat()}"><span>{day_title(d)}</span></div>')
            last_day = d
        out.append(row(s))
    return '<div class="cards-col">' + "".join(out) + "</div>"


def subscribe_box(wide=False, title="The close, in your inbox", text=None) -> str:
    text = text or "Every market day, the stories that moved stocks and why. Free, from the Mostly Markets newsletter."
    return (f'<aside class="sub{"" if wide else " col"}"><div><h4>{esc(title)}</h4><p>{esc(text)}</p></div>'
            f'<a class="btn" href="{CFG["subscribe"]}">Subscribe free</a></aside>')


# ---------------------------------------------------------------------- story page

SECOND_CLASS = {"GOOG", "FOX", "NWS"}  # CNBC gives each class the whole company's market value; count the company once
SP500 = [t for t, x in UMAP.items() if "S&P 500" in x.get("index", []) and t not in SECOND_CLASS]


def day_moves(day: str, members: list[str] | None = None) -> list[dict]:
    """Each stock's close-to-close move on `day`, with its market value then (today's value scaled by price)."""
    out = []
    for t in [x for x in (members or SP500) if x not in SECOND_CLASS]:
        bars = prices(t)
        c = close_on(t, day)
        cap = (Q.get(t) or {}).get("cap")
        if not c or c[0]["date"] != day or not cap or not bars:
            continue
        last = bars[-1]["close"]
        out.append({"t": t, "name": UMAP[t]["name"], "sector": UMAP[t]["sector"], "v": (c[0]["close"] / c[1]["close"] - 1) * 100,
                    "cap": cap * c[0]["close"] / last, "cap_prev": cap * c[1]["close"] / last})
    return out


def last_trading_day(day: str | None = None) -> str:
    bars = [b for b in prices("AAPL") if not day or b["date"] <= day]
    return bars[-1]["date"]


def day_label(day: str) -> str:
    d = dt.date.fromisoformat(day)
    return f"{WD[d.weekday()]} {d.day} {MON[d.month - 1]}"


def treemap_html(day: str, title: str | None = None, subtitle: str | None = None, n: int = 220) -> str:
    mv = sorted(day_moves(day), key=lambda m: -m["cap"])[:n]
    groups = defaultdict(list)
    for m in mv:
        groups[m["sector"]].append({"t": m["t"], "name": m["name"], "v": m["v"], "w": m["cap"]})
    allm = day_moves(day)
    up = sum(1 for m in allm if m["v"] > 0)
    return C.treemap_chart([{"name": k, "items": v} for k, v in groups.items()],
                           title or f"{up} of {len(allm)} S&P 500 stocks rose on {day_label(day)}",
                           subtitle or f"The {len(mv)} biggest S&P 500 companies, sized by market value, coloured by the day's move",
                           "Source: Nasdaq daily closes; market values from CNBC")


def contrib_html(day: str, n: int = 10, title: str | None = None, subtitle: str | None = None, size: str = "full") -> str:
    mv = day_moves(day)
    tot = sum(m["cap_prev"] for m in mv) or 1
    for m in mv:
        m["c"] = m["cap_prev"] / tot * m["v"]
    est = sum(m["c"] for m in mv)
    neg = sorted([m for m in mv if m["c"] < 0], key=lambda m: m["c"])
    pos = sorted([m for m in mv if m["c"] > 0], key=lambda m: -m["c"])
    k_pos = min(len(pos), max(2, n // 3)) if est < 0 else min(len(pos), n - max(2, n // 3))
    pick = (neg[:n - k_pos] + pos[:k_pos]) if est < 0 else (pos[:k_pos] + neg[:n - k_pos])
    pick.sort(key=lambda m: m["c"])
    spec = {"labels": [m["t"] for m in pick], "values": [round(m["c"], 3) for m in pick], "unit": " pts"}
    inner = C.both(lambda k, W, H, fs: C.hbars_svg(k, W, H, fs, spec["labels"], spec["values"], spec["unit"]), size)
    big = pick[0] if est < 0 else pick[-1]
    return C.figure(inner, title or f"{UMAP[big['t']]['name']} did the most to move the S&P 500 on {day_label(day)}",
                    subtitle or (f"Each stock's contribution to the S&P 500's move, in percentage points. "
                                 f"Together our estimate comes to {est:+.2f}%".replace("-", "−")),
                    "Mostly Markets estimate from Nasdaq closes and CNBC market values")


def compare_html(spec: dict, story_date: str) -> str:
    ts = [t for t in spec["tickers"] if t in UMAP and prices(t)]
    end = spec.get("end") or story_date
    rng = spec.get("range", "3m")
    last = dt.date.fromisoformat(last_trading_day(end))
    start = {"1w": last - dt.timedelta(days=7), "1m": last - dt.timedelta(days=31), "3m": last - dt.timedelta(days=92),
             "6m": last - dt.timedelta(days=183), "1y": last - dt.timedelta(days=366),
             "ytd": dt.date(last.year - 1, 12, 31)}.get(rng, last - dt.timedelta(days=92))
    dates = [b["date"] for b in prices(ts[0]) if start.isoformat() <= b["date"] <= last.isoformat()]
    series = []
    for t in ts:
        m = {b["date"]: b["close"] for b in prices(t)}
        base = next((m[d] for d in dates if d in m), None)
        vals, prev = [], None
        for d in dates:
            prev = m.get(d, prev)
            vals.append((prev / base - 1) * 100 if prev and base else None)
        series.append({"name": t, "values": vals})
    hl = spec.get("highlight")
    hi = ts.index(hl) if hl in ts else None
    return C.compare_chart(dates, series, spec["title"], spec.get("subtitle") or f"Change in share price since {C.human(dates[0])}, %",
                           highlight=hi)


def block_chart(spec_text: str, story: Story) -> str:
    try:
        spec = json.loads(spec_text)
    except json.JSONDecodeError:
        return ""
    k = spec.get("kind")
    try:
        if k == "price":
            t = spec["ticker"]
            name = UMAP.get(t, {}).get("name", t)
            return C.price_chart(prices(t), spec.get("range", "1y"), spec.get("end") or story.date, spec["title"],
                                 spec.get("subtitle") or f"{name}, daily close, $", spec.get("mark", "last"),
                                 notes=spec.get("notes"))
        if k == "compare":
            return compare_html(spec, story.date)
        if k == "moves":  # close-to-close moves over a period, computed from our prices
            a, b = spec["from"], spec.get("to") or story.date
            rows = []
            for t in spec["tickers"]:
                m = {x["date"]: x["close"] for x in prices(t)}
                da = max((d for d in m if d <= a), default=None)
                db = max((d for d in m if d <= b), default=None)
                if da and db and da < db:
                    rows.append((t, (m[db] / m[da] - 1) * 100))
            rows.sort(key=lambda r: r[1], reverse=not all(v < 0 for _, v in rows))
            lab = [UMAP[t]["name"].replace(", Inc.", "").replace(" Inc.", "") if spec.get("names") else t for t, _ in rows]
            return C.hbars_chart({"labels": lab, "values": [round(v, 2) for _, v in rows], "unit": "%", "title": spec["title"],
                                  "subtitle": spec.get("subtitle") or f"Share price change, {C.human(a)} close to {C.human(b)} close, %",
                                  "source": "Source: Nasdaq daily closes", "highlight": spec.get("highlight")})
        if k == "treemap":
            return treemap_html(spec.get("date") or last_trading_day(story.date), spec.get("title"), spec.get("subtitle"))
        if k == "contrib":
            return contrib_html(spec.get("date") or last_trading_day(story.date), spec.get("n", 10), spec.get("title"),
                                spec.get("subtitle"))
        if k == "bars":
            return C.bars_chart(spec)
        if k == "hbars":
            return C.hbars_chart(spec)
        if k == "line":
            return C.line_chart(spec)
    except Exception as e:  # noqa: BLE001
        print(f"  chart failed in {story.slug}: {e}")
    return ""


def block_stat(text: str, story: Story) -> str:
    """Big numbers. A value can be written out, or computed from our prices: {"ticker", "metric": day|week|month|ytd, "date"}."""
    try:
        spec = json.loads(text)
    except json.JSONDecodeError:
        return ""
    items = []
    for it in (spec if isinstance(spec, list) else [spec]):
        t = it.get("ticker") if it.get("ticker") in UMAP else None
        val, tone_ = it.get("value"), it.get("tone", "")
        if not val and t:
            day = last_trading_day(it.get("date") or story.date)
            v = {"day": lambda: (close_on(t, day)[0]["close"] / close_on(t, day)[1]["close"] - 1) * 100,
                 "week": lambda: ret_since(t, 5, day), "month": lambda: ret_since(t, 21, day),
                 "ytd": lambda: ytd(t, day)}[it.get("metric", "day")]()
            val = f"{'+' if v >= 0 else '−'}{abs(v):.1f}%"
            tone_ = tone_ or ("up" if v >= 0 else "down")
        if not val:
            continue
        sp = ""
        if t and it.get("spark"):
            n = {"1w": 6, "1m": 22, "3m": 64, "6m": 127, "1y": 253}.get(it["spark"], 22)
            sp = C.spark([b["close"] for b in [b for b in prices(t) if b["date"] <= (it.get("date") or story.date)][-n:]], 120, 34)
        items.append({"value": str(val).replace("-", "−"), "label": it.get("label", ""), "note": it.get("note", ""),
                      "tone": tone_, "logo": logo(t, 34) if t else "", "spark": sp})
    return C.stat_cards(items) if items else ""


def block_picks(text: str, story: Story) -> str:
    cards = []
    for line in text.strip().splitlines():
        if ":" not in line:
            continue
        kind, names = line.split(":", 1)
        kind = kind.strip().lower()
        lab = {"love": "We love", "hate": "We hate", "like": "We like", "skip": "We'd skip"}.get(kind, kind.title())
        cls = "love" if kind in ("love", "like") else "hate"
        for t in [x.strip() for x in names.split(",") if x.strip() in UMAP]:
            c = close_on(t, story.date)
            r1 = ret_since(t, 252, story.date)
            price = c[0]["close"] if c else None
            cards.append(f'<a class="pk {cls}" href="{u(tpath(t))}">{logo(t, 44)}<span class="lab">{lab}</span>'
                         f'<span class="tt">{t}</span><span class="nm">{esc(UMAP[t]["name"])} · {esc(UMAP[t]["industry"])}</span>'
                         f'<span class="pr"><span>{money(price)}</span><span class="{tone(r1)}">{pct(r1, 1)} 1y</span></span></a>')
    return f'<div class="picks">{"".join(cards)}</div>'


def block_highlights(text: str, r: Renderer) -> str:
    lines = [x for x in text.strip().splitlines() if x.strip()]
    title = lines[0].lstrip("# ").strip() if lines and not lines[0].lstrip().startswith("-") else "Highlights"
    items = [x.strip()[2:] for x in lines if x.strip().startswith("- ")]

    def badge(x: str) -> str:
        m = re.search(r"(\d+(?:\.\d+)?)%\s+(beat|miss)\b", x)
        if m:
            return f'<span class="bdg {m.group(2)}">{"▲" if m.group(2) == "beat" else "▼"} {m.group(1)}% {m.group(2)}</span>'
        if re.search(r"\b(in line|matched|met) (with )?(analyst )?(estimates|expectations|consensus)", x):
            return '<span class="bdg inline">In line</span>'
        return "<span></span>"
    lis = "".join(f"<li><span>{r.inline(x)}</span>{badge(x)}</li>" for x in items)
    return f'<aside class="hlbox"><p class="ht">{esc(title)}</p><ul>{lis}</ul></aside>'


def tweet_card(url: str) -> str:
    """An X post, drawn at build time from the cache pipeline/news.py fills (data/news/tweets.json), linking to the
    original. No X script on our pages. Uncached posts show as a plain link card."""
    m = re.search(r"(?:x|twitter)\.com/([^/]+)/status/(\d+)", url.strip())
    if not m:
        return ""
    handle, tid = m.group(1), m.group(2)
    tw = TWEETS.get(tid) or {}
    link = f"https://x.com/{handle}/status/{tid}"
    if not tw.get("text"):
        return (f'<aside class="tw"><a class="tw-a" href="{esc(link)}" target="_blank" rel="noopener">'
                f'<span class="tw-x">𝕏</span><span>Post by <b>@{esc(handle)}</b> on X</span></a></aside>')
    av = f'<img src="{esc(tw["avatar"])}" alt="" loading="lazy">' if tw.get("avatar") else "<b></b>"
    when_ = ""
    try:
        d = dt.datetime.fromisoformat(tw["created_at"].replace("Z", "+00:00")).astimezone(ET)
        when_ = ago(d, "ago q")
    except Exception:  # noqa: BLE001
        pass
    text = esc(tw["text"]).replace("\n", "<br>")
    return (f'<aside class="tw"><div class="tw-h"><span class="tw-av">{av}</span><span class="tw-n"><b>{esc(tw.get("author") or handle)}</b>'
            f'<i>@{esc(tw.get("handle") or handle)}</i></span><span class="tw-x">𝕏</span></div><p>{text}</p>'
            f'<div class="tw-f">{when_}<a href="{esc(link)}" target="_blank" rel="noopener">View on X</a></div></aside>')


def render_body(s: Story) -> str:
    if s._rendered is None:
        r = Renderer(link_ticker=lambda t: u(tpath(t)) if t in UMAP else None, url=u, blocks={},
                     takes=s.type == "daily", page_url=absu(s.path))
        s.visuals = []

        def keep(h: str) -> str:  # remember the story's pictures in order: the first one leads the page
            if h:
                s.visuals.append(h)
            return h
        r.blocks = {"chart": lambda x: keep(block_chart(x, s)), "picks": lambda x: block_picks(x, s),
                    "highlights": lambda x: block_highlights(x, r), "stat": lambda x: keep(block_stat(x, s)),
                    "tweet": lambda x: tweet_card(x)}
        s._rendered = r.render(s.body)
        s.takes = r.takes
        s.headings = r.headings
    return s._rendered


def hero_visual(s: Story) -> tuple[str, str]:
    """The picture that opens a story: its own first chart (moved up from the body, so readers see the evidence
    before they scroll), or else the main stock's last three months, or that day's market map."""
    body = render_body(s)
    if s.visuals:
        v = s.visuals[0]
        i = body.find(v)
        return v, (body[:i] + body[i + len(v):] if i >= 0 else body)
    if s.tickers and prices(s.tickers[0]):
        t = s.tickers[0]
        name = UMAP[t]["name"]
        return C.price_chart(prices(t), "3m", s.date, f"{name}'s shares over the last three months",
                             f"{name}, daily close, $, to {C.human(last_trading_day(s.date))}", "last"), body
    return treemap_html(last_trading_day(s.date), n=160), body


def stockbar(s: Story) -> str:
    if not s.tickers:
        return ""
    rows = []
    mv = {m["t"]: m for m in s.moves}
    for t in s.tickers[:5]:
        m = mv.get(t)
        sess = {"after-hours": "after hours", "pre-market": "before the open", "regular": "intraday", "close": "at the close"}.get(
            (m or {}).get("s"), "")
        if m and m.get("c") is not None:
            # The move's own date: its asof, or for a close the last session on or before the story (a weekend
            # story about Friday says Friday).
            d = dt.date.fromisoformat(m.get("d") or (last_trading_day(s.date) if m.get("s") in ("close", "regular") else s.date))
            p = (f'<span class="{tone(m["c"])}">{"▲" if m["c"] >= 0 else "▼"} {abs(m["c"]):.2f}%</span> {money(m["p"])}'
                 f'<small>{sess}, {d.day} {MON[d.month - 1]}</small>')
        elif Q.get(t):
            q = Q[t]
            p = (f'<span data-live="{t}" data-k="price">{money(q["price"])}</span> '
                 f'<span data-live="{t}" data-k="chg" class="{tone(q.get("change_pct"))}">{pct(q.get("change_pct"))}</span><small>latest</small>')
        else:
            p = ""
        rows.append(f'<div class="sbr"><a href="{u(tpath(t))}">{logo(t, 40)}</a><a class="nm" href="{u(tpath(t))}"><b>{t}</b><span>{esc(UMAP[t]["name"])}</span></a>'
                    f'<div class="p">{p}</div>'
                    f'<button class="btn sm ghost" type="button" data-follow="{t}" aria-pressed="false">{ICON["plus"]}<span>Follow</span></button></div>')
    return f'<div class="stockbar">{"".join(rows)}</div>'


_MOVERS = None


def session_movers(n: int = 5, min_cap: float = 1e10) -> tuple[str, list[dict], list[dict]]:
    """The last session's biggest gainers and losers among companies worth $10bn+, close to close."""
    global _MOVERS
    if _MOVERS is None:
        day = last_trading_day()
        mv = [m for m in day_moves(day, list(UMAP)) if m["cap"] >= min_cap]
        _MOVERS = (day, sorted(mv, key=lambda m: -m["v"])[:n], sorted(mv, key=lambda m: m["v"])[:n])
    return _MOVERS


def mover_rows(ms: list[dict]) -> str:
    out = []
    for m in ms:
        st = next((x for x in BY_TICKER.get(m["t"], []) if (NOW.date() - x.pub.date()).days <= 3), None)
        href = u(st.path) if st else u(tpath(m["t"]))
        out.append(f'<a class="mr" href="{href}">{logo(m["t"], 28)}<span class="mr-n"><b>{m["t"]}</b><i>{esc(UMAP[m["t"]]["name"])}</i></span>'
                   f'<span class="pc {tone(m["v"])}"><i>{"▲" if m["v"] >= 0 else "▼"} {abs(m["v"]):.1f}%</i></span></a>')
    return "".join(out)


def rail_box(title: str, inner: str, more: tuple[str, str] | None = None, sub: str = "") -> str:
    link = f'<a class="rb-more" href="{more[0]}">{esc(more[1])}</a>' if more else ""
    return (f'<section class="rb"><div class="rb-h"><h4>{esc(title)}</h4>{link}</div>'
            f'{f"<p class=rb-sub>{sub}</p>" if sub else ""}{inner}</section>')


def rail_movers() -> str:
    day, ups, downs = session_movers()
    if not ups:
        return ""
    return rail_box("Biggest movers", f'<div class="mrs">{mover_rows(ups[:4])}<hr>{mover_rows(downs[:4])}</div>',
                    sub=f"{esc(day_label(day))}, close to close, companies worth $10 billion or more")


def rail_markets() -> str:
    rows = []
    for k, lab in STRIP:
        m = MKT["markets"].get(k) or {}
        if m.get("price") is None:
            continue
        p = m["price"]
        val = f"{p:.2f}%" if k == "US10Y" else (f"${p:,.2f}" if k in ("@CL.1", "@GC.1") else f"{p:,.0f}" if p > 1000 else f"{p:,.2f}")
        c = m.get("change_pct")
        chg = "" if k == "US10Y" else f'<span class="{tone(c)}" data-mk="{k}" data-k="chg">{"▲" if (c or 0) >= 0 else "▼"} {abs(c or 0):.2f}%</span>'
        rows.append(f'<div class="mk"><b>{lab}</b><span data-mk="{k}" data-k="px">{val}</span>{chg}</div>')
    asof = ""
    if MKT.get("asof"):
        a = dt.datetime.fromisoformat(MKT["asof"]).astimezone(ET)
        asof = f"Updated {ago(a, 'ago q')}"
    return rail_box("Markets", f'<div class="mks">{"".join(rows)}</div>', sub=asof)


def rail_latest(exclude=(), n: int = 6) -> str:
    st = [x for x in STORIES if x not in exclude][:n]
    return rail_box("Just published", f'<div class="minis">{"".join(mini(x, False) for x in st)}</div>', (u(""), "All stories"))


def rail_news(t: str | None, n: int = 6) -> str:
    items = news_items(t, n)
    if not items:
        return ""
    name = UMAP[t]["name"] if t else "the market"
    return rail_box(f"Latest on {name}" if t else "Market headlines", f'<ul class="nws">{"".join(news_row(i) for i in items)}</ul>',
                    (u(tpath(t)) + "#latest", "More") if t else None, "Headlines from around the web")


def story_page(s: Story) -> str:
    hero, body = hero_visual(s)
    sector = UMAP[s.tickers[0]]["sector"] if s.tickers else None
    crumbs = f'<span class="kick hl">{TYPE_LABEL[s.type]}</span>'
    if sector:
        crumbs += f'<a class="kick" href="{u("sectors/" + slugify(sector) + "/")}">{esc(sector)}</a>'
    more = []
    if s.tickers:
        t = s.tickers[0]
        others = [x for x in BY_TICKER[t] if x is not s][:4]
        if others:
            more.append(f'<section class="related"><h3>More on {esc(UMAP[t]["name"])}</h3><div class="cards-col">{"".join(row(x) for x in others)}</div></section>')
    latest = [x for x in STORIES if x is not s and x not in BY_TICKER.get(s.tickers[0] if s.tickers else "", [])][:5]
    more.append(f'<section class="related"><h3>Read next</h3><div class="cards-col">{"".join(row(x) for x in latest)}</div></section>')
    follow_t = s.tickers[0] if s.tickers else None
    endbox = (f'<div class="endbox"><div><h4>Follow {esc(UMAP[follow_t]["name"])}</h4><p>Its stories collect under My stocks on the front page. '
              f'For the daily email, subscribe to the newsletter.</p></div><div class="acts">'
              f'<button class="btn ghost" type="button" data-follow="{follow_t}" aria-pressed="false">{ICON["plus"]}<span>Follow</span></button>'
              f'<a class="btn" href="{CFG["subscribe"]}">Subscribe free</a></div></div>') if follow_t else (
        '<div class="endbox"><div><h4>Get the close in your inbox</h4><p>Every market day, the stories that moved stocks and why.</p></div>'
        f'<div class="acts"><a class="btn" href="{CFG["subscribe"]}">Subscribe free</a></div></div>')
    ld = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": s.title, "description": s.dek,
          "datePublished": s.pub.isoformat(), "author": {"@type": "Person", "name": s.author["name"]},
          "image": [absu("static/og.jpg")], "publisher": {"@type": "Organization", "name": CFG["name"]}}
    initials = "".join(w[0] for w in s.author["name"].split()[:2])
    rs = running_story(s)
    running = (f'<a class="running" href="{u(rs.path)}"><span>Part of the running story</span><b>{esc(rs.title)}</b></a>' if rs else "")
    t0 = s.tickers[0] if s.tickers else None
    rail = "".join(x for x in (
        f'<section class="rb">{stockbar(s)}</section>' if s.tickers else "",
        rail_news(t0, 5) if t0 else rail_news(None, 5),
        rail_movers(), rail_latest((s,), 5)) if x)
    html_ = f"""<div class="wrap art">
 <article class="story amain">
  <header class="story-head">
   <div class="crumbs">{crumbs}<span class="fresh-line"{fresh(s)}>{NEWB}Published {ago(s.pub, "ago b")}</span></div>
   <h1>{esc(s.title)}</h1>
   <p class="dek">{esc(s.dek)}</p>
   <div class="byl"><span class="av" aria-hidden="true">{esc(initials)}</span><a class="by" href="{u('authors/' + s.fm.get('author', '') + '/')}">{esc(s.author['name'])}</a><span class="sep">·</span><span>{esc(when(s.pub, True))}</span><span class="sep">·</span><span>{s.minutes} min read</span></div>
   {running}
  </header>
  <div class="hero-vis">{hero}</div>
  <div class="story-body">
   <div class="prose">{body}</div>
   {story_log(s) if s.type == "narrative" else ""}
   {endbox}
   <p class="disc">Mostly Markets is for information and education only and isn't investment advice. {esc(s.author['name'])} is a pen name. Prices are from Nasdaq and CNBC as of the time stated.</p>
  </div>
 </article>
 <aside class="arail" aria-label="Around the market">{rail}</aside>
 <div class="amore">{''.join(more)}</div>
</div>
<script type="application/ld+json">{json.dumps(ld)}</script>"""
    return page(s.path, s.title, html_, s.dek, None, og_type="article")


# ---------------------------------------------------------------------- the daily edition

def long_date(d: dt.date) -> str:
    return f"{WD[d.weekday()]}, {d.day} {MONTH[d.month - 1]} {d.year}"


def strip_tags(h: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h))).strip()


def take_parts(tk: dict) -> tuple[str, str]:
    """A take's first visual (chart, market map or big numbers) and its first paragraph as plain text."""
    vis, text = "", ""
    for blk in tk.get("body", []):
        if not vis and (blk.startswith("<figure") or blk.startswith('<div class="hov"') or blk.startswith('<div class="bigstats')):
            vis = blk
        elif not text and blk.startswith("<p>"):
            text = strip_tags(blk)
    return vis, text


def clip(t: str, n: int) -> str:
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def edition_label(s: Story) -> str:
    return "Weekend edition" if s.fm.get("edition") == "weekend" else ("Monday edition" if s.pub.weekday() == 0 else "Morning edition")


def edition_card(s: Story, size: int = 800) -> str:
    """The Daily's archive row: date, edition, headline, the first takes, and a picture of that session's market."""
    render_body(s)
    lis = "".join(f'<li><b>{tk["n"]}</b>{esc(tk["title"])}</li>' for tk in s.takes[:3])
    return (f'<article class="ed-card"{fresh(s)}><a class="cover-link" href="{u(s.path)}" aria-label="{esc(s.title)}"></a>'
            f'<div class="tx"><span class="ed-k">{NEWB}<b>{esc(long_date(s.pub.date()))}</b> · {edition_label(s)} · No. {s.edition}</span>'
            f'<h3>{esc(s.title)}</h3><p>{esc(s.dek)}</p>{f"<ol class=tks>{lis}</ol>" if lis else ""}'
            f'<span class="ed-m">{len(s.takes)} takes · {s.minutes} min read</span></div>'
            f'<div class="th tmap-th">{thumb_map(last_trading_day(s.date))}</div></article>')


def daily_page(s: Story) -> str:
    body = render_body(s)
    d = s.pub.date()
    toc = "".join(f'<a href="#{sid}">{esc(t)}</a>' for lv, sid, t in s.headings if lv == 2)
    others = [x for x in DAILIES if x is not s][:3]
    more = ""
    if others:
        more = f'<section class="related"><h3>More editions</h3><div class="ed-grid">{"".join(edition_card(x, 480) for x in others)}</div></section>'
    latest = [x for x in STORIES if x.type != "daily"][:5]
    more += f'<section class="related"><h3>Latest stories</h3><div class="cards-col">{"".join(row(x) for x in latest)}</div></section>'
    initials = "".join(w[0] for w in s.author["name"].split()[:2])
    ld = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": s.title, "description": s.dek,
          "datePublished": s.pub.isoformat(), "author": {"@type": "Person", "name": s.author["name"]},
          "image": [absu("static/og.jpg")], "publisher": {"@type": "Organization", "name": CFG["name"]}}
    play = (f'<button class="btn sm play" type="button" data-story-open="ed-{s.date}">{ICON["play"]}<span>Swipe through it</span></button>'
            if s.takes else "")
    html_ = f"""<article class="daily">
 <header class="ed-head wrap">
  <div class="ed-mast"><a href="{u('daily/')}" class="ed-name">Mostly Markets <b>Daily</b></a><span>{edition_label(s)} · {esc(long_date(d))}</span><span class="ed-no">No. {s.edition}</span></div>
  <div class="crumbs" style="margin-top:14px"><span class="fresh-line"{fresh(s)}>{NEWB}Published {ago(s.pub, "ago b")}</span></div>
  <h1>{esc(s.title)}</h1>
  <p class="dek">{esc(s.dek)}</p>
  <div class="byl"><span class="av" aria-hidden="true">{esc(initials)}</span><a class="by" href="{u('authors/' + s.fm.get('author', '') + '/')}">{esc(s.author['name'])}</a><span class="sep">·</span><span>{s.minutes} min read</span><span class="sep">·</span><span>{len(s.takes)} takes</span>{play}</div>
 </header>
 {f'<nav class="ed-toc wrap" aria-label="In this edition"><span>In this edition</span>{toc}</nav>' if toc else ''}
 <div class="story-body">
  <div class="prose daily-prose">{body}</div>
  <div class="endbox"><div><h4>Get The Daily in your inbox</h4><p>The story behind the market every morning, in charts. Free.</p></div><div class="acts"><a class="btn" href="{CFG["subscribe"]}">Subscribe free</a></div></div>
  <p class="disc">Mostly Markets is for information and education only and isn't investment advice. {esc(s.author['name'])} is a pen name. Prices are from Nasdaq and CNBC as of the time stated.</p>
  {more}
 </div>
</article>
{story_templates([edition_group(s)])}
<script type="application/ld+json">{json.dumps(ld)}</script>"""
    return page(s.path, s.title, html_, s.dek, None, og_type="article", active="daily/")


def daily_index():
    """Every edition we've published, newest first: the latest one opened up with its first take's chart, then the
    archive by month."""
    if not DAILIES:
        body = f'<div class="wrap ph"><h1>The Daily</h1><p>The first edition is on its way.</p></div>'
    else:
        first, rest = DAILIES[0], DAILIES[1:]
        render_body(first)
        vis = take_parts(first.takes[0])[0] if first.takes else ""
        lis = "".join(f'<li><a href="{u(first.path)}#{tk["id"]}"><b>{tk["n"]}</b>{esc(tk["title"])}</a></li>' for tk in first.takes)
        months, arch = None, []
        for x in rest:
            mk = f"{MONTH[x.pub.month - 1]} {x.pub.year}"
            if mk != months:
                arch.append(f'<h2 class="arch-m">{mk}</h2>')
                months = mk
            arch.append(edition_card(x))
        body = f"""<div class="wrap ph ed-ph"><span class="ed-name big">Mostly Markets <b>Daily</b></span>
<p>Every day's edition: the one story behind the market, a thread of sharp takes, and the charts that prove them.</p></div>
<section class="wrap"><article class="ed-today"{fresh(first)}><div class="ed-t-tx"><span class="ed-k">{NEWB}<b>{esc(long_date(first.pub.date()))}</b> · {edition_label(first)} · No. {first.edition} · {ago(first.pub, "ago q")}</span>
<h2><a href="{u(first.path)}">{esc(first.title)}</a></h2><p class="dek">{esc(first.dek)}</p>
<ol class="tks">{lis}</ol><div class="acts"><a class="btn" href="{u(first.path)}">Read today's edition</a>
<button class="btn ghost" type="button" data-story-open="ed-{first.date}">{ICON["play"]}<span>Swipe through</span></button></div></div>
<div class="ed-t-vis">{vis}</div></article>
{f'<div class="arch">{"".join(arch)}</div>' if arch else ''}</section>
{story_templates([edition_group(first)])}"""
    write("daily/", page("daily/", "The Daily", body, "Every day's edition of Mostly Markets Daily: the story behind the market, in charts.", active="daily/"))


# ---------------------------------------------------------------------- stories (tap-through slides)

def slide(kind: str, inner: str, bg: str = "", href: str = "") -> str:
    style = f' style="--img:url({bg})"' if bg else ""
    link = f' data-href="{esc(href)}"' if href else ""
    return f'<section class="sl {kind}{" hasbg" if bg else ""}"{style}{link}>{inner}</section>'


def edition_group(s: Story) -> dict:
    render_body(s)
    slides = [slide("cover", f'<div class="sl-k">Mostly Markets Daily · No. {s.edition}</div><h2>{esc(s.title)}</h2>'
                             f'<p>{esc(s.dek)}</p><div class="sl-hint">Tap to start · {len(s.takes)} takes</div>',
                    "", u(s.path))]
    for tk in s.takes:
        vis, text = take_parts(tk)
        slides.append(slide("take", f'<div class="sl-n">{tk["n"]}<i>/{tk["total"]}</i></div><h3>{esc(tk["title"])}</h3>'
                                    f'<div class="sl-v">{vis}</div><p>{esc(clip(text, 210))}</p>'
                                    f'<a class="sl-cta" href="{u(s.path)}#{tk["id"]}">Read the take</a>', href=f'{u(s.path)}#{tk["id"]}'))
    slides.append(slide("end", f'<div class="sl-k">That was The Daily</div><h2>Get it in your inbox every morning</h2>'
                               f'<a class="sl-cta big" href="{CFG["subscribe"]}">Subscribe free</a>'
                               f'<a class="sl-cta ghost" href="{u(s.path)}">Read the full edition</a>'))
    return {"id": f"ed-{s.date}", "name": "The Daily", "when": day_title(s.pub.date()),
            "avatar": '<span class="av-ic tmi" aria-hidden="true"><i></i><i></i><i></i><i></i></span>', "slides": slides}


def movers_group(day: str) -> dict | None:
    mv = day_moves(day, list(UMAP))
    if len(mv) < 50:
        return None
    ups = sorted(mv, key=lambda m: -m["v"])[:6]
    downs = sorted(mv, key=lambda m: m["v"])[:6]

    def rows(ms):
        out = []
        for m in ms:
            st = next((x for x in BY_TICKER.get(m["t"], []) if x.date >= day), None)
            href = u(st.path) if st else u(tpath(m["t"]))
            out.append(f'<a class="mv" href="{href}">{logo(m["t"], 40)}<span class="nm"><b>{m["t"]}</b><i>{esc(m["name"])}</i></span>'
                       f'<span class="pc {tone(m["v"])}"><i>{"▲" if m["v"] >= 0 else "▼"} {abs(m["v"]):.1f}%</i></span></a>')
        return "".join(out)
    lab = day_label(day)
    sub = f'<p class="sl-sub">Of the {len(UMAP)} stocks we cover, close to close</p>'
    slides = [slide("list", f'<div class="sl-k">Biggest gainers · {lab}</div><h3>What went up</h3>{sub}<div class="mvs">{rows(ups)}</div>'),
              slide("list", f'<div class="sl-k">Biggest losers · {lab}</div><h3>What went down</h3>{sub}<div class="mvs">{rows(downs)}</div>'),
              slide("take", f'<div class="sl-k">Market map · {lab}</div><div class="sl-v">{treemap_html(day, n=120)}</div>'),
              slide("take", f'<div class="sl-k">Who moved the index · {lab}</div><div class="sl-v">{contrib_html(day, 8)}</div>')]
    return {"id": f"mv-{day}", "name": "Movers", "when": lab,
            "avatar": '<span class="av-ic tmi" aria-hidden="true"><i></i><i></i><i></i><i></i></span>', "slides": slides}


def hl_lines(st: Story, n: int = 3) -> list[str]:
    m = re.search(r"```highlights\n(.*?)```", st.body, re.S)
    if not m:
        return []
    return [re.sub(r"\*\*|\$(?=[A-Z])", "", x.strip()[2:]) for x in m.group(1).splitlines() if x.strip().startswith("- ")][:n]


def earnings_group() -> dict | None:
    recs = [x for x in STORIES if x.type == "earnings-recap"]
    if not recs:
        return None
    newest = recs[0].pub.date()
    recs = [x for x in recs if (newest - x.pub.date()).days <= 1][:8]
    slides = []
    for st in recs:
        lis = "".join(f"<li>{esc(clip(x, 120))}</li>" for x in hl_lines(st))
        slides.append(slide("story", f'<div class="sl-img">{cover_img(st.cover, 800, lazy=True, alt=False)}</div>'
                                     f'<div class="sl-b"><div class="sl-row">{logo(st.tickers[0] if st.tickers else None, 36)}{chips(st, 2)}</div>'
                                     f'<h3>{esc(st.title)}</h3><ul class="sl-hl">{lis}</ul>'
                                     f'<a class="sl-cta" href="{u(st.path)}">Read the story</a></div>', href=u(st.path)))
    t0 = recs[0].tickers[0] if recs[0].tickers else None
    return {"id": f"er-{recs[0].date}-{len(recs)}", "name": "Earnings", "when": day_title(newest),
            "avatar": logo(t0, 64) if t0 else "", "slides": slides}


def charts_group() -> dict | None:
    cs = [x for x in STORIES if x.type == "chart"][:5]
    if not cs:
        return None
    slides = []
    for st in cs:
        figs = re.findall(r'(<div class="hov".*?</figure></div>|<figure class="chart.*?</figure>)', render_body(st), re.S)
        slides.append(slide("take", f'<div class="sl-k">Chart · {esc(day_title(st.pub.date()))}</div><h3>{esc(st.title)}</h3>'
                                    f'<div class="sl-v">{figs[0] if figs else ""}</div><a class="sl-cta" href="{u(st.path)}">Read it</a>',
                            href=u(st.path)))
    return {"id": f"ch-{cs[0].date}-{cs[0].slug[:12]}", "name": "Charts", "when": day_title(cs[0].pub.date()),
            "avatar": '<span class="av-ic chi" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 18l5-6 4 3 7-9"/></svg></span>',
            "slides": slides}


def picks_group() -> dict | None:
    ls = [x for x in STORIES if x.type == "list"]
    if not ls:
        return None
    st = ls[0]
    m = re.search(r"```picks\n(.*?)```", st.body, re.S)
    if not m:
        return None
    cards = block_picks(m.group(1), st)
    return {"id": f"pk-{st.date}-{st.slug[:12]}", "name": "Our picks", "when": day_title(st.pub.date()),
            "avatar": logo(st.tickers[0], 64) if st.tickers else "",
            "slides": [slide("story", f'<div class="sl-img">{cover_img(st.cover, 800, alt=False)}</div><div class="sl-b"><div class="sl-k">Our picks</div>'
                                      f'<h3>{esc(st.title)}</h3><p>{esc(clip(st.dek, 200))}</p><a class="sl-cta" href="{u(st.path)}">Read our reasons</a></div>', href=u(st.path)),
                       slide("list", f'<div class="sl-k">Our picks</div><h3>{esc(st.title)}</h3>{cards}', href=u(st.path))]}


def story_groups() -> list[dict]:
    gs = []
    if DAILIES:
        gs.append(edition_group(DAILIES[0]))
    for g in (movers_group(last_trading_day()), earnings_group(), charts_group(), picks_group()):
        if g and g["slides"]:
            gs.append(g)
    return gs


def story_templates(groups: list[dict]) -> str:
    out = []
    for g in groups:
        out.append(f'<template class="stg" data-id="{esc(g["id"])}" data-name="{esc(g["name"])}" data-when="{esc(g["when"])}">'
                   f'<div class="stg-av">{g["avatar"]}</div>{"".join(g["slides"])}</template>')
    return "".join(out)


def story_rail(groups: list[dict]) -> str:
    items = "".join(f'<button class="ring" type="button" data-story-open="{esc(g["id"])}"><span class="rg">{g["avatar"]}</span>'
                    f'<span class="rn">{esc(g["name"])}</span></button>' for g in groups)
    return f'<section class="rail wrap" aria-label="Stories"><div class="rail-in">{items}</div></section>{story_templates(groups)}'


# ---------------------------------------------------------------------- home / feed

def pick_lead(pool: list[Story], n_tops: int = 5) -> tuple[Story, list[Story]]:
    """The lead is the most important story of the last day and a half (age costs a point every three hours); the top
    stories under it are the next most important, one per company, shown newest first."""
    if not pool:
        return None, []
    recent = [s for s in pool if (pool[0].pub - s.pub) < dt.timedelta(hours=36)]
    feat = [s for s in recent if s.featured]

    def score(s):
        return s.weight() - (NOW - s.pub).total_seconds() / 3600 / 3
    lead = feat[0] if feat else max(recent, key=lambda s: (score(s), s.pub))
    rest = sorted([s for s in recent if s is not lead], key=lambda s: (score(s), s.pub), reverse=True)
    tops, seen_t = [], set(lead.tickers[:1])
    for s in rest:
        if s.type == "movers" or (s.tickers and s.tickers[0] in seen_t):
            continue
        tops.append(s)
        seen_t.update(s.tickers[:1])
        if len(tops) == n_tops:
            break
    if len(tops) < n_tops:
        tops += [s for s in pool if s is not lead and s not in tops][:n_tops - len(tops)]
    return lead, sorted(tops, key=lambda s: s.pub, reverse=True)


def tile(s: Story, size: int = 800) -> str:
    """A grid card (earnings and picks pages): the chart picture on top, then when, kind, headline, dek."""
    return (f'<article class="tile" data-type="{s.type}" data-tickers="{" ".join(s.tickers)}"{fresh(s)}><a class="cover-link" href="{u(s.path)}" aria-label="{esc(s.title)}"></a>'
            f'{thumb(s)}<div class="tx"><div class="c-top">{NEWB}{ago(s.pub)}<span class="tag">{TYPE_LABEL[s.type]}</span></div>'
            f'<h3>{esc(s.title)}</h3><p class="dk">{esc(s.dek)}</p><div class="c-ft">{chips(s, 2)}</div></div></article>')


def hsec(title: str, inner: str, more: tuple[str, str] | None = None, sub: str = "", cls: str = "") -> str:
    link = f'<a class="see" href="{u(more[0])}">{esc(more[1])}</a>' if more else ""
    return (f'<section class="wrap hsec{(" " + cls) if cls else ""}"><div class="hsec-h"><div><h2>{esc(title)}</h2>'
            f'{f"<p>{esc(sub)}</p>" if sub else ""}</div>{link}</div>{inner}</section>')


def lead_block(s: Story) -> str:
    """The feed's first screen: what just happened, how long ago, and the chart that proves it."""
    if s.type == "daily":
        render_body(s)
        vis = take_parts(s.takes[0])[0] if s.takes else ""
    else:
        vis = hero_visual(s)[0]
    by = f'<span>{esc(s.author["name"])}</span><span class="sep">·</span><span>{s.minutes} min read</span>'
    return (f'<article class="lead2"{fresh(s)}><div class="l-k">{NEWB}{ago(s.pub, "ago b")}<span class="tag">{TYPE_LABEL[s.type]}</span>'
            f'{logos(s.tickers, 26) if s.tickers else ""}</div>'
            f'<h1><a href="{u(s.path)}">{esc(s.title)}</a></h1><p class="dek">{esc(s.dek)}</p>'
            f'<div class="meta">{chips(s, 3)}{by}</div>'
            f'<div class="l-vis">{vis}</div><a class="l-go" href="{u(s.path)}">Read the full story <span aria-hidden="true">→</span></a></article>')


def rail_daily() -> str:
    if not DAILIES:
        return ""
    s = DAILIES[0]
    render_body(s)
    lis = "".join(f'<li><a href="{u(s.path)}#{tk["id"]}"><b>{tk["n"]}</b>{esc(tk["title"])}</a></li>' for tk in s.takes[:4])
    return rail_box("The Daily", f'<a class="rd-t" href="{u(s.path)}">{esc(s.title)}</a><ol class="tks sm">{lis}</ol>',
                    (u("daily/"), "Every edition"), f"{esc(long_date(s.pub.date()))} · {ago(s.pub, 'ago q')}")


def feed_rail() -> str:
    return "".join(x for x in (rail_markets(), rail_movers(), rail_daily(), rail_news(None, 6)) if x)


def home_pages():
    size = CFG["feed_page_size"]
    lead, tops = pick_lead(STORIES)
    skip = {id(lead)} | {id(x) for x in tops}
    feed = [s for s in STORIES if id(s) not in skip]
    pages = max(1, math.ceil(len(feed) / size))
    chips_html = "".join(f'<button class="chip" type="button" data-filter="{k}" aria-pressed="{"true" if k == "all" else "false"}">{esc(v)}</button>'
                         for k, v in FILTERS)
    for pi in range(pages):
        items = feed[pi * size:(pi + 1) * size]
        nav = []
        if pi > 0:
            nav.append(f'<a class="btn ghost" href="{u("" if pi == 1 else f"page/{pi}/")}">Newer stories</a>')
        if pi < pages - 1:
            nav.append(f'<a class="btn ghost" href="{u(f"page/{pi + 2}/")}">Older stories</a>')
        river = (f'<section class="river"><div class="rv-h"><h2>{"Latest" if pi == 0 else f"Latest, page {pi + 1}"}</h2>'
                 f'<span class="rv-up">Updated {ago(STORIES[0].pub, "ago q")}</span></div><div class="chips" role="group" aria-label="Filter stories">{chips_html}</div>'
                 f'<div class="feed cards-col">{mini_rows(items)}<p class="empty" hidden></p></div><div class="more">{"".join(nav)}</div></section>')
        main = []
        if pi == 0 and lead:
            main.append(lead_block(lead))
            main.append(f'<section class="tops2"><div class="rv-h"><h2>Top stories</h2><span class="rv-up">Newest first</span></div>'
                        f'<div class="minis">{"".join(mini(x) for x in tops)}</div></section>')
        main.append(river)
        body = (f'<div class="wrap fg"><div class="fmain">{"".join(main)}</div>'
                f'<aside class="frail" aria-label="Markets">{feed_rail()}{subscribe_box()}</aside></div>')
        path = "" if pi == 0 else f"page/{pi + 1}/"
        title = CFG["name"] + (": " + CFG["tagline"] if pi == 0 else f" | Latest stories, page {pi + 1}")
        write(path, page(path, title, body, CFG["tagline"] + " Why-it-moved stories, earnings, analysis and our picks.",
                         None, active=""))
    return pages


# ---------------------------------------------------------------------- stock pages

SECTOR_MED: dict[str, dict] = {}
SCORES: dict[str, dict] = {}
PCT: dict[str, dict] = {}  # each stock's percentile within its sector, per metric (0 = lowest, 1 = highest)
QUALITY_KEYS = ("revenue_growth_yoy_pct", "gross_margin_pct", "operating_margin_pct", "fcf_margin_pct")


def ttm(t):
    f = FUND.get(t) or {}
    return f.get("ttm") or {}


def median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def multiple(t):
    """The valuation multiple we rank on: forward P/E when there is one, else trailing P/E. None = no profits."""
    q = Q.get(t) or {}
    if (q.get("fpe") or 0) > 0:
        return "fpe", q["fpe"]
    if (q.get("pe") or 0) > 0:
        return "pe", q["pe"]
    return None, None


def compute_sector_medians():
    by = defaultdict(list)
    for x in UNIV:
        by[x["sector"]].append(x["ticker"])
    for sec, ts in by.items():
        SECTOR_MED[sec] = {k: median([ttm(t).get(k) for t in ts]) for k in QUALITY_KEYS + ("net_margin_pct",)}
        SECTOR_MED[sec]["pe"] = median([(Q.get(t) or {}).get("pe") for t in ts if ((Q.get(t) or {}).get("pe") or 0) > 0])
        SECTOR_MED[sec]["fpe"] = median([(Q.get(t) or {}).get("fpe") for t in ts if ((Q.get(t) or {}).get("fpe") or 0) > 0])
        SECTOR_MED[sec]["n"] = len(ts)

        def pctile(vals, v):  # share of the sector below v (ties count half), 0..1
            if len(vals) < 2:
                return 0.5
            below = sum(1 for x in vals if x < v)
            same = sum(1 for x in vals if x == v) - 1
            return (below + same / 2) / (len(vals) - 1)
        keys = QUALITY_KEYS + ("net_margin_pct",)
        cols = {k: [ttm(t)[k] for t in ts if ttm(t).get(k) is not None] for k in keys}
        mults = {kind: [(Q.get(t) or {}).get(kind) for t in ts if ((Q.get(t) or {}).get(kind) or 0) > 0] for kind in ("fpe", "pe")}
        for t in ts:
            PCT[t] = {k: pctile(cols[k], ttm(t)[k]) for k in keys if ttm(t).get(k) is not None and len(cols[k]) > 4}
            ps = [pctile(cols[k], ttm(t)[k]) for k in QUALITY_KEYS if ttm(t).get(k) is not None and len(cols[k]) > 4]
            if len(ps) < 2 and ttm(t).get("net_margin_pct") is not None and len(cols["net_margin_pct"]) > 4:
                ps.append(pctile(cols["net_margin_pct"], ttm(t)["net_margin_pct"]))  # banks and insurers report no gross/operating margin
            qs = (sum(ps) / len(ps) * 2 - 1) if len(ps) >= 2 else None
            kind, m = multiple(t)
            vs = (1 - 2 * pctile(mults[kind], m)) if kind and len(mults[kind]) > 4 else (-0.9 if kind is None else None)
            SCORES[t] = {"q": qs, "v": vs, "kind": kind, "mult": m}


def band(score):
    if score is None:
        return None
    return "good" if score >= 0.33 else "bad" if score <= -0.33 else "mid"


# ---------------------------------------------------------------------- ratings (descriptive, never buy/sell)

RATING_ICON = {
    "quality": '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M6 3h4v10H6zM1 8h4v5H1zm10-2h4v7h-4z"/></svg>',
    "price": '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M8.6 1.5H14v5.4l-7.2 7.2a1 1 0 0 1-1.4 0L1.9 10.6a1 1 0 0 1 0-1.4zM11.5 5.6a1.1 1.1 0 1 0 0-2.2 1.1 1.1 0 0 0 0 2.2z"/></svg>',
    "growth": '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12l4-4 3 3 5-6M10 5h4v4"/></svg>',
    "cash": '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><circle cx="8" cy="8" r="6.5"/><path d="M8.6 4.5v.8c.9.2 1.5.8 1.6 1.6H9c-.1-.4-.4-.6-1-.6-.6 0-.9.2-.9.6 0 .3.3.5 1.1.7 1.3.3 2 .8 2 1.8 0 .9-.7 1.5-1.6 1.7v.8H7.4v-.8c-1-.2-1.7-.9-1.7-1.8h1.2c.1.5.5.8 1.1.8.6 0 1-.3 1-.7 0-.3-.3-.5-1.1-.7-1.2-.3-1.9-.8-1.9-1.8 0-.8.6-1.4 1.6-1.6v-.8z" fill="#fff"/></svg>',
}


def ratings(t: str) -> list[tuple[str, str, str]]:
    """(css tone, icon, label) tags for a stock, from its sector-relative scores. Descriptive only."""
    sc = SCORES.get(t) or {}
    out = []
    qb, vb = band(sc.get("q")), band(sc.get("v"))
    if qb == "good":
        out.append(("good", "quality", "High quality"))
    elif qb == "mid":
        out.append(("mid", "quality", "Solid business"))
    if sc.get("kind") is None and sc.get("v") is not None:
        out.append(("bad", "price", "No profits yet"))
    elif vb == "good":
        out.append(("good-2", "price", "Cheaper than peers"))
    elif vb == "bad":
        out.append(("bad", "price", "Pricier than peers"))
    return out


def rating_chips(t: str, extra: list | None = None, limit: int = 2) -> str:
    tags = (extra or []) + ratings(t)
    return "".join(f'<span class="rt {tone_}">{RATING_ICON[ic]}{esc(lab)}</span>' for tone_, ic, lab in tags[:limit])


SECTOR_NOUN = {"Information Technology": "tech", "Health Care": "health-care", "Financials": "financial",
               "Consumer Discretionary": "consumer", "Communication Services": "media and telecom", "Industrials": "industrial",
               "Consumer Staples": "consumer-staples", "Energy": "energy", "Utilities": "utility", "Real Estate": "real-estate",
               "Materials": "materials"}


def rank_words(p: float) -> str:
    return "almost all" if p >= 0.9 else "most"


def than(p: float | None, text: str) -> str:
    """A comparison clause, only when it's true of most peers."""
    return f", {text.format(rank_words(p))}" if p is not None and p >= 0.7 else ""


def why_line(t: str, focus: str = "quality") -> str:
    """One or two plain sentences on why a stock stands out, with at most two numbers."""
    m, pc = ttm(t), PCT.get(t, {})
    noun = SECTOR_NOUN.get(UMAP[t]["sector"], "")
    parts = {}
    g = m.get("revenue_growth_yoy_pct")
    if g is not None and pc.get("revenue_growth_yoy_pct") is not None:
        parts["growth"] = (pc["revenue_growth_yoy_pct"], f"Sales grew {g:.0f}% over the past year{than(pc['revenue_growth_yoy_pct'], 'faster than {} ' + noun + ' companies we cover')}.")
    f = m.get("fcf_margin_pct")
    if f is not None and f > 0 and pc.get("fcf_margin_pct") is not None:
        parts["cash"] = (pc["fcf_margin_pct"], f"It turns {f:.0f} cents of every sales dollar into free cash.")
    o = m.get("operating_margin_pct")
    if o is not None and o > 0 and pc.get("operating_margin_pct") is not None:
        parts["margin"] = (pc["operating_margin_pct"], f"It keeps {o:.0f} cents of each sales dollar as operating profit{than(pc['operating_margin_pct'], 'more than {} peers')}.")
    gm = m.get("gross_margin_pct")
    if gm is not None and gm > 0 and pc.get("gross_margin_pct") is not None:
        parts["gross"] = (pc["gross_margin_pct"] - 0.05, f"It keeps {gm:.0f} cents of each sales dollar after the cost of what it sells.")
    n = m.get("net_margin_pct")
    if n is not None and n > 0 and pc.get("net_margin_pct") is not None and "margin" not in parts:
        parts["net"] = (pc["net_margin_pct"] - 0.02, f"It keeps {n:.0f}% of its revenue as profit{than(pc['net_margin_pct'], 'more than {} peers')}.")
    sc = SCORES.get(t) or {}
    med = SECTOR_MED.get(UMAP[t]["sector"], {}).get(sc.get("kind") or "")
    if sc.get("mult") and med and sc["mult"] < med:
        basis = "next year's" if sc["kind"] == "fpe" else "the past year's"
        parts["value"] = (1 - sc["mult"] / med / 2, f"At {sc['mult']:.0f} times {basis} earnings, it costs less than the {noun} median of {med:.0f} times.")
    first = {"growth": "growth", "cash": "cash", "value": "value"}.get(focus)
    order = sorted(parts, key=lambda k: -parts[k][0])
    if first in parts:
        order = [first] + [k for k in order if k != first]
    a, b = [parts[k][1] for k in order[:2]] + [""] * (2 - len(order[:2]))
    if b.startswith("It ") and a.startswith("It "):
        b = "It also " + b[3:]
    return (a + " " + b).strip()


def qlabel(q) -> str:
    lab = q.get("label") or ""
    m = re.match(r"(Q\d) FY(\d\d)", lab)
    return f"{m.group(1)} ’{m.group(2)}" if m else lab


def unit_for(vals):
    mx = max([abs(v) for v in vals if v is not None] or [0])
    return ("$bn", 1e9) if mx >= 1e9 else ("$m", 1e6)


def pe_history(t):
    """Daily close over the trailing-12-month diluted EPS known on that day (from each quarter's filing date)."""
    qs = [q for q in (FUND.get(t) or {}).get("quarters", []) if q.get("eps_diluted") is not None and q.get("filed")]
    known = []
    for i in range(3, len(qs)):
        win = qs[i - 3:i + 1]
        known.append((win[-1]["filed"], sum(q["eps_diluted"] for q in win)))
    if len(known) < 3:
        return None
    dates, pes = [], []
    k = 0
    for bar in prices(t):
        while k + 1 < len(known) and known[k + 1][0] <= bar["date"]:
            k += 1
        if bar["date"] < known[0][0]:
            continue
        eps = known[k][1]
        if eps <= 0:
            return None
        dates.append(bar["date"])
        pes.append(round(bar["close"] / eps, 2))
    if len(dates) < 120:
        return None
    step = 3
    idx = list(range(0, len(dates), step))
    if idx[-1] != len(dates) - 1:
        idx.append(len(dates) - 1)
    return [dates[i] for i in idx], [pes[i] for i in idx]


def peers_of(t, n=7):
    x = UMAP[t]
    peers = [p["ticker"] for p in UNIV if p["industry"] == x["industry"] and p["ticker"] != t]
    if len(peers) < 4:
        peers += [p["ticker"] for p in UNIV if p["sector"] == x["sector"] and p["ticker"] != t and p["ticker"] not in peers]
    peers = [p for p in peers if p not in ("GOOG", "FOX", "NWS")]
    peers.sort(key=lambda p: -((Q.get(p) or {}).get("cap") or 0))
    return peers[:n]


def valuation_section(t: str) -> str:
    x = UMAP[t]
    name, sec = x["name"], x["sector"]
    sc = SCORES.get(t) or {}
    med = SECTOR_MED.get(sec, {})
    qb, vb = band(sc.get("q")), band(sc.get("v"))
    if qb is None and vb is None:
        return ""
    secl = sec.lower()
    chips_ = []
    if qb:
        chips_.append(f'<span class="vchip {qb}"><i></i>Business quality: {"stronger than most" if qb == "good" else "weaker than most" if qb == "bad" else "about average"}</span>')
    if sc.get("kind") is None:
        chips_.append('<span class="vchip bad"><i></i>Valuation: no profits to value</span>')
    elif vb:
        chips_.append(f'<span class="vchip {vb}"><i></i>Valuation: {"cheaper than most" if vb == "good" else "pricier than most" if vb == "bad" else "in line with its sector"}</span>')
    qpart = ({"good": "A stronger business than most", "mid": "An average business among", "bad": "A weaker business than most"}[qb]
             + f" {secl} companies") if qb else f"Next to other {secl} companies, it is"
    vpart = ("with no profits yet to value" if sc.get("kind") is None else
             {"good": "priced below most of them", "mid": "priced about in line with them", "bad": "priced above most of them",
              None: "with too few peers to rank its price"}[vb])
    kind, m = sc.get("kind"), sc.get("mult")
    medm = med.get(kind) if kind else None
    what = "the next 12 months of expected earnings" if kind == "fpe" else "its last 12 months of earnings"
    para = (f"{esc(name)} trades at {m:.1f} times {what}, against a median of {medm:.1f}x for the {med.get('n', 0)} {esc(secl)} stocks we cover. "
            if kind and medm else f"{esc(name)} has no positive earnings to put a price-to-earnings multiple on. ")
    if qb:
        para += ("The quality score blends where it ranks on revenue growth, gross margin, operating margin and free-cash-flow margin "
                 "(net margin for banks and insurers) over the last 12 months, from SEC filings.")
    # facts vs the sector median
    tt = ttm(t)
    words = {"revenue_growth_yoy_pct": ("Revenue grew faster than the sector median", "Revenue grew slower than the sector median", True),
             "gross_margin_pct": ("Keeps more of each sale (gross margin)", "Keeps less of each sale (gross margin)", False),
             "operating_margin_pct": ("More profitable (operating margin)", "Less profitable (operating margin)", False),
             "fcf_margin_pct": ("Turns more of its sales into cash", "Turns less of its sales into cash", False),
             "net_margin_pct": ("Keeps more of its revenue as profit (net margin)", "Keeps less of its revenue as profit (net margin)", False)}
    facts = []
    for k, (gw, bw, sign) in words.items():
        if k == "net_margin_pct" and tt.get("operating_margin_pct") is not None:
            continue
        v, mm = tt.get(k), med.get(k)
        if v is None or mm is None:
            continue
        good = v > mm
        facts.append(f'<li class="{"g" if good else "b"}">{gw if good else bw}: {pct(v, 1, sign=sign)} vs {pct(mm, 1, sign=sign)}</li>')
    # quadrant against industry peers
    pts = []
    for p in [t] + peers_of(t):
        ps = SCORES.get(p) or {}
        if ps.get("q") is None or ps.get("v") is None:
            continue
        pk, pm = ps.get("kind"), ps.get("mult")
        mtxt = f"{pm:.1f}x {'fwd P/E' if pk == 'fpe' else 'P/E'}" if pk else "no profits"
        g = ttm(p).get("revenue_growth_yoy_pct")
        om = ttm(p).get("operating_margin_pct")
        tip = f"{p}: {mtxt}" + (f", growth {pct(g, 0)}" if g is not None else "") + (f", op. margin {pct(om, 0, sign=False)}" if om is not None else "")
        pts.append({"t": p, "x": ps["v"], "y": ps["q"], "me": p == t, "url": u(tpath(p)), "logo": logo(p, 34), "tip": tip})
    quad = ""
    if len(pts) >= 3:
        hi = max((SCORES[p["t"]]["mult"] or 0) for p in pts)
        lo = min((SCORES[p["t"]]["mult"] or 1e9) for p in pts)
        quad = (C.quadrant(pts, f"Pricier · {hi:.0f}x", f"{lo:.0f}x · Cheaper") +
                f'<p class="qlegend">{esc(name)} and {len(pts) - 1} {esc(x["industry"].lower())} peers. Across: valuation (P/E) against '
                f'the sector. Up: business quality against the sector. Hover or tap a logo for its numbers.</p>')
    # charts: multiple vs peers, P/E history
    charts = []
    if kind:
        rows = [(p, (SCORES.get(p) or {}).get("mult")) for p in [t] + peers_of(t) if (SCORES.get(p) or {}).get("kind") == kind]
        rows.sort(key=lambda r: r[1])
        if len(rows) >= 3:
            labels = [r[0] for r in rows]
            vals = [round(r[1], 1) for r in rows]
            lab = "forward P/E" if kind == "fpe" else "P/E"
            rel = "below" if medm and m < medm else "above"
            charts.append(C.hbars_chart({
                "title": f"{t} trades at {m:.1f}x {'forward ' if kind == 'fpe' else ''}earnings, {rel} the sector median" if medm else f"{t} on {lab} against its peers",
                "subtitle": f"{lab.capitalize()}, {x['industry']} peers", "labels": labels, "values": vals, "unit": "x",
                "highlight": labels.index(t), "median": medm, "median_label": f"Sector median {medm:.1f}x" if medm else "",
                "neutral": True, "size": "half", "source": "CNBC quotes; Mostly Markets"}))
    ph = pe_history(t)
    if ph:
        d, v = ph
        avg = sum(v) / len(v)
        now = v[-1]
        charts.append(C.pe_history_chart(
            d, v, f"At {now:.1f}x earnings, {t} is {'cheaper' if now < avg else 'pricier'} than its average since {C.human(d[0])[-8:]}",
            "Price over the last 12 months of reported (GAAP) diluted EPS", "Source: Nasdaq prices; SEC filings"))
    valcharts = f'<div class="valgrid">{"".join(charts)}</div>' if charts else ""
    return (f'<section id="quality"><h2 class="sh2">Quality and valuation</h2>'
            f'<p class="lede">How {esc(name)} compares with other {esc(secl)} stocks. A description, not a recommendation.</p>'
            f'<div class="verdict{"" if quad else " solo"}">{f"<div>{quad}</div>" if quad else ""}<div class="vtext"><div class="vchips">{"".join(chips_)}</div>'
            f'<h3>{qpart}, {vpart}.</h3><p>{para}</p><ul class="facts">{"".join(facts)}</ul></div></div>{valcharts}</section>')


def fund_section(t: str) -> str:
    f = FUND.get(t)
    if not f or not f.get("quarters"):
        return ""
    allq = [q for q in f["quarters"] if q.get("revenue") is not None]
    qs = allq[-8:]
    if len(qs) < 4:
        return ""
    name = UMAP[t]["name"]
    out = []
    labels = [qlabel(q) for q in qs]
    rev = [q["revenue"] for q in qs]
    unit, div = unit_for(rev)
    yoy = None
    if len(allq) >= 5 and allq[-5]["revenue"]:
        yoy = (allq[-1]["revenue"] / allq[-5]["revenue"] - 1) * 100
    rt = (f"Revenue {'grew' if yoy >= 0 else 'fell'} {abs(yoy):.1f}% from a year earlier" if yoy is not None
          else f"{name}'s quarterly revenue")
    out.append(C.bars_chart({"title": rt, "subtitle": f"Quarterly revenue, {unit}, latest {labels[-1]}",
                             "labels": labels, "values": [round(v / div, 2) for v in rev], "unit": unit,
                             "source": "SEC filings", "highlight": -1, "size": "half"}))
    growth = []
    for i, q in enumerate(allq):
        if i >= 4 and allq[i - 4]["revenue"]:
            growth.append((qlabel(q), (q["revenue"] / allq[i - 4]["revenue"] - 1) * 100))
    if len(growth) >= 4:
        g = growth[-8:]
        out.append(C.bars_chart({"title": f"Growth {'sped up' if g[-1][1] > g[-2][1] else 'slowed'} to {pct(g[-1][1], 1)} last quarter",
                                 "subtitle": "Revenue growth, year on year, %", "labels": [x[0] for x in g],
                                 "values": [round(x[1], 1) for x in g], "unit": "%", "tone": "sign", "highlight": -1,
                                 "source": "SEC filings", "size": "half"}))
    om = [(q["operating_income"] / q["revenue"] * 100) if q.get("operating_income") is not None and q["revenue"] else None for q in qs]
    if sum(1 for v in om if v is not None) >= 4 and om[-1] is not None:
        out.append(C.bars_chart({"title": f"Operating margin was {om[-1]:.1f}% last quarter",
                                 "subtitle": "Operating income as a share of revenue, %", "labels": labels,
                                 "values": [round(v, 1) if v is not None else None for v in om], "unit": "%",
                                 "tone": "sign" if any(v is not None and v < 0 for v in om) else "", "highlight": -1,
                                 "source": "SEC filings", "size": "half"}))
    fcf = [q.get("fcf") for q in qs]
    if sum(1 for v in fcf if v is not None) >= 4:
        u3, d3 = unit_for(fcf)
        tt = ttm(t)
        title = (f"Free cash flow was {big_money(tt.get('fcf'))} over 12 months" if tt.get("fcf") is not None
                 else "Free cash flow by quarter")
        out.append(C.bars_chart({"title": title, "subtitle": f"Quarterly free cash flow (operating cash flow minus capex), {u3}",
                                 "labels": labels, "values": [round(v / d3, 2) if v is not None else None for v in fcf],
                                 "unit": u3, "tone": "sign", "source": "SEC filings", "highlight": -1, "size": "half"}))
    eps = [q.get("eps_diluted") for q in qs]
    if sum(1 for v in eps if v is not None) >= 4 and len(out) < 4:
        out.append(C.bars_chart({"title": f"Diluted EPS was {money(eps[-1])} last quarter" if eps[-1] is not None else "Earnings per share",
                                 "subtitle": "Quarterly diluted earnings per share, $", "labels": labels,
                                 "values": eps, "unit": "$", "tone": "sign", "source": "SEC filings", "highlight": -1, "size": "half"}))
    sec = UMAP[t]["sector"]
    med = SECTOR_MED.get(sec, {})
    tt = ttm(t)
    q = Q.get(t) or {}
    rows = []

    def cmp_row(label, v, m, fmtf=lambda x: pct(x, 1, sign=False)):
        if v is None:
            return
        rows.append(f"<tr><td>{label}</td><td class='n me'>{fmtf(v)}</td><td class='n'>{fmtf(m) if m is not None else '–'}</td></tr>")
    cmp_row("Revenue growth", tt.get("revenue_growth_yoy_pct"), med.get("revenue_growth_yoy_pct"), fmtf=lambda x: pct(x, 1))
    cmp_row("Gross margin", tt.get("gross_margin_pct"), med.get("gross_margin_pct"))
    cmp_row("Operating margin", tt.get("operating_margin_pct"), med.get("operating_margin_pct"))
    cmp_row("Free cash flow margin", tt.get("fcf_margin_pct"), med.get("fcf_margin_pct"))
    if (q.get("pe") or 0) > 0:
        cmp_row("Price to earnings", q.get("pe"), med.get("pe"), fmtf=lambda x: f"{x:.1f}x")
    table = (f'<div class="tbl" style="margin-top:20px"><table class="cmp"><thead><tr><th>Last 12 months</th><th class="n">{t}</th><th class="n">Sector median</th></tr></thead>'
             f'<tbody>{"".join(rows)}</tbody></table></div>') if rows else ""
    upd = f.get("quarters", [{}])[-1].get("end", "")
    return (f'<section id="financials"><h2 class="sh2">Financials</h2><p class="lede">From {esc(name)}\'s SEC filings, through the quarter ending '
            f'{C.human(upd) if upd else "–"}. Hover or tap a bar for its value.</p>'
            f'<div class="fundgrid">{"".join(out[:4])}</div>{table}</section>')


def stock_page(t: str) -> str:
    x = UMAP[t]
    name = x["name"]
    bars = prices(t)
    q = Q.get(t) or {}
    price = q.get("price") or (bars[-1]["close"] if bars else None)
    chg = q.get("change_pct")
    if chg is None and len(bars) > 1:
        chg = (bars[-1]["close"] / bars[-2]["close"] - 1) * 100
    asof = ""
    if q.get("time"):
        qt = quote_time(q)
        asof = (f"At the close, {qt.day} {MON[qt.month - 1]}" if qt.time() >= dt.time(16, 0) else f"As of {when(qt)}") + " · Prices from CNBC, may be delayed"
    elif bars:
        asof = f"At the close, {C.human(bars[-1]['date'])}"
    ext = q.get("ext") or {}
    ext_html = (f'<span class="ext" data-live="{t}" data-k="ext">{"After hours" if ext.get("session") == "POST_MKT" else "Before the open"}: '
                f'<span>{money(ext.get("price"))} ({pct(ext.get("change_pct"))})</span></span>' if ext.get("price") else
                f'<span class="ext" data-live="{t}" data-k="ext" hidden></span>')
    rngs = [("1m", "1M"), ("6m", "6M"), ("ytd", "YTD"), ("1y", "1Y"), ("5y", "5Y")]
    panels = []
    for k, lab in rngs:
        ch = C.price_chart(bars, k, None, f"{name} over {C.RANGE_LABEL[k]}", f"Daily close, $, to {C.human(bars[-1]['date'])}" if bars else "",
                           "last", size="wide") if bars else ""
        panels.append(f'<div class="rng-panel" data-r="{k}"{"" if k == "1y" else " hidden"}>{ch}</div>')
    ranges = "".join(f'<button type="button" data-r="{k}" aria-pressed="{"true" if k == "1y" else "false"}">{lab}</button>' for k, lab in rngs)
    hi52 = max((b["close"] for b in bars[-252:]), default=None)
    lo52 = min((b["close"] for b in bars[-252:]), default=None)
    pos = ((price - lo52) / (hi52 - lo52) * 100) if price and hi52 and lo52 and hi52 > lo52 else None
    pos = max(0, min(100, pos)) if pos is not None else None
    ne = next_earnings(t)
    ne_s = "Not scheduled"
    if ne:
        d = dt.date.fromisoformat(ne[0])
        ne_s = f"{WD[d.weekday()][:3]} {d.day} {MON[d.month - 1]}" + {"bmo": ", before the open", "amc": ", after the close"}.get(ne[1]["time"], "")
    y = ytd(t)
    r1 = ret_since(t, 252)
    stats = [
        ("Market value", short_money(q.get("cap")) if q.get("cap") else "–"),
        ("Price to earnings", f"{q['pe']:.1f}x" if (q.get("pe") or 0) > 0 else "–"),
        ("Forward P/E", f"{q['fpe']:.1f}x" if (q.get("fpe") or 0) > 0 else "–"),
        ("Dividend yield", f"{q['dividend_yield']:.2f}%" if q.get("dividend_yield") else "–"),
        ("Year to date", f'<span class="{tone(y)}">{pct(y, 1)}</span>'),
        ("One year", f'<span class="{tone(r1)}">{pct(r1, 1)}</span>'),
        ("Next earnings", esc(ne_s)),
        ("Sector", f'<a href="{u("sectors/" + slugify(x["sector"]) + "/")}">{esc(x["sector"])}</a>'),
    ]
    stat_html = "".join(f'<div class="stat">{k}<b>{v}</b></div>' for k, v in stats)
    rangebar = (f'<div class="stat full">52-week range (closes)<div class="rangebar"><i style="left:calc({pos:.1f}% - 2px)"></i></div>'
                f'<div><span>{money(lo52)}</span><span>{money(hi52)}</span></div></div>') if pos is not None else ""
    st = BY_TICKER.get(t, [])
    ours = "".join(mini(x) for x in st[:6])
    heads = news_items(t, 12, since_days=21)
    latest_html = (f'<section id="latest"><h2 class="sh2">The latest on {esc(name)}</h2>'
                   f'<p class="lede">Our stories first, then the headlines that could move it, newest first.</p>'
                   + (f'<div class="minis">{ours}</div>' if ours else
                      f'<p class="empty" style="text-align:left;padding:14px 0">We haven\'t written about {esc(name)} yet. Follow it, and its first story will show under My stocks.</p>')
                   + (f'<h3 class="sh3">Headlines from around the web</h3><ul class="nws big">{"".join(news_row(i) for i in heads)}</ul>' if heads else "")
                   + (f'<details class="allst"><summary>All {len(st)} of our stories on {esc(name)}</summary>{mini_rows(st)}</details>' if len(st) > 6 else "")
                   + "</section>")
    prow = []
    for p in peers_of(t, 8):
        pq = Q.get(p) or {}
        py = ytd(p)
        prow.append(f'<tr><td class="nm"><a href="{u(tpath(p))}">{logo(p, 30)}<span class="t"><b>{p}</b><i>{esc(UMAP[p]["name"])}</i></span></a></td>'
                    f'<td class="n">{money(pq.get("price"))}</td><td class="n {tone(pq.get("change_pct"))}">{pct(pq.get("change_pct"))}</td>'
                    f'<td class="n hide-s {tone(py)}">{pct(py, 1)}</td><td class="n hide-m">{short_money(pq.get("cap"))}</td></tr>')
    peers_html = (f'<section id="peers"><h2 class="sh2">Similar companies</h2><p class="lede">{esc(x["industry"])}, by market value.</p>'
                  f'<table class="big" style="margin-top:16px"><thead><tr><th>Company</th><th class="n">Price</th><th class="n">Today</th><th class="n hide-s">YTD</th><th class="n hide-m">Value</th></tr></thead>'
                  f'<tbody>{"".join(prow)}</tbody></table></section>') if prow else ""
    val = valuation_section(t)
    fin = fund_section(t)
    nav = [("overview", "Overview"), ("latest", "Latest")] + ([("quality", "Quality & valuation")] if val else []) + (
        [("financials", "Financials")] if fin else []) + ([("peers", "Peers")] if prow else [])
    navh = "".join(f'<a href="#{k}"{" class=on" if i == 0 else ""}>{v}</a>' for i, (k, v) in enumerate(nav))
    body = f"""<div class="sp wrap">
 <div class="crumbs"><a class="kick" href="{u('stocks/')}">Stocks</a><span class="kick">/</span><a class="kick" href="{u('sectors/' + slugify(x['sector']) + '/')}">{esc(x['sector'])}</a><span class="kick hide-m">/</span><span class="kick hide-m">{esc(x['industry'])}</span></div>
 <div class="sp-hero">
  <div><div class="sp-id">{logo(t, 64)}<div><h1>{esc(name)}<small>{t}</small></h1>
   <div class="sect">{esc(x['industry'])}{(' · ' + esc(x['hq'])) if x.get('hq') else ''}{' · In the S&amp;P 500' if 'S&P 500' in x.get('index', []) else ''}</div>
   {f'<div class="rts">{rating_chips(t)}</div>' if ratings(t) else ''}</div></div>
   <div class="px"><b data-live="{t}" data-k="price">{money(price)}</b><span class="chg {tone(chg)}" data-live="{t}" data-k="chg">{pct(chg)}</span>{ext_html}<span class="asof">{esc(asof)}</span></div>
  </div>
  <div><button class="btn" type="button" data-follow="{t}" aria-pressed="false">{ICON['plus']}<span>Follow</span></button></div>
 </div>
</div>
<nav class="secnav" aria-label="Sections"><div class="wrap"><div class="in">{navh}</div></div></nav>
<div class="wrap"><div class="sp-grid">
 <div class="sp-main">
  <section id="overview"><div class="ranges" role="group" aria-label="Chart range">{ranges}</div><div class="pchart">{''.join(panels)}</div>
   <div class="stats show-t">{stat_html}{rangebar}</div></section>
  {latest_html}
  {val}
  {fin}
  {peers_html}
 </div>
 <aside class="side"><div class="stats hide-t">{stat_html}{rangebar}</div>
  {rail_movers()}
  {subscribe_box(title='Follow the market with us', text='The stories that moved stocks, every market day, free by email.')}</aside>
</div></div>"""
    desc = f"{name} ({t}) stock: price, chart, quality and valuation against peers, financials and the latest stories explaining why it moved."
    return page(tpath(t), f"{name} ({t}) Stock: Price, News and Analysis", body, desc, active="stocks/")


# ---------------------------------------------------------------------- discover, sectors, stocks index

def week_change(t):
    bars = prices(t)
    if not bars:
        return None
    last = dt.date.fromisoformat(bars[-1]["date"])
    monday = last - dt.timedelta(days=last.weekday())
    before = [b for b in bars if b["date"] < monday.isoformat()]
    return (bars[-1]["close"] / before[-1]["close"] - 1) * 100 if before else None


def stock_card(t: str, focus: str = "quality", extra: list | None = None, hidden: bool = False) -> str:
    """The Discover card: logo and rating tags, the name, the industry, and one plain line on why it stands out."""
    x = UMAP[t]
    return (f'<a class="sk{" more" if hidden else ""}" href="{u(tpath(t))}"><div class="sk-top">{logo(t, 44)}<span class="rts">{rating_chips(t, extra)}</span></div>'
            f'<h3>{esc(x["name"])}</h3><div class="sk-ind">{esc(x["industry"])}</div><p>{esc(why_line(t, focus))}</p></a>')


def discover_lists():
    """Discover's lists: quality first, then price, growth and cash. Each is (key, tab, title, intro, focus, extra tag, tickers)."""
    cap = lambda t: (Q.get(t) or {}).get("cap") or 0  # noqa: E731
    pool = [t for t in UMAP if t not in SECOND_CLASS and SCORES.get(t) and cap(t) > 5e9]
    q = lambda t: SCORES[t].get("q")  # noqa: E731
    v = lambda t: SCORES[t].get("v")  # noqa: E731
    hq = [t for t in pool if band(q(t)) == "good"]
    cheap = [t for t in pool if band(v(t)) == "good" and band(q(t)) in ("good", "mid") and SCORES[t].get("kind")]
    grow = [t for t in pool if (ttm(t).get("revenue_growth_yoy_pct") or 0) >= 20 and (ttm(t).get("revenue") or 0) > 1e9
            and band(q(t)) != "bad"]
    cash = [t for t in pool if (ttm(t).get("fcf_margin_pct") or 0) >= 25 and (ttm(t).get("revenue_growth_yoy_pct") or 0) > 3
            and (ttm(t).get("revenue") or 0) > 1e9]
    by_cap = lambda ts: sorted(ts, key=lambda t: -cap(t))  # noqa: E731
    return [
        ("", "High quality", "High-quality businesses",
         "Companies that grow faster and keep more of each sales dollar than most of their sector, from their SEC filings.",
         "quality", None, by_cap(hq)),
        ("cheaper/", "Cheaper than peers", "Good businesses at a lower price",
         "Solid or better businesses whose shares cost less than most of their sector's, measured by price to earnings.",
         "value", None, by_cap(cheap)),
        ("growers/", "Fast growers", "Fast growers",
         "Sales up 20% or more over the past year, at companies with more than $1 billion in revenue.",
         "growth", [("amber", "growth", "Fast grower")], by_cap(grow)),
        ("cash-machines/", "Cash machines", "Cash machines",
         "At least 25 cents of free cash from every sales dollar, with sales still growing.",
         "cash", [("teal", "cash", "Cash machine")], by_cap(cash)),
    ]


def discover_tabs(active: str) -> str:
    tabs = [(k, tab) for k, tab, *_ in discover_lists_cache()] + [("picks/", "Our picks")]
    return '<nav class="tabs" aria-label="Discover">' + "".join(
        f'<a href="{u("discover/" + k)}"{" aria-current=page" if k == active else ""}>{esc(tab)}</a>' for k, tab in tabs) + "</nav>"


_DL = None


def discover_lists_cache():
    global _DL
    if _DL is None:
        _DL = discover_lists()
    return _DL


def grouped_cards(ts: list[str], focus: str, extra, per: int = 3) -> str:
    by = defaultdict(list)
    for t in ts:
        by[UMAP[t]["sector"]].append(t)
    secs = []
    for sec in sorted(by, key=lambda k: -len(by[k])):
        items = by[sec]
        cards = "".join(stock_card(t, focus, extra, hidden=i >= per) for i, t in enumerate(items))
        more = (f'<button class="lnk" type="button" data-more>Show all {len(items)}</button>' if len(items) > per else "")
        secs.append(f'<section class="grp"><div class="grp-h"><h2>{esc(sec)}</h2>{more}</div><div class="sks">{cards}</div></section>')
    return "".join(secs)


def discover_pages():
    for key, tab, title, intro, focus, extra, ts in discover_lists_cache():
        body = (f'<div class="wrap"><div class="ph"><h1>Discover</h1><p>Find stocks worth a closer look. Ratings describe the business '
                f'and the price against its sector; they aren\'t advice to buy or sell.</p></div>{discover_tabs(key)}'
                f'<div class="lst-h"><h2>{esc(title)}</h2><p>{esc(intro)} <span class="cnt">{len(ts)} stocks</span></p></div>'
                f'{grouped_cards(ts, focus, extra)}</div>')
        path = "discover/" + key
        write(path, page(path, f"{title} | Discover", body, intro, active="discover/"))
    picks = [s for s in STORIES if s.type == "list"][:9]
    body = (f'<div class="wrap"><div class="ph"><h1>Discover</h1><p>Find stocks worth a closer look. Ratings describe the business '
            f'and the price against its sector; they aren\'t advice to buy or sell.</p></div>{discover_tabs("picks/")}'
            f'<div class="lst-h"><h2>Our picks</h2><p>Three stocks we\'d skip and one we like, or the reverse, one theme at a time, with the reasons in numbers.</p></div>'
            f'<div class="feed-wrap" style="margin:8px 0 0"><div class="cards-col">{"".join(row(s) for s in picks)}</div></div></div>')
    write("discover/picks/", page("discover/picks/", "Our picks | Discover", body, "Three stocks we'd skip and one we like, with the reasons in numbers.", active="discover/"))


def table_rows(ts):
    out = []
    for t in ts:
        x = UMAP[t]
        q = Q.get(t) or {}
        y = ytd(t)
        out.append(f'<tr><td class="nm"><a href="{u(tpath(t))}">{logo(t, 30)}<span class="t"><b>{t}</b><i>{esc(x["name"])}</i></span></a></td>'
                   f'<td class="hide-m">{esc(x["industry"])}</td><td class="n" data-v="{q.get("price") or ""}">{money(q.get("price"))}</td>'
                   f'<td class="n {tone(q.get("change_pct"))}" data-v="{q.get("change_pct") if q.get("change_pct") is not None else ""}">{pct(q.get("change_pct"))}</td>'
                   f'<td class="n hide-s {tone(y)}" data-v="{y if y is not None else ""}">{pct(y, 1)}</td>'
                   f'<td class="n hide-m" data-v="{q.get("cap") or 0}">{short_money(q.get("cap"))}</td></tr>')
    return "".join(out)


TABLE_HEAD = ('<thead><tr><th>Company</th><th class="hide-m">Industry</th><th class="n">Price</th><th class="n">Today</th>'
              '<th class="n hide-s">YTD</th><th class="n hide-m">Value</th></tr></thead>')


def sector_pages():
    by = defaultdict(list)
    for x in UNIV:
        by[x["sector"]].append(x["ticker"])
    for sec, ts in by.items():
        ts.sort(key=lambda t: -((Q.get(t) or {}).get("cap") or 0))
        st = [s for s in STORIES if s.tickers and UMAP[s.tickers[0]]["sector"] == sec][:8]
        stories = f'<section class="dsec"><div class="dsec-h"><div><h2>Latest stories</h2></div></div><div class="feed cards-col">{"".join(row(s) for s in st)}</div></section>' if st else ""
        med = SECTOR_MED.get(sec, {})
        meds = []
        if med.get("revenue_growth_yoy_pct") is not None:
            meds.append(f"median revenue growth {pct(med['revenue_growth_yoy_pct'], 1)}")
        if med.get("operating_margin_pct") is not None:
            meds.append(f"median operating margin {pct(med['operating_margin_pct'], 1, sign=False)}")
        body = (f'<div class="wrap"><div class="ph"><div class="crumbs"><a class="kick" href="{u("stocks/")}">Stocks</a></div><h1>{esc(sec)}</h1>'
                f'<p>{len(ts)} stocks we cover{(", with a " + " and a ".join(meds) + " over the last 12 months") if meds else ""}.</p></div>{stories}'
                f'<section class="dsec"><div class="dsec-h"><div><h2>All {esc(sec.lower())} stocks</h2><p>By market value. Tap a column to sort.</p></div></div>'
                f'<table class="big" data-sort style="margin-top:8px">{TABLE_HEAD}<tbody>{table_rows(ts)}</tbody></table></section></div>')
        write(f"sectors/{slugify(sec)}/", page(f"sectors/{slugify(sec)}/", f"{sec} Stocks", body, f"Every {sec.lower()} stock we cover, with prices, moves and stories.", active="stocks/"))


def stocks_index():
    ts = sorted(UMAP, key=lambda t: -((Q.get(t) or {}).get("cap") or 0))
    body = (f'<div class="wrap"><div class="ph"><h1>All stocks</h1><p>The {len(ts)} companies we cover: the S&amp;P 500 and the most-followed names outside it.</p></div>'
            f'<div class="filter"><input type="search" placeholder="Filter by name, ticker or industry" data-table-filter aria-label="Filter stocks"></div>'
            f'<table class="big" data-sort>{TABLE_HEAD}<tbody>{table_rows(ts)}</tbody></table></div>')
    write("stocks/", page("stocks/", "All Stocks", body, "Every stock Mostly Markets covers, with prices, moves and stories.", active="stocks/"))


# ---------------------------------------------------------------------- earnings

EARN_MIN_CAP = 2.5e10  # the calendar shows the companies people follow: $25bn+ (always at least the biggest few)


def earnings_days(days: list[dt.date], per_day: int = 8) -> str:
    """A week of reporters as logo tiles, biggest first. Reports already out carry a Recap tag when we wrote one."""
    today = NOW.date()
    cols = []
    for d in days:
        rows = [r for r in CAL.get(d.isoformat(), []) if r["ticker"] in UMAP and r["ticker"] not in SECOND_CLASS | {"BF.B"}]
        rows.sort(key=lambda r: -((Q.get(r["ticker"]) or {}).get("cap") or r.get("mktcap") or 0))
        big = [r for r in rows if ((Q.get(r["ticker"]) or {}).get("cap") or r.get("mktcap") or 0) >= EARN_MIN_CAP]
        rows = (big or rows[:3])[:per_day]
        tiles = []
        for r in rows:
            t = r["ticker"]
            out = d < today or (d == today and (r["time"] == "bmo" and NOW.hour >= 9 or r["time"] == "amc" and NOW.hour >= 17))
            st = next((x for x in BY_TICKER.get(t, []) if x.type == "earnings-recap" and 0 <= (x.pub.date() - d).days <= 2), None) if out else \
                next((x for x in BY_TICKER.get(t, []) if x.type == "earnings-preview" and 0 <= (d - x.pub.date()).days <= 6), None)
            tag = (f'<span class="et-tag{" rc" if st.type == "earnings-recap" else ""}">{"Recap" if st.type == "earnings-recap" else "Preview"}</span>'
                   if st else "")
            when_ = {"bmo": "Before the open", "amc": "After the close"}.get(r["time"], "Time not confirmed")
            href = u(st.path) if st else u(tpath(t))
            tiles.append(f'<a class="et{" done" if out else ""}" href="{href}" title="{esc(UMAP[t]["name"])}: {when_}">{logo(t, 44)}'
                         f'<b>{t}</b>{tag}</a>')
        cols.append(f'<div class="eday{" today" if d == today else ""}"><h3>{WD[d.weekday()][:3]}<span>{d.day} {MON[d.month - 1]}</span></h3>'
                    f'<div class="ets">{"".join(tiles) or "<p class=none>None</p>"}</div></div>')
    return f'<div class="ecal">{"".join(cols)}</div>'


def week_start(d: dt.date) -> dt.date:
    s0 = d - dt.timedelta(days=d.weekday())
    return s0 + dt.timedelta(days=7) if d.weekday() >= 5 else s0


def earnings_page():
    start = week_start(NOW.date())
    weeks = []
    labels = ("This week", "Next week") if NOW.weekday() < 5 else ("Next week", "The week after")
    for w, label in enumerate(labels):
        days = [start + dt.timedelta(days=7 * w + i) for i in range(5)]
        weeks.append(f'<section class="hsec"><div class="hsec-h"><div><h2>{label}</h2><p>Week of {days[0].day} {MONTH[days[0].month - 1]}</p></div></div>'
                     f'{earnings_days(days)}</section>')
    recaps = [s for s in STORIES if s.type in ("earnings-recap", "earnings-preview")][:12]
    rec = (f'<section class="hsec"><div class="hsec-h"><div><h2>Latest earnings stories</h2></div></div>'
           f'<div class="tiles t3">{"".join(tile(x) for x in recaps)}</div></section>') if recaps else ""
    body = (f'<div class="wrap"><div class="ph"><h1>Earnings</h1><p>The big companies reporting this week and next. We publish a preview '
            f'before each one and a recap within hours: tap a logo to read it.</p></div>{"".join(weeks)}{rec}</div>')
    write("earnings/", page("earnings/", "Earnings Calendar", body, "This week's and next week's big earnings reports, with our previews and recaps.", active="earnings/"))


# ---------------------------------------------------------------------- misc pages

def author_pages():
    for aid, a in AUTHORS.items():
        st = [s for s in STORIES if s.fm.get("author") == aid]
        body = (f'<div class="wrap"><div class="read" style="max-width:780px"><div class="ph"><div class="crumbs"><span class="kick">{esc(a["role"])}</span></div>'
                f'<h1>{esc(a["name"])}</h1><p>{esc(a["beat"])}. {esc(a["name"])} is a pen name; every Mostly Markets writer uses one.</p></div>'
                f'<div class="feed" style="margin-top:20px">{mini_rows(st[:60])}</div></div></div>')
        write(f"authors/{aid}/", page(f"authors/{aid}/", a["name"], body, f"Stories by {a['name']}, {a['role']}."))


def about_page():
    body = f"""<div class="wrap"><div class="read prose-page"><h1>About Mostly Markets</h1><div class="prose">
<p>Mostly Markets explains why stocks move. When a company reports, a stock jumps or slides, or the Fed speaks, we publish a short story the same day that says what happened, why, and what it means, in plain English.</p>
<h2>What we publish</h2>
<ul><li><strong>Why it moved:</strong> a stock moved 4% or more on news, and we found the cause in at least two reliable sources.</li>
<li><strong>Earnings:</strong> a preview the evening before each big report, and a recap minutes to hours after it.</li>
<li><strong>Markets and the economy:</strong> the day's story at the close, the Fed, inflation and jobs.</li>
<li><strong>Analysis:</strong> the stories Wall Street is telling, the evidence for and against them, and who is arguing what.</li>
<li><strong>Our picks:</strong> three stocks we'd skip and one we like, on one theme at a time, with the numbers behind each call.</li></ul>
<h2>How we work</h2>
<p>Every fact in a story is checked against two independent sources, and company figures against the company's own release or SEC filing. Stock prices come from Nasdaq and CNBC; financial history from SEC filings. Every number carries its basis: adjusted or not, year on year or quarter on quarter, at the close or after hours.</p>
<p>Stories are researched and drafted with AI tools and checked against our sources before they go out; our writers publish under pen names. Charts are drawn from our own price files. Outside headlines link to the publishers that reported them.</p>
<h2>What we aren't</h2>
<p>Mostly Markets is for information and education only. It is not investment advice, and nothing on this site is a recommendation to buy or sell any security. We don't know your circumstances. Do your own research or talk to a licensed adviser before you invest.</p>
<h2>Get it by email</h2>
<p>The <a href="{CFG['substack']}">Mostly Markets newsletter</a> sends the day's stories after the close, free. We're also on <a href="{CFG['instagram']}">Instagram</a>.</p>
</div></div></div>"""
    write("about/", page("about/", "About", body, "How Mostly Markets works: what we publish, how we check it, and what we aren't."))


def not_found():
    body = f'<div class="wrap notfound"><h1>Page not found</h1><p>That story or stock isn\'t here.</p><p style="margin-top:20px"><a class="btn" href="{u("")}">Back to the latest</a></p></div>'
    (DIST / "404.html").write_text(page("404.html", "Page not found", body))


def feeds():
    items = []
    for s in STORIES[:60]:
        items.append(f"<item><title>{esc(s.title)}</title><link>{absu(s.path)}</link><guid>{absu(s.path)}</guid>"
                     f"<pubDate>{format_datetime(s.pub)}</pubDate><description>{esc(s.dek)}</description>"
                     f"<category>{TYPE_LABEL[s.type]}</category></item>")
    (DIST / "feed.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{CFG["name"]}</title><link>{BASE_URL}/</link>'
        f'<description>{esc(CFG["tagline"])}</description><language>en-us</language>{"".join(items)}</channel></rss>')
    urls = [""] + [s.path for s in STORIES] + [tpath(t) for t in UMAP] + ["daily/", "discover/", "earnings/", "stocks/", "about/"]
    (DIST / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                                      + "".join(f"<url><loc>{absu(p)}</loc></url>" for p in urls) + "</urlset>")
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n" if LAUNCHED else
                                     "User-agent: *\nDisallow: /\n")
    # client data
    qd = {}
    for t, q in Q.items():
        ext = q.get("ext") or {}
        lab = ""
        if q.get("time"):
            qt = quote_time(q)
            lab = f"At the close, {qt.day} {MON[qt.month - 1]}" if qt.time() >= dt.time(16, 0) else f"As of {when(qt)}"
        qd[t] = [q.get("price"), q.get("change_pct"), ext.get("price"), ext.get("change_pct"), lab,
                 "After hours" if ext.get("session") == "POST_MKT" else "Before the open"]
    (DIST / "data").mkdir(exist_ok=True)
    md_ = {k: [v.get("price"), v.get("change_pct")] for k, v in MKT["markets"].items()}
    (DIST / "data/quotes.json").write_text(json.dumps({"asof": QUOTES.get("asof"), "q": qd, "m": md_}, separators=(",", ":")))
    search = {"s": [[t, x["name"], x["sector"], 1 if t in LOGOS else 0, "High quality" if band((SCORES.get(t) or {}).get("q")) == "good" else ""]
                    for t, x in sorted(UMAP.items())],
              "n": [[s.title, s.path, f"{s.pub.day} {MON[s.pub.month - 1]}"] for s in STORIES[:400]]}
    (DIST / "data/search.json").write_text(json.dumps(search, separators=(",", ":")))


def static():
    out = DIST / "static"
    shutil.copytree(SITE / "static", out, dirs_exist_ok=True)
    # Cover art is retired (v5): pages use charts drawn from our prices, so assets/covers isn't shipped.
    shutil.rmtree(out / "covers", ignore_errors=True)
    lg = out / "logos"
    lg.mkdir(exist_ok=True)
    for f in (ROOT / "assets/logos").glob("*.png"):
        dst = lg / f.name
        if not dst.exists() or dst.stat().st_size != f.stat().st_size:
            shutil.copy2(f, dst)


ASSET_V = hashlib.md5((SITE / "static/style.css").read_bytes() + (SITE / "static/app.js").read_bytes()).hexdigest()[:8]


def main():
    t0 = time.time()
    if DIST.exists():
        for p in DIST.iterdir():
            if p.name != "static":
                shutil.rmtree(p) if p.is_dir() else p.unlink()
    DIST.mkdir(exist_ok=True)
    static()
    compute_sector_medians()
    n = home_pages()
    for s in STORIES:
        write(s.path, daily_page(s) if s.type == "daily" else story_page(s))
    daily_index()
    for t in UMAP:
        write(tpath(t), stock_page(t))
    discover_pages()
    sector_pages()
    stocks_index()
    earnings_page()
    author_pages()
    about_page()
    not_found()
    feeds()
    (DIST / ".nojekyll").write_text("")
    if os.environ.get("MM_CNAME"):
        (DIST / "CNAME").write_text(os.environ["MM_CNAME"] + "\n")
    print(f"built {len(STORIES)} stories, {len(UMAP)} stock pages, {n} feed pages in {time.time() - t0:.1f}s -> {DIST}")


if __name__ == "__main__":
    main()
