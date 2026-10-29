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
from marketdata import read_prices  # noqa: E402
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
TYPE_LABEL = {"market-wrap": "Markets", "why-it-moved": "Why it moved", "movers": "Big movers",
              "earnings-recap": "Earnings", "earnings-preview": "Earnings preview", "list": "Our picks",
              "macro": "Economy", "chart": "Chart", "analysis": "Analysis"}
FILTERS = [("all", "All"), ("why-it-moved,movers", "Why it moved"), ("earnings-recap,earnings-preview", "Earnings"),
           ("market-wrap,macro,chart", "Markets & economy"), ("list,analysis", "Our picks & analysis"),
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
        self.path = f"news/{self.date}/{self.slug}/"
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
        base = {"market-wrap": 6, "earnings-recap": 5, "macro": 5, "analysis": 4, "why-it-moved": 3, "list": 3,
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

# ---------------------------------------------------------------------- page shell

ICON = {
    "search": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/></svg>',
    "theme": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z"/></svg>',
    "plus": '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
}
NAV = [("", "Latest"), ("discover/", "Discover"), ("earnings/", "Earnings"), ("stocks/", "Stocks")]


def page(path: str, title: str, body: str, desc: str = "", image: str | None = None, active: str = "",
         og_type: str = "website", extra_head: str = "") -> str:
    full_title = title if title.endswith(CFG["name"]) else f"{title} | {CFG['name']}"
    desc = desc or CFG["tagline"]
    img = absu(image) if image else absu("static/og.jpg")
    robots = "" if LAUNCHED else '<meta name="robots" content="noindex, nofollow">'
    nav = "".join(f'<a href="{u(p)}"{" aria-current=page" if active == p else ""}>{n}</a>' for p, n in NAV)
    fonts = ("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Newsreader:ital,opsz,wght@"
             "0,6..72,400..700;1,6..72,400&family=IBM+Plex+Mono:wght@500;600&display=swap")
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
<meta name="theme-color" content="#faf8f3" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#12110e" media="(prefers-color-scheme: dark)">
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

def chip(m: dict) -> str:
    s = m.get("s")
    tag = {"after-hours": "AH", "pre-market": "PM"}.get(s, "")
    c = m.get("c")
    arrow = "" if c is None else ("▲" if c >= 0 else "▼")
    return (f'<span class="pc">{m["t"]}<i class="{tone(c)}">{arrow}{abs(c):.1f}%</i>'
            f'{f"<small>{tag}</small>" if tag else ""}</span>') if c is not None else f'<span class="pc">{m["t"]}</span>'


def chips(s: Story, limit=3) -> str:
    if not s.moves:
        return ""
    extra = len(s.moves) - limit
    return '<span class="pcs">' + "".join(chip(m) for m in s.moves[:limit]) + (
        f'<span class="pc">+{extra}</span>' if extra > 0 else "") + "</span>"


def cover_img(key: str, size: int, cls: str = "", lazy=True, alt=True) -> str:
    a = esc(COVERS["covers"].get(key, {}).get("alt", "")) if alt else ""
    srcset = ""
    if size == 1600:
        srcset = f' srcset="{u(f"static/covers/{key}-800.webp")} 800w, {u(f"static/covers/{key}-1600.webp")} 1600w" sizes="(max-width: 760px) 100vw, 680px"'
    return (f'<img src="{u(f"static/covers/{key}-{size}.webp")}"{srcset} alt="{a}"'
            f'{" loading=lazy decoding=async" if lazy else ""} class="{cls}">')


def time_tag(s: Story, rel=True) -> str:
    return f'<time datetime="{s.pub.isoformat()}"{" data-rel" if rel else ""}>{esc(ampm(s.pub))} ET</time>'


def row(s: Story) -> str:
    return (f'<article class="row" data-type="{s.type}" data-tickers="{" ".join(s.tickers)}"><a href="{u(s.path)}">'
            f'<div><div class="top-l"><span class="kick">{TYPE_LABEL[s.type]}</span>{chips(s)}</div>'
            f'<h3>{esc(s.title)}</h3><p>{esc(s.dek)}</p>'
            f'<div class="meta" style="margin-top:8px">{time_tag(s)}<span class="sep"></span><span>{esc(s.author["name"])}</span></div></div>'
            f'<div class="th">{cover_img(s.cover, 480)}</div></a></article>')


def mini_rows(stories: list[Story]) -> str:
    out = []
    last_day = None
    for s in stories:
        d = s.pub.date()
        if d != last_day:
            out.append(f'<div class="day"><span>{day_title(d)}</span></div>')
            last_day = d
        out.append(row(s))
    return "".join(out)


def subscribe_box(wide=False, title="The close, in your inbox", text=None) -> str:
    text = text or "Every market day, the stories that moved stocks and why. Free, from the Mostly Markets newsletter."
    return (f'<aside class="sub{" wide" if wide else ""}"><div><h4>{esc(title)}</h4><p>{esc(text)}</p></div>'
            f'<a class="btn" href="{CFG["subscribe"]}">Subscribe free</a></aside>')


# ---------------------------------------------------------------------- story page

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
                                 spec.get("subtitle") or f"{name}, daily close, $", spec.get("mark", "last"))
        if k == "bars":
            return C.bars_chart(spec)
        if k == "hbars":
            return C.hbars_chart(spec)
        if k == "line":
            return C.line_chart(spec)
    except Exception as e:  # noqa: BLE001
        print(f"  chart failed in {story.slug}: {e}")
    return ""


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
            cards.append(f'<a class="pk {kind}" href="{u(tpath(t))}"><span class="lab">{"We love" if kind == "love" else "We hate"}</span>'
                         f'<span class="tt">{t}</span><span class="nm">{esc(UMAP[t]["name"])} · {esc(UMAP[t]["industry"])}</span>'
                         f'<span class="pr"><span>{money(price)}</span><span class="{tone(r1)}">{pct(r1, 1)} 1y</span></span></a>')
    return f'<div class="picks">{"".join(cards)}</div>'


def block_highlights(text: str, r: Renderer) -> str:
    lines = [x for x in text.strip().splitlines() if x.strip()]
    title = lines[0].lstrip("# ").strip() if lines and not lines[0].lstrip().startswith("-") else "Highlights"
    items = [x.strip()[2:] for x in lines if x.strip().startswith("- ")]
    lis = "".join(f"<li>{r.inline(x)}</li>" for x in items)
    return f'<aside class="hlbox"><p class="ht">{esc(title)}</p><ul>{lis}</ul></aside>'


def render_body(s: Story) -> str:
    r = Renderer(link_ticker=lambda t: u(tpath(t)) if t in UMAP else None, url=u, blocks={})
    r.blocks = {"chart": lambda x: block_chart(x, s), "picks": lambda x: block_picks(x, s),
                "highlights": lambda x: block_highlights(x, r)}
    return r.render(s.body)


def stockbar(s: Story) -> str:
    if not s.tickers:
        return ""
    rows = []
    mv = {m["t"]: m for m in s.moves}
    for t in s.tickers[:5]:
        m = mv.get(t)
        sess = {"after-hours": "after hours", "pre-market": "before the open", "regular": "intraday", "close": "at the close"}.get(
            (m or {}).get("s"), "")
        moved = (f'<span class="{tone(m["c"])}">{"▲" if m["c"] >= 0 else "▼"} {abs(m["c"]):.2f}%</span> {money(m["p"])}'
                 if m and m.get("c") is not None else "")
        q = Q.get(t)
        now = (f'<small>Now <span data-live="{t}" data-k="price">{money(q["price"])}</span> '
               f'<span data-live="{t}" data-k="chg" class="{tone(q.get("change_pct"))}">{pct(q.get("change_pct"))}</span></small>'
               if q else "")
        rows.append(f'<div class="sbr"><a class="t" href="{u(tpath(t))}">{t}</a><a class="n" href="{u(tpath(t))}">{esc(UMAP[t]["name"])}</a>'
                    f'<div class="p">{moved}{f" <small>{sess}, {s.pub.day} {MON[s.pub.month - 1]}</small>" if moved else ""}{now if not moved else ""}</div>'
                    f'<button class="btn sm ghost" type="button" data-follow="{t}" aria-pressed="false">{ICON["plus"]}<span>Follow</span></button></div>')
    return f'<div class="stockbar">{"".join(rows)}</div>'


def story_page(s: Story) -> str:
    body = render_body(s)
    sector = UMAP[s.tickers[0]]["sector"] if s.tickers else None
    crumbs = f'<span class="kick hl">{TYPE_LABEL[s.type]}</span>'
    if sector:
        crumbs += f'<a class="kick" href="{u("sectors/" + slugify(sector) + "/")}">{esc(sector)}</a>'
    cap = COVERS["covers"].get(s.cover, {}).get("alt", "")
    more = []
    if s.tickers:
        t = s.tickers[0]
        others = [x for x in BY_TICKER[t] if x is not s][:4]
        if others:
            more.append(f'<section class="related"><h3>More on {esc(UMAP[t]["name"])}</h3>{"".join(row(x) for x in others)}</section>')
    latest = [x for x in STORIES if x is not s and x not in BY_TICKER.get(s.tickers[0] if s.tickers else "", [])][:5]
    more.append(f'<section class="related"><h3>Latest from Mostly Markets</h3>{"".join(row(x) for x in latest)}</section>')
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
    html_ = f"""<article class="story wrap">
 <div class="read">
  <div class="crumbs">{crumbs}</div>
  <h1>{esc(s.title)}</h1>
  <p class="dek">{esc(s.dek)}</p>
  <div class="byl"><a class="by" href="{u('authors/' + s.fm.get('author', '') + '/')}">{esc(s.author['name'])}</a><span class="sep">·</span><span>{esc(s.author.get('role', ''))}</span><span class="sep">·</span><time datetime="{s.pub.isoformat()}">{esc(when(s.pub, True))}</time><span class="sep">·</span><span>{s.minutes} min read</span></div>
  {stockbar(s)}
  <figure class="cover"><div class="ci">{cover_img(s.cover, 1600, lazy=False)}</div><figcaption>{esc(cap)}. Image: AI-generated.</figcaption></figure>
  <div class="prose">{body}</div>
  {endbox}
  <p class="disc">Mostly Markets is for information and education only and isn't investment advice. {esc(s.author['name'])} is a pen name. Prices are from Nasdaq and CNBC as of the time stated.</p>
  {''.join(more)}
 </div>
</article>
<script type="application/ld+json">{json.dumps(ld)}</script>"""
    return page(s.path, s.title, html_, s.dek, f"static/covers/{s.cover}-1600.webp", og_type="article")


# ---------------------------------------------------------------------- home / feed

def pick_lead(pool: list[Story]) -> tuple[Story, list[Story]]:
    if not pool:
        return None, []
    newest_day = pool[0].pub.date()
    recent = [s for s in pool if (pool[0].pub - s.pub) < dt.timedelta(hours=30)]
    feat = [s for s in recent if s.featured]
    lead = feat[0] if feat else max(recent, key=lambda s: (s.weight(), s.pub))
    rest = sorted([s for s in recent if s is not lead], key=lambda s: (s.weight(), s.pub), reverse=True)
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
    lead, tops = pick_lead(STORIES)
    skip = {id(lead)} | {id(x) for x in tops}
    feed = [s for s in STORIES if id(s) not in skip]
    pages = max(1, math.ceil(len(feed) / size))
    chips_ = "".join(f'<button class="chip" type="button" data-filter="{k}" aria-pressed="{"true" if k == "all" else "false"}">{n}</button>'
                     for k, n in FILTERS)
    for pi in range(pages):
        items = feed[pi * size:(pi + 1) * size]
        top_html = ""
        if pi == 0 and lead:
            top_html = f"""<section class="wrap"><div class="lead"><a href="{u(lead.path)}" class="cv-img">{cover_img(lead.cover, 1600, lazy=False)}</a>
 <a href="{u(lead.path)}"><div><span class="kick hl">{TYPE_LABEL[lead.type]}</span></div><h1>{esc(lead.title)}</h1><p class="dek">{esc(lead.dek)}</p>
 {chips(lead, 4)}<div class="meta">{time_tag(lead)}<span class="sep"></span><span>{esc(lead.author['name'])}</span><span class="sep"></span><span>{lead.minutes} min read</span></div></a></div>
 <div class="tops">{''.join(f'<article class="top"><a href="{u(t.path)}"><div class="cv-img">{cover_img(t.cover, 800)}</div><div><span class="kick">{TYPE_LABEL[t.type]}</span><h2>{esc(t.title)}</h2><p class="dek" style="margin:0;color:var(--ink-2);font-size:14.5px">{esc(t.dek)}</p>{chips(t)}</div></a></article>' for t in tops)}</div></section>"""
        rows_html = []
        last_day = None
        for i, s in enumerate(items):
            d = s.pub.date()
            if d != last_day:
                rows_html.append(f'<div class="day"><span>{day_title(d)}</span><small>{sum(1 for x in items if x.pub.date() == d)} stories</small></div>')
                last_day = d
            rows_html.append(row(s))
            if pi == 0 and i == 7:
                rows_html.append(subscribe_box(wide=True))
        nav = []
        if pi > 0:
            nav.append(f'<a class="btn ghost" href="{u("" if pi == 1 else f"page/{pi}/")}">Newer stories</a>')
        if pi < pages - 1:
            nav.append(f'<a class="btn ghost" href="{u(f"page/{pi + 2}/")}">Older stories</a>')
        body = f"""{top_html}
<section class="wrap"><div class="read" style="max-width:780px"><div class="feed">
 <div class="chips" role="toolbar" aria-label="Filter stories">{chips_}</div>
 {''.join(rows_html)}
 <p class="empty" hidden></p>
 <div class="more" style="gap:10px">{''.join(nav)}</div>
</div></div></section>"""
        path = "" if pi == 0 else f"page/{pi + 1}/"
        title = CFG["name"] + (": " + CFG["tagline"] if pi == 0 else f" | Latest stories, page {pi + 1}")
        write(path, page(path, title, body, CFG["tagline"] + " Why-it-moved stories, earnings, and our picks.",
                         f"static/covers/{lead.cover}-1600.webp" if lead else None, active=""))
    return pages


# ---------------------------------------------------------------------- stock pages

SECTOR_MED: dict[str, dict] = {}


def ttm(t):
    f = FUND.get(t) or {}
    return f.get("ttm") or {}


def median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def compute_sector_medians():
    by = defaultdict(list)
    for x in UNIV:
        by[x["sector"]].append(x["ticker"])
    for sec, ts in by.items():
        SECTOR_MED[sec] = {k: median([ttm(t).get(k) for t in ts]) for k in
                           ("revenue_growth_yoy_pct", "operating_margin_pct", "fcf_margin_pct", "gross_margin_pct")}
        SECTOR_MED[sec]["pe"] = median([(Q.get(t) or {}).get("pe") for t in ts if ((Q.get(t) or {}).get("pe") or 0) > 0])


def qlabel(q) -> str:
    lab = q.get("label") or ""
    m = re.match(r"(Q\d) FY(\d\d)", lab)
    return f"{m.group(1)} ’{m.group(2)}" if m else lab


def unit_for(vals):
    mx = max([abs(v) for v in vals if v is not None] or [0])
    return ("$bn", 1e9) if mx >= 1e9 else ("$m", 1e6)


def fund_section(t: str) -> str:
    f = FUND.get(t)
    if not f or not f.get("quarters"):
        return ""
    qs = [q for q in f["quarters"] if q.get("revenue") is not None][-8:]
    if len(qs) < 4:
        return ""
    name = UMAP[t]["name"]
    out = []
    rev = [q["revenue"] for q in qs]
    unit, div = unit_for(rev)
    labels = [qlabel(q) for q in qs]
    allq = [q for q in f["quarters"] if q.get("revenue") is not None]
    yoy = None
    if len(allq) >= 5 and allq[-5]["revenue"]:
        yoy = (allq[-1]["revenue"] / allq[-5]["revenue"] - 1) * 100
    rt = (f"Revenue {'grew' if yoy >= 0 else 'fell'} {abs(yoy):.1f}% from a year earlier" if yoy is not None
          else f"{name}'s quarterly revenue")
    out.append(C.bars_chart({"title": rt, "subtitle": f"Quarterly revenue, {unit.replace('$', '$ ')}, latest {labels[-1]}",
                             "labels": labels, "values": [round(v / div, 2) for v in rev], "unit": "$bn" if unit == "$bn" else "",
                             "source": "SEC filings", "highlight": -1}).replace('class="chart "', 'class="chart"'))
    oi = [q.get("operating_income") for q in qs]
    if sum(1 for v in oi if v is not None) >= 4:
        u2, d2 = unit_for(oi)
        m = (qs[-1]["operating_income"] / qs[-1]["revenue"] * 100) if qs[-1].get("operating_income") is not None and qs[-1]["revenue"] else None
        title = f"Operating margin was {m:.1f}% last quarter" if m is not None else "Operating income by quarter"
        out.append(C.bars_chart({"title": title, "subtitle": f"Quarterly operating income, {u2.replace('$', '$ ')}",
                                 "labels": labels, "values": [round(v / d2, 2) if v is not None else None for v in oi],
                                 "unit": "$bn" if u2 == "$bn" else "", "source": "SEC filings", "highlight": -1}))
    fcf = [q.get("fcf") for q in qs]
    if sum(1 for v in fcf if v is not None) >= 4:
        u3, d3 = unit_for(fcf)
        tt = ttm(t)
        title = (f"Free cash flow was {big_money(tt.get('fcf'))} over 12 months" if tt.get("fcf") is not None
                 else "Free cash flow by quarter")
        out.append(C.bars_chart({"title": title, "subtitle": f"Quarterly free cash flow (operating cash flow minus capex), {u3.replace('$', '$ ')}",
                                 "labels": labels, "values": [round(v / d3, 2) if v is not None else None for v in fcf],
                                 "unit": "$bn" if u3 == "$bn" else "", "source": "SEC filings", "highlight": -1}))
    eps = [q.get("eps_diluted") for q in qs]
    if sum(1 for v in eps if v is not None) >= 4:
        out.append(C.bars_chart({"title": f"Diluted EPS was {money(eps[-1])} last quarter" if eps[-1] is not None else "Earnings per share",
                                 "subtitle": "Quarterly diluted earnings per share, $", "labels": labels,
                                 "values": eps, "unit": "$", "source": "SEC filings", "highlight": -1}))
    sec = UMAP[t]["sector"]
    med = SECTOR_MED.get(sec, {})
    tt = ttm(t)
    q = Q.get(t) or {}
    rows = []
    verdicts = []

    def cmp_row(label, v, m, good_high=True, fmtf=lambda x: pct(x, 1, sign=False)):
        if v is None:
            return
        rows.append(f"<tr><td>{label}</td><td class='n'>{fmtf(v)}</td><td class='n'>{fmtf(m) if m is not None else '–'}</td></tr>")
        if m is not None:
            better = (v > m) if good_high else (v < m)
            verdicts.append((better, label, v, m))
    cmp_row("Revenue growth, last 12 months", tt.get("revenue_growth_yoy_pct"), med.get("revenue_growth_yoy_pct"),
            fmtf=lambda x: pct(x, 1))
    cmp_row("Gross margin", tt.get("gross_margin_pct"), med.get("gross_margin_pct"))
    cmp_row("Operating margin", tt.get("operating_margin_pct"), med.get("operating_margin_pct"))
    cmp_row("Free cash flow margin", tt.get("fcf_margin_pct"), med.get("fcf_margin_pct"))
    if (q.get("pe") or 0) > 0:
        cmp_row("Price to earnings", q.get("pe"), med.get("pe"), good_high=False, fmtf=lambda x: f"{x:.1f}x")
    words = {"Revenue growth, last 12 months": ("grows faster than", "grows slower than"),
             "Gross margin": ("keeps more of each sale than", "keeps less of each sale than"),
             "Operating margin": ("is more profitable than", "is less profitable than"),
             "Free cash flow margin": ("turns more of its sales into cash than", "turns less of its sales into cash than"),
             "Price to earnings": ("is cheaper than", "is pricier than")}
    vl = "".join(f'<li class="{"g" if b else "b"}">{esc(name)} {words[lab][0 if b else 1]} the median {esc(sec.lower())} stock ({fmt_cmp(lab, v)} vs {fmt_cmp(lab, m)}).</li>'
                 for b, lab, v, m in verdicts)
    table = (f'<div class="tbl"><table class="cmp"><thead><tr><th>Last 12 months</th><th class="n">{t}</th><th class="n">{esc(sec)} median</th></tr></thead>'
             f'<tbody>{"".join(rows)}</tbody></table></div>') if rows else ""
    upd = f.get("quarters", [{}])[-1].get("end", "")
    return (f'<h2 class="sh2" id="financials">The business</h2><p class="lede">From {esc(name)}\'s SEC filings, through the quarter ending '
            f'{C.human(upd) if upd else "–"}.</p>'
            f'<ul class="verdicts">{vl}</ul>{table}<div class="fundgrid">{"".join(out)}</div>')


def fmt_cmp(label, v):
    if v is None:
        return "–"
    return f"{v:.1f}x" if label == "Price to earnings" else pct(v, 1, sign=label.startswith("Revenue"))


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
        qt = dt.datetime.fromisoformat(q["time"].replace("-0400", "-04:00").replace("-0500", "-05:00")).astimezone(ET)
        asof = (f"At the close, {qt.day} {MON[qt.month - 1]}" if qt.time() >= dt.time(16, 0) else f"As of {when(qt)}") + " · Prices from CNBC, may be delayed"
    elif bars:
        asof = f"At the close, {C.human(bars[-1]['date'])}"
    ext = q.get("ext") or {}
    ext_html = (f'<span class="ext" data-live="{t}" data-k="ext">{"After hours" if ext.get("session") == "POST_MKT" else "Before the open"}: '
                f'<span>{money(ext.get("price"))} ({pct(ext.get("change_pct"))})</span></span>' if ext.get("price") else
                f'<span class="ext" data-live="{t}" data-k="ext" hidden></span>')
    # charts by range
    rngs = [("1m", "1M"), ("6m", "6M"), ("ytd", "YTD"), ("1y", "1Y"), ("5y", "5Y")]
    panels = []
    for k, lab in rngs:
        ch = C.price_chart(bars, k, None, f"{name} over {C.RANGE_LABEL[k]}", f"Daily close, $, to {C.human(bars[-1]['date'])}" if bars else "",
                           "last") if bars else ""
        panels.append(f'<div class="rng-panel" data-r="{k}"{"" if k == "1y" else " hidden"}>{ch}</div>')
    ranges = "".join(f'<button type="button" data-r="{k}" aria-pressed="{"true" if k == "1y" else "false"}">{lab}</button>' for k, lab in rngs)
    # stats
    hi52 = max((b["close"] for b in bars[-252:]), default=None)
    lo52 = min((b["close"] for b in bars[-252:]), default=None)
    pos = ((price - lo52) / (hi52 - lo52) * 100) if price and hi52 and lo52 and hi52 > lo52 else None
    ne = next_earnings(t)
    ne_s = "–"
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
    rangebar = (f'<div class="stat" style="grid-column:1/-1">52-week range (closes)<div class="rangebar"><i style="left:calc({pos:.1f}% - 1px)"></i></div>'
                f'<div><span>{money(lo52)}</span><span>{money(hi52)}</span></div></div>') if pos is not None else ""
    # stories
    st = BY_TICKER.get(t, [])
    if st:
        stories_html = mini_rows(st[:12])
    else:
        stories_html = (f'<p class="empty" style="text-align:left;padding:18px 0">We haven\'t written about {esc(name)} yet. '
                        f'Follow it, and its first story will show under My stocks on the front page.</p>')
    # peers
    peers = [p for p in UNIV if p["industry"] == x["industry"] and p["ticker"] != t]
    if len(peers) < 4:
        peers = [p for p in UNIV if p["sector"] == x["sector"] and p["ticker"] != t]
    peers.sort(key=lambda p: -((Q.get(p["ticker"]) or {}).get("cap") or 0))
    prow = []
    for p in peers[:8]:
        pq = Q.get(p["ticker"]) or {}
        py = ytd(p["ticker"])
        prow.append(f'<tr><td class="nm"><a href="{u(tpath(p["ticker"]))}"><span class="tt">{p["ticker"]}</span>{esc(p["name"])}</a></td>'
                    f'<td class="n">{money(pq.get("price"))}</td><td class="n {tone(pq.get("change_pct"))}">{pct(pq.get("change_pct"))}</td>'
                    f'<td class="n {tone(py)}">{pct(py, 1)}</td><td class="n hide-m">{short_money(pq.get("cap"))}</td></tr>')
    peers_html = (f'<h2 class="sh2">Similar companies</h2><p class="lede">{esc(x["industry"])}, by market value.</p>'
                  f'<table class="big"><thead><tr><th>Company</th><th class="n">Price</th><th class="n">Today</th><th class="n">YTD</th><th class="n hide-m">Value</th></tr></thead>'
                  f'<tbody>{"".join(prow)}</tbody></table>') if prow else ""
    body = f"""<div class="sp wrap">
 <div class="sp-top">
  <div><div class="crumbs" style="margin:0"><a class="kick" href="{u('stocks/')}">Stocks</a><span class="kick">/</span><a class="kick" href="{u('sectors/' + slugify(x['sector']) + '/')}">{esc(x['sector'])}</a></div>
   <h1>{esc(name)}<small>{t}</small></h1>
   <div class="sect">{esc(x['industry'])}{(' · ' + esc(x['hq'])) if x.get('hq') else ''}{' · In the S&amp;P 500' if 'S&P 500' in x.get('index', []) else ''}</div>
   <div class="px"><b data-live="{t}" data-k="price">{money(price)}</b><span class="chg {tone(chg)}" data-live="{t}" data-k="chg">{pct(chg)}</span>{ext_html}<span class="asof">{esc(asof)}</span></div>
  </div>
  <div><button class="btn" type="button" data-follow="{t}" aria-pressed="false">{ICON['plus']}<span>Follow</span></button></div>
 </div>
 <div class="sp-grid">
  <div style="min-width:0">
   <div class="ranges" role="group" aria-label="Chart range">{ranges}</div>
   {''.join(panels)}
   <h2 class="sh2" id="stories">Stories on {esc(name)}</h2>
   <div class="feed">{stories_html}</div>
   {fund_section(t)}
   {peers_html}
  </div>
  <aside><div class="stats" style="margin-top:6px">{stat_html}{rangebar}</div>
   <div style="margin-top:28px">{subscribe_box(title='Follow the market with us', text='The stories that moved stocks, every market day, free by email.')}</div></aside>
 </div>
</div>"""
    desc = f"{name} ({t}) stock: price, chart, financials and the latest stories explaining why it moved."
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
    sp = C.spark([b["close"] for b in prices(t)[-63:]], 200, 30)
    return (f'<a class="sc" href="{u(tpath(t))}"><div class="r1"><span class="tt">{t}</span><span class="cg {tone(q.get("change_pct"))}">'
            f'{money(q.get("price"))} {pct(q.get("change_pct"), 1)}</span></div><div class="nm">{esc(x["name"])}</div>'
            f'<div class="ind">{esc(x["industry"])}</div>{sp}<div class="ml">{esc(metric_label)}: <b class="{tone(tone_v) if tone_v is not None else ""}">{metric_value}</b></div></a>')


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
            f'<tr><td class="nm"><a href="{u(tpath(t))}"><span class="tt">{t}</span>{esc(UMAP[t]["name"])}</a></td>'
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
                      f'<div class="feed">{"".join(row(s) for s in picks)}</div></section>')
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
        out.append(f'<tr><td class="nm"><a href="{u(tpath(t))}"><span class="tt">{t}</span>{esc(x["name"])}</a></td>'
                   f'<td class="hide-m">{esc(x["industry"])}</td><td class="n" data-v="{q.get("price") or ""}">{money(q.get("price"))}</td>'
                   f'<td class="n {tone(q.get("change_pct"))}" data-v="{q.get("change_pct") if q.get("change_pct") is not None else ""}">{pct(q.get("change_pct"))}</td>'
                   f'<td class="n {tone(y)}" data-v="{y if y is not None else ""}">{pct(y, 1)}</td>'
                   f'<td class="n hide-m" data-v="{q.get("cap") or 0}">{short_money(q.get("cap"))}</td></tr>')
    return "".join(out)


TABLE_HEAD = ('<thead><tr><th>Company</th><th class="hide-m">Industry</th><th class="n">Price</th><th class="n">Today</th>'
              '<th class="n">YTD</th><th class="n hide-m">Value</th></tr></thead>')


def sector_pages():
    by = defaultdict(list)
    for x in UNIV:
        by[x["sector"]].append(x["ticker"])
    for sec, ts in by.items():
        ts.sort(key=lambda t: -((Q.get(t) or {}).get("cap") or 0))
        st = [s for s in STORIES if s.tickers and UMAP[s.tickers[0]]["sector"] == sec][:8]
        stories = f'<section class="dsec"><div class="dsec-h"><div><h2>Latest stories</h2></div></div><div class="feed">{"".join(row(s) for s in st)}</div></section>' if st else ""
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
                    items.append(f'<div class="cal-e"><a href="{u(tpath(t))}"><b>{t}</b></a>{info}{link}</div>')
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
    urls = [""] + [s.path for s in STORIES] + [tpath(t) for t in UMAP] + ["discover/", "earnings/", "stocks/", "about/"]
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
            qt = dt.datetime.fromisoformat(q["time"].replace("-0400", "-04:00").replace("-0500", "-05:00")).astimezone(ET)
            lab = f"At the close, {qt.day} {MON[qt.month - 1]}" if qt.time() >= dt.time(16, 0) else f"As of {when(qt)}"
        qd[t] = [q.get("price"), q.get("change_pct"), ext.get("price"), ext.get("change_pct"), lab,
                 "After hours" if ext.get("session") == "POST_MKT" else "Before the open"]
    (DIST / "data").mkdir(exist_ok=True)
    (DIST / "data/quotes.json").write_text(json.dumps({"asof": QUOTES.get("asof"), "q": qd}, separators=(",", ":")))
    search = {"s": [[t, x["name"], x["sector"]] for t, x in sorted(UMAP.items())],
              "n": [[s.title, s.path, f"{s.pub.day} {MON[s.pub.month - 1]}"] for s in STORIES[:400]]}
    (DIST / "data/search.json").write_text(json.dumps(search, separators=(",", ":")))


def static():
    out = DIST / "static"
    shutil.copytree(SITE / "static", out, dirs_exist_ok=True)
    cov = out / "covers"
    cov.mkdir(exist_ok=True)
    for f in (ROOT / "assets/covers").glob("*.webp"):
        dst = cov / f.name
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
        write(s.path, story_page(s))
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
