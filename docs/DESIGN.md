# Mostly Markets design system (v2, 31 Oct 2026)

Built from a measured study of StockStory (`../research/2026-10-31-stockstory-design/DESIGN_SPEC.md`, 105 stills).
We copy what works there, fix what's weak, and keep our own identity: a navy-ink, white-page, modern newsletter.

## StockStory vs Mostly Markets: what makes the better experience

| Area | StockStory | Old Mostly Markets (v1) | Mostly Markets v2 (this system) |
|---|---|---|---|
| Overall feel | Research publication: navy ink, white page, serif headings + Inter | Old broadsheet: warm beige paper, black ink, mono ticker chips | Modern newsletter: white page, navy ink, rounded cards, company logos, one bright accent |
| Type | Tiempos Headline 500 + Tiempos Text 18/30 + Inter for data. Doesn't scale on phones (36 px H1 runs 6 lines) | Newsreader + Inter + IBM Plex Mono | Source Serif 4 (display opsz for headings, text opsz for body) + Inter for all UI and numbers (tabular). Headings scale down on phones |
| Feed card | White card, 1 px border, radius 10, logo circles + type chip, serif title, grey snippet, price + date | Flat rows, mono chips, no logos | Card with logos + type chip + time, serif title, two-line dek, coloured move pills, thumbnail, gentle lift on hover |
| Scanning device | Lavender "actual vs estimate (x% beat)" box floated beside the lede | Plain bordered list | Highlights scorecard: each line gets an automatic green "beat" / red "miss" badge |
| Charts | Dark #21202B PNGs on a light site, one green for everything (even debt), ~6 px text on phones, no hover | Beige/black bars, no grid, no colour meaning | Live inline SVG on the page's own surface: light grid, latest value highlighted and labelled, green/red only when the sign means something, hover/tap tooltips, phone-sized variant with legible type |
| Price chart | Default Chart.js (Helvetica 12 px, grey grid, black tooltip), red/green area | Black line on beige | Area chart tinted by the period's direction, gradient fill, end-value pill, dashed crosshair + tooltip, pill range tabs |
| Cheap vs expensive | One sentence + the quality/value quadrant (no numbers, logos overlap at rest, needs hover) | A table row "Price to earnings vs sector median" | Three pictures: (1) quality vs price quadrant against peers, de-cluttered at rest, numbers in the tooltip; (2) forward P/E vs peers and the sector median; (3) P/E over two years against its own average band. Plain verdict chips: "Business quality: Strong" and "Valuation: Cheaper than peers" |
| Verdicts | Buy / Underperform ratings and "Why is now the time to buy X?" | None | Descriptive only (stronger/weaker, cheaper/pricier than peers): never "buy" or "sell", per STYLE.md and the advice rules |
| Accessibility | Several greys fail contrast (#69d1a4 text 1.87:1) | OK | Every text colour ≥ 4.5:1 on its background; colour never the only signal (arrows and signs too) |
| Gates | Unclosable sign-up wall on stock pages | None | None |

## Tokens

- Surfaces: page `#ffffff`, soft band `#f6f7fb`, card border `#e7e9f1`.
- Ink: `#101a3a` (all text), secondary `#3b4566`, meta `#5f6886`, quiet `#9aa1b9` (decoration only).
- Accent: blue `#3355ff` (links on hover, active states, the highlighted series). Brand yellow `#ffe45c` stays in the wordmark and `<mark>`.
- Up / down text `#0b8043` / `#d32545`; chart fills `#12b76a` / `#f04461`.
- Verdict tones: strong `#0b6b3d` on `#e3f7ec`, middle `#2347c9` on `#e8eeff`, weak `#b4213d` on `#ffe6ec`.
- Radius 14 (cards), 10 (images in cards), 999 (pills). Shadow on hover only.
- Type scale (desktop / phone): H1 44/50 → 30/36, card title 22/28 → 19/25, body 18/30 → 17/28, UI 14/20, meta 13/18.

## Charts grammar

1. The title is the finding ("Revenue grew 58% from a year earlier"), the subtitle says the measure and units.
2. History in a light tint of the accent; the latest point in the accent with its value printed.
3. Green/red only for signed measures (growth, cash flow, net cash), never decoration.
4. Light horizontal grid, axis labels in meta grey, numbers in Inter tabular figures.
5. Every point has a tooltip (hover on desktop, tap on phones). Two renders: 680 px desktop, 360 px phone.

## Valuation module (stock pages)

- Quality score: average sector percentile of revenue growth, gross margin, operating margin and free-cash-flow margin (last 12 months, SEC filings), mapped to −1…+1.
- Value score: sector percentile of forward P/E (trailing P/E if there's no forward), lower = cheaper, mapped to −1…+1. No positive earnings = treated as expensive.
- Bands: ≥ +0.33 strong / cheaper, ≤ −0.33 weak / pricier, otherwise average / fair.
- The quadrant shows the stock plus up to 7 industry peers by market value; points are pushed apart before render so nothing overlaps at rest.

## v3 (31 Oct 2026): The Daily, takes and Stories

The brief: make it addictive for people who scroll. Daily editions with stories and X-level analysis, AI covers like Opening Bell Daily's, more visual, full of storytelling charts.

- **The Daily** (`type = "daily"`, `/daily/<date>/`, archive at `/daily/`):
  - Masthead with edition number, then a big serif headline and a full-width 16:9 AI cover.
  - "In this edition" pills, then a drop-cap narrative lede.
  - Then the thread: every `###` becomes a numbered **take card** (`1/8`) with one picture and Copy link / Post on X buttons. Takes are deep-linkable at `#<id>`.
- **Home:**
  - A **Stories rail** (rings, unseen first): The Daily, Movers (gainers, losers, market map, who moved the index), Earnings, Charts, Our picks.
  - Under it, the **Daily hero**: a dark navy card with the cover, the first five takes, "Read the edition" and "Swipe through it".
  - Up to three take cards are mixed into the river.
- **Stories viewer** (`app.js`):
  - Full-screen 9:16 slides with progress bars and seven-second auto-advance.
  - Tap left or right to move; hold to pause; swipe sideways to change group, down to close; arrow keys and Esc on desktop.
  - The back button closes it. Slides reuse the phone render of each chart on a dark navy surface.
- **Storytelling charts**, all computed from our prices so their numbers are right by construction:
  - `price` with `notes`: an event marker on the line
  - `compare`: rebased lines with end labels
  - `moves`: change between two closes
  - `treemap`: the S&P 500 market map, sized by market value, with a finviz-style diverging red/green that reads in both themes
  - `contrib`: each stock's contribution to the index move
  - `stat`: big-number cards, written or computed
- **Covers:**
  - House style is a torn-paper halftone collage in our palette: navy ink, cobalt `#3355ff` and lemon `#ffe45c` on warm paper. Red and green appear only as chart lines.
  - Opening Bell Daily uses red/navy/cream with photo cut-outs of real executives. We never depict real people, logos or text: covers are symbolic scenes.
  - Prompt prefix in `pipeline/covers.py`. Briefs come from the writer (`cover_brief`); `.github/workflows/covers.yml` draws them after each push when the `OPENAI_API_KEY` secret is set.

## v4 (31 Oct 2026): one calm system

The user's feedback on v3:
- the hover colour changes felt cheap
- Discover's mover charts were useless, and the earnings calendar had too many numbers
- StockStory's home lets you see the top stories, discover stocks and their ratings in one place, carrying the same design all the way down

They want Apple-style minimalism: a lot in one place, but not so many numbers that you don't know where to look. In articles, the number in focus should stand out, as it does in Carbon Finance.

- **Hovers:** none change colour or lift a card. Cards are plain links, like StockStory's. Buttons dim slightly, links underline, and ghost buttons get a faint grey fill.
- **Home is the hub.** One section frame (serif title, one-line intro, "See all →") and one story tile (picture, logos and type, headline, two-line dek, one price tag), in this order:
  1. the Stories rail
  2. top stories (the lead plus three tiles)
  3. The Daily
  4. Earnings this week (logos)
  5. Discover (rated stock cards)
  6. latest stories in a three-up grid
  On phones the tiles become compact rows and the Discover cards swipe.
- **Ratings, descriptive and never buy/sell.** Tags come from the sector-relative scores:
  - quality: "High quality" (green) or "Solid business" (grey)
  - price: "Cheaper than peers" (blue), "Pricier than peers" (pink) or "No profits yet"
  - list tags: "Fast grower" (amber) and "Cash machine" (teal)
  They show on Discover, the stock hero and search.
- **Discover:** StockStory's shape, with our data.
  - Tabs: High quality, Cheaper than peers, Fast growers, Cash machines and Our picks.
  - Cards are grouped by sector, three per row with "Show all".
  - Each card: logo, tags, name, industry, and one or two plain sentences on why it stands out, with at most two numbers (`why_line`).
  - No price charts.
- **Earnings:** logo tiles only, for companies worth $25 billion or more, biggest first, with a Preview or Recap tag when we've written one. No EPS figures.
- **Articles:** the figure a section is about gets a highlighter mark (`strong.fig`). The build marks the price move, or else the first figure, in each opening paragraph that has no bold. Cashtags are quiet grey text instead of chips.

**Covers (31 Oct, later the same day):**
- They're free now: FLUX.1 schnell on AI Horde, drawn for every story with a `cover_brief` after each push.
- OpenAI remains as an optional, richer provider.
- The first FLUX prompt ("bold graphic shapes") came out as flat vector art. On 31 Oct the prompt became a dense mixed-media collage (photo cut-outs with white borders, a torn yellow paper sun, torn navy and cobalt layers, a photographic backdrop), which is close to the first seven OpenAI covers. All 22 FLUX covers were redrawn in it.
- Tested and rejected the same day: AlbedoBase XL and Juggernaut XL (photographic, drew a brand logo and faces, read "lemon-yellow" as lemons) and Z-Image-Turbo (blurry on the Horde's workers).

## v5: separate pages, story first, recency everywhere (31 Oct 2026)

The owner's brief: don't put every section on one page; four pages in the nav (Feed, The Daily, Discover, Earnings; stock pages stay but leave the nav). Interest falls as a reader scrolls, so every page is ordered by what matters most. A reader who opens an article meets the article, with its chart early, and the market's random moves sit to the side. Everything should say how new it is. No cover art: "i really didnt like the art used at covers".

- **Market strip** (every page, under the header): market status set live in the browser (open, pre-market, after hours, closed, with exchange holidays), the indexes, oil, gold, bitcoin, and "Newest story 14 min ago".
- **Recency:** every timestamp is relative and keeps ticking (`time[data-rel]`: "Just now", "12 min ago", "3h 5m ago", "Yesterday, 4:55 p.m.", "Thu, 4:15 p.m."). Anything published in the last 6 hours wears an orange **New** pill and an orange time; anything published since the reader's last visit gets a blue dot. Day dividers say "Today" and "Yesterday".
- **Feed** (`/`): the lead story (most important of the last 36 hours, minus a point every three hours) with its chart in the first screen, then five **Top stories** newest first, then **Latest** (the river, with filters). A sticky right rail lurks: Markets, Biggest movers, The Daily, market headlines. On phones the rail comes after the river.
- **Article:** kicker, "Published 2h ago", headline, dek, byline, then the story's **first chart lifted to the top** (`hero_visual`: or the stock's three months, or the day's market map), then the story. The rail on the right: the stocks in the story (live), latest headlines on the main stock, biggest movers, just published. On phones it follows the article.
- **The Daily** (`/daily/`): every day's edition. Today's opened up with its takes and first chart, then the archive by month.
- **Card pictures are charts, never stock art:** the main stock's last two months ending on the story's day (a dot marks the news, pulsing while it's new), with its logo; market-wide stories get that day's market map in miniature.
- **Stock pages:** "The latest on {company}" sits right under the price chart: our stories, then outside headlines (`data/news/<T>.json` from `pipeline/news.py`).
- **X posts:** the ```tweet block draws a post as a static card (no X script), from the data job's cache.
- New story types: `narrative` (The big story), `viewpoints` (Bulls vs bears), `breakdown` (Breakdown), `brief` (News). Lists are "3 we like and 1 we'd skip" or the reverse.
