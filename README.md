# mostlymarkets.org

A StockStory-style site that explains why stocks move. It publishes stories every few hours on market days, and has a page for each of the 582 stocks it covers.

## How it runs

```
every 15 min (GitHub Actions: data.yml)                     scheduled cloud routine (Claude)
  refresh quotes / calendar / prices / SEC filings            pulls the queue + data
  detect events  ──►  events/queue/*.json  ──────────────►    researches, writes content/articles/*.md
  rebuild + deploy the site (fresh prices)                    checks, then pushes each story to main
        ▲                                                            │
        └──────── build.yml rebuilds + deploys on every push ◄───────┘
```

- **Events** (`pipeline/detect.py`):
  - earnings released (an SEC 8-K Item 2.02, or past the calendar time), for companies worth $20bn or more
  - a stock moving 4–5% or more (a group of three or more in one industry becomes a basket story)
  - after-hours moves of 8% or more
  - tomorrow's big reporters
  - the close
  - yesterday's movers, and this week's movers on Fridays
  - a top-tier economic release
  - Fed decision days
  - a picks list on Tuesdays and Thursdays
  - the week ahead on Sundays

  Daily caps keep the feed readable.
- **Writer** (`pipeline/WRITER.md`): the runbook the routine follows. Two sources per fact, prices only from our data, `pipeline/check.py` must pass.
- **Site** (`site/build.py`): a static build, standard-library Python, into `dist/`:
  - the feed, story pages and stock pages (price charts plus SEC financials)
  - Discover lists, sectors, the earnings calendar, RSS and the sitemap

  The design is warm paper and ink with a highlighter yellow; the CSS is in `site/static/style.css`.
- **Data:** prices from Nasdaq, live quotes from CNBC, calendars from Nasdaq, financials from SEC XBRL, 8-K releases from EDGAR. Market data lives on the `data` branch (force-pushed, no history) so `main` stays small.

## Local use

```bash
bash pipeline/data_pull.sh                 # or: python3 pipeline/marketdata.py history && ... quotes && ... calendar
python3 site/build.py && python3 -m http.server -d dist 8787
python3 pipeline/check.py                  # validate every story
python3 pipeline/detect.py --dry           # what would be queued now
```

## Docs
- `docs/STYLE.md`: voice, rules and a template per story type
- `docs/FORMAT.md`: the story file format, chart blocks and checks
- `docs/DATA.md`: the data files
- `pipeline/WRITER.md`: the writer's runbook
