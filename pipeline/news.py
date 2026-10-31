"""Outside headlines for each stock and for the market, plus X post cards, from free feeds that need no key.

  python3 pipeline/news.py --tickers AAPL,NVDA     # these stocks -> data/news/<T>.json (BRK.B stays BRK.B.json)
  python3 pipeline/news.py --top 150               # the 150 biggest by market cap in data/quotes/latest.json
  python3 pipeline/news.py --all                   # the whole universe
  python3 pipeline/news.py --market                # market-wide headlines -> data/news/market.json
  python3 pipeline/news.py --tweet https://x.com/<handle>/status/<id>   # cache one X post -> data/news/tweets.json
  python3 pipeline/news.py --tweets                # cache every post a ```tweet block in content/ links to

Standard library only. We keep the headline, the outlet, the time and the link, never the article text. The site
builder and detect.py read the files directly; load(ticker) does the same here, without the network. The format,
the sources and their limits are in docs/NEWS.md.

Per stock, three sources, each on its own: one failing never stops the others, and a stock whose sources all fail
keeps its old file.
  TradingView  news-headlines.tradingview.com, the JSON behind a symbol's News tab: Reuters, Dow Jones (WSJ, Barron's,
               MarketWatch), Seeking Alpha, Benzinga, wire press releases and analyst actions, the latest ~200. It wants
               EXCHANGE:TICKER; the exchange comes from SEC's company_tickers_exchange.json and is kept in the file.
               Undocumented, so it can change or vanish without notice.
  Google News  news.google.com/rss/search on the company's names, kept only from outlets we know (Bloomberg, CNBC,
               WSJ, Reuters, FT, Barron's, AP...). Its links are news.google.com redirects to the article.
  SEC EDGAR    data.sec.gov submissions: 8-Ks (named by their items), 10-Q/10-K, 20-F/6-K, 13D, merger and tender
               filings.
The market file reads CNBC (top news, markets, economy, earnings), MarketWatch's top stories, WSJ Markets and Reuters
(through TradingView), and keeps market news only.

Compressed: a headline must name the company or be tagged to it alone; law-firm notices, other companies' press
releases, 13F filler, listicles and "buy or sell?" bait are dropped; the same story from several outlets becomes one
item with the others in `also`. A file keeps 14 days and merges with what it already holds. When more is left than
fits (40 a stock, 60 the market), the best outlets, the stories most outlets carried, filings and the newest win.
"""
from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import gzip
import hashlib
import html
import json
import math
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import marketdata as md  # noqa: E402

OUT = md.DATA / "news"
TWEETS = OUT / "tweets.json"
DAYS = 14                       # what a file keeps
MAX_STOCK, MAX_MARKET = 40, 60
WORKERS = 4                     # stocks fetched at once; one stock's sources go one after another
PAUSE = 0.4                     # seconds between one stock's requests

TV_SYMBOL = "https://news-headlines.tradingview.com/v2/view/headlines/symbol?client=web&lang=en&symbol={}"
TV_PROVIDER = "https://news-headlines.tradingview.com/v2/headlines?client=web&lang=en&provider={}"
GNEWS = "https://news.google.com/rss/search?"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{:010d}.json"
SEC_EXCHANGES = "https://www.sec.gov/files/company_tickers_exchange.json"
CNBC = "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id={}"
DJ = "https://feeds.content.dowjones.io/public/rss/{}"
# (outlet, feed, which items: all | market news only | tagged with one of our stocks or a market symbol).
# CNBC's ids: top news, markets, economy, earnings.
MARKET_FEEDS = [("CNBC", CNBC.format(100003114), "market"), ("CNBC", CNBC.format(20409666), "all"),
                ("CNBC", CNBC.format(20910258), "all"), ("CNBC", CNBC.format(15839135), "all"),
                ("MarketWatch", DJ.format("mw_topstories"), "market"), ("WSJ", DJ.format("RSSMarketsMain"), "all"),
                ("Reuters", TV_PROVIDER.format("reuters"), "tagged")]
MACRO_SYMBOLS = {"SPX", "DJI", "IXIC", "NDX", "RUT", "VIX", "US10Y", "US02Y", "DXY", "CL1!", "BRN1!", "GC1!", "BTCUSD",
                 "USOIL", "UKOIL", "XAUUSD", "ES1!", "NQ1!", "YM1!", "SOX"}

# ---------------------------------------------------------------- outlets

# What a headline from an outlet is worth when a file has more than it can keep. Google News items are kept only
# from these; anything else (TradingView's long tail) counts 1. Dow Jones' own wire is 2: TradingView shows only its
# headline.
TIER = {**dict.fromkeys(["Reuters", "Bloomberg", "WSJ", "Barron's", "CNBC", "Financial Times", "AP", "MarketWatch",
                         "The Information", "The New York Times", "Nikkei Asia", "The Economist"], 3.0),
        "Yahoo Finance": 1.5,  # its own reporting and its partners' copies (Motley Fool, Zacks) look alike in a feed
        **dict.fromkeys(["Seeking Alpha", "Benzinga", "Investing.com", "Business Insider", "Fortune",
                         "Forbes", "Morningstar", "Investor's Business Daily", "TheStreet", "Fox Business", "Axios",
                         "The Washington Post", "CNN", "Quartz", "TechCrunch", "The Verge", "Semafor", "Politico",
                         "BBC", "The Guardian", "CBS News", "NBC News", "ABC News", "Kiplinger", "STAT",
                         "Fierce Pharma", "Fierce Biotech", "Endpoints News", "American Banker", "Automotive News",
                         "Electrek", "Ars Technica", "Wired", "Tom's Hardware", "Variety", "The Hollywood Reporter",
                         "Deadline", "Puck", "MT Newswires", "Dow Jones"], 2.0),
        # Kept from Google News only so a Yahoo copy of their article is credited to them; they rank last.
        **dict.fromkeys(["The Motley Fool", "Zacks", "Barchart", "Investopedia", "GuruFocus", "24/7 Wall St.",
                         "MarketBeat", "Nasdaq", "Stocktwits", "StockStory", "TradingView"], 1.0)}
OUTLET = {"The Wall Street Journal": "WSJ", "Wall Street Journal": "WSJ", "Bloomberg.com": "Bloomberg",
          "Bloomberg News": "Bloomberg", "AP News": "AP", "Associated Press": "AP", "The Associated Press": "AP",
          "Barrons.com": "Barron's", "Barrons": "Barron's", "FT": "Financial Times", "Insider": "Business Insider",
          "Markets Insider": "Business Insider", "FOX Business": "Fox Business", "New York Times": "The New York Times",
          "NYT": "The New York Times", "Washington Post": "The Washington Post", "CNN Business": "CNN",
          "Investors Business Daily": "Investor's Business Daily", "Dow Jones Newswires": "Dow Jones",
          "BusinessWire": "Business Wire", "Zacks Investment Research": "Zacks", "Barchart.com": "Barchart",
          "STAT News": "STAT", "FiercePharma": "Fierce Pharma", "FierceBiotech": "Fierce Biotech"}
SYNDICATORS = {"Yahoo Finance", "Nasdaq", "MSN", "AOL"}   # carry other outlets' articles under their own name
# TradingView providers we skip: crypto and Indian aggregators, LSE/EQS regulatory notices.
TV_SKIP = {"binance_news", "cryptoprowl", "cryptobriefing", "bloomingbit", "mint", "moneycontrol",
           "economic_times_india", "business_line_india", "cnbctv", "lse", "eqs"}
WIRE = re.compile(r"business ?wire|globe ?news ?wire|pr ?news ?wire|access ?(?:news)?wire|newsfile|cision", re.I)
DJ_TAIL = re.compile(r"\s+[—–-]+\s*(WSJ(?: Newsletter)?|Heard on the Street|Barrons\.com|Barron's|MarketWatch|"
                     r"Market Talk|Update)\s*$")


def outlet(name: str) -> str:
    n = re.sub(r"\s+", " ", name or "").strip()
    return "Yahoo Finance" if n.startswith("Yahoo Finance") else OUTLET.get(n, n)


# ---------------------------------------------------------------- what we drop

JUNK = re.compile("|".join([
    # law firms fishing for class-action clients (a real lawsuit or fraud charge in the news stays)
    r"\bclass action (?:reminder|alert|notice|deadline|lawsuit filed)", r"\bsecurities (?:fraud )?class action\b",
    r"\b(?:investors?|shareholders?) (?:alert|notice|reminder)\b", r"\bshareholder investigation\b",
    r"\blead[- ]plaintiff", r"\bdeadline (?:alert|reminder|approaching)\b", r"\binvestors who (?:lost|suffered)\b",
    r"\blost money\b", r"\bshould contact\b",
    r"(?:encourages|reminds|alerts|notifies) (?:\w+ )?(?:investors|shareholders)\b",
    r"\blaw offices of\b", r"\ba leading (?:securities )?law firm\b",
    r"\b(?:rosen|pomerantz|levi & korsinsky|bronstein|faruqi|kessler topaz|robbins geller|glancy|schall law|bragar|"
    r"kirby mcinerney|portnoy|block & leviton|johnson fistel|holzer|bernstein liebhard|hagens berman|rigrodsky|"
    r"halper sadeh|monteverde|kahn swick|gainey mckenna|bfa law|edelson lechtzin|dicello levitt)\b",
    # 13F, insider, congressional and price-move filler
    r"\b(?:shares|stock) (?:sold|bought|acquired|purchased) by\b",
    r"\bshares of .{1,80} (?:acquired|sold|purchased|bought) by\b",
    r"\b(?:sells|buys|purchases|acquires|unloads) [\d,]+ shares\b",
    r"\b(?:sells|buys) \$[\d,]+\.\d\d (?:in|of) stock\b",
    r"\b(?:holdings|position|stake)s? (?:in .{1,60} )?(?:lifted|raised|boosted|trimmed|lowered|cut|reduced|"
    r"increased|decreased|grown) by\b",
    r"\b(?:has|holds) \$[\d.,]+ ?(?:million|billion|thousand)? (?:stock |share )?(?:holdings|position|stake)\b",
    r"\b(?:takes|opens|acquires|buys|initiates|establishes) (?:a |an )?(?:new )?(?:\$[\d.,]+ ?(?:million|billion)? )?"
    r"(?:stake|position) in\b",
    r"\b(?:increases|decreases|trims|boosts|raises|lowers|cuts|reduces|grows|lifts|adds to) (?:its |their )?"
    r"(?:stock |share )?(?:stake|position|holdings) in\b",
    r"\b(?:increases|decreases|boosts|cuts|trims|reduces|raises|lowers|lifts|grows|sells|buys|acquires|adds|takes|"
    r"initiates|establishes|opens)(?: new)? (?:stock )?(?:position|holdings|stake)s?\s*$",
    r"\b\d+(?:st|nd|rd|th) largest (?:position|holding)\b", r"^insider (?:buying|selling)", r"\$[A-Z]{1,5}\s*$",
    r"\b(?:stock|share)s? (?:sale|purchase|trade)s? (?:disclosed|revealed|reported) by\b",
    r"\bhouse of representatives?\b.{0,40}\b(?:bought|sold|buys|sells)\b",
    r"\b(?:rep\.|representative|senator|congressman|congresswoman) [\w. ]{2,40} "
    r"(?:buys|sells|bought|sold|discloses|reveals)\b",
    r"\bnet etf (?:buying|selling)\b", r"\b(?:moderately |strongly )?(?:bullish|bearish) activity in\b",
    r"\bsays hkex\b", r"\blong position in \w", r"\bmoving average\b", r"\bunusual (?:options )?activity\b",
    r"\b(?:shares|stock(?: price)?) (?:up|down|gaps? (?:up|down)|trading (?:up|down)|rises?|falls?|declines?|"
    r"increases?|decreases?) [\d.]+%\s*[-–—:]\s*(?:here|what|should|time|is it|why)",
    # quote pages and machine-written lines (Zacks, Simply Wall St, GuruFocus, MarketWatch's automated stories)
    r"stock price,? (?:quote|today|chart|history|forecast|prediction|& news)", r"\bcompany overview\b",
    r"\bstock (?:charts?|quotes?|forecasts?)\b", r"\bprice prediction\b", r"meta_title", r"\bhistorical prices\b",
    r"\breturns? chart\b", r"- stock analysis$", r"12.month price target (?:raised|cut|lowered) to",
    r"\bearnings call (?:is live|transcript)\b", r"\bzacks\b", r"\bgf score\b", r"\bis a trending stock\b",
    r"\blatest attention\b", r"\bfacts to know before\b", r"\battracting investor attention\b",
    r"\bhere is what you (?:should|need to) know\b", r"\bsince last earnings report\b", r"\bfeatured highlights\b",
    r"\bimportant facts to note\b", r"\bsome information for investors\b", r"\binvestors heavily search\b",
    r":\s*key facts\s*$", r"\bwhy the market (?:dipped|rose|fell|gained|climbed|slid)\b",
    r"\banalysts estimate .{1,60} to report\b", r"\bexploring analyst estimates\b", r"\bwhat'?s in store\b",
    r"\bjustify its (?:price|valuation)\b", r"\bbull case for\b", r"\boutpacing its .{1,40} peers\b",
    r"\bsmart investment\b", r"\b\d+% undervalued\b", r"\bnarrative holds\b",
    r"\bstock looks (?:reasonable|about right|cheap|expensive|fair|attractive)\b", r"\bsees (?:modest )?fair value\b",
    r"\bfair value (?:edges|cut|nudged|lift|bump|trimmed|raised)\b",
    r"\b(?:out|under)performs (?:\w+ )?(?:when compared to )?competitors\b",
    r"\b(?:declines?|declined|falls?|fell|rises?|rose|gains?|gained|dips?|dipped|climbs?|slides?)\s+(?:more|less)\s+"
    r"than\s+(?:the\s+)?(?:broader\s+)?market\b",
    r"\b(?:despite|while) (?:the )?market (?:gains|dips|rises|falls|climbs|slides|uptick)\b", r"\bamid market\b",
    r"\bas market (?:gains|dips|falls|rises|slides|drops|climbs)\b",
    r"\b(?:outpaces|lags|trails|underperforms|outperforms) (?:the )?(?:broader |stock )?market\b",
    r"- earnings (?:summary|preview)$", r"\bexpected to post (?:earnings|a loss|a profit) of\b",
    r"\breports results for the quarter ended\b",
    # Dow Jones' analyst and one-line flashes, which repeat TradingView's fuller analyst lines and the stories
    r"\bis maintained at\b",
    r"\bprice target (?:cut|raised|lowered|maintained|announced|set)(?: with a| at)? (?:to |at )?\$[\d,.]+/share\b",
    r"\b(?:cut|raised|upgraded|downgraded|lowered) to [\w-]+(?: [\w-]+)? from [\w-]+(?: [\w-]+)? by\b",
    r">\s*[A-Z][A-Z.]{0,6}\s*$",  # "Sandisk 1Q EPS $52.60 >SNDK"
    r"\bleverage shares\b", r"\bleveraged etfs?\b", r"\b[23]x (?:long|short|bull|bear)\b", r"\bintraday rebalance\b",
    # listicles and buy/sell bait
    r"(?<!s&p )\b\d+ (?:[\w'-]+ ){0,3}stocks? (?:to|that|for|you|i|i'd|i'm|worth|with|under|set|poised|making|"
    r"are|alone|we|from|everyone|have|billionaires?)\b", r"\band \d+ (?:[\w'-]+ ){0,3}stocks?\s*$",
    r"\bstocks? to (?:buy|own|hold|watch|sell|avoid)\b", r"\b(?:should you|time to|is it time to|worth) (?:buy|sell)",
    r"\ba (?:buy|sell)\b(?![ -](?:back|off|side|rating|signal))",
    r"\b(?:a|the) (?:genius|smart|great|good|top|screaming) buy\b",
    r"\bbuy,? (?:or )?sell\b", r"\bbuy or hold\b", r"\b(?:buy|sell|hold)\s*\?\s*$", r"\bbuy the dip\s*\?",
    r"\bif you(?:'d| had| would have) invested\b",
    r"\bwhat \$[\d,.]+ (?:becomes|could become|would become|turns into)\b",
    r"\bhow much you'?d have\b", r"\byou'?d need\b", r"\bmillionaire", r"\bno-brainer\b", r"\bhand over fist\b",
    r"\bunstoppable\b", r"\bi'?d buy\b", r"\bi'?m buying\b", r"\bmy top pick\b",
    r"\bbetter (?:[\w-]+ ){0,2}(?:stock|buy|bet|pick)\b", r"\bsafer bet\b", r"\bmust-have\b", r"^prediction:",
    r"\bsign to buy\b", r"\bis it too late\b", r"\bcan you invest in\b", r"\b(?:bull|bear) of the day\b",
    r"\bstrong (?:buy|sell) stocks?\b", r"\bbrilliant (?:[\w-]+ ){0,2}stocks?\b", r"\bbuy these (?:\d+ )?stocks\b",
    r"\bbefore it'?s too late\b",
    # wire leftovers, regulatory notices, roundups and columns
    r"- SEC Filing$", r"^REG - ", r"\broundup: market talk\b", r"^wsj dollar index\b", r"^opinion\s*[|:]", r"\bquiz\b",
    r"^moody's ratings (?:affirms|upgrades|downgrades|assigns|places|changes|withdraws|revises)\b",
]), re.I)

TEMPLATE = re.compile(r"\((?:NYSE|NASDAQ|Nasdaq|NYSEARCA)\s*:\s*[A-Z.]+\)|\$[A-Z]{1,5}\b")


def is_junk(x: dict) -> bool:
    """Filler, bait and law-firm spam; MarketBeat's machine-written lines (they carry a ticker tag); a bare name."""
    t = x.get("title") or ""
    return bool(JUNK.search(t)) or len(t.split()) < 3 or (x.get("source") == "MarketBeat" and bool(TEMPLATE.search(t)))


# Market news, for the general feeds (CNBC top news, MarketWatch): these words, or one of our companies by name.
MARKET_WORDS = re.compile(
    r"\b(?:stocks?|shares|markets?|wall street|s&p|dow|nasdaq|russell|futures|fed|federal reserve|fomc|interest rates?|"
    r"rate (?:cut|hike)s?|yields?|treasur(?:y|ies)|bonds?|inflation|cpi|pce|jobs report|payrolls?|jobless|unemployment|"
    r"gdp|economy|recession|tariffs?|oil prices?|crude|opec|gold prices?|dollar|bitcoin|earnings|revenue|profits?|"
    r"guidance|forecast|ipo|merger|acquisition|takeover|buyout|bankruptcy|layoffs?|sell-?off|rally|valuation)\b", re.I)
_NAMES_RX: re.Pattern | None = None


def names_rx() -> re.Pattern:
    """Any of our companies by its plain name (not the ambiguous ones), for market headlines."""
    global _NAMES_RX
    if _NAMES_RX is None:
        names = {re.sub(r"\s*\(.*?\)", "", u["name"]).strip(" &,") for u in md.universe()}
        names |= {n for v in EXTRA.values() for n in v if len(n) > 2}
        names -= NEVER | STRICT | COMMON
        _NAMES_RX = re.compile(rf"(?<![\w&])(?:{_alts(names)})(?![\w&])")
    return _NAMES_RX


# ---------------------------------------------------------------- fetching

_SEC_LOCK = threading.Lock()
_sec_next = 0.0


def _sec_pace() -> None:
    """SEC asks for at most 10 requests a second; we take 5."""
    global _sec_next
    with _SEC_LOCK:
        now = time.monotonic()
        at = max(now, _sec_next)
        _sec_next = at + 0.2
    if at > now:
        time.sleep(at - now)


def fetch(url: str, ua: str = md.UA, accept: str = "*/*", tries: int = 2, timeout: int = 20) -> bytes:
    """One GET with a timeout and gzip, retried once after a 429, a 5xx or a network error. A 404 fails at once."""
    if "sec.gov/" in url:
        _sec_pace()
        ua = md.SEC_UA  # SEC wants a named contact and refuses browser user agents
    for i in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": accept, "Accept-Encoding": "gzip",
                                                   "Accept-Language": "en-US,en;q=0.9"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
                return gzip.decompress(body) if r.headers.get("Content-Encoding") == "gzip" else body
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or i == tries - 1:
                raise
            wait = (e.headers.get("Retry-After") or "").strip()
            time.sleep(min(float(wait), 30.0) if wait.isdigit() else 3.0 * (i + 1))
        except OSError:  # URLError, timeouts, resets
            if i == tries - 1:
                raise
            time.sleep(2.0 * (i + 1))
    raise RuntimeError(f"unreachable: {url}")


def why(e: Exception) -> str:
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code}"
    return f"{type(e).__name__}: {str(e)[:60]}"


# ---------------------------------------------------------------- items

def iso(d: dt.datetime) -> str:
    return d.astimezone(md.ET).isoformat(timespec="seconds")


def parse_time(s) -> dt.datetime | None:
    """RSS dates, ISO strings (a trailing Z included) and epoch seconds, as New York time."""
    if s in (None, ""):
        return None
    try:
        if isinstance(s, (int, float)):
            d = dt.datetime.fromtimestamp(s, dt.timezone.utc)
        elif re.match(r"\d{4}-\d\d-\d\d", s):
            d = dt.datetime.fromisoformat(s.strip())
        else:
            d = email.utils.parsedate_to_datetime(s.strip())
    except (TypeError, ValueError, OverflowError):
        return None
    return (d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)).astimezone(md.ET)


DROP_QUERY = {"mod", "feed_item_type", ".tsrc", "source", "ref", "ref_src", "cmpid", "yptr", "siteid", "guccounter"}


def clean_url(u: str) -> str:
    p = urllib.parse.urlsplit((u or "").strip())
    if p.scheme not in ("http", "https"):
        return ""
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
         if not (k.startswith("utm_") or k in DROP_QUERY)]
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, urllib.parse.urlencode(q), ""))


def tidy(title: str) -> str:
    t = re.sub(r"\s+", " ", html.unescape(title or "")).replace("‑", "-").strip()
    t = re.sub(r"\s+-\s+[^-]{1,60}\((?:NASDAQ|NYSE|NYSEARCA|CBOE)\s*:[^)]*\)\s*$", "", t)  # " - Apple (NASDAQ:AAPL)"
    t = re.sub(r"\s*\((?:NASDAQ|NYSE|NYSEARCA|CBOE)\s*:\s*[A-Z.]+\)\s*$", "", t)
    return re.sub(r"\s*\([A-Z.]+\s*:\s*(?:NASDAQ|NYSE|NYSEARCA|CBOE)\)\s*$", "", t).strip()


def make(title: str, source: str, url: str, when: dt.datetime | None, kind: str = "news") -> dict | None:
    title, url = tidy(title), clean_url(url)
    if not (title and url and when):
        return None
    return {"id": hashlib.sha1(url.encode()).hexdigest(), "title": title, "source": source, "url": url,
            "published": iso(when), "also": [], "kind": kind, "_dt": when}


def _tag(raw: str, name: str) -> str:
    m = re.search(rf"<{name}\b[^>]*>(.*?)</{name}>", raw, re.S)
    return html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1))).strip() if m else ""


# ---------------------------------------------------------------- sources

def tradingview(url: str) -> list[dict]:
    d = json.loads(fetch(url, accept="application/json"))
    out = []
    for x in d.get("items") or []:
        p = x.get("provider")
        prov = p if isinstance(p, str) else (p or {}).get("id", "")
        if prov in TV_SKIP or not x.get("title"):
            continue
        title = x["title"]
        src = outlet(x.get("source") or ("" if isinstance(p, str) else (p or {}).get("name", "")) or prov)
        m = DJ_TAIL.search(title) if prov in ("dow-jones", "market-watch") else None
        if m:  # "... — Barrons.com": Dow Jones carries WSJ, Barron's and MarketWatch under its own name
            title, tail = title[:m.start()], m.group(1)
            src = {"Barrons.com": "Barron's", "Barron's": "Barron's", "MarketWatch": "MarketWatch"}.get(
                tail, "WSJ" if tail.startswith(("WSJ", "Heard")) else src)
        link = x.get("link") or (("https://www.tradingview.com" + x["storyPath"]) if x.get("storyPath") else "")
        it = make(title, src, link, parse_time(x.get("published")),
                  "press-release" if WIRE.search(f"{prov} {src}") else "news")
        if it:
            it["_syms"] = [s.get("symbol", "").split(":")[-1] for s in x.get("relatedSymbols") or []]
            # the publisher's page, then TradingView's copy, then a Google redirect, then a headline-only page
            it["_via"] = 0 if x.get("link") else 3 if x.get("permission") == "headline" or x.get("paywall") else 1
            out.append(it)
    return out


def google_news(query: str) -> list[dict]:
    q = urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    s = fetch(GNEWS + q, accept="application/rss+xml").decode("utf-8", "ignore")
    out = []
    for raw in re.findall(r"<item>(.*?)</item>", s, re.S):
        name = _tag(raw, "source")
        src = outlet(name)
        if src not in TIER:
            continue
        title = _tag(raw, "title")
        if name and title.endswith(" - " + name):
            title = title[: -len(name) - 3]
        it = make(title, src, _tag(raw, "link"), parse_time(_tag(raw, "pubDate")))
        if it:
            it["_via"] = 2  # a news.google.com redirect: the last choice of link
            out.append(it)
    return out


def rss(url: str, source: str) -> list[dict]:
    s = fetch(url, accept="application/rss+xml, application/xml").decode("utf-8", "ignore")
    out = []
    for raw in re.findall(r"<item>(.*?)</item>", s, re.S):
        if _tag(raw, "metadata:sponsored") == "true" or "/bulletins/redirect" in raw:
            continue
        it = make(_tag(raw, "title"), source, _tag(raw, "link"), parse_time(_tag(raw, "pubDate")))
        if it:
            out.append(it)
    return out


ITEMS_8K = {"1.01": "a material agreement", "1.02": "an agreement ended", "1.03": "bankruptcy",
            "1.05": "a cybersecurity incident", "2.01": "an acquisition or sale completed", "2.02": "quarterly results",
            "2.03": "new debt", "2.04": "debt accelerated", "2.05": "restructuring costs", "2.06": "an impairment",
            "3.01": "a listing notice", "3.02": "unregistered share sales", "4.01": "an auditor change",
            "4.02": "a restatement", "5.01": "a change in control", "5.02": "executive or board changes",
            "7.01": "a Reg FD disclosure", "8.01": "other events"}
FORMS = {"10-Q": "files its 10-Q quarterly report", "10-K": "files its 10-K annual report",
         "20-F": "files its 20-F annual report", "40-F": "files its 40-F annual report", "6-K": "files a 6-K report",
         "SC 13D": "is the subject of a 13D: an investor holds 5% or more and may push for change",
         "SCHEDULE 13D": "is the subject of a 13D: an investor holds 5% or more and may push for change",
         "SC 13D/A": "13D update: an active investor changed its stake",
         "SCHEDULE 13D/A": "13D update: an active investor changed its stake",
         "S-4": "files an S-4 for a merger or exchange offer", "DEFM14A": "files its merger proxy",
         "SC TO-T": "faces a tender offer", "SC 14D9": "responds to a tender offer",
         "S-1": "files an S-1 to sell shares"}
MAJOR_FILING = re.compile(r"quarterly results|material agreement|bankruptcy|acquisition|restructuring|impairment|"
                          r"restatement|change in control|executive|cybersecurity|listing notice|13D|tender|merger|"
                          r"10-Q|10-K|20-F|40-F")


def sec_filings(cik: str, name: str, since: dt.date) -> list[dict]:
    d = json.loads(fetch(SEC_SUBMISSIONS.format(int(cik)), accept="application/json"))
    r = (d.get("filings") or {}).get("recent") or {}
    out = []
    for i, form in enumerate(r.get("form") or []):
        if r["filingDate"][i] < since.isoformat():
            break  # newest first
        if form in ("8-K", "8-K/A"):
            said = [ITEMS_8K[k] for k in (r["items"][i] or "").split(",") if k in ITEMS_8K]
            if not said:
                continue  # exhibits, votes and bylaws only
            title = f"{name} {form}: {', '.join(said)}"
        elif form in FORMS:
            title = f"{name} {FORMS[form]}"
        else:
            continue
        acc, doc = r["accessionNumber"][i], r["primaryDocument"][i]
        folder = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/"
        # An 8-K's index lists its exhibits (99.1 is the press release); other forms open on the document itself.
        page = doc.endswith((".htm", ".html")) and not form.startswith(("8-K", "6-K"))
        url = folder + (doc if page else f"{acc}-index.htm")
        when = parse_time(r["acceptanceDateTime"][i]) or parse_time(r["filingDate"][i])
        it = make(title, "SEC filing", url, when, "filing")
        if it:
            out.append(it)
    return out


_EXCHANGES: dict[str, str] | None = None
_EX_LOCK = threading.Lock()


def exchange_of(ticker: str) -> str | None:
    """NASDAQ / NYSE / CBOE, as TradingView names them. SEC's map is fetched at most once a run."""
    global _EXCHANGES
    with _EX_LOCK:
        if _EXCHANGES is None:
            try:
                rows = json.loads(fetch(SEC_EXCHANGES, accept="application/json"))["data"]
                _EXCHANGES = {r[2]: r[3] for r in rows if r[2] and r[3]}
            except Exception as e:  # noqa: BLE001
                print(f"  exchange map: {why(e)}", file=sys.stderr)
                _EXCHANGES = {}
    e = _EXCHANGES.get(ticker.replace(".", "-")) or _EXCHANGES.get(ticker)
    names = {"Nasdaq": "NASDAQ", "NYSE": "NYSE", "CBOE": "CBOE", "NYSE American": "AMEX", "NYSE Arca": "AMEX"}
    return names.get(e or "")


# ---------------------------------------------------------------- is it about this company?

SUFFIX = re.compile(r"(?:,?\s+(?:Inc\.?|Corp\.?|Corporation|Company|Companies|Co\.?|Holdings|Group|Technologies|"
                    r"Technology|Pharmaceuticals|Sciences|Laboratories|Networks|Platforms|Scientific|Systems|"
                    r"International|plc|Ltd\.?|US|Markets|Management|Motor|Motors|Bancorp|Brands|Industries|"
                    r"Therapeutics|Biosciences|Communications|Solutions|Software|Worldwide|Enterprises|Labs|Resorts|"
                    r"Entertainment|Foods|Athletica))+$")
EXTRA = {"GOOGL": ["Google"], "GOOG": ["Google"], "META": ["Facebook"], "BRK.B": ["Berkshire"], "AAPL": ["iPhone"],
         "AMZN": ["AWS"], "JPM": ["JPMorgan", "J.P. Morgan", "JP Morgan"], "BAC": ["BofA"], "C": ["Citi"],
         "GS": ["Goldman"], "TSM": ["TSMC"], "XOM": ["Exxon", "ExxonMobil"], "JNJ": ["J&J"], "PG": ["P&G"],
         "LLY": ["Lilly"], "KO": ["Coke"], "PEP": ["Pepsi"], "DIS": ["Disney"], "TMUS": ["T-Mobile"],
         "SCHW": ["Schwab"], "BKNG": ["Booking.com"], "NVO": ["Novo"], "BMY": ["Bristol-Myers", "Bristol Myers"],
         "ADP": ["ADP"], "VLO": ["Valero"], "NEE": ["NextEra"], "UNH": ["UnitedHealthcare", "Optum"], "GM": ["GM"],
         "F": ["Ford"], "GE": ["GE"], "DOW": ["Dow Inc", "Dow Chemical"], "NDAQ": ["Nasdaq Inc", "Nasdaq, Inc"],
         "MSTR": ["MicroStrategy"], "XYZ": ["Block Inc", "Cash App"], "RTX": ["Raytheon"], "LMT": ["Lockheed"],
         "NOC": ["Northrop"], "PDD": ["Temu"], "MELI": ["Mercado Libre"], "NU": ["Nubank"], "APO": ["Apollo"],
         "HOOD": ["Robinhood"], "CBOE": ["Cboe"], "FICO": ["FICO"], "LULU": ["Lululemon"], "CMG": ["Chipotle"],
         "ORLY": ["O'Reilly"], "ODFL": ["Old Dominion"], "HIMS": ["Hims"], "IFF": ["IFF"], "JD": ["JD"],
         "SKYD": ["Paramount"], "ABNB": ["Airbnb"], "PM": ["Philip Morris"], "MO": ["Altria"]}
NEVER = {"News", "Dow", "Nasdaq", "Strategy"}       # a stock's name that is mostly something else
# Names that are also plain words: they count only as "<Name>'s", "<Name> Inc", "<Name> stock" and the like.
STRICT = {"Ball", "Block", "Target", "Progressive", "Southern", "Coherent", "Flex", "Snap", "Toast", "Dover", "Waters",
          "Hartford", "Visa", "Fox", "Booking", "Affirm", "Upstart", "Mosaic", "Palo Alto", "Monster", "Principal",
          "Carnival", "Shell", "Apollo", "Everpure", "Generac", "Gartner", "Q"}
COMMON = {"General", "American", "United", "First", "National", "Global", "Western", "Northern", "Eastern", "Central",
          "Pacific", "Atlantic", "Public", "Digital", "Universal", "Live", "Old", "Royal", "Federal", "Health", "Texas"}
# Tickers that are words or common abbreviations: matched only as $T, (T) or NYSE:T.
WORDS = set("a ai all amp app are be ball br c cat cf coo cost d dash de doc dow ed eg el es exe f fast fig fix "
            "flex ge gen gl gm gs has hd hood hum ice ip ir it j key keys kim l low luv ma mas met mo mp ms mu net "
            "ni now nu o on p path pg ph pm q reg rf rl se snap snow so spot ste sw t team tech tel tt ups usb v well "
            "wm zs".split())
BROKERS = {"JPM", "GS", "MS", "BAC", "C", "WFC", "UBS", "HSBC", "RJF", "BCS", "DB", "JEF", "EVR", "MUFG"}
EXCHANGE_TAG = re.compile(r"\b(?:NYSE|NASDAQ|Nasdaq|NYSEARCA|NYSE American|CBOE|OTC)\s*:\s*([A-Z][A-Z.]{0,6})\b|"
                          r"\$([A-Z][A-Z.]{0,5})\b|\(([A-Z]{2,5}(?:\.[A-Z])?)\)")
# Parenthesised capitals that aren't tickers.
ACRONYMS = set("AI EV EVS FDA SEC ECB BOJ IPO ETF ETFS GDP CEO CFO US UK EU IMF OPEC FTC DOJ EPA FAA ADR ESG EPS CPI "
               "PCE PPI AGM NYSE LLM GPU CPU API SAAS AWS NIH CMS DOE DOD NATO WHO ATH YOY QOQ TTM FY PT REIT".split())


def _base(sym: str) -> str:
    return re.sub(r"[.\-/][A-Z]$", "", sym)


def _alts(names) -> str:
    return "|".join(re.escape(n).replace(r"\-", "[-–]") for n in sorted(names, key=len, reverse=True))


class Company:
    """Who a stock is in headlines: its names, its share classes, and other companies whose names contain its own."""

    def __init__(self, u: dict, univ: list[dict]):
        self.ticker, self.cik = u["ticker"], u.get("cik") or ""
        sibs = {x["ticker"] for x in univ if self.cik and x.get("cik") == self.cik} | {self.ticker}
        self.symbols = sibs | {_base(s) for s in sibs}
        full = re.sub(r"\s*\(.*?\)", "", u["name"]).replace("–", "-").strip(" &,")
        self.name = full
        short = SUFFIX.sub("", full).strip(" &,")
        firsts = {x["name"].split()[0] for x in univ if x.get("cik") != self.cik and x.get("name")}
        names = [full]
        if short and short != full and short not in COMMON and short not in firsts:
            names.append(short)
        names += EXTRA.get(self.ticker, [])
        names = [n for n in dict.fromkeys(names) if n not in NEVER and len(n) >= 2]
        self.names = names
        loose, strict = [n for n in names if n not in STRICT], [n for n in names if n in STRICT]
        self.rx_loose = re.compile(rf"(?<![\w&])(?:{_alts(loose)})(?![\w&])", re.I) if loose else None
        self.rx_strict = re.compile(
            rf"(?<![\w&])(?:{_alts(strict)})(?:['’]s\b|,? (?:Inc|Corp|Co|Company|Holdings|Group|plc|stock|shares|"
            rf"earnings|CEO|results)\b|\s*\()", re.I) if strict else None
        # Other companies whose names hold one of ours ("GE Vernova" for GE) are blanked out before we look.
        others = {re.sub(r"\s*\(.*?\)", "", x["name"]).replace("–", "-").strip(" &,") for x in univ
                  if x["ticker"] not in sibs and x.get("name")}
        mine = [re.compile(rf"(?<!\w){re.escape(n)}(?!\w)", re.I) for n in names]
        inside = [o for o in others if o not in names and any(rx.search(o) for rx in mine)]
        self.rx_others = re.compile(rf"(?<!\w)(?:{_alts(inside)})(?!\w)", re.I) if inside else None
        word = self.ticker.lower() in WORDS or len(self.ticker) < 2
        tk = re.escape(self.ticker)
        self.rx_ticker = re.compile(rf"\${tk}\b|\b(?:NYSE|NASDAQ|Nasdaq|NYSEARCA|CBOE)\s*:\s*{tk}\b|\(\s*{tk}\s*\)" +
                                    ("" if word else rf"|(?<![\w$.&'-]){tk}(?![\w&-])"))
        # A bank's name in someone else's story: "price target cut by JPMorgan", "Buy Boeing, says Citi".
        self.broker_use = re.compile(
            rf"(?:target|rating|coverage|outlook|estimates?|forecast|upgraded|downgraded|initiated|reiterated|"
            rf"lowered|raised|cut|boosted|trimmed|bump|nod|call|pick)\s+(?:\w+\s+){{0,2}}(?:by|at|from|with)\s+"
            rf"(?:{_alts(names)})\b|"
            rf"\b(?:according to|via|per|cites?)\s+(?:{_alts(names)})\b|"
            rf"\b(?:says|said|tells|told)\s+(?:{_alts(names)})\s*(?:[.,;:!?)]|$)|"
            rf"(?:{_alts(names)})(?:['’]s)?[/\w-]*\s+(?:still |now |also |again )?"
            r"(?:analysts?|strategists?|economists?|research|survey|poll|note|desk|team|bull|bear|says|said|sees|"
            r"expects|predicts|forecasts?|believes|thinks|recommends|prefers|favou?rs|bets|flags|touts|upgrades?|"
            r"downgrades?|maintains|initiates|reiterates|resumes|starts|revises|rates|likes|warns|names|terms|dubs|"
            r"picks|turns|calls|"
            r"is (?:bullish|bearish|betting)|bullish|bearish|top picks?|"
            r"(?:raises|lifts|lowers|cuts|boosts|trims)\s+(?:[\w$.,'-]+\s+){0,4}(?:price\s+target|target|rating))",
            re.I) if self.ticker in BROKERS else None

    def named(self, title: str) -> bool:
        t = self.rx_others.sub(" ", title) if self.rx_others else title
        if self.broker_use and self.broker_use.search(t):
            t = self.broker_use.sub(" ", t)  # "price target cut by JPMorgan" is not news about JPMorgan
        for rx in (self.rx_loose, self.rx_strict):
            for m in rx.finditer(t) if rx else ():
                s = m.group(0)
                if s[:1].isupper() or s[:1].isdigit() or any(s.startswith(n) for n in self.names):
                    return True
        shouting = sum(c.isupper() for c in t) > 0.6 * max(1, sum(c.isalpha() for c in t))
        return bool(self.rx_ticker.search(t)) and not (shouting and self.ticker.lower() in WORDS)

    def relevant(self, x: dict) -> bool:
        if x["kind"] == "filing":
            return True
        title = x["title"]
        tags = {a or b or c for a, b, c in EXCHANGE_TAG.findall(title)} - ACRONYMS
        if tags and not tags & self.symbols and not {_base(t) for t in tags} & self.symbols:
            return False  # tagged with other companies' tickers only
        if x["kind"] == "press-release":  # its own release names it up front; other companies' releases don't
            return self.named(" ".join(title.split()[:4]))
        if self.named(title):
            return True
        if self.broker_use:  # TradingView tags a bank to stories that only quote its analysts
            return False
        # Not named, but TradingView tags it to this company alone (its share classes count): a story about it
        # ("GitHub ships Copilot ..."). Tagged alongside others, it's usually market commentary.
        syms = x.get("_syms") or []
        return bool(syms) and all(s in self.symbols or _base(s) in self.symbols for s in syms)

    def query(self) -> str:
        names = [n for n in self.names if n not in STRICT][:3] or [self.name]
        return " OR ".join(f'"{n}"' for n in names) + " stock"


# ---------------------------------------------------------------- one story, many outlets

STOP = set("a an the of to in on for and or as at by with from is are was be its it this that after amid over into "
           "vs via than about new why what how here heres who will may could would can just more most says said "
           "report reports today week stock stocks share shares market markets inc corp co company news update "
           "live".split())


def words(title: str) -> set[str]:
    t = re.sub(r"['’]s\b", "", title.lower())
    out = set()
    for w in re.findall(r"[a-z0-9][a-z0-9.,%]*", t):
        w = w.strip(".,%")
        if not w or w in STOP:
            continue
        if w[0].isdigit():
            w = re.sub(r"\.0+$", "", w.replace(",", ""))
        elif len(w) > 5:
            w = w[:5]  # a crude stem: plunges, plunged, plunge -> plung
        out.add(w)
    return out


ANALYST = re.compile(r"^\s*(.+?)\s+(?:maintains|upgrades|downgrades|initiates|reiterates|resumes|assumes|"
                     r"reinstates)\b", re.I)
UP = set("up rise rises rose jump jumps jumped gain gains soar soars surge surges rally rallies climb climbs beat "
         "beats raise raises raised upgrade upgrades higher record".split())
DOWN = set("down fall falls fell drop drops slide slides slump slumps sink sinks plunge plunges tumble tumbles crash "
           "crashes miss misses cut cuts lower lowers downgrade downgrades".split())


def _way(title: str) -> int:
    w = set(re.findall(r"[a-z]+", title.lower()))
    return (bool(w & UP) and not w & DOWN) - (bool(w & DOWN) and not w & UP)


def same_story(a: dict, b: dict) -> bool:
    if a["id"] == b["id"]:
        return True
    if "filing" in (a["kind"], b["kind"]) or abs((a["_dt"] - b["_dt"]).total_seconds()) > 36 * 3600:
        return False
    ba, bb = ANALYST.match(a["title"]), ANALYST.match(b["title"])
    if ba and bb and ba.group(1).lower() != bb.group(1).lower():
        return False  # two brokers' notes on the same day read alike but aren't one story
    if _way(a["title"]) * _way(b["title"]) < 0:
        return False  # "up 5%" and "down 5%" are two stories
    A, B = a.setdefault("_w", words(a["title"])), b.setdefault("_w", words(b["title"]))
    if not A or not B:
        return False
    n, small = len(A & B), min(len(A), len(B))
    return n / len(A | B) >= 0.5 or (small >= 3 and n / small >= 0.8)


def fold(head: dict, x: dict) -> None:
    """x is another outlet's take on head's story: note the outlet. An identical headline is a syndicated copy of the
    same article (Yahoo carrying The Motley Fool), not a second outlet."""
    copy = re.sub(r"\W+", " ", head["title"].lower()) == re.sub(r"\W+", " ", x["title"].lower())
    for s in [x["source"], *(x.get("also") or [])]:
        if s and s != head["source"] and s not in head["also"] and not (copy and s == x["source"]):
            head["also"].append(s)
    del head["also"][6:]


def tier(x: dict) -> float:
    if x["kind"] == "filing":
        return 4.0 if MAJOR_FILING.search(x["title"]) else 2.0  # few and primary: a material one always makes the cut
    if x["kind"] == "press-release":
        return 2.5
    if x["source"] == "TradingView":  # its analyst-action lines: a rating change counts, a maintained one barely
        return 2.0 if re.search(r"\b(?:upgrades|downgrades|initiates|resumes|reinstates)\b", x["title"], re.I) else 1.0
    return TIER.get(x["source"], 1.0)


def worth(x: dict, now: dt.datetime) -> float:
    age = max(0.0, (now - x["_dt"]).total_seconds() / 86400)
    return tier(x) + 0.6 * min(len(x["also"]), 4) - 0.15 * age


def merge(old: list[dict], new: list[dict], cap: int) -> tuple[list[dict], int]:
    """Old items first, so a story keeps its id and link; new takes on it only add their outlet to `also`."""
    now = md.now_et()
    cut = now - dt.timedelta(days=DAYS)
    kept = []
    for x in old:
        d = parse_time(x.get("published"))
        if d and d >= cut and x.get("title") and not is_junk(x):
            kept.append({**x, "also": list(x.get("also") or []), "_dt": d, "_old": True})
    new = [x for x in new if cut <= x["_dt"] <= now + dt.timedelta(hours=1)]
    new.sort(key=lambda x: (x["source"] in SYNDICATORS, -tier(x), x.get("_via", 0), x["_dt"]))
    heads: list[dict] = []
    for x in kept + new:
        for h in heads:
            if same_story(h, x):
                fold(h, x)
                break
        else:
            heads.append(x)
    heads.sort(key=lambda x: worth(x, now), reverse=True)
    out = sorted(heads[:cap], key=lambda x: x["_dt"], reverse=True)
    fresh = sum(1 for x in out if not x.get("_old"))
    return [{k: v for k, v in x.items() if not k.startswith("_")} for x in out], fresh


# ---------------------------------------------------------------- files

def path_for(ticker: str | None) -> Path:
    return OUT / f"{ticker or 'market'}.json"  # the raw ticker (BRK.B.json): detect.py and the builder read it so


def load(ticker: str | None = None) -> dict | None:
    """A stock's headlines file (the market's when ticker is None), or None. No network."""
    try:
        return json.loads(path_for(ticker).read_text())
    except (OSError, ValueError):
        return None


def save(p: Path, d: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")
    os.replace(tmp, p)


# ---------------------------------------------------------------- stocks

def update_stock(c: Company) -> tuple[str, str, int]:
    """Fetch, filter, merge and write one stock. Returns (ok|partial|failed, what went wrong, new headlines)."""
    old = load(c.ticker) or {}
    ex = old.get("exchange") or exchange_of(c.ticker)
    since = md.now_et().date() - dt.timedelta(days=DAYS)
    got, errs = [], []

    def tv():
        for exch in [ex] if ex else ["NYSE", "NASDAQ"]:  # no exchange on file: try both, keep the one that answers
            items = tradingview(TV_SYMBOL.format(urllib.parse.quote(f"{exch}:{c.ticker}")))
            if items or ex:
                return exch, items
        return None, []

    jobs = [("tradingview", tv),
            ("google", lambda: (None, google_news(f"{c.query()} when:{3 if old.get('items') else DAYS}d"))),
            ("sec", lambda: (None, sec_filings(c.cik, c.name, since) if c.cik else []))]
    for i, (name, job) in enumerate(jobs):
        if i:
            time.sleep(PAUSE)
        try:
            exch, items = job()
            ex = exch or ex
            got += items
        except Exception as e:  # noqa: BLE001 - one source failing never stops the others
            errs.append(f"{name} {why(e)}")
    if len(errs) == len(jobs):
        return "failed", "; ".join(errs), 0
    fresh = [x for x in got if c.relevant(x) and not is_junk(x)]
    items, n_new = merge(old.get("items") or [], fresh, MAX_STOCK)
    d = {"ticker": c.ticker, "updated": iso(md.now_et()), **({"exchange": ex} if ex else {}), "items": items}
    save(path_for(c.ticker), d)
    return ("partial" if errs else "ok"), "; ".join(errs), n_new


def cap_of(q: dict | None) -> float:
    m = re.match(r"([\d.]+)\s*([TBMK]?)", str((q or {}).get("mktcap") or ""))
    return float(m.group(1)) * {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3, "": 1}[m.group(2)] if m else 0.0


def top(n: int) -> list[str]:
    """The n biggest by market cap in data/quotes/latest.json, then universe order for any without one."""
    q = md.latest_quotes().get("quotes") or {}
    univ = [u["ticker"] for u in md.universe()]
    capped = sorted((t for t in univ if cap_of(q.get(t))), key=lambda t: -cap_of(q.get(t)))
    return (capped + [t for t in univ if t not in set(capped)])[:n]


def run_stocks(tickers: list[str], verbose: bool = False) -> dict[str, tuple[str, str, int]]:
    univ = md.universe()
    umap = {u["ticker"]: u for u in univ}
    tickers = [t if t in umap else t.replace("-", ".") for t in tickers]
    res: dict[str, tuple[str, str, int]] = {t: ("failed", "not in universe", 0) for t in tickers if t not in umap}
    todo = [t for t in tickers if t in umap]
    started = time.monotonic()

    def one(t: str):
        try:
            return update_stock(Company(umap[t], univ))
        except Exception as e:  # noqa: BLE001
            return "failed", why(e), 0

    with ThreadPoolExecutor(WORKERS) as pool:
        for t, r in zip(todo, pool.map(one, todo)):
            res[t] = r
            if verbose:
                print(f"  {t:6} {r[0]:7} +{r[2]:<3} {r[1]}", flush=True)
    n = {k: sum(1 for r in res.values() if r[0] == k) for k in ("ok", "partial", "failed")}
    bad = [f"{t} ({r[1]})" for t, r in res.items() if r[0] != "ok"]
    print(f"news: {len(res)} stocks in {time.monotonic() - started:.0f}s: {n['ok']} ok, {n['partial']} partial, "
          f"{n['failed']} failed; {sum(r[2] for r in res.values())} new headlines"
          + (f" | {'; '.join(bad[:8])}{' ...' if len(bad) > 8 else ''}" if bad else ""), flush=True)
    return res


# ---------------------------------------------------------------- market

def market_news(x: dict, which: str, ours: set[str]) -> bool:
    if is_junk(x):
        return False
    said = bool(MARKET_WORDS.search(x["title"]) or names_rx().search(x["title"]))
    # Reuters' whole wire: tagged with one of our stocks or an index, rate or commodity, and about markets.
    if which == "tagged":
        return said and bool({_base(s) for s in x.get("_syms") or []} & (ours | MACRO_SYMBOLS))
    return said or which == "all"


def run_market() -> dict:
    started = time.monotonic()
    ours = {_base(u["ticker"]) for u in md.universe()}
    got, errs = [], []
    for name, url, which in MARKET_FEEDS:
        try:
            items = tradingview(url) if "tradingview" in url else rss(url, name)
        except Exception as e:  # noqa: BLE001
            errs.append(f"{name} {why(e)}")
            continue
        got += [x for x in items if market_news(x, which, ours)]
        time.sleep(PAUSE)
    if len(errs) == len(MARKET_FEEDS):
        print(f"news: market failed, kept the old file | {'; '.join(errs)}")
        return load(None) or {}
    old = load(None) or {}
    items, n_new = merge(old.get("items") or [], got, MAX_MARKET)
    d = {"ticker": "MARKET", "updated": iso(md.now_et()), "items": items}
    save(path_for(None), d)
    print(f"news: market {len(items)} headlines, {n_new} new, {len(MARKET_FEEDS) - len(errs)}/{len(MARKET_FEEDS)} "
          f"feeds in {time.monotonic() - started:.0f}s" + (f" | {'; '.join(errs)}" if errs else ""), flush=True)
    return d


# ---------------------------------------------------------------- X posts

TWEET_URL = re.compile(r"(?:x|twitter)\.com/(\w{1,15})/status(?:es)?/(\d+)")
_TWEET_LOCK = threading.Lock()


def _token(tid: str) -> str:
    """react-tweet's token for the syndication endpoint: (id / 1e15 * pi) in base 36, zeros and the point dropped."""
    x = int(tid) / 1e15 * math.pi
    digits, ip, fp = "0123456789abcdefghijklmnopqrstuvwxyz", int(x), x - int(x)
    s = ""
    while ip:
        ip, r = divmod(ip, 36)
        s = digits[r] + s
    for _ in range(11):
        fp *= 36
        s += digits[int(fp)]
        fp -= int(fp)
    return re.sub(r"0+", "", s) or "a"


def _syndication(tid: str) -> dict | None:
    """The JSON react-tweet renders from (cdn.syndication.twimg.com). None when the post is gone."""
    try:
        d = json.loads(fetch(f"https://cdn.syndication.twimg.com/tweet-result?id={tid}&token={_token(tid)}&lang=en",
                             accept="application/json"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    if not d or d.get("__typename") == "TweetTombstone" or not d.get("user"):
        return None
    ents = d.get("entities") or {}
    text = d.get("text") or ""
    for m in ents.get("media") or []:
        text = text.replace(m.get("url", "\0"), "")
    for u in ents.get("urls") or []:
        text = text.replace(u.get("url", "\0"), u.get("display_url") or u.get("expanded_url") or "")
    text = html.unescape(text).strip()
    if (d.get("display_text_range") or [0])[0] > 0:  # a reply: X hides the leading @mentions
        text = re.sub(r"^(?:@\w+\s+)+", "", text)
    if d.get("note_tweet"):  # a long post: the endpoint only sends its first 280 characters
        text = text.rstrip(" .…") + "…"
    u = d["user"]
    media = [p["url"] for p in d.get("photos") or [] if p.get("url")]
    if (d.get("video") or {}).get("poster"):
        media.append(d["video"]["poster"])
    when = parse_time(d.get("created_at"))
    return {"url": f"https://x.com/{u['screen_name']}/status/{tid}", "author": u.get("name") or u["screen_name"],
            "handle": u["screen_name"], "text": text, "created_at": iso(when) if when else None,
            "avatar": (u.get("profile_image_url_https") or "").replace("_normal.", "_bigger.") or None, "media": media}


def _oembed(handle: str, tid: str) -> dict | None:
    """X's official oEmbed (publish.x.com): name, handle, text and the date, but no avatar or time of day."""
    url = f"https://x.com/{handle}/status/{tid}"
    try:
        d = json.loads(fetch("https://publish.x.com/oembed?" + urllib.parse.urlencode(
            {"url": url, "omit_script": "1", "dnt": "true"}), accept="application/json"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    p = re.search(r"<p[^>]*>(.*?)</p>", d.get("html") or "", re.S)
    text = re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", "\n", p.group(1))) if p else ""
    text = re.sub(r"\s*pic\.(?:twitter|x)\.com/\w+", "", text)
    day = re.findall(r">([A-Z][a-z]+ \d{1,2}, \d{4})</a>", d.get("html") or "")
    when = dt.datetime.strptime(day[-1], "%B %d, %Y").replace(hour=12, tzinfo=md.ET) if day else None
    who = (d.get("author_url") or url).rstrip("/").split("/")[-1]
    return {"url": f"https://x.com/{who}/status/{tid}", "author": d.get("author_name") or who, "handle": who,
            "text": html.unescape(text).strip(), "created_at": iso(when) if when else None, "avatar": None, "media": []}


def tweets() -> dict:
    """The cached X post cards, keyed by post id. No network."""
    try:
        return json.loads(TWEETS.read_text())
    except (OSError, ValueError):
        return {}


def tweet_card(url: str, refresh: bool = False) -> dict | None:
    """An X post as {url, author, handle, text, created_at, avatar, media} for a static card at build time, cached in
    data/news/tweets.json by post id. Tries the syndication JSON, then oEmbed. A post that is gone (both answer 404)
    is dropped from the cache and returns None; a network error raises and leaves the cache alone."""
    m = TWEET_URL.search(url or "")
    if not m:
        raise ValueError(f"not an X post URL: {url!r}")
    handle, tid = m.groups()
    if not refresh and tid in tweets():
        return tweets()[tid]
    try:
        card = _syndication(tid)
    except Exception as e:  # noqa: BLE001 - the official endpoint is the fallback
        print(f"  syndication {tid}: {why(e)}; trying oEmbed", file=sys.stderr)
        card = None
    card = card or _oembed(handle, tid)
    with _TWEET_LOCK:
        cache = tweets()
        if card:
            cache[tid] = {**card, "fetched": iso(md.now_et())}
        else:
            cache.pop(tid, None)
        save(TWEETS, cache)
    return card


def content_tweets() -> list[str]:
    """Every post a ```tweet block in content/ links to."""
    urls = []
    for f in sorted((md.ROOT / "content").rglob("*.md")):
        urls += re.findall(r"```tweet\s*\n\s*(\S+)\s*\n\s*```", f.read_text(errors="ignore"))
    return list(dict.fromkeys(urls))


def run_tweets(urls: list[str], refresh_days: int = 7) -> None:
    """Cache the posts not cached yet, and re-check those fetched over refresh_days ago (dropping deleted ones)."""
    have, n_new, n_gone, errs = tweets(), 0, 0, []
    cut = md.now_et() - dt.timedelta(days=refresh_days)
    for url in urls:
        m = TWEET_URL.search(url)
        if not m:
            errs.append(f"bad URL {url[:60]}")
            continue
        old = have.get(m.group(2))
        if old and (parse_time(old.get("fetched")) or cut) > cut:
            continue
        try:
            card = tweet_card(url, refresh=True)
            n_new += bool(card and not old)
            n_gone += card is None
        except Exception as e:  # noqa: BLE001
            errs.append(f"{m.group(2)} {why(e)}")
        time.sleep(PAUSE)
    print(f"news: {len(urls)} X posts, {n_new} newly cached, {n_gone} gone"
          + (f" | {'; '.join(errs)}" if errs else ""), flush=True)


# ---------------------------------------------------------------- command line

def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(prog="news.py", description="Outside headlines and X post cards -> data/news/")
    ap.add_argument("--tickers", help="comma-separated tickers, e.g. AAPL,NVDA")
    ap.add_argument("--top", type=int, metavar="N", help="the N biggest stocks by market cap")
    ap.add_argument("--all", action="store_true", help="the whole universe")
    ap.add_argument("--market", action="store_true", help="market-wide headlines -> data/news/market.json")
    ap.add_argument("--tweet", nargs="+", metavar="URL", help="cache these X posts -> data/news/tweets.json")
    ap.add_argument("--tweets", action="store_true", help="cache every post a ```tweet block in content/ links to")
    ap.add_argument("-v", "--verbose", action="store_true", help="a line per stock")
    a = ap.parse_args(argv)
    tickers = ([t.strip().upper() for t in a.tickers.split(",") if t.strip()] if a.tickers else []) + \
        (top(a.top) if a.top else []) + ([u["ticker"] for u in md.universe()] if a.all else [])
    if not (tickers or a.market or a.tweet or a.tweets):
        ap.print_help()
        return
    for url in a.tweet or []:
        try:
            card = tweet_card(url, refresh=True)
            print(json.dumps(card, indent=1, ensure_ascii=False) if card else f"news: {url} is gone or private")
        except Exception as e:  # noqa: BLE001
            print(f"news: {url}: {why(e) if not isinstance(e, ValueError) else e}")
    if a.tweets:
        run_tweets(content_tweets())
    if tickers:
        run_stocks(list(dict.fromkeys(tickers)), a.verbose)
    if a.market:
        run_market()


if __name__ == "__main__":
    main(sys.argv[1:])
