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
DIST = ROOT / "dist"
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
              "macro": "Economy", "chart": "Chart", "analysis": "Analysis"}
FILTERS = [("all", "All"), ("why-it-moved,movers", "Why it moved"), ("earnings-recap,earnings-preview", "Earnings"),
           ("daily,market-wrap,macro,chart", "Markets & economy"), ("list,analysis", "Our picks & analysis"),
           ("mine", "My stocks")]


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
                out.append({"t": t, "p": m.get("price"), "c": m.get("change_pct"), "s": m.get("session", "close")})
                continue
            c = close_on(t, self.date)
            if c and c[0]["date"] == self.date:
                out.append({"t": t, "p": c[0]["close"], "c": (c[0]["close"] / c[1]["close"] - 1) * 100, "s": "close"})
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
        base = {"daily": 7, "market-wrap": 6, "earnings-recap": 5, "macro": 5, "analysis": 4, "why-it-moved": 3, "list": 3,
                "earnings-preview": 2, "movers": 2, "chart": 1}[self.type]
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
NAV = [("", "Latest"), ("daily/", "The Daily"), ("discover/", "Discover"), ("earnings/", "Earnings"), ("stocks/", "Stocks")]


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
<main>
{body}
</main>
<footer class="ft">
 <div class="wrap">
  <div><a class="wm" href="{u('')}">Mostly <span>Markets</span></a><p>{esc(CFG['tagline'])} Stories every few hours on market days, and a free newsletter.</p></div>
  <nav aria-label="Footer"><a href="{u('')}">Latest</a><a href="{u('discover/')}">Discover</a><a href="{u('earnings/')}">Earnings</a><a href="{u('stocks/')}">All stocks</a><a href="{CFG['substack']}">Newsletter</a><a href="{CFG['instagram']}">Instagram</a><a href="{u('about/')}">About</a><a href="{u('feed.xml')}">RSS</a></nav>
  <div><p>Mostly Markets is for information and education only. It is not investment advice, and nothing here is a recommendation to buy or sell any security.</p><p>Our writers publish under pen names. Cover images are AI-generated. Prices from Nasdaq and CNBC, financials from SEC filings.</p></div>
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
        f'<span class="pc">+{extra}</span>' if extra > 0 else "") + "</span>"


def cover_img(key: str, size: int, cls: str = "", lazy=True, alt=True) -> str:
    a = esc(COVERS["covers"].get(key, {}).get("alt", "") or COVER_ALT.get(key, "")) if alt else ""
    srcset = ""
    if size == 1600:
        srcset = f' srcset="{u(f"static/covers/{key}-800.webp")} 800w, {u(f"static/covers/{key}-1600.webp")} 1600w" sizes="(max-width: 760px) 100vw, 680px"'
    return (f'<img src="{u(f"static/covers/{key}-{size}.webp")}"{srcset} alt="{a}"'
            f'{" loading=lazy decoding=async" if lazy else ""} class="{cls}">')


def time_tag(s: Story, rel=True) -> str:
    return f'<time datetime="{s.pub.isoformat()}"{" data-rel" if rel else ""}>{esc(ampm(s.pub))} ET</time>'


def row(s: Story) -> str:
    return (f'<article class="card" data-type="{s.type}" data-tickers="{" ".join(s.tickers)}">'
            f'<a class="cover-link" href="{u(s.path)}" aria-label="{esc(s.title)}"></a><div>'
            f'<div class="c-top">{logos(s.tickers)}<span class="tag">{TYPE_LABEL[s.type]}</span>{time_tag(s)}</div>'
            f'<h3>{esc(s.title)}</h3><p class="dk">{esc(s.dek)}</p>'
            f'<div class="c-ft">{chips(s)}<span class="by">{esc(s.author["name"])}</span>{time_tag(s)}<span class="hide-m">· {s.minutes} min read</span></div></div>'
            f'<div class="th">{cover_img(s.cover, 480)}</div></article>')


def mini_rows(stories: list[Story]) -> str:
    out = []
    last_day = None
    for s in stories:
        d = s.pub.date()
        if d != last_day:
            out.append(f'<div class="day"><span>{day_title(d)}</span></div>')
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
        for t in [x.strip() for x in names.split(",") if x.strip() in UMAP]:
            c = close_on(t, story.date)
            r1 = ret_since(t, 252, story.date)
            price = c[0]["close"] if c else None
            cards.append(f'<a class="pk {kind}" href="{u(tpath(t))}">{logo(t, 44)}<span class="lab">{"We love" if kind == "love" else "We hate"}</span>'
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


def render_body(s: Story) -> str:
    if s._rendered is None:
        r = Renderer(link_ticker=lambda t: u(tpath(t)) if t in UMAP else None, url=u, blocks={},
                     takes=s.type == "daily", page_url=absu(s.path))
        r.blocks = {"chart": lambda x: block_chart(x, s), "picks": lambda x: block_picks(x, s),
                    "highlights": lambda x: block_highlights(x, r), "stat": lambda x: block_stat(x, s)}
        s._rendered = r.render(s.body)
        s.takes = r.takes
        s.headings = r.headings
    return s._rendered


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
            p = (f'<span class="{tone(m["c"])}">{"▲" if m["c"] >= 0 else "▼"} {abs(m["c"]):.2f}%</span> {money(m["p"])}'
                 f'<small>{sess}, {s.pub.day} {MON[s.pub.month - 1]}</small>')
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


def story_page(s: Story) -> str:
    body = render_body(s)
    sector = UMAP[s.tickers[0]]["sector"] if s.tickers else None
    crumbs = f'<span class="kick hl">{TYPE_LABEL[s.type]}</span>'
    if sector:
        crumbs += f'<a class="kick" href="{u("sectors/" + slugify(sector) + "/")}">{esc(sector)}</a>'
    cap = COVERS["covers"].get(s.cover, {}).get("alt", "") or COVER_ALT.get(s.cover, "")
    more = []
    if s.tickers:
        t = s.tickers[0]
        others = [x for x in BY_TICKER[t] if x is not s][:4]
        if others:
            more.append(f'<section class="related"><h3>More on {esc(UMAP[t]["name"])}</h3><div class="cards-col">{"".join(row(x) for x in others)}</div></section>')
    latest = [x for x in STORIES if x is not s and x not in BY_TICKER.get(s.tickers[0] if s.tickers else "", [])][:5]
    more.append(f'<section class="related"><h3>Latest from Mostly Markets</h3><div class="cards-col">{"".join(row(x) for x in latest)}</div></section>')
    follow_t = s.tickers[0] if s.tickers else None
    endbox = (f'<div class="endbox"><div><h4>Follow {esc(UMAP[follow_t]["name"])}</h4><p>Its stories collect under My stocks on the front page. '
              f'For the daily email, subscribe to the newsletter.</p></div><div class="acts">'
              f'<button class="btn ghost" type="button" data-follow="{follow_t}" aria-pressed="false">{ICON["plus"]}<span>Follow</span></button>'
              f'<a class="btn" href="{CFG["subscribe"]}">Subscribe free</a></div></div>') if follow_t else (
        '<div class="endbox"><div><h4>Get the close in your inbox</h4><p>Every market day, the stories that moved stocks and why.</p></div>'
        f'<div class="acts"><a class="btn" href="{CFG["subscribe"]}">Subscribe free</a></div></div>')
    ld = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": s.title, "description": s.dek,
          "datePublished": s.pub.isoformat(), "author": {"@type": "Person", "name": s.author["name"]},
          "image": [absu(f"static/covers/{s.cover}-1600.webp")], "publisher": {"@type": "Organization", "name": CFG["name"]}}
    initials = "".join(w[0] for w in s.author["name"].split()[:2])
    html_ = f"""<article class="story wrap">
 <header class="story-head">
  <div class="crumbs">{crumbs}</div>
  <h1>{esc(s.title)}</h1>
  <p class="dek">{esc(s.dek)}</p>
  <div class="byl"><span class="av" aria-hidden="true">{esc(initials)}</span><a class="by" href="{u('authors/' + s.fm.get('author', '') + '/')}">{esc(s.author['name'])}</a><span class="sep">·</span><time datetime="{s.pub.isoformat()}">{esc(when(s.pub, True))}</time><span class="sep">·</span><span>{s.minutes} min read</span></div>
 </header>
 <figure class="cover"><div class="ci">{cover_img(s.cover, 1600, lazy=False)}</div><figcaption>{esc(cap)}. Image: AI-generated.</figcaption></figure>
 <div class="story-body">
  {stockbar(s)}
  <div class="prose" style="margin-top:28px">{body}</div>
  {endbox}
  <p class="disc">Mostly Markets is for information and education only and isn't investment advice. {esc(s.author['name'])} is a pen name. Prices are from Nasdaq and CNBC as of the time stated.</p>
  {''.join(more)}
 </div>
</article>
<script type="application/ld+json">{json.dumps(ld)}</script>"""
    return page(s.path, s.title, html_, s.dek, f"static/covers/{s.cover}-1600.webp", og_type="article")


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


def edition_card(s: Story, size: int = 800) -> str:
    render_body(s)
    return (f'<article class="ed-card"><a class="cover-link" href="{u(s.path)}" aria-label="{esc(s.title)}"></a>'
            f'<div class="th">{cover_img(s.cover, size)}</div><div class="tx"><span class="ed-k">No. {s.edition} · {esc(day_title(s.pub.date()))}</span>'
            f'<h3>{esc(s.title)}</h3><p>{esc(s.dek)}</p><span class="ed-m">{len(s.takes)} takes · {s.minutes} min read</span></div></article>')


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
          "image": [absu(f"static/covers/{s.cover}-1600.webp")], "publisher": {"@type": "Organization", "name": CFG["name"]}}
    play = (f'<button class="btn sm play" type="button" data-story-open="ed-{s.date}">{ICON["play"]}<span>Swipe through it</span></button>'
            if s.takes else "")
    html_ = f"""<article class="daily">
 <header class="ed-head wrap">
  <div class="ed-mast"><a href="{u('daily/')}" class="ed-name">Mostly Markets <b>Daily</b></a><span>{"Weekend edition · " if s.fm.get("edition") == "weekend" else ""}{esc(long_date(d))}</span><span class="ed-no">No. {s.edition}</span></div>
  <h1>{esc(s.title)}</h1>
  <p class="dek">{esc(s.dek)}</p>
  <div class="byl"><span class="av" aria-hidden="true">{esc(initials)}</span><a class="by" href="{u('authors/' + s.fm.get('author', '') + '/')}">{esc(s.author['name'])}</a><span class="sep">·</span><span>{s.minutes} min read</span><span class="sep">·</span><span>{len(s.takes)} takes</span>{play}</div>
 </header>
 <figure class="ed-cover"><div class="ci">{cover_img(s.cover, 1600, lazy=False)}</div><figcaption>{esc(COVER_ALT.get(s.cover) or COVERS["covers"].get(s.cover, {}).get("alt", ""))}. Illustration: AI-generated.</figcaption></figure>
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
    return page(s.path, s.title, html_, s.dek, f"static/covers/{s.cover}-1600.webp", og_type="article", active="daily/")


def daily_index():
    if not DAILIES:
        body = f'<div class="wrap pagehead"><h1>The Daily</h1><p>The first edition is on its way.</p></div>'
    else:
        first, rest = DAILIES[0], DAILIES[1:]
        body = f"""<div class="wrap pagehead ed-ph"><span class="ed-name big">Mostly Markets <b>Daily</b></span>
<p>The story behind the market every morning: one big story, a thread of sharp takes, and the charts that explain them. Free.</p>
<a class="btn" href="{CFG["subscribe"]}">Get it in your inbox</a></div>
<section class="wrap"><div class="ed-feature">{edition_card(first, 1600)}</div>
{f'<div class="ed-grid">{"".join(edition_card(x) for x in rest)}</div>' if rest else ''}</section>"""
    write("daily/", page("daily/", "The Daily", body, "The story behind the market every morning, in charts.", active="daily/"))


# ---------------------------------------------------------------------- stories (tap-through slides)

def slide(kind: str, inner: str, bg: str = "", href: str = "") -> str:
    style = f' style="--img:url({bg})"' if bg else ""
    link = f' data-href="{esc(href)}"' if href else ""
    return f'<section class="sl {kind}{" hasbg" if bg else ""}"{style}{link}>{inner}</section>'


def edition_group(s: Story) -> dict:
    render_body(s)
    slides = [slide("cover", f'<div class="sl-k">Mostly Markets Daily · No. {s.edition}</div><h2>{esc(s.title)}</h2>'
                             f'<p>{esc(s.dek)}</p><div class="sl-hint">Tap to start · {len(s.takes)} takes</div>',
                    u(f"static/covers/{s.cover}-800.webp"), u(s.path))]
    for tk in s.takes:
        vis, text = take_parts(tk)
        slides.append(slide("take", f'<div class="sl-n">{tk["n"]}<i>/{tk["total"]}</i></div><h3>{esc(tk["title"])}</h3>'
                                    f'<div class="sl-v">{vis}</div><p>{esc(clip(text, 210))}</p>'
                                    f'<a class="sl-cta" href="{u(s.path)}#{tk["id"]}">Read the take</a>', href=f'{u(s.path)}#{tk["id"]}'))
    slides.append(slide("end", f'<div class="sl-k">That was The Daily</div><h2>Get it in your inbox every morning</h2>'
                               f'<a class="sl-cta big" href="{CFG["subscribe"]}">Subscribe free</a>'
                               f'<a class="sl-cta ghost" href="{u(s.path)}">Read the full edition</a>'))
    return {"id": f"ed-{s.date}", "name": "The Daily", "when": day_title(s.pub.date()),
            "avatar": f'<img src="{u(f"static/covers/{s.cover}-480.webp")}" alt="">', "slides": slides}


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


def daily_hero(s: Story) -> str:
    render_body(s)
    lis = "".join(f'<li><a href="{u(s.path)}#{tk["id"]}"><b>{tk["n"]}</b><span>{esc(tk["title"])}</span></a></li>' for tk in s.takes[:5])
    return f"""<section class="wrap dhero"><article class="dh">
 <a class="dh-cv" href="{u(s.path)}" aria-label="{esc(s.title)}">{cover_img(s.cover, 1600, lazy=False)}<span class="dh-badge">Mostly Markets <b>Daily</b> · No. {s.edition}</span></a>
 <div class="dh-tx"><div class="dh-k">{esc(long_date(s.pub.date()))}</div><h1><a href="{u(s.path)}">{esc(s.title)}</a></h1><p class="dek">{esc(s.dek)}</p>
 <ol class="dh-takes">{lis}</ol>
 <div class="dh-acts"><a class="btn" href="{u(s.path)}">Read the edition</a><button class="btn ghost" type="button" data-story-open="ed-{s.date}">{ICON["play"]}<span>Swipe through it</span></button></div></div>
</article></section>"""


def take_card(s: Story, tk: dict) -> str:
    vis, text = take_parts(tk)
    return (f'<article class="card takecard" data-type="daily"><div class="tc-top"><span class="tag dl">From The Daily</span>'
            f'<span class="tc-n">{tk["n"]}/{tk["total"]}</span></div><h3><a href="{u(s.path)}#{tk["id"]}">{esc(tk["title"])}</a></h3>'
            f'{vis}<p class="dk">{esc(clip(text, 240))}</p><a class="tc-more" href="{u(s.path)}#{tk["id"]}">Read the take in today’s edition</a></article>')


# ---------------------------------------------------------------------- home / feed

def pick_lead(pool: list[Story]) -> tuple[Story, list[Story]]:
    if not pool:
        return None, []
    newest_day = pool[0].pub.date()
    recent = [s for s in pool if (pool[0].pub - s.pub) < dt.timedelta(hours=30)]
    feat = [s for s in recent if s.featured]
    def score(s):  # importance, minus a point for every three hours of age
        return s.weight() - (NOW - s.pub).total_seconds() / 3600 / 3
    lead = feat[0] if feat else max(recent, key=lambda s: (score(s), s.pub))
    rest = sorted([s for s in recent if s is not lead], key=lambda s: (score(s), s.pub), reverse=True)
    tops, seen_t = [], set(lead.tickers[:1])
    for s in rest:
        if s.type == "movers" or (s.tickers and s.tickers[0] in seen_t):
            continue
        tops.append(s)
        seen_t.update(s.tickers[:1])
        if len(tops) == 3:
            break
    _ = newest_day
    return lead, tops


def home_pages():
    size = CFG["feed_page_size"]
    lead, tops = pick_lead([x for x in STORIES if x.type != "daily"])
    hero = DAILIES[0] if DAILIES else None
    skip = {id(lead)} | {id(x) for x in tops} | ({id(hero)} if hero else set())
    feed = [s for s in STORIES if id(s) not in skip]
    pages = max(1, math.ceil(len(feed) / size))
    chips_ = "".join(f'<button class="chip" type="button" data-filter="{k}" aria-pressed="{"true" if k == "all" else "false"}">{n}</button>'
                     for k, n in FILTERS)
    takes_for_feed = [tk for tk in (render_body(hero) and hero.takes if hero else []) if take_parts(tk)[0]][:3]
    for pi in range(pages):
        items = feed[pi * size:(pi + 1) * size]
        top_html = ""
        if pi == 0 and lead:
            tops_html = "".join(
                f'<article class="top"><a class="cover-link" href="{u(t.path)}" aria-label="{esc(t.title)}"></a>'
                f'<div class="th">{cover_img(t.cover, 800)}</div><div class="tx"><div class="c-top" style="display:flex;gap:8px;align-items:center">'
                f'{logos(t.tickers, 28)}<span class="tag">{TYPE_LABEL[t.type]}</span></div><h2>{esc(t.title)}</h2><p>{esc(t.dek)}</p>'
                f'<div class="c-ft">{chips(t)}</div></div></article>' for t in tops)
            top_html = story_rail(story_groups()) + (daily_hero(hero) if hero else "")
            top_html += f"""<section class="wrap home-top"><article class="lead"><a class="cover-link" href="{u(lead.path)}" aria-label="{esc(lead.title)}"></a>
 <div class="cv">{cover_img(lead.cover, 1600, lazy=False)}</div>
 <div class="tx"><div class="c-top">{logos(lead.tickers, 36)}<span class="kick hl">{TYPE_LABEL[lead.type]}</span></div><h1>{esc(lead.title)}</h1><p class="dek">{esc(lead.dek)}</p>
 {chips(lead, 4)}<div class="meta">{time_tag(lead)}<span>·</span><span>{esc(lead.author['name'])}</span><span>·</span><span>{lead.minutes} min read</span></div></div></article>
 <div class="tops">{tops_html}</div></section>"""
        rows_html = []
        last_day = None
        for i, s in enumerate(items):
            d = s.pub.date()
            if d != last_day:
                rows_html.append(f'<div class="day"><span>{day_title(d)}</span><small>{sum(1 for x in items if x.pub.date() == d)} stories</small></div>')
                last_day = d
            rows_html.append(row(s))
            if pi == 0 and i == 5:
                rows_html.append(subscribe_box(wide=True))
            if pi == 0 and i in (2, 9, 16) and takes_for_feed:
                rows_html.append(take_card(hero, takes_for_feed.pop(0)))
        nav = []
        if pi > 0:
            nav.append(f'<a class="btn ghost" href="{u("" if pi == 1 else f"page/{pi}/")}">Newer stories</a>')
        if pi < pages - 1:
            nav.append(f'<a class="btn ghost" href="{u(f"page/{pi + 2}/")}">Older stories</a>')
        body = f"""{top_html}
<section class="wrap"><div class="feed-wrap"><div class="feed">
 <div class="feed-head"><h2>{"Latest stories" if pi == 0 else f"Latest stories, page {pi + 1}"}</h2></div>
 <div class="chips" role="toolbar" aria-label="Filter stories">{chips_}</div>
 <div class="cards-col">{''.join(rows_html)}</div>
 <p class="empty" hidden></p>
 <div class="more">{''.join(nav)}</div>
</div></div></section>"""
        path = "" if pi == 0 else f"page/{pi + 1}/"
        title = CFG["name"] + (": " + CFG["tagline"] if pi == 0 else f" | Latest stories, page {pi + 1}")
        write(path, page(path, title, body, CFG["tagline"] + " Why-it-moved stories, earnings, and our picks.",
                         f"static/covers/{lead.cover}-1600.webp" if lead else None, active=""))
    return pages


# ---------------------------------------------------------------------- stock pages

SECTOR_MED: dict[str, dict] = {}
SCORES: dict[str, dict] = {}
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
    stories_html = (mini_rows(st[:12]) if st else
                    f'<p class="empty" style="text-align:left;padding:18px 0">We haven\'t written about {esc(name)} yet. '
                    f'Follow it, and its first story will show under My stocks on the front page.</p>')
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
    nav = [("overview", "Overview")] + ([("quality", "Quality & valuation")] if val else []) + (
        [("financials", "Financials")] if fin else []) + [("stories", "Stories")] + ([("peers", "Peers")] if prow else [])
    navh = "".join(f'<a href="#{k}"{" class=on" if i == 0 else ""}>{v}</a>' for i, (k, v) in enumerate(nav))
    body = f"""<div class="sp wrap">
 <div class="crumbs"><a class="kick" href="{u('stocks/')}">Stocks</a><span class="kick">/</span><a class="kick" href="{u('sectors/' + slugify(x['sector']) + '/')}">{esc(x['sector'])}</a><span class="kick hide-m">/</span><span class="kick hide-m">{esc(x['industry'])}</span></div>
 <div class="sp-hero">
  <div><div class="sp-id">{logo(t, 64)}<div><h1>{esc(name)}<small>{t}</small></h1>
   <div class="sect">{esc(x['industry'])}{(' · ' + esc(x['hq'])) if x.get('hq') else ''}{' · In the S&amp;P 500' if 'S&P 500' in x.get('index', []) else ''}</div></div></div>
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
  {val}
  {fin}
  <section id="stories"><h2 class="sh2">Stories on {esc(name)}</h2><div class="feed">{stories_html}</div></section>
  {peers_html}
 </div>
 <aside class="side"><div class="stats hide-t">{stat_html}{rangebar}</div>
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


def card(t, metric_label, metric_value, tone_v=None) -> str:
    x = UMAP[t]
    q = Q.get(t) or {}
    sp = C.spark([b["close"] for b in prices(t)[-63:]], 240, 44)
    return (f'<a class="sc" href="{u(tpath(t))}"><div class="r1">{logo(t, 40)}<div class="id"><b>{t}</b><span>{esc(x["name"])}</span></div>'
            f'<div class="cg">{money(q.get("price"))}<small class="{tone(q.get("change_pct"))}">{pct(q.get("change_pct"), 1)}</small></div></div>'
            f'{sp}<div class="ml">{esc(metric_label)} <b class="{tone(tone_v) if tone_v is not None else ""}">{metric_value}</b></div></a>')


def discover_lists():
    sp = [x["ticker"] for x in UNIV if "S&P 500" in x.get("index", [])]
    allt = [x["ticker"] for x in UNIV]
    wk = {t: week_change(t) for t in allt}
    lists = []
    g = sorted([t for t in allt if wk[t] is not None], key=lambda t: -wk[t])
    lists.append(("gainers-this-week", "Biggest gainers this week", "The stocks up most since last Friday's close.",
                  [(t, "This week", pct(wk[t], 1), wk[t]) for t in g[:30]]))
    lists.append(("losers-this-week", "Biggest losers this week", "The stocks down most since last Friday's close.",
                  [(t, "This week", pct(wk[t], 1), wk[t]) for t in g[::-1][:30]]))
    hi = []
    for t in sp:
        b = prices(t)[-252:]
        if len(b) > 200:
            m = max(x["close"] for x in b)
            off = (1 - b[-1]["close"] / m) * 100
            hi.append((t, off))
    near = sorted([h for h in hi if h[1] <= 1.5], key=lambda h: -(ytd(h[0]) or 0))
    lists.append(("near-highs", "At or near a 52-week high", "S&P 500 stocks within 1.5% of their highest close in a year, best year first.",
                  [(t, "Year to date", pct(ytd(t), 1), ytd(t)) for t, _ in near[:30]]))
    down = sorted([h for h in hi if h[1] >= 30 and ((Q.get(h[0]) or {}).get("cap") or 0) > 2e10], key=lambda h: -h[1])
    lists.append(("beaten-down", "Beaten down", "Large S&P 500 companies at least 30% below their 52-week high.",
                  [(t, "Below 52-week high", f"−{off:.1f}%", -off) for t, off in down[:30]]))
    gr = sorted([t for t in sp if (ttm(t).get("revenue_growth_yoy_pct") is not None and (ttm(t).get("revenue") or 0) > 1e9)],
                key=lambda t: -ttm(t)["revenue_growth_yoy_pct"])
    if gr:
        lists.append(("fastest-growers", "Fastest growers", "S&P 500 companies with the fastest revenue growth over the last 12 months (revenue over $1 billion).",
                      [(t, "Revenue growth", pct(ttm(t)["revenue_growth_yoy_pct"], 1), ttm(t)["revenue_growth_yoy_pct"]) for t in gr[:30]]))
    cm = sorted([t for t in sp if (ttm(t).get("fcf_margin_pct") or 0) >= 25 and (ttm(t).get("revenue_growth_yoy_pct") or 0) > 5
                 and (ttm(t).get("revenue") or 0) > 1e9], key=lambda t: -ttm(t)["fcf_margin_pct"])
    if cm:
        lists.append(("cash-machines", "Cash machines", "Free cash flow of at least 25 cents per dollar of sales, with sales still growing.",
                      [(t, "Free cash flow margin", pct(ttm(t)["fcf_margin_pct"], 1, sign=False), None) for t in cm[:30]]))
    return lists


def discover_pages():
    lists = discover_lists()
    secs = []
    for key, title, desc, items in lists:
        cards = "".join(card(t, ml, mv, tv) for t, ml, mv, tv in items[:6])
        secs.append(f'<section class="dsec"><div class="dsec-h"><div><h2>{esc(title)}</h2><p>{esc(desc)}</p></div>'
                    f'<a href="{u(f"discover/{key}/")}">View all</a></div><div class="cards">{cards}</div></section>')
        rows = "".join(
            f'<tr><td class="nm"><a href="{u(tpath(t))}">{logo(t, 30)}<span class="t"><b>{t}</b><i>{esc(UMAP[t]["name"])}</i></span></a></td>'
            f'<td class="hide-m">{esc(UMAP[t]["industry"])}</td><td class="n">{money((Q.get(t) or {}).get("price"))}</td>'
            f'<td class="n {tone(tv)}" data-v="{tv if tv is not None else ""}">{mv}</td></tr>' for t, ml, mv, tv in items)
        body = (f'<div class="wrap"><div class="ph"><div class="crumbs"><a class="kick" href="{u("discover/")}">Discover</a></div><h1>{esc(title)}</h1><p>{esc(desc)}</p></div>'
                f'<table class="big" data-sort style="margin-top:22px"><thead><tr><th>Company</th><th class="hide-m">Industry</th><th class="n">Price</th>'
                f'<th class="n">{esc(items[0][1] if items else "")}</th></tr></thead><tbody>{rows}</tbody></table></div>')
        write(f"discover/{key}/", page(f"discover/{key}/", title, body, desc, active="discover/"))
    picks = [s for s in STORIES if s.type == "list"][:6]
    picks_html = ""
    if picks:
        picks_html = (f'<section class="dsec"><div class="dsec-h"><div><h2>Our picks</h2><p>Three stocks we love and one we hate, on one theme at a time.</p></div></div>'
                      f'<div class="feed cards-col">{"".join(row(s) for s in picks)}</div></section>')
    by = defaultdict(int)
    for x in UNIV:
        by[x["sector"]] += 1
    sectors = "".join(f'<a href="{u("sectors/" + slugify(k) + "/")}">{esc(k)}<span>{v}</span></a>' for k, v in sorted(by.items()))
    body = f"""<div class="wrap"><div class="ph"><h1>Discover</h1><p>Lists that update every market day from prices and SEC filings, plus our own picks. Tap any stock for its chart, financials and stories.</p></div>
{picks_html}{''.join(secs)}
<section class="dsec"><div class="dsec-h"><div><h2>Browse by sector</h2><p>All {len(UNIV)} stocks we cover.</p></div><a href="{u('stocks/')}">All stocks</a></div><div class="sectors">{sectors}</div></section></div>"""
    write("discover/", page("discover/", "Discover stocks", body, "Stock lists that update every market day: movers, highs, growers, cash machines and our picks.", active="discover/"))


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

def earnings_page():
    today = NOW.date()
    start = today - dt.timedelta(days=today.weekday())
    if today.weekday() >= 5:
        start += dt.timedelta(days=7)
    weeks = []
    for w in range(2):
        days = [start + dt.timedelta(days=7 * w + i) for i in range(5)]
        cols = []
        for d in days:
            rows = [r for r in CAL.get(d.isoformat(), []) if r["ticker"] not in ("GOOG", "FOX", "NWS", "BF.B")]
            rows = sorted(rows, key=lambda r: -((Q.get(r["ticker"]) or {}).get("cap") or r.get("mktcap") or 0))
            groups = []
            for tm, lab in (("bmo", "Before the open"), ("amc", "After the close"),
                            ("unknown", "Reported" if d < today else "Time not confirmed")):
                g = [r for r in rows if r["time"] == tm][:12]
                if not g:
                    continue
                items = []
                for r in g:
                    t = r["ticker"]
                    st = [s for s in BY_TICKER.get(t, []) if s.type in ("earnings-recap", "earnings-preview")
                          and abs((s.pub.date() - d).days) <= 2]
                    if r.get("eps_actual") is not None and r.get("eps_forecast") is not None:
                        sp = r.get("surprise_pct")
                        info = f'<span class="{tone(sp)}">EPS {money(r["eps_actual"])} vs {money(r["eps_forecast"])}</span>'
                    elif r.get("eps_forecast") is not None:
                        info = f'<span>Est. EPS {money(r["eps_forecast"])}</span>'
                    else:
                        info = "<span></span>"
                    link = f'<a class="st" href="{u(st[0].path)}">{"Recap" if st[0].type == "earnings-recap" else "Preview"}</a>' if st else ""
                    items.append(f'<div class="cal-e"><a class="co" href="{u(tpath(t))}">{logo(t, 22)}<b>{t}</b></a>{info}{link}</div>')
                more = len([r for r in rows if r["time"] == tm]) - len(g)
                groups.append(f'<div class="tm">{lab}</div>{"".join(items)}' + (f'<div class="cal-e"><span>+{more} more</span></div>' if more > 0 else ""))
            cols.append(f'<div class="cal-d{" today" if d == today else ""}"><h3>{WD[d.weekday()][:3]} {d.day} {MON[d.month - 1]}<small>{len(rows)}</small></h3>'
                        f'{"".join(groups) or "<p class=empty style=text-align:left;padding:12px 0>No reports we cover.</p>"}</div>')
        label = "This week" if w == 0 else "Next week"
        weeks.append(f'<section class="dsec"><div class="dsec-h"><div><h2>{label}</h2><p>Week of {days[0].day} {MONTH[days[0].month - 1]}. Consensus EPS from Nasdaq; the biggest companies first.</p></div></div><div class="cal">{"".join(cols)}</div></section>')
    recaps = [s for s in STORIES if s.type in ("earnings-recap", "earnings-preview")][:20]
    rec = f'<section class="dsec"><div class="dsec-h"><div><h2>Latest earnings stories</h2></div></div><div class="read" style="max-width:780px;margin:0"><div class="feed">{mini_rows(recaps)}</div></div></section>' if recaps else ""
    body = f'<div class="wrap"><div class="ph"><h1>Earnings</h1><p>Who reports, when, and what Wall Street expects. We publish a recap minutes to hours after each big release, and a preview the evening before.</p></div>{"".join(weeks)}{rec}</div>'
    write("earnings/", page("earnings/", "Earnings Calendar", body, "This week's and next week's earnings calendar with consensus estimates, previews and recaps.", active="earnings/"))


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
<li><strong>Our picks:</strong> three stocks we love and one we hate, on one theme at a time, with the numbers behind each call.</li></ul>
<h2>How we work</h2>
<p>Every fact in a story is checked against two independent sources, and company figures against the company's own release or SEC filing. Stock prices come from Nasdaq and CNBC; financial history from SEC filings. Every number carries its basis: adjusted or not, year on year or quarter on quarter, at the close or after hours.</p>
<p>Stories are researched and drafted with AI tools and checked against our sources before they go out; our writers publish under pen names. Cover images are AI-generated illustrations, not photographs of the companies named.</p>
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
    (DIST / "data/quotes.json").write_text(json.dumps({"asof": QUOTES.get("asof"), "q": qd}, separators=(",", ":")))
    search = {"s": [[t, x["name"], x["sector"], 1 if t in LOGOS else 0] for t, x in sorted(UMAP.items())],
              "n": [[s.title, s.path, f"{s.pub.day} {MON[s.pub.month - 1]}"] for s in STORIES[:400]]}
    (DIST / "data/search.json").write_text(json.dumps(search, separators=(",", ":")))


def static():
    out = DIST / "static"
    shutil.copytree(SITE / "static", out, dirs_exist_ok=True)
    cov = out / "covers"
    cov.mkdir(exist_ok=True)
    for f in (ROOT / "assets/covers").rglob("*.webp"):
        dst = cov / f.relative_to(ROOT / "assets/covers")
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists() or dst.stat().st_size != f.stat().st_size:
            shutil.copy2(f, dst)
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
