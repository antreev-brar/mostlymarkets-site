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
            COVER_ALT[f"story/{self.slug}"] = self.fm.get("cover_alt") or ""
            return f"story/{self.slug}"
        want = self.fm.get("cover")
        if want in keys:
            self.cover_opts = [want, "trading-floor", "wall-street-sun", "market-screens", "wall-street-rain", "markets-calm"]
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
        # Second choices, so neighbours in the feed don't share a photo (spread_covers): the type's, then the
        # market's own photos, which fit any story here (another sector's photo wouldn't).
        more = COVERS["type"].get(self.type, []) + ["trading-floor", "wall-street-sun", "market-screens", "wall-street-rain", "markets-calm"]
        self.cover_opts = list(dict.fromkeys(opts + more))
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


def spread_covers(order: list[Story], window: int = 4):
    """Stories without a photo of their own borrow a topic photo; swap a borrowed photo that one of the previous few
    stories in the feed (in the order it shows them: the top story first) already shows for the next unused choice."""
    shown: list[str] = []
    for s in order:
        if not s.cover.startswith("story/") and s.cover in shown[-window:]:
            alt = [o for o in getattr(s, "cover_opts", []) if o not in shown[-window:]]
            if alt:
                s.cover = alt[0]
        shown.append(s.cover)

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


def cover_img(key: str, size: int, cls: str = "", lazy=True, alt=True, sizes: str = "") -> str:
    a = esc(COVERS["covers"].get(key, {}).get("alt", "") or COVER_ALT.get(key, "")) if alt else ""
    srcset = ""
    if size == 1600:
        srcset = f' srcset="{u(f"static/covers/{key}-800.webp")} 800w, {u(f"static/covers/{key}-1600.webp")} 1600w" sizes="(max-width: 900px) 100vw, (max-width: 1180px) 54vw, 760px"'
    elif size == 800:  # list rows, shelves and boxes: a phone's small square needs only the 480
        srcset = (f' srcset="{u(f"static/covers/{key}-480.webp")} 480w, {u(f"static/covers/{key}-800.webp")} 800w"'
                  f' sizes="{sizes or "(max-width: 640px) 104px, 300px"}"')
    return (f'<img src="{u(f"static/covers/{key}-{size}.webp")}"{srcset} alt="{a}"'
            f'{" loading=lazy decoding=async" if lazy else ""} class="{cls}">')


def time_tag(s: Story, rel=True) -> str:
    return f'<time datetime="{s.pub.isoformat()}"{" data-rel" if rel else ""}>{esc(ampm(s.pub))} ET</time>'


def ago(d: dt.datetime, cls: str = "ago") -> str:
    """A timestamp that app.js turns into "12 min ago", "3h ago", "Yesterday, 4:05 p.m." and keeps ticking; with class
    "s" (narrow cards) it says just "3h ago", "Yesterday", "Fri"."""
    fb = f"{WD[d.weekday()][:3]} {d.day} {MON[d.month - 1]}" + ("" if " s" in f" {cls} " else f", {ampm(d)}")
    return f'<time class="{cls}" datetime="{d.isoformat()}" data-rel>{esc(fb)}</time>'


def fresh(s: Story) -> str:
    """Attributes app.js reads to mark a card New (published in the last few hours) or unseen since the last visit."""
    return f' data-pub="{s.pub.isoformat()}"'


NEWB = '<span class="newb">New</span>'

# ---------------------------------------------------------------------- pictures: every story has a cover photo

def cover_th(s: Story, size: int = 480, cls: str = "th", sizes: str = "") -> str:
    return f'<div class="{cls}">{cover_img(s.cover, size, sizes=sizes)}</div>'


TPAREN = re.compile(r"\s\((?:[A-Z]{1,5}(?:\.[A-Z])?)\)")  # "Okta (OKTA) Will Join...": the price tag shows the ticker
FIRST_SENTENCE = re.compile(r"(?<!\b[A-Z]\.)(?<=[.!?])\s+(?=[A-Z\"“])")


def card_title(s: Story) -> str:
    """A headline as cards show it: without the ticker in brackets, which the card's price tag already shows. The story
    page, its <title> and feeds keep the full headline."""
    return TPAREN.sub("", s.title)


def dek1(t: str) -> str:
    """The dek's first sentence: cards lead with the headline and keep the dek to one quiet line or two."""
    return FIRST_SENTENCE.split(t.strip(), 1)[0]


def row(s: Story) -> str:
    """A story in a list (the home page's rows, story pages, The Daily, stock and sector pages), headline first: the
    kind of story and when, a big headline, a quiet two-line dek, one price tag, and the cover on the right."""
    return (f'<article class="r8" data-type="{s.type}" data-tickers="{" ".join(s.tickers)}"{fresh(s)}>'
            f'<a class="cover-link" href="{u(s.path)}" aria-label="{esc(s.title)}"></a>'
            f'<div class="r8-tx"><div class="r8-k"><b>{TYPE_LABEL[s.type]}</b><i>·</i>{ago(s.pub, "ago q t-lg")}{ago(s.pub, "ago q s t-sm")}{NEWB}</div>'
            f'<h3>{esc(card_title(s))}</h3><p class="dk">{esc(dek1(s.dek))}</p>'
            f'{f"<div class=r8-ft>{chips(s, 1)}</div>" if s.moves else ""}</div>'
            f'{cover_th(s, 800)}</article>')


def mini(s: Story, show_thumb: bool = True) -> str:
    """A compact headline row for top-story lists and side rails: time, kind, headline."""
    th = cover_th(s) if show_thumb else ""
    return (f'<article class="mini{" nt" if not show_thumb else ""}"{fresh(s)}><a class="cover-link" href="{u(s.path)}" aria-label="{esc(s.title)}"></a>'
            f'{th}<div class="mi-tx"><div class="mi-k">{ago(s.pub)}<span>{TYPE_LABEL[s.type]}</span></div>'
            f'<h3>{esc(s.title)}</h3></div></article>')


def news_items(t: str | None, n: int = 6, since_days: int = 10) -> list[dict]:
    """Aggregated outside headlines (pipeline/news.py) for a ticker, or the market's when t is None. Newest first."""
    d = NEWS.get(t or "_market") or {}
    out = []
    cutoff = NOW - dt.timedelta(days=since_days)
    for it in d.get("items", []):
        if not it.get("title") or not str(it.get("url") or "").startswith(("https://", "http://")):
            continue
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
    src = it.get("source") or ""
    return (f'<li class="nw"><a href="{esc(it["url"])}" target="_blank" rel="noopener nofollow">{esc(it["title"])}</a>'
            f'<span class="nw-m">{src_av(src, 18)}<span>{esc(src)}{also} · {ago(it["dt"], "ago q")}</span></span></li>')


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


def rail_box(title: str, inner: str, more: tuple[str, str] | None = None, sub: str = "") -> str:
    link = f'<a class="rb-more" href="{more[0]}">{esc(more[1])}</a>' if more else ""
    return (f'<section class="rb"><div class="rb-h"><h4>{esc(title)}</h4>{link}</div>'
            f'{f"<p class=rb-sub>{sub}</p>" if sub else ""}{inner}</section>')


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


NO_PICTURE_MOVE = {"list", "movers", "brief", "daily"}  # pipeline/check.py mirrors this


def picture_first(s: Story, body: str) -> str:
    """Readers should meet the evidence early. If a story's first chart or stat block sits deep in the text (older
    templates put it last), move it up to right after the opening paragraph; a story with no picture at all gets the
    main stock's last three months there, or that day's market map. Lists, movers and briefs keep their own order."""
    if s.type in NO_PICTURE_MOVE:
        return body
    end = body.find("</p>")
    if end < 0:
        return body
    end += 4
    if s.visuals:
        v = s.visuals[0]
        i = body.find(v)
        if i < 0 or len(re.findall(r"\w+", re.sub(r"<[^>]+>", " ", body[:i]))) <= 140:
            return body
        body = body[:i] + body[i + len(v):]
        return body[:end] + v + body[end:]
    if s.tickers and prices(s.tickers[0]):
        t = s.tickers[0]
        name = UMAP[t]["name"]
        v = C.price_chart(prices(t), "3m", s.date, f"{name}'s shares over the last three months",
                          f"{name}, daily close, $, to {C.human(last_trading_day(s.date))}", "last")
    else:
        v = treemap_html(last_trading_day(s.date), n=160)
    return body[:end] + v + body[end:]


def story_page(s: Story) -> str:
    body = picture_first(s, render_body(s))
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
    endbox = (f'<div class="endbox"><div><h4>Follow {esc(UMAP[follow_t]["name"])}</h4><p>Its stories show on the home page, under Your stocks. '
              f'For the daily email, subscribe to the newsletter.</p></div><div class="acts">'
              f'<button class="btn ghost" type="button" data-follow="{follow_t}" aria-pressed="false">{ICON["plus"]}<span>Follow</span></button>'
              f'<a class="btn" href="{CFG["subscribe"]}">Subscribe free</a></div></div>') if follow_t else (
        '<div class="endbox"><div><h4>Get the close in your inbox</h4><p>Every market day, the stories that moved stocks and why.</p></div>'
        f'<div class="acts"><a class="btn" href="{CFG["subscribe"]}">Subscribe free</a></div></div>')
    ld = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": s.title, "description": s.dek,
          "datePublished": s.pub.isoformat(), "author": {"@type": "Person", "name": s.author["name"]},
          "image": [absu(f"static/covers/{s.cover}-1600.webp")], "publisher": {"@type": "Organization", "name": CFG["name"]}}
    initials = "".join(w[0] for w in s.author["name"].split()[:2])
    rs = running_story(s)
    running = (f'<a class="running" href="{u(rs.path)}"><span>Part of the running story</span><b>{esc(rs.title)}</b></a>' if rs else "")
    t0 = s.tickers[0] if s.tickers else None
    rail = "".join(x for x in (
        f'<section class="rb">{stockbar(s)}</section>' if s.tickers else "",
        rail_news(t0, 5) if t0 else rail_news(None, 5),
        rail_latest((s,), 5)) if x)
    html_ = f"""<div class="wrap art">
 <article class="story amain">
  <header class="story-head">
   <div class="crumbs">{crumbs}<span class="fresh-line"{fresh(s)}>{NEWB}Published {ago(s.pub, "ago b")}</span></div>
   <h1>{esc(s.title)}</h1>
   <p class="dek">{esc(s.dek)}</p>
   <div class="byl"><span class="av" aria-hidden="true">{esc(initials)}</span><a class="by" href="{u('authors/' + s.fm.get('author', '') + '/')}">{esc(s.author['name'])}</a><span class="sep">·</span><span>{esc(when(s.pub, True))}</span><span class="sep">·</span><span>{s.minutes} min read</span></div>
   {running}
  </header>
  {cover_fig(s)}
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
    return page(s.path, s.title, html_, s.dek, f"static/covers/{s.cover}-1600.webp", og_type="article")


def cover_fig(s: Story, cls: str = "a-cv") -> str:
    """The story's cover with its caption. Covers are AI-generated pictures, and say so."""
    alt = COVERS["covers"].get(s.cover, {}).get("alt", "") or COVER_ALT.get(s.cover, "")
    cap = f"{esc(alt.rstrip('.'))}. " if alt else ""
    return (f'<figure class="{cls}"><div class="ci">{cover_img(s.cover, 1600, lazy=False)}</div>'
            f'<figcaption>{cap}Image: AI-generated.</figcaption></figure>')


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


def daily_page(s: Story) -> str:
    body = render_body(s)
    d = s.pub.date()
    toc = "".join(f'<a href="#{sid}">{esc(t)}</a>' for lv, sid, t in s.headings if lv == 2)
    others = earlier_days(s)[:3]
    more = ""
    if others:
        more = f'<section class="related"><h3>Previous days</h3><div class="cards-col">{"".join(row(x) for x in others)}</div></section>'
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
  <div class="ed-mast"><a href="{u('daily/')}" class="ed-name">Mostly Markets <b>Daily</b></a><span>{edition_label(s)} · {esc(long_date(d))}</span><span class="ed-no">No. {s.edition}</span></div>
  <div class="crumbs" style="margin-top:14px"><span class="fresh-line"{fresh(s)}>{NEWB}Published {ago(s.pub, "ago b")}</span></div>
  <h1>{esc(s.title)}</h1>
  <p class="dek">{esc(s.dek)}</p>
  <div class="byl"><span class="av" aria-hidden="true">{esc(initials)}</span><a class="by" href="{u('authors/' + s.fm.get('author', '') + '/')}">{esc(s.author['name'])}</a><span class="sep">·</span><span>{s.minutes} min read</span><span class="sep">·</span><span>{len(s.takes)} takes</span>{play}</div>
 </header>
 {cover_fig(s, "ed-cover")}
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


def edition_box(s: Story) -> str:
    """An earlier edition as a box: its cover, its date, its headline and dek. A day before The Daily began shows that
    day's closing report ("The close")."""
    label = [edition_label(s), f"No. {s.edition}"] if s.type == "daily" else ["The close"]
    day = s.pub.date() if s.type == "daily" else market_day(s)
    head = re.sub(r"^Stock Market Today:\s*", "", card_title(s), flags=re.I) if s.type == "market-wrap" else card_title(s)
    return (f'<article class="ed-box"{fresh(s)}><a class="cover-link" href="{u(s.path)}" aria-label="{esc(s.title)}"></a>'
            f'{cover_th(s, 800, sizes="(max-width: 640px) 104px, (max-width: 960px) 50vw, 440px")}<div class="tx"><span class="ed-k">{meta_line([f"<b>{esc(long_date(day))}</b>"] + label)}</span>'
            f'<h3>{esc(head)}</h3><p>{esc(s.dek)}</p></div></article>')


def market_day(s: Story) -> dt.date:
    """The trading session a story is about. A closing report: the day it went out (the day before when it went out
    after midnight). An edition of The Daily, out before the open: the session before it (a weekend edition, Friday's).
    Weekends roll back to Friday."""
    if s.type == "daily":
        d = s.pub.date() if s.pub.hour >= 16 else s.pub.date() - dt.timedelta(days=1)
    else:
        d = s.pub.date() if s.pub.hour >= 9 else s.pub.date() - dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def earlier_days(first: Story) -> list[Story]:
    """The days before an edition, newest first: every earlier edition of The Daily, plus, for a session no edition
    covered (before The Daily began), that session's closing report (the market wrap). The edition's own session is
    left out, so its close doesn't repeat it."""
    eds = [x for x in DAILIES if x is not first and x.pub < first.pub]
    covered = {market_day(x) for x in DAILIES if x.pub <= first.pub}
    wraps: dict[dt.date, Story] = {}
    for x in STORIES:  # newest first, so each session keeps its latest close
        if x.type == "market-wrap" and x.pub < first.pub and market_day(x) not in covered:
            wraps.setdefault(market_day(x), x)
    return sorted(eds + list(wraps.values()), key=lambda x: (market_day(x), x.pub), reverse=True)


def meta_line(items: list[str]) -> str:
    """Items joined by dots that wrap only between items, so no line ends or starts mid-item ('No.' / '1')."""
    return " ".join(f'<span class="mi">{x}</span>' for x in items if x)


EDITIONS_SHOWN = 9  # previous days on /daily/ (three rows); /daily/editions/ lists them all


def daily_index():
    """The Daily's front page, laid out like a newspaper's (Opening Bell Daily's): the masthead; the latest edition big
    in the middle, our top stories on its left and the latest on its right; then the previous days as boxes three to
    a row (earlier editions, or before The Daily began, each day's closing report). The edition's takes are on its
    own page and in "Swipe through"."""
    if not DAILIES:
        body = f'<div class="wrap ph"><h1>The Daily</h1><p>The first edition is on its way.</p></div>'
        write("daily/", page("daily/", "The Daily", body, active="daily/"))
        return
    first, rest = DAILIES[0], DAILIES[1:]
    render_body(first)
    pool = [x for x in STORIES if x.type != "daily"]
    recent = [x for x in pool if (pool[0].pub - x.pub) < dt.timedelta(hours=36)]
    top = sorted(recent, key=lambda s: -(s.weight() - (NOW - s.pub).total_seconds() / 3600 / 1.5))[:3]
    latest = [x for x in pool if x not in top][:5]
    tops = "".join(f'<article class="df-tc{"" if i < 2 else " tx-only"}"{fresh(x)}><a class="cover-link" href="{u(x.path)}" '
                   f'aria-label="{esc(x.title)}"></a>{cover_th(x, 800, sizes="(max-width: 640px) 45vw, 270px") if i < 2 else ""}<h3>{esc(card_title(x))}</h3>'
                   f'<div class="mi-k">{ago(x.pub)}<span>{TYPE_LABEL[x.type]}</span></div></article>' for i, x in enumerate(top))
    lis = "".join(f'<li{fresh(x)}><a href="{u(x.path)}">{esc(card_title(x))}</a><div class="mi-k">{ago(x.pub)}<span>{TYPE_LABEL[x.type]}</span></div></li>'
                  for x in latest)
    play = (f'<button class="btn ghost" type="button" data-story-open="ed-{first.date}">{ICON["play"]}<span>Swipe through</span></button>'
            if first.takes else "")
    older = ""
    prev = earlier_days(first)
    if prev:
        # A run of equal days: whole rows of three (no box spans two columns), and every day on /daily/editions/.
        shown = prev[:EDITIONS_SHOWN]
        shown = shown[:len(shown) // 3 * 3] or shown
        kinds = {x.type for x in prev}
        sub = ("Every edition so far" if kinds == {"daily"} else "Each day's close, before The Daily began"
               if "daily" not in kinds else "Every edition, and each day's close before The Daily began")
        more = (f'<a class="see" href="{u("daily/editions/")}">All previous days</a>' if len(prev) > len(shown) else
                f'<p>{sub}</p>')
        cls = "dgrid odd" if len(shown) % 2 else "dgrid"
        older = (f'<section class="dfs"><div class="dfs-h"><h2>Previous days</h2>{more}</div>'
                 f'<div class="{cls}">{"".join(edition_box(x) for x in shown)}</div></section>')
        if len(prev) > len(shown):
            arch = (f'<div class="wrap wd"><header class="dmast sm"><h1><a class="dm-name" href="{u("daily/")}">Mostly Markets <b>Daily</b></a></h1>'
                    f'<p>Every day, newest first: each edition, and the close before The Daily began.</p></header>'
                    f'<section class="dfs"><div class="dgrid{" odd" if (len(prev) + 1) % 2 else ""}">'
                    f'{"".join(edition_box(x) for x in [first] + prev)}</div></section></div>')
            write("daily/editions/", page("daily/editions/", "Every day of The Daily", arch,
                                          "Every edition of Mostly Markets Daily, and each day's close before it began.", active="daily/"))
    meta = NEWB + " " + meta_line([f"<b>{esc(long_date(first.pub.date()))}</b>", edition_label(first), f"No. {first.edition}",
                                   ago(first.pub, "ago q")])
    body = f"""<div class="wrap wd">
<header class="dmast"><a class="dm-name" href="{u('daily/')}">Mostly Markets <b>Daily</b></a>
<p>The one story behind the market, a thread of sharp takes, and the charts that prove them. Every morning, free.</p>
<a class="btn" href="{CFG['subscribe']}">Get it in your inbox</a></header>
<div class="dfront">
<section class="df-side df-top" aria-label="Top stories"><h2>Top stories</h2>{tops}</section>
<article class="df-hero"{fresh(first)}><a class="df-cv" href="{u(first.path)}" aria-label="{esc(first.title)}">{cover_img(first.cover, 1600, lazy=False)}</a>
<div class="ed-k df-k">{meta}</div>
<h1><a href="{u(first.path)}">{esc(first.title)}</a></h1><p class="dek">{esc(first.dek)}</p>
<div class="acts"><a class="btn" href="{u(first.path)}">Read the edition</a>{play}<span class="df-m">{len(first.takes)} takes · {first.minutes} min read</span></div></article>
<aside class="df-side df-latest" aria-label="Latest stories"><h2>Latest</h2><ol>{lis}</ol>{subscribe_box(title="The Daily, in your inbox", text="Every morning before the open: the story behind the market, in charts. Free.")}</aside>
</div>
{older}
</div>
{story_templates([edition_group(first)])}"""
    write("daily/", page("daily/", "The Daily", body, "Every day's edition of Mostly Markets Daily: the story behind the market, in charts.",
                         f"static/covers/{first.cover}-1600.webp", active="daily/"))


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
            "avatar": f'<img src="{u(f"static/covers/{s.cover}-480.webp")}" alt="">', "slides": slides}


def story_templates(groups: list[dict]) -> str:
    out = []
    for g in groups:
        out.append(f'<template class="stg" data-id="{esc(g["id"])}" data-name="{esc(g["name"])}" data-when="{esc(g["when"])}">'
                   f'<div class="stg-av">{g["avatar"]}</div>{"".join(g["slides"])}</template>')
    return "".join(out)


# ---------------------------------------------------------------------- home / feed

def pick_lead(pool: list[Story]) -> Story | None:
    """The top story is the newest one ("start top with recent story"), the Daily included, so it is never older than
    the rows under it; an editor can put another first with featured = true (it leads for a day and a half)."""
    if not pool:
        return None
    feat = [s for s in pool if s.featured and (pool[0].pub - s.pub) < dt.timedelta(hours=36)]
    return feat[0] if feat else pool[0]


def tile(s: Story, size: int = 800) -> str:
    """A grid card (earnings and picks pages): the cover photo on top, then logos, kind, when, headline, dek."""
    return (f'<article class="tile" data-type="{s.type}" data-tickers="{" ".join(s.tickers)}"{fresh(s)}><a class="cover-link" href="{u(s.path)}" aria-label="{esc(s.title)}"></a>'
            f'{cover_th(s, size)}<div class="tx"><div class="c-top">{logos(s.tickers, 24)}<span class="tag">{TYPE_LABEL[s.type]}</span>{ago(s.pub)}</div>'
            f'<h3>{esc(s.title)}</h3><p class="dk">{esc(s.dek)}</p><div class="c-ft">{chips(s, 1)}</div></div></article>')


def hsec(title: str, inner: str, more: tuple[str, str] | None = None, sub: str = "", cls: str = "") -> str:
    link = f'<a class="see" href="{u(more[0])}">{esc(more[1])}</a>' if more else ""
    return (f'<section class="wrap hsec{(" " + cls) if cls else ""}"><div class="hsec-h"><div><h2>{esc(title)}</h2>'
            f'{f"<p>{esc(sub)}</p>" if sub else ""}</div>{link}</div>{inner}</section>')


# Section headings that say nothing on their own, so the top story's card doesn't list them as its points.
GENERIC_HEADS = re.compile(r"^(our (read|take|view|verdict)|what(['’]s| is| comes) next|what to watch|why it matters|"
                           r"the (numbers?( that matter)?|price list|outlook|bottom line|short version|details|background|"
                           r"context|takeaway|setup|catalysts?)|what (happened|stood out)|highlights|key (numbers|takeaways)|"
                           r"sources?|the risks?|bulls?|bears?)\b", re.I)


def hero_points(s: Story, skip: set | None = None, news: list | None = None) -> tuple[str, list[tuple[str, str]]]:
    """What the top story's card lists, as (heading, [(link, line)]): what's inside, each line a link into the story
    (an edition's takes, else the story's section headings when they say something on their own, not "Our read" or
    "What's next"); else, like a newspaper's lead package, our other stories of the last week on the same company,
    leaving out the ones the rows right under the card show (skip), then the newsrooms' latest on it from Top news
    (news)."""
    render_body(s)
    if s.type == "daily" and s.takes:
        return "", [(f"{u(s.path)}#{tk['id']}", tk["title"]) for tk in s.takes[:4]]
    heads = [(f"{u(s.path)}#{sid}", h) for lv, sid, t in s.headings if lv == 2
             for h in [html.unescape(t)] if not GENERIC_HEADS.match(h) and len(h) > 16]
    if len(heads) >= 2:
        return "", heads[:4]
    if not s.tickers:
        return "", []
    t = s.tickers[0]
    if t not in s.title and UMAP[t]["name"].split()[0] not in s.title:
        return "", []  # the company is only related (the Binance theft lists COIN): "More on Coinbase" would mislead
    rel = [(u(x.path), card_title(x)) for x in STORIES if x is not s and x not in (skip or ())
           and abs(x.pub - s.pub) < dt.timedelta(days=7) and x.type != "daily" and t in x.tickers[:2]]
    # then the newsrooms' latest on it from Top news (the X posts the story quotes first): the lead as a package
    for x in sorted(news or [], key=lambda x: (x.get("story") is not s, -x["dt"].timestamp())):
        if len(rel) >= 3:
            break
        if x.get("kind") == "x" and x.get("story") is s:
            rel.append((x["link"], f'{x.get("author") or "On X"}: {one_line(x["text"], 90)}'))
        elif x.get("kind") != "x" and set(x.get("tickers") or []) & set(s.tickers[:2]) and abs(x["dt"] - s.pub) < dt.timedelta(hours=48):
            rel.append((x["url"], f'{x["source"]}: {clip(x["title"], 90)}'))
    return f"More on {UMAP[t]['name']}", rel[:3]


def hero_card(s: Story, skip: set | None = None, news: list | None = None) -> str:
    """The home page's top story as a designed card (the owner's favourite, from 31 October): the cover large on the
    left; on navy, the kicker, a big headline, a quiet dek, what's inside as a numbered list (or more on the story),
    and one button."""
    head, pts = hero_points(s, skip, news)
    ext = ' target="_blank" rel="noopener nofollow"'
    lis = "".join(f'<li><a href="{href}"{ext if href.startswith("http") else ""}><b>{"" if head else i}</b><span>{esc(t)}</span></a></li>'
                  for i, (href, t) in enumerate(pts, 1))
    plist = ((f'<h2 class="hc-ph" id="hc-ph">{esc(head)}</h2><ul class="hc-pts rel" aria-labelledby="hc-ph">{lis}</ul>' if head else
              f'<ol class="hc-pts">{lis}</ol>') if lis else "")
    daily = s.type == "daily"
    kick = (f'<b>{esc(long_date(s.pub.date()))}</b>' if daily else
            f'<b>{TYPE_LABEL[s.type]}</b><span class="hc-sep">·</span>{ago(s.pub, "ago q")}')
    badge = (f'<span class="hc-badge">Mostly Markets <b>Daily</b> · No. {s.edition}</span>' if daily else "")
    play = (f'<button class="btn ghost" type="button" data-story-open="ed-{s.date}">{ICON["play"]}<span>Swipe through</span></button>'
            if daily and s.takes else "")
    cta = "Read the edition" if daily else "Read the story"
    meta = (f'{len(s.takes)} takes · {s.minutes} min read' if daily and s.takes else
            f'{esc(s.author["name"])} · {s.minutes} min read')
    return (f'<article class="hc{" pts" if pts else ""}"{fresh(s)}>'
            f'<a class="hc-cv" href="{u(s.path)}" tabindex="-1" aria-hidden="true">{cover_img(s.cover, 1600, lazy=False)}{badge}</a>'
            f'<div class="hc-tx"><div class="hc-k">{NEWB}{kick}</div>'
            f'<h1><a href="{u(s.path)}">{esc(card_title(s))}</a></h1><p class="dek">{esc(dek1(s.dek) if pts else s.dek)}</p>'
            f'{plist}'
            f'<div class="hc-acts"><a class="btn" href="{u(s.path)}">{cta}</a>{play}<span class="hc-m">{meta}</span></div></div>'
            f'</article>' + (story_templates([edition_group(s)]) if play else ""))


# The shelves between the home page's rows, in the order they come: (key, title, the story types, the line under the
# title, the page that lists them all).
SHELVES = [("earnings", "Earnings", ("earnings-recap", "earnings-preview"), "What the reports said, and how the stocks took it",
            "earnings/"),
           ("moves", "Why it moved", ("why-it-moved", "movers"), "The big moves, explained", None),
           ("picks", "Our picks", ("list",), "Stocks we like and the ones we'd skip, with our reasons", None),
           ("charts", "Charts", ("chart",), "One chart, one point", None)]
CHEVRON = ('<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" '
           'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="{d}"/></svg>')


def shelf_card(s: Story) -> str:
    """A shelf's card: the cover on top, the headline right under it, then one price tag and when."""
    return (f'<article class="sh-c" data-type="{s.type}"{fresh(s)}><a class="cover-link" href="{u(s.path)}" aria-label="{esc(s.title)}"></a>'
            f'{cover_th(s, 800, sizes="(max-width: 640px) 76vw, 300px")}<div class="sh-tx"><h3>{esc(card_title(s))}</h3>'
            f'<div class="r8-ft">{chips(s, 1) if s.moves else ""}{ago(s.pub, "ago q s")}{NEWB}</div></div></article>')


def shelf(key: str, title: str, sub: str, items: list[Story], more: str | None, hidden: bool = False) -> str:
    """A horizontal bar of one kind of story between the rows: swipe it on a phone, use the arrows on a computer."""
    nav = (f'<a class="see" href="{u(more)}">See all</a>' if more else "") + "".join(
        f'<button class="ib sh-b" type="button" data-dir="{d}" aria-label="{lab}">{CHEVRON.format(d=p)}</button>'
        for d, lab, p in ((-1, "Scroll back", "M15 18l-6-6 6-6"), (1, "Scroll on", "M9 18l6-6-6-6")))
    return (f'<section class="shelf" data-shelf="{key}" aria-label="{esc(title)}"{" hidden" if hidden else ""}><div class="sh-h">'
            f'<div><h2>{esc(title)}</h2><p>{esc(sub)}</p></div><div class="sh-nav">{nav}</div></div>'
            f'<div class="sh-tr">{"".join(shelf_card(s) for s in items)}</div></section>')


# The outlets whose headlines run in Top news: newsrooms that do their own reporting. Stock pages show every source.
FEED_SOURCES = {"Reuters", "Bloomberg", "WSJ", "Dow Jones", "Barron's", "CNBC", "MarketWatch", "Financial Times",
                "The New York Times", "AP", "Nikkei Asia", "Fortune", "Business Insider", "The Economist",
                "Investor's Business Daily", "Axios", "The Information", "CNN", "BBC", "The Guardian"}
SPATH = ROOT / "assets/sources/sources.json"
SOURCES = json.loads(SPATH.read_text()) if SPATH.exists() else {}


def src_av(name: str, size: int = 40) -> str:
    """A news outlet's logo in a circle (assets/sources/), or its initials."""
    k = (SOURCES.get(name) or {}).get("key")
    if k:
        return (f'<span class="sav" style="--s:{size}px"><img src="{u(f"static/sources/{k}.png")}" alt="" loading="lazy" '
                f'decoding="async"></span>')
    letters = "".join(w[0] for w in re.findall(r"[A-Za-z]+", name)[:2]).upper() or "N"
    return f'<span class="sav mono" style="--s:{size}px" aria-hidden="true"><b>{esc(letters)}</b></span>'


# Not news: personal-finance columns, shopping guides and members-only clubs that ride along in the market wires.
JUNK_URL = ("/select/", "/buyside/", "/personal-finance/", "/retirement/", "/guides/", "/investingclub/", "/picks/",
            "moneyist", "/coupons/", "/underscored/", "/health/", "/lifestyle/", "/real-estate/")
JUNK_TITLE = re.compile(r"^(i['’]m|i['’]ve|i |my |should (i|we)\b|ask |dear )|['’]re in our \d|annuit|"
                        r"\bbest\b.*\b(savings accounts|credit cards|cd rates|accounts|cards)\b|mortgage rates today|"
                        r"\bcramer\b|^brief-", re.I)  # BRIEF- lines are Reuters' terse data wires: stock pages keep them
STOP = {"with", "after", "from", "that", "this", "says", "said", "will", "have", "into", "over", "amid", "their", "about",
        "more", "than", "were", "what", "when", "they", "shares", "stock", "stocks"}


def _words(t: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", t.lower()) if len(w) > 3 and w not in STOP}


def _key(t: str) -> str:
    """A headline with curly quotes, spacing and case ironed out: the same article in two feeds is one post."""
    return re.sub(r"\s+", " ", t.translate({0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"'})).strip().casefold()


def feed_news(since: dt.datetime, until: dt.datetime) -> list[dict]:
    """Newsroom headlines published between since and until, newest first: the market wires plus each company's
    news, without personal-finance columns. One post per story: the same headline from several tickers' feeds, or
    a close rewrite of it from another outlet within six hours, merges into the first, keeping every ticker. A copy
    re-posted days later (Google News re-dates WSJ's print edition) merges into the original, so it doesn't come back
    as Saturday's news: the five days before since are read for that."""
    raw: list[dict] = []
    for key, d in NEWS.items():
        t = None if key == "_market" else key
        if t and t not in UMAP:
            continue
        for it in d.get("items", []):
            if (it.get("kind") != "news" or it.get("source") not in FEED_SOURCES or not it.get("title")
                    or not str(it.get("url") or "").startswith(("https://", "http://"))):
                continue
            if any(j in it["url"] for j in JUNK_URL) or JUNK_TITLE.search(it["title"]):
                continue
            try:
                when_ = dt.datetime.fromisoformat(it["published"]).astimezone(ET)
            except Exception:  # noqa: BLE001
                continue
            if since - dt.timedelta(days=5) <= when_ <= min(until, NOW + dt.timedelta(minutes=5)):
                raw.append({**it, "dt": when_, "t": t})
    raw.sort(key=lambda x: x["dt"])  # oldest first: the first report keeps the post
    out: list[dict] = []
    for it in raw:
        w, k = _words(it["title"]), _key(it["title"])
        # A close rewrite only merges with a post from the same feed (the same company, or both market-wide).
        dup = next((x for x in out if x["k"] == k or (
            it["t"] in x["feeds"] and abs((x["dt"] - it["dt"]).total_seconds()) < 6 * 3600 and len(w & x["w"]) >= 4 and
            len(w & x["w"]) / len(w | x["w"]) >= .34) or (
            it["source"] == x["source"] and it["t"] in x["feeds"] and len(w & x["w"]) >= 3
            and len(w & x["w"]) / len(w | x["w"]) >= .6) or (
            # the same outlet's second take on a company's news within half an hour ("Chevron Stock Rises as Oil
            # Price Surge Fuels Earnings Beat" and "Chevron Beats Sky-High Targets as Oil Prices Surge")
            it["source"] == x["source"] and it["t"] and it["t"] in x["feeds"]
            and abs((x["dt"] - it["dt"]).total_seconds()) < 1800 and len(w & x["w"]) >= 2)), None)
        if dup is None:
            dup = {**it, "w": w, "k": k, "feeds": set(), "tickers": [], "also": list(it.get("also") or [])}
            out.append(dup)
        elif it["source"] != dup["source"] and it["source"] not in dup["also"]:
            dup["also"].append(it["source"])
        dup["feeds"].add(it["t"])
        if it["t"] and it["t"] not in dup["tickers"]:
            dup["tickers"].append(it["t"])
    return sorted((x for x in out if x["dt"] >= since), key=lambda x: x["dt"], reverse=True)


TIER = {"Reuters": 1, "Bloomberg": 1, "WSJ": 1, "Financial Times": 1, "AP": 1, "The New York Times": .8, "Dow Jones": .8,
        "CNBC": .8, "Nikkei Asia": .8, "The Economist": .8, "The Information": .8, "Barron's": .6, "Axios": .6}
BIG_NEWS = re.compile(r"\b(plung|soar|surg|tumbl|sink|sank|slump|crash|record|worst|biggest|halt|bankrupt|acquir|to buy|"
                      r"merger|takeover|layoff|guidance|forecast|outlook|fed\b|powell|rate cut|rate hike|inflation|jobs report|"
                      r"payrolls|tariff|opec|sanction|s&p 500|nasdaq|dow\b|treasur|yields?\b|recession|ipo\b|downgrad)", re.I)
SOFT_NEWS = re.compile(r"\?\s*$|^(opinion|commentary|yes,|here['’]s|watch these|funds:|behind the scenes|what to|how to)|"
                       r"\b(should you|could|might)\b", re.I)
WIRE_NEWS = re.compile(r"\b(announces?|signs|tender offers?|price target|net proceeds|initiates|reiterates|prices? .*offering|"
                       r"offering of|declares|dividend|to present at|conference call|webcast|files? for|completes?)\b", re.I)


def news_weight(x: dict, ours: set[str]) -> float:
    """How big a headline is: how many newsrooms ran it, whether it's about the whole market or a giant company, whether
    it's about a stock we cover this week, and whether it reports a move or a decision rather than an opinion."""
    big = max([(Q.get(t) or {}).get("cap") or 0 for t in x["tickers"]] or [0])
    w = TIER.get(x["source"], .4) + min(len([a for a in x.get("also") or [] if a in FEED_SOURCES]), 3)
    w += (1.25 if not x["tickers"] else 0) + (1.25 if big > 1e12 else 1 if big > 2e11 else .5 if big > 5e10 else 0)
    w += (.75 if ours & set(x["tickers"]) else 0) + (.75 if BIG_NEWS.search(x["title"]) else 0)
    return w - (1.25 if SOFT_NEWS.search(x["title"]) else 0) - (1.25 if WIRE_NEWS.search(x["title"]) else 0)


def top_news(n: int = 40, floor: int = 24, big: int = 10) -> tuple[dict | None, list[dict]]:
    """Top news, the home page's right-hand column: newsroom headlines and the X posts our stories quote, newest first.
    A headline stays as long as it matters, from about five hours for a minor one to a day and a half for news every
    newsroom ran. The column holds 40: the 10 biggest still in their time, however old, then the rest by weight less a
    point every four hours, so the big stories are still there after a busy morning's small ones have gone. The biggest of the last day is pinned
    on top. A quiet weekend is topped up with the biggest headlines of the last two days."""
    ours = {t for s in STORIES[:30] for t in s.tickers}
    pool = feed_news(NOW - dt.timedelta(hours=48), NOW)
    for x in pool:
        x["w"] = news_weight(x, ours)
        x["age"] = (NOW - x["dt"]).total_seconds() / 3600
    # A running story's updates (the same companies, much the same words, within three hours) show as one post: the
    # newest version, as big as the biggest of them.
    for x in pool:  # newest first
        if x.get("gone") or not x["tickers"]:
            continue
        for y in pool:
            if (y is not x and not y.get("gone") and y["tickers"] == x["tickers"] and y["dt"] <= x["dt"]
                    and (x["dt"] - y["dt"]) < dt.timedelta(hours=3) and len(_words(x["title"]) & _words(y["title"])) >= 3):
                y["gone"] = True
                x["w"] = max(x["w"], y["w"])
    pool = [x for x in pool if not x.get("gone")]
    keep = [x for x in pool if x["age"] < min(36.0, 4 + 5 * max(x["w"], 0))]
    if len(keep) < floor:
        keep += sorted((x for x in pool if x not in keep), key=lambda x: -x["w"])[:floor - len(keep)]
    pin = max((x for x in keep if x["age"] < 24 and x["w"] >= 3.25), key=lambda x: (x["w"], x["dt"]), default=None)
    keep = [x for x in keep if x is not pin]
    biggest = sorted((x for x in keep if x["w"] >= 3.5), key=lambda x: (-x["w"], -x["age"]))[:big]
    rest = sorted((x for x in keep if x not in biggest), key=lambda x: x["w"] - x["age"] / 4, reverse=True)
    chosen = biggest + rest[:max(0, n - len(biggest))]
    # No company fills the column: at most two posts each (the heaviest), so it reads as the day's news, not one story.
    per: dict[str, int] = defaultdict(int)
    capped = []
    for x in sorted(chosen, key=lambda x: -x["w"]):
        t = (x["tickers"] or [None])[0]
        if t and per[t] >= 2:
            continue
        per[t] += 1 if t else 0
        capped.append(x)
    chosen = capped
    # The X posts our stories quote stay three days: a story chose them.
    xs = [{**x, "kind": "x"} for x in cited_posts(STORIES[:40]) if (NOW - x["dt"]) < dt.timedelta(hours=72)]
    return pin, sorted(chosen + xs, key=lambda x: x["dt"], reverse=True)


def cited_posts(stories: list[Story]) -> list[dict]:
    """X posts our stories quote (```tweet blocks, cached by pipeline/news.py), with the story that quotes each."""
    out, seen = [], set()
    for s in stories:
        for url in re.findall(r"```tweet\s*\n\s*(\S+)\s*\n\s*```", s.body):
            m = re.search(r"/status/(\d+)", url)
            tw = TWEETS.get(m.group(1)) if m else None
            if not tw or not tw.get("text") or m.group(1) in seen:
                continue
            try:
                d = dt.datetime.fromisoformat(tw["created_at"].replace("Z", "+00:00")).astimezone(ET)
            except Exception:  # noqa: BLE001
                continue
            if d <= NOW + dt.timedelta(minutes=5) and (s.pub - d) < dt.timedelta(days=7):
                seen.add(m.group(1))
                out.append({**tw, "dt": d, "story": s,
                            "link": f'https://x.com/{tw.get("handle") or "i"}/status/{m.group(1)}'})
    return out


def post_news(x: dict) -> str:
    """A newsroom's headline as a post (a stock page's headlines): the outlet's logo and name, how long ago, and the
    headline, linking to the publisher."""
    also = (f'<span class="p-also">and {esc(x["also"][0])}</span>' if len(x.get("also") or []) == 1 else
            f'<span class="p-also">and {len(x["also"])} more</span>' if x.get("also") else "")
    src = x.get("source") or ""
    return (f'<article class="post pn" data-pub="{x["dt"].isoformat()}">'
            f'<a class="cover-link" href="{esc(x["url"])}" target="_blank" rel="noopener nofollow" aria-label="{esc(x["title"])} ({esc(src)})"></a>'
            f'<div class="p-av">{src_av(src, 40)}</div><div class="p-b">'
            f'<div class="p-h"><b>{esc(src)}</b>{ago(x["dt"], "ago q")}{also}</div>'
            f'<p class="p-t">{esc(x["title"])}</p></div></article>')


def cashtags(ts: list[str]) -> str:
    """The companies a post is about as X-style cashtags ($INTC), each a link to its stock page."""
    shown = [t for t in ts if t not in SECOND_CLASS] or ts[:1]  # one tag per company
    return "".join(f' <a class="xp-tk" href="{u(tpath(t))}">${esc(t)}</a>' for t in shown[:3])


# A headline that credits another newsroom's scoop ("... Robotics Push - The Information") shows the credit in the
# post's byline ("Reuters, via The Information") rather than as the end of the one-liner.
VIA = re.compile(r"\s+[-–—]\s+(The Information|Bloomberg(?: News)?|The Wall Street Journal|WSJ|Financial Times|FT|"
                 r"Reuters|CNBC|Barron's|Axios|Semafor|The Times|Nikkei(?: Asia)?|Filing|Conf\. Call|Report)\s*$")


def one_line(t: str, n: int) -> str:
    """A post's text cut to a one-liner: its first sentence when that's short enough, else about n characters."""
    t = re.sub(r"\s+", " ", t).strip()
    first = re.split(r"(?<=[a-z0-9%)][.!?])\s+(?=[A-Z\"“])", t, maxsplit=1)[0]
    return first if len(first) <= n else clip(t, n)


def xpost(x: dict, label: str = "", hero: bool = False) -> str:
    """A post in Top news, a one-liner as on X: what happened first, then who said it and when, small. A newsroom's
    headline links to its publisher, with cashtags for the companies; an X post our story quotes links to the post and
    to our story. The newest post is drawn largest (hero) and the day's biggest is labelled "Top headline"."""
    lab = (f'<div class="xp-l{" lt" if label == "Latest" else ""}">{esc(label)}</div>' if label else "")
    cls = " hero" if hero else " pin" if label else ""
    if x.get("kind") == "x":
        s = x["story"]
        text = esc(one_line(x["text"], 120))
        return (f'<article class="xp xx{cls}" data-id="x{esc(x["link"].rsplit("/", 1)[-1])}" data-pub="{x["dt"].isoformat()}">'
                f'<a class="cover-link" href="{esc(x["link"])}" target="_blank" rel="noopener" '
                f'aria-label="Post by {esc(x.get("author") or "")} on X"></a>{lab}<p class="xp-t">{text}</p>'
                f'<div class="xp-m"><b>{esc(x.get("author") or "")}</b><span>on X</span>{ago(x["dt"], "ago q s")}'
                f'<a class="xp-in" href="{u(s.path)}" aria-label="Our story: {esc(s.title)}">Our story</a></div></article>')
    src = x.get("source") or ""
    title = x["title"]
    m = VIA.search(title)
    via = ""
    if m and m.group(1).lower() not in src.lower():
        title, via = title[:m.start()], m.group(1)
        via = "" if via in ("Filing", "Conf. Call", "Report") else via
    also = x.get("also") or []
    also = (f'<span class="xp-also" title="Also in {esc(", ".join(also))}">and {len(also)} more</span>' if also else "")
    who = f'<b>{esc(src)}</b>' + (f'<span>via {esc(via)}</span>' if via else "")
    return (f'<article class="xp{cls}" data-id="{hashlib.md5(x["k"].encode()).hexdigest()[:10]}" '
            f'data-pub="{x["dt"].isoformat()}"><a class="cover-link" href="{esc(x["url"])}" target="_blank" rel="noopener nofollow" '
            f'aria-label="{esc(x["title"])} ({esc(src)})"></a>{lab}<p class="xp-t">{esc(clip(title, 120))}{cashtags(x["tickers"])}</p>'
            f'<div class="xp-m">{who}{also}{ago(x["dt"], "ago q s")}</div></article>')


def news_rail(pin: dict | None, stream: list[dict]) -> str:
    """Top news: one-liners, newest first, the newest drawn largest and the day's biggest right under it. The column
    keeps itself up to date (app.js re-reads data/topnews.json every few minutes and offers the new posts, as X does)."""
    items = sorted(stream + ([pin] if pin else []), key=lambda x: x["dt"], reverse=True)
    if pin and items and items[0] is not pin:  # the big story sits under the newest post
        items.remove(pin)
        items.insert(1, pin)
    posts = "".join(xpost(x, "Top headline" if x is pin else "Latest" if i == 0 else "", hero=i == 0)
                    for i, x in enumerate(items))
    write("data/topnews.json", json.dumps({"asof": NOW.isoformat(), "html": posts}, separators=(",", ":")))
    if not posts:  # the news pull failed: say so, and the next build with headlines fills the column
        posts = '<p class="xr-empty">No headlines in the last two days.</p>'
    return (f'<aside class="hm-rail" id="top-news" aria-label="Top news"><div class="xr-h"><h2>Top news</h2>'
            f'{"<span class=live>Live</span>" if "xr-empty" not in posts else ""}<span class="rv-up">Updated {ago(NOW, "ago q s xr-asof")}</span></div>'
            f'<button class="xr-new" type="button" hidden></button><div class="xr-feed">{posts}</div>'
            f'<p class="xr-ft">Headlines link to their publishers. The biggest stay longest.</p></aside>')


HOME_TABS = '<div class="hm-tabs" role="group" aria-label="Show"><button type="button" data-view="stories" aria-pressed="true">Stories</button><button type="button" data-view="news" aria-pressed="false">Top news</button></div>'


def home_pages():
    """The home page: our stories on the left, Top news on the right. The top story first, a bit bigger; then our
    stories one under another, StockStory-style, with a horizontal shelf of one kind of story (earnings, the day's
    moves, our picks, charts) after every four rows. The older pages list everything else, newest first."""
    size = CFG["feed_page_size"]
    lead = pick_lead(STORIES)
    rest = [s for s in STORIES if s is not lead]
    live = []  # a shelf needs three stories to fill a screen's width
    for key, title, types, sub, more in SHELVES:
        items = [s for s in rest if s.type in types][:12]
        if len(items) >= 3:
            live.append((key, title, types, sub, items, more))
    shelved = {t for x in live for t in x[2]}
    first = [s for s in rest if s.type not in shelved][:4 * (len(live) + 1)]
    # Borrowed topic photos are spread in the order the page shows the stories, so two cards side by side on a shelf
    # don't share one; every other page then uses the same photo for the story.
    order = ([lead] if lead else []) + [x for i in range(len(live) + 1)
                                        for x in first[i * 4:i * 4 + 4] + (live[i][4] if i < len(live) else [])]
    spread_covers(order + [s for s in STORIES if s not in order])
    # Your stocks: the stocks you follow (app.js fills it from data/stories.json; it stays hidden until you follow one).
    blocks = [shelf("mine", "Your stocks", "The latest on the stocks you follow", [], None, True)]
    write("data/stories.json", json.dumps([{"t": s.title, "p": s.path, "k": s.tickers[:4], "c": s.cover, "d": s.pub.isoformat()}
                                           for s in STORIES[:200]], separators=(",", ":")))
    for i in range(len(live) + 1):
        if first[i * 4:i * 4 + 4]:
            blocks.append(f'<div class="rows8">{"".join(row(s) for s in first[i * 4:i * 4 + 4])}</div>')
        if i < len(live):
            key, title, _, sub, items, more = live[i]
            blocks.append(shelf(key, title, sub, items, more))
    shown = set(first) | {s for x in live for s in x[4]}
    later = [s for s in rest if s not in shown]
    pages = 1 + math.ceil(len(later) / size)
    tn = top_news()
    rail = news_rail(*tn)
    for pi in range(pages):
        nav = []
        if pi > 0:
            nav.append(f'<a class="btn ghost" href="{u("" if pi == 1 else f"page/{pi}/")}">Newer stories</a>')
        if pi < pages - 1:
            nav.append(f'<a class="btn ghost" href="{u(f"page/{pi + 2}/")}">Older stories</a>')
        if pi == 0:
            main = "".join(blocks)
        else:
            main = (f'<h1 class="hm-pg">Older stories, page {pi + 1}</h1>'
                    f'<div class="rows8">{"".join(row(s) for s in later[(pi - 1) * size:pi * size])}</div>')
        hero = (f'<section class="hero8">{hero_card(lead, set(first[:4]), tn[1] + ([tn[0]] if tn[0] else []))}</section>'
                if pi == 0 and lead else "")
        # The top story spans both columns; on a phone it belongs to the Stories tab, so it sits after the tabs.
        body = (f'<div class="wrap wd"><div class="hm">{HOME_TABS}{hero}<div class="hm-main">{main}'
                f'<div class="more">{"".join(nav)}</div>{subscribe_box(wide=True) if pi == 0 else ""}</div>{rail}</div></div>')
        path = "" if pi == 0 else f"page/{pi + 1}/"
        title = CFG["name"] + (": " + CFG["tagline"] if pi == 0 else f" | Latest stories, page {pi + 1}")
        write(path, page(path, title, body, CFG["tagline"] + " Why-it-moved stories, earnings, analysis and our picks.",
                         f"static/covers/{lead.cover}-1600.webp" if lead else None, active=""))
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
                      f'<p class="empty" style="text-align:left;padding:14px 0">We haven\'t written about {esc(name)} yet. Follow it, and its first story will show on the home page, under Your stocks.</p>')
                   + (f'<h3 class="sh3">Headlines from around the web</h3><div class="feed sfeed">'
                      f'{"".join(post_news(i) for i in heads)}</div>' if heads else "")
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
    for src, name in ((ROOT / "assets/covers", "covers"), (ROOT / "assets/sources", "sources")):
        dst_dir = out / name
        dst_dir.mkdir(exist_ok=True)
        for f in src.rglob("*"):
            if f.suffix not in (".webp", ".png"):
                continue
            dst = dst_dir / f.relative_to(src)
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
    n = home_pages()  # first: it decides which photo each story borrows (spread_covers)
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
