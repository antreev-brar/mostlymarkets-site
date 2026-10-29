# Article format

Every story is one Markdown file with TOML front matter:

`content/articles/<YYYY-MM-DD>-<slug>.md` → published at `/news/<YYYY-MM-DD>/<slug>/`.

The date is the New York date of `published`. `python3 pipeline/check.py <file>` validates a file; `python3 site/build.py` renders the site.

## Front matter

```toml
+++
title = "Why Amazon (AMZN) Stock Is Falling Today"
dek = "Amazon fell 6.7% after hours after its cloud growth slowed to 17%, short of the 19% analysts wanted."
type = "why-it-moved"
published = 2026-10-29T16:45:00-04:00
author = "marcus-lindqvist"
tickers = ["AMZN", "MSFT"]
reason = "Earnings"
cover = "ecommerce"
moves = [
  { ticker = "AMZN", price = 227.48, change_pct = -6.69, session = "after-hours", asof = 2026-10-29T16:25:00-04:00 },
]
sources = [
  "https://www.cnbc.com/...",
  "https://www.reuters.com/...",
]
+++
```

| Field | Required | Notes |
|---|---|---|
| `title` | yes | A plain, search-style headline, in Title Case, with the ticker in brackets after the company name. No colons in the first three words, no puns, no emojis. 40–90 characters. |
| `dek` | yes | 1–2 sentences, 90–220 characters. It's the card excerpt and the meta description. It must hold the main number and the cause. |
| `type` | yes | One of the types below. |
| `published` | yes | A TOML datetime with the New York offset (-04:00 until 1 Nov 2026, then -05:00). |
| `author` | yes | A pen-name id from `data/authors.json`. |
| `tickers` | yes | Universe tickers, primary first. Use `[]` for macro and market stories with no single stock. |
| `reason` | why-it-moved only | One of: Earnings, Guidance, Analyst upgrade, Analyst downgrade, Deal, Product, Legal or regulatory, Management, Peer news, Macro, Sector move, No clear news. |
| `cover` | no | A cover-library key (see `site/covers.json`). By default it's chosen from the type and the primary ticker's sector. |
| `moves` | no | Price chips printed on the card and the story: the price and % move **at the time the story describes**. Copy them from `pipeline/facts.py` (regular-session close) or `data/quotes/latest.json` (live and after-hours). `session` is one of `regular`, `close`, `after-hours` or `pre-market`. |
| `sources` | yes | URLs for every fact that isn't from our price files: at least two independent outlets for the cause of a move, and the company's release for earnings numbers. They're kept for checking and never printed. |
| `featured` | no | `true` pins the story as the lead on the front page until a newer featured story arrives. |
| `status` | no | `draft` keeps the story out of the build. |
| `event` | no | The event id that triggered the story. The pipeline sets it. |

## Types

| `type` | Card chip | What it is | Words |
|---|---|---|---|
| `market-wrap` | Markets | "Stock Market Today": the day's story at the close | 450–800 |
| `why-it-moved` | Why it moved | One stock (or a basket with one cause) moved 4%+ on news | 280–520 |
| `movers` | Big movers | The 5 biggest moves of a session, one paragraph each, linking to their stories | 220–420 |
| `earnings-recap` | Earnings | Results against estimates, with the highlights box | 380–750 |
| `earnings-preview` | Earnings preview | What to expect before a company reports | 260–480 |
| `list` | Our picks | "3 Stocks We Love and 1 We Hate" on one theme | 500–850 |
| `macro` | Economy | The Fed, inflation, jobs, GDP, yields, oil | 350–700 |
| `chart` | Chart | One chart, a headline that states the insight, ~150 words | 100–260 |
| `analysis` | Analysis | A longer explainer on a theme | 600–1,200 |

## Body

Markdown, with these parts only:

- `## Heading` and `### Subheading`. Never an H1; the title is the H1.
- Paragraphs, `**bold**`, `*italic*`, `[links](https://...)`.
- Bulleted (`- `) and numbered (`1. `) lists.
- `> quote` for one pull quote at most.
- Pipe tables, with a header row.
- **Cashtags:** `$AMZN` becomes a link to the stock page. Use one on the first mention of each company in the body, as "Amazon ($AMZN)". The ticker must be in the universe (`data/universe/universe.json`).

Fenced blocks:

````
```chart
{"kind": "price", "ticker": "AMZN", "range": "1y", "end": "2026-10-29",
 "title": "Amazon gave back its summer gains", "subtitle": "Daily close, $", "mark": "last"}
```
````

Chart kinds:

| `kind` | Fields | Use |
|---|---|---|
| `price` | `ticker`, `range` (1m, 3m, 6m, ytd, 1y, 5y), `end` (date), `mark`: `last`, `high`, `low` or a date | A stock's price, drawn from `data/prices` at build time |
| `bars` | `labels`, `values`, `unit` ($bn, %, $), optional `compare` + `compare_label` (estimates), `highlight` (index, -1 = last) | Quarterly revenue, EPS against estimates |
| `hbars` | `labels`, `values`, `unit`; colours follow the sign | Comparing moves or metrics across stocks |
| `line` | `x` (labels), `series`: [{`name`, `values`}], `unit` | Yields, inflation, any time series that isn't a stock price |

Every chart needs a `title` that **states the insight** ("Amazon gave back its summer gains", not "Amazon stock price"), a `subtitle` that says the measure and unit, and a `source` (except `price`, which is always Nasdaq daily closes).

````
```highlights
Amazon (AMZN) Q3 2026 highlights
- **Revenue:** $X billion vs analyst estimates of $Y billion (Z% year on year, a W% beat)
- **Adjusted EPS:** $A vs analyst estimates of $B (a C% beat)
- **AWS revenue:** ...
- **Q4 guidance:** ...
- **Market value:** $2.49 trillion
```
````

The highlights box is required in `earnings-recap` and gets the first line as its title.

````
```picks
love: NVDA, AVGO, TSM
hate: INTC
```
````

`picks` draws stock cards (price, 1-day and 1-year moves, sector) at that point in a `list` story.

## Checks (`pipeline/check.py`)

A story fails if:
- a required field is missing or has the wrong type, the author or a ticker is unknown, or the slug is already taken
- the words are out of range for the type
- the `dek` holds no digit (except for `list` and `analysis`)
- it contains an emoji, "As an AI", "In conclusion", "delve", "it's worth noting", "buckle up" or "game-changer"
- a `price` chart names a ticker with no price file, or a fenced block is malformed
- fewer than two `sources` are given (except `chart` stories built on our own data, and `movers`)
- an `earnings-recap` has no highlights box
- a `$`-figure in the body that the checker can match to a stock price is more than 1% away from our price files on that date (a warning, not a failure)
