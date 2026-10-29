# Brief for the launch backfill writers

You are writing real stories for mostlymarkets.org, a StockStory-style site that explains why stocks move. The site launches with about 60 stories covering 22–29 October 2026 plus next week's previews. Each writer gets one slice.

## Read first, in full
1. `docs/STYLE.md`: the voice, the rules and a template per story type.
2. `docs/FORMAT.md`: the file format, the chart and highlights blocks, and the checks.

## Tools (run from the repo root, `~/Desktop/Projects/mostlymarkets/site`)
- `python3 pipeline/facts.py TKR --asof YYYY-MM-DD`: the close, % move and "What the market is telling us" sentences. Quote these numbers exactly.
- `python3 pipeline/movers.py YYYY-MM-DD [--sp500] [--n 20]`: the day's biggest close-to-close moves in our universe.
- `python3 pipeline/movers.py --week YYYY-MM-DD`: this week's moves so far.
- `data/quotes/latest.json`: live quotes, including after-hours (`ext`), as of `asof`.
- `data/calendar/<date>.json`: earnings dates, consensus EPS (`eps_forecast`) and, once reported, `eps_actual`/`surprise_pct` (from Nasdaq).
- `data/universe/universe.json`: the 582 tickers we cover. Cashtags and `tickers` must come from it.
- `python3 pipeline/check.py content/articles/<your files>`: run it on every file. A file isn't finished until it passes.

## Research
- **It's late October 2026, and the world has moved on from what you remember.** Kevin Warsh chairs the Fed, rates are 3.75–4.00% after a September hike, oil is around $100, and Anthropic has filed to go public. **Verify every fact by searching; never fill gaps from memory.** Names, titles, numbers and dates all come from sources.
- Every fact needs two independent sources (company releases and SEC filings first), with their URLs in `sources`. Use WebSearch and WebFetch. Prefer Reuters, CNBC, AP, Bloomberg, the WSJ, the FT, MarketWatch, Barron's, Yahoo Finance, Investing.com, company IR pages and sec.gov.
- **Already-checked material:** the Mostly Markets newsletter issues in `~/Desktop/Projects/mostlymarkets/<date>-<weekday>/post.md` (2026-10-22-thursday, 2026-10-23-friday, 2026-10-26-monday, 2026-10-26-anthropic-ipo, 2026-10-27-tuesday, 2026-10-28-wednesday). Each issue covers the session of the day before its folder's date:
  - the 10-23 folder covers Thursday 22 October
  - the 10-27 folder covers Monday 26 October
  - the 10-28 folder covers Tuesday 27 October
  - the 10-28-wednesday file is headed "It's Wednesday" but describes Wednesday 28 October's session, written that night

  **Read the post to see which day it covers.** Their `data/` folders hold the raw quotes. Reuse their facts and quotes freely; they were checked against two sources. Re-confirm any price against `facts.py`. Don't copy whole paragraphs; rewrite each story in our story format.
- Prices and % moves for stocks come only from `facts.py`/`data/quotes`. Index levels, yields, oil and bitcoin come from two outlets or the newsletter's data folders.

## Writing
- Follow the template for the type in `docs/STYLE.md`. Use the byline that matches the beat.
- **`published`:** the New York time the story would really have gone out:
  - why-it-moved: 10:30, 12:30, 14:30 or 16:15 on the day
  - recaps: 20–60 minutes after the release
  - market wraps: 16:45–17:30
  - movers: 09:00 the next morning
  - previews: 20:00 the evening before

  Use -04:00, since daylight saving time ends on 1 November. **Never later than now** (`TZ=America/New_York date`). For a story about something still to come, use the current time.
- **Intraday moves:** for a story published during a session, the move is the one at that time. If you can't know the intraday level, publish the story at 16:15, after the close, and use the close.
- **Charts:** at least one per story, except `movers`. Use `price` charts for stocks. For `bars`, use values from releases or SEC filings and name the source.
- **Links:** link to stories in your own slice by URL (`/news/<date>/<slug>/`) where it helps, for example from a market wrap to the day's why-it-moved stories. Don't link to stories outside your slice; you can't know their slugs.
- **File names:** `content/articles/<YYYY-MM-DD>-<slug>.md`, where the slug is the title in lower case with hyphens and no "the-" or "a-" at the start. Don't create or edit anything outside `content/articles/`.

## Report back
- A table: file, type, title, and the one fact you're least sure of.
- Anything you found but couldn't confirm twice, and therefore left out.
- The `check.py` summary line.
