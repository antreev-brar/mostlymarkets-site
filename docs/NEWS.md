# News files

Outside headlines for each stock and for the market, plus cached X posts, from free feeds that need no key. Built by `pipeline/news.py` (Python standard library only). We store the headline, the outlet, the time and the link, never the article text.

```
python3 pipeline/news.py --tickers AAPL,NVDA   # these stocks
python3 pipeline/news.py --top 150             # the 150 biggest by market cap (data/quotes/latest.json), ~2.5 min
python3 pipeline/news.py --all                 # the whole universe (~580), ~10 min
python3 pipeline/news.py --market              # market-wide headlines, ~12 s
python3 pipeline/news.py --tweet <x.com post URL> [more URLs]   # cache X posts
python3 pipeline/news.py --tweets              # cache every post a ```tweet block in content/ links to
```

Add `-v` for a line per stock. Every run prints one summary line, for example `news: 150 stocks in 148s: 150 ok, 0 partial, 0 failed; 4673 new headlines`. A stock is **partial** when one or two of its three sources failed. Its file is still merged and written. A stock is **failed** when all three sources failed, and then its old file is kept. One stock failing never stops the run.

## Files: `data/news/`

| File | Contents |
|---|---|
| `<TICKER>.json` | One stock. The raw ticker is the file name, so BRK.B is `BRK.B.json`, which is what `detect.py` and `site/build.py` read. At most 40 items. |
| `market.json` | Market-wide headlines in the same shape, with `"ticker": "MARKET"`. At most 60 items. |
| `tweets.json` | X post cards keyed by post id (see below). |

```json
{"ticker": "SNDK", "updated": "2026-10-31T10:19:05-04:00", "exchange": "NASDAQ", "items": [
  {"id": "7fc0405edd01acbd91d0580af8a3575ded585ada",
   "title": "Sandisk Q1 results beat, with revenue up 378% on strong datacenter demand", "source": "Reuters",
   "url": "https://www.tradingview.com/news/reuters.com,2026:newsml_L2N46F1HG:0-sandisk-q1-results-beat-...",
   "published": "2026-10-29T16:15:36-04:00", "also": [], "kind": "news"},
  {"id": "...", "title": "Rosenblatt reiterates Buy on SanDisk stock, $2,400 target on NBM", "source": "Investing.com",
   "url": "https://news.google.com/rss/articles/...", "published": "2026-10-30T07:45:03-04:00",
   "also": ["TradingView"], "kind": "news"}]}
```

- `items` are newest first, and `published` is ISO time in New York with its offset.
- `kind` is `news`, `filing` (SEC; `source` is "SEC filing") or `press-release` (the company's own release on a wire).
- `also` lists the other outlets that ran the same story under a different headline. It is empty for a story only one outlet carried. Syndicated copies (the same article on Yahoo Finance) are not counted.
- `exchange` is TradingView's exchange code for the stock, saved so later runs can skip the SEC lookup.
- `load(ticker)` / `load()` (market) and `tweets()` read the files without the network.

**History.** Each run merges with the file that's already there. A story keeps its first id and link, and later takes on it only add their outlet to `also`. Items older than 14 days drop out. When more is left than fits, items are ranked on a score:

- the outlet's tier: 3 for Reuters, Bloomberg, WSJ, Barron's, CNBC, FT, AP and MarketWatch; 2 for Seeking Alpha, Benzinga, Investing.com, Dow Jones' wire and the like; 1.5 for Yahoo Finance; 1 for the rest;
- plus 0.6 for each other outlet in `also` (counting up to 4);
- material filings (8-K results, deals, executive changes, 10-Q/10-K, 13D) score 4, and the company's own releases 2.5;
- less 0.15 for each day of age.

The best-scoring items are kept and written newest first.

## Sources

Each stock makes three requests, about a second each, with 4 stocks at a time and a short pause between one stock's requests.

| Source | What it gives | Notes |
|---|---|---|
| **TradingView** `news-headlines.tradingview.com/v2/view/headlines/symbol?symbol=NASDAQ:AAPL` | The JSON behind a symbol's News tab: the latest ~200 items from Reuters, Dow Jones (WSJ, Barron's, MarketWatch), Seeking Alpha, Benzinga, Zacks, wire press releases and TradingView's analyst-action lines. Each item has a title, source, epoch time, link (or a TradingView story page) and tagged symbols. | Needs `EXCHANGE:TICKER`; the exchange comes from SEC's `company_tickers_exchange.json`. No key or special User-Agent needed. Undocumented, so it can change without notice. Dow Jones items open on a page that shows only the headline, so a wsj.com link from Google News wins when we have both. |
| **Google News** `news.google.com/rss/search?q="Intel" stock when:14d` | Up to 100 items, ranked by relevance, with a title, outlet (`<source>`), time and link. It covers Bloomberg, CNBC, WSJ, Reuters, FT, Barron's, AP, NYT, Morningstar, IBD and others. | Kept only from outlets in the tier list. Links are `news.google.com` redirects that a browser follows to the article. A file's first run asks for 14 days, later runs for 3. |
| **SEC EDGAR** `data.sec.gov/submissions/CIK##########.json` | Filings with form, 8-K item numbers and acceptance time. | Official. Needs the declared SEC User-Agent (it refuses browser ones). Paced at 5 requests a second, gzip. |
| **Market**: CNBC RSS (top news, markets, economy, earnings), MarketWatch top stories and WSJ Markets (`feeds.content.dowjones.io`), Reuters via TradingView (`v2/headlines?provider=reuters`) | Market news. | CNBC top news and MarketWatch are kept only when the headline is about markets or names one of our companies. Reuters' wire is kept only when it is tagged with one of our stocks or a market symbol (SPX, US10Y, CL1!...) and is about markets. |

We tested other sources and don't use them:

- **Yahoo Finance RSS** answers 429 to a full Chrome User-Agent (a bare `Mozilla/5.0` works). It returns 15 to 20 items, many about other companies, and has no outlet field.
- **Nasdaq RSS** needs a browser User-Agent and is mostly Motley Fool and Zacks.
- **Finviz** has a good news table, but scraping its quote page is against its terms, and it blocks bots.
- **Reuters** has no public RSS any more. Its headlines come through TradingView.

## What gets dropped, and how a headline is matched to a stock

- **Relevance.** A headline must name the company: its universe name, a shortened name (`Micron Technology` → `Micron`), aliases in `EXTRA` (Google, TSMC, BofA...), or its ticker. Bare tickers that are words (`T`, `ON`, `NOW`, `AI`...) count only as `$T`, `(T)` or `NYSE:T`. Names that are also plain words (Target, Southern, Visa...) count only as "Target's" or "Target stock". Other companies' names that contain ours are blanked first, so "GE Vernova" doesn't count for GE.
- **TradingView tags.** A headline that doesn't name the company is kept only when TradingView tags it to the company alone.
- **Other companies' tickers.** A headline tagged only with other companies' tickers (`(NASDAQ:INTC)`, `$TFC`, `(JJSF)`) is dropped.
- **Banks.** For banks (JPM, GS, MS, C, BAC, WFC, UBS, HSBC...), headlines that only quote their analysts ("price target cut by JPMorgan", "Buy Boeing, says Citi") don't count.
- **Press releases** count only when the company is named in the first few words, so other companies' releases that mention it are dropped.
- **Junk** (`JUNK` in news.py) covers law-firm class-action notices, 13F and congressional-trade filler, MarketBeat's machine-written lines, quote pages, Zacks/Simply Wall St/GuruFocus templates, listicles ("3 stocks to buy now"), "buy or sell?" bait, Dow Jones' one-line flashes and analyst flashes (TradingView's fuller analyst lines stay), leveraged-ETF notices and UK regulatory notices.
- **One story, many outlets.** Two items are the same story when they're within 36 hours and their headline words overlap enough (Jaccard ≥ 0.5, or 80% of the shorter one). Two exceptions are never merged: two different brokers' notes, and "up" against "down".

## X posts: `data/news/tweets.json`

`tweet_card(url)` returns `{url, author, handle, text, created_at, avatar, media}` and caches it under the post id, which is what `site/build.py` reads for a ```tweet block. It tries two keyless endpoints:

1. **`cdn.syndication.twimg.com/tweet-result?id=<id>&token=<t>`** (what react-tweet uses). It gives the text, name, handle, avatar, exact time, photos and counts. Any `token` works today; we send react-tweet's.
2. **`publish.x.com/oembed?url=...`** (X's official oEmbed). It gives the name, handle, text and the date only, with no avatar and no time of day.

Both answer 404 for a deleted or private post. That post is then removed from the cache, and the card falls back to a plain link. `--tweets` caches posts that aren't cached yet and re-checks any card older than 7 days. Neither endpoint can search, so finding posts is up to the writer.

## Known limits

- **Datacenter IPs.** Everything was tested from a Mac on a home connection. From GitHub Actions:
  - SEC, CNBC and the Dow Jones feeds should work; the data job already uses SEC and CNBC.
  - Google News and TradingView may rate-limit or block datacenter IPs. Watch for `partial` lines in the summary. Google News starts answering 429 or 503 with heavy use, so keep `--top 150` to about hourly and `--all` to once a day.
  - Yahoo and Finviz are the most likely to block, and neither is used.
- **Undocumented endpoints.** TradingView's headlines JSON and X's syndication JSON are undocumented and can change without notice. Each source fails on its own and old files are kept.
- **Terms.** Show only the headline, outlet, time and a link to the original, as we do. Google News and the Dow Jones RSS feeds are offered for personal, non-commercial use, and TradingView's terms discourage automated access. For a commercial launch, a licensed feed is the safe path.
- **Heuristics miss.** Name matching misses some stories and lets the odd unrelated one through, especially for common-word names and stocks TradingView tags loosely. Only the junk rules are re-applied to items already in a file; a new relevance rule applies to new headlines.
- **Coverage depth.** TradingView's ~200 latest items span about two days for the biggest stocks and weeks for quiet ones. Google News fills older days on a file's first run.

## Wiring it in (not done yet)

- **`pipeline/data_push.sh`**: add `data/news` to the `git add -f` list. `data_pull.sh` already extracts all of `data/`.
- **`.gitignore`**: add `data/news/` next to the other data folders.
- **Schedule**: call `news.py --market --top 150` from `refresh.py` about hourly, `--all` once a day, and `--tweets` before each build.
