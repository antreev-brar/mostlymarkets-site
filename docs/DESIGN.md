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

## v6: the feed is one timeline, cover photos are back (1 Nov 2026)

The owner on v5: "the front page looks uglier than ever you are just throwing way too much numbers on the user you dont need to tell them about nasdaq, gold and all those prices and it has to be highly visual". v4 "was good visually and just needed a news addition": a news feed that looks like an X timeline, with StockStory's simplicity, "top and then others", and good covers ("now even they are just ugly graphs").

- **No market numbers in the chrome.** The market strip and the Markets and Biggest movers boxes are gone. The only numbers on a card are one price tag; the stock box on a story page shows that story's stocks.
- **Feed** (`/`): one centred 720 px column, as on StockStory's list and X. The stories rail, then the **top story** (most important of the last 36 hours, minus a point every three hours; never the Daily) with a 16:9 cover, then **one timeline**, newest first, with a line per day:
  - **our stories** as posts: the company's logo (the Mostly Markets mark for the Daily), name, kind and "2h ago", then the headline, the dek and the cover photo (2:1; full width on phones);
  - **newsroom headlines** as posts: the outlet's logo (`assets/sources/`, 38 outlets), name, time, the headline linking to the publisher, and the companies it's about. Only newsrooms that report (`FEED_SOURCES`: Reuters, Bloomberg, WSJ, Barron's, CNBC, MarketWatch, FT, AP, NYT and others), no personal-finance columns (`JUNK_URL`, `JUNK_TITLE`), and close rewrites merge ("Reuters and 1 more"). Under **All** at most three run between two of our stories, market-wide and biggest companies first; the **Headlines** tab shows every one;
  - **X posts our stories quote**, at their own time, linking to the post and to our story.
  - Tabs: All, Our stories, Headlines, My stocks (follows).
- **Covers:** every story has a photo again. Since 1 Nov the house look is **documentary editorial photography** (the look of the 56 topic photos in `assets/covers/`), drawn free with FLUX.1 schnell on AI Horde from the writer's `cover_brief` (STYLE.md, "Covers"). The 28 collage covers were redrawn as photos (masters of the collages are kept in `cover-masters/story-collage-2026-10-31/`). Story and edition pages caption the cover "Image: AI-generated".
- **Article:** header, then the cover photo, then the story with its first chart or stat block right after the opening paragraph (`picture_first` moves a late one up there, and gives a story with none the main stock's three months). The rail: the story's stocks, headlines on the main stock, just published.
- **The Daily:** editions show their cover again (archive rows, today's edition, the edition page, the stories-rail circle).
- **Kept from v5:** separate pages, ticking relative times, the New pill (top story) and the unseen dot, story types, story logs, X cards, per-stock headlines on stock pages.
- **Who a post is from** (`post_who`): a one-company story shows that company's logo and name (only when the headline is
  about it); analysis across several companies shows their logos and the running story it belongs to (`THEME_LABEL`:
  "The memory cycle", "AI spending", "The chip selloff"); the Daily shows the Mostly Markets mark.
- **Headlines everywhere look the same:** stock pages list a company's headlines as posts with outlet logos, and rail
  headlines carry the logo too.
- **Editorial standard (1 Nov):** STYLE.md "No filler". Every sentence reports a fact, explains a mechanism, sizes it,
  says what it means for whom, or gives our read; long analysis opens with "The short version" box. The 20 front-page
  stories of 31 Oct were edited to it and fact-checked twice (an editor, then an adversarial checker against every
  source, then a second checker), and every one needed corrections: implied causes, single-source claims without
  attribution, stale "year to date" figures, overstated analyst views.

## v7: stories on the left, Top news on the right (1 Nov 2026)

The owner on v6's one-column feed: "bunch of stuff again". They want "more stuff per vertical space", "the main page with major of horizontal space": the most recent story first as "a bit bigger card", then "the stories like the StockStory fashion ones one by one vertically stacked", and "after 3-4 of those a horizontal stacked bar of different type of stories, and that goes on". Top news goes "X.com style on the right side", "the important ones stay longer". The Daily should look "like the Opening Bell Daily front" (their main page), with editions "in rows of 3 boxes".

- **Width:** the home page and The Daily use a 1360 px frame (`.wrap.wd`). The header and footer are 1360 px on every page, so they don't jump between pages. Other pages' bodies keep 1200 px.
- **Home** (`/`, `home_pages`): two columns, stories on the left and Top news (380 px) on the right.
  - **Top story** (`lead_card`, `.lead7`): the photo on the left, the headline, dek and one price tag on the right. `pick_lead` takes **the newest story** ("start top with recent story"), so it is never older than the rows under it. `featured = true` lets an editor put another first for a day and a half. It is never the Daily.
  - **Your stocks** (hidden until you follow a stock): a shelf app.js fills from `data/stories.json` with the latest stories on the stocks you follow.
  - **Rows** (`row()`, `.rows .card`): StockStory's stacked cards with logos and kind, a serif headline, a two-line dek, one price tag and the time at the bottom, and the cover on the right. They come four at a time. On phones the footer spans the card (the text column is a `display: contents` grid), so the price tag and time share a line.
  - **Shelves** (`SHELVES`, `shelf()`) follow each group of four rows, each holding one kind of story: Earnings (recaps and previews; "See all" goes to /earnings/), Why it moved (single-stock moves and movers), Our picks (lists), Charts. A shelf shows the latest 12 and needs at least three. Those types then leave the rows, so nothing shows twice. It swipes on phones (edge to edge) and has arrows on computers. Cards are at least 224 px wide, and their times are short ("3h ago", "Yesterday", "Fri").
  - **Cover photos** are spread in display order (`spread_covers` runs inside `home_pages`, before any other page), so two shelf neighbours never borrow the same topic photo.
  - **Later pages** (`/page/2/`…) list everything not on page one, newest first, 20 to a page, so every story appears exactly once.
- **Top news** (`top_news`, `news_rail`, `xpost`): newsroom headlines and the X posts our stories quote, drawn like posts on X. Each post has the outlet's logo, name, "· 2h", the headline linking to the publisher, the companies, and "Also in Bloomberg and 2 more".
  - **The important ones stay longer:** `news_weight` scores how many newsrooms ran the story, market-wide news, company size, our stocks, and moves or decisions over opinion. Press releases and analyst notes (`WIRE_NEWS`) weigh less. A headline lives `4 + 5 × weight` hours (36 at most). The column holds 40: the **10 biggest** still in their time, however old, and the newest of the rest. The biggest of the last day is **pinned** on top.
  - **Re-posts:** `feed_news` reads the five days before its window, so a copy of an old headline (Google News re-dates WSJ's print edition) merges into the original. It needs the same outlet and nearly the same words, and it doesn't come back as today's news.
  - A running story's updates (the same companies, much the same words, within three hours) show once, as the newest version.
  - A quiet weekend is topped up to 24 posts with the biggest of the last two days. X posts quoted by our stories stay three days.
  - **Updating:** the build writes `data/topnews.json`. app.js re-reads it every three minutes while the tab is visible and offers "Show 3 new posts", as X does, rather than moving the column under the reader. It counts only posts newer than the newest on screen. On phones the pill clears the header, and tapping it scrolls to the posts. An empty column says "No headlines in the last two days".
  - Live X timelines need X's paid API (the free endpoint answers 429), so Top news carries only the X posts our stories quote.
- **Phones (≤1000 px):** one column with two tabs at the top, Stories and Top news. The top story stacks, rows get a square thumbnail, shelves run edge to edge and swipe.
- **The Daily** (`/daily/`, `daily_index`), laid out like Opening Bell Daily's main page:
  - a centred serif masthead with one line and a subscribe button;
  - a three-column front: **Top stories** on the left (the two biggest of the last day and a half with photos, a third as text); **the latest edition** big in the middle (cover, date, edition, a 46 px headline, the dek, "Read the edition" and "Swipe through"); **Latest** headlines and the dark subscribe box on the right;
  - **In this edition**: the edition's takes as boxes three to a row (`take_box`, `take_grid`). Each box has its chart, whole, in a fixed 300 px frame, with no chart caption, range chip or hover data. It shows one big number at most, the take's number, its headline and its opening sentence. When the last row would have a gap, the first take (and if need be the last) spans two columns with its wide chart;
  - **Earlier editions**: boxes three to a row (`edition_box`), once there are any. They come right after one row of takes ("All 8 takes" links to the edition). The page shows 9, and `/daily/editions/` lists every edition.
- **Removed:** the stories rail on the home page (the slide viewer stays for The Daily's "Swipe through"), the feed tabs and filter, and the headline posts between our stories (they moved to Top news).

## v8: the top story as a designed card, headlines first, Top news as one-liners (1 Nov 2026)

The owner on v7: "better than before but not the best ... doesn't look clean". Top news "has the sources as main hero",
where "the latest tweet should be the main hero" and it "should take less horizontal space": "a place where we throw in
the recent one liner tweets like the way Kalshi does or major news companies' latest tweets", while "the main character
is the main feed". The feed's covers were "generic boring covers off the internet" (the Daily's too): "look at
SemiAnalysis or Opening Bell Daily", "take covers seriously", "we are unique winners". "The heading should be the main
winner, the article starting sentence can be less so." The top story should be the "good designer card" of 31 October
(v3's navy Daily card), and The Daily's bottom should show previous editions, not this edition's cards.

- **Top story** (`hero_card`, `.hc`): v3's designed card brought back, across the whole 1360 px frame above the two
  columns. The cover large on the left (1.32 : 1), and on navy: a yellow kicker (the kind of story and "3h ago", or the
  edition's date), a 42 px white serif headline, a quiet two-line sans dek, **what's inside as a numbered list**
  (`hero_points`: an edition's takes, else the story's own `##` headings when they say something on their own, not
  "Our read" or "What's next"), and one yellow button. A story with no points centres its text. `pick_lead` is
  unchanged (the newest story, the Daily included; `featured = true` overrides). A Daily lead keeps "Swipe through it".
- **Rows** (`row`, `.r8`, used by every story list on the site): headline first. No boxes: hairlines between rows. A small blue uppercase kind and the time,
  a 25 px bold serif headline, a two-line 15 px grey dek, one price tag only when the story has a move (no logo
  clusters), and the cover on the right at 300 px, 16:10. Phones: a square thumbnail, 19 px headline.
- **Shelves**: no grey panel. A 3 px yellow rule (as on The Daily), a 26 px serif title, then cards with the cover on
  top, the time, an 18 px serif headline and one price tag.
- **Top news** (`news_rail`, `xpost`, `.xp`): 304 px wide (was 380), on a light panel. **The words lead**: each post is
  the headline as a one-liner (14.5 px, semibold) with **cashtags** for its companies ($INTC, linking to the stock
  page), then the outlet, "+2" when other newsrooms ran it too, and the time, small and grey. No outlet logos and no
  ticker chips. **The newest post is the hero** ("Latest" in red, 18 px bold) and the day's biggest sits under it
  ("The big story"). X posts our stories quote read the same way, with "Our story →". Weighting, lifetimes, re-post
  merging and the "Show N new posts" refresh are unchanged from v7.
- **The Daily** (`daily_index`): the bottom is **Previous days**, boxes three to a row (`edition_box`): each earlier
  day's Daily edition, or before The Daily began, that day's closing report ("The close", the `market-wrap`), one per
  trading day (`earlier_days`, `market_day`). This edition's takes are no longer boxed on the front; they are on the
  edition's page and in "Swipe through". An edition's own page ends with the same previous days, as rows.
- **Covers** (see STYLE.md "Covers"): a witty visual metaphor per story, drawn in one house style, instead of literal
  documentary photos.

## v9: logos on every story, follow anywhere, news in News, urgency in every timestamp (2 Nov 2026)

The owner on v8: articles should show urgency, "this article is 4 hours ago rather than its published time"; "each
article must have some logos of the stocks affected by them like the stockstory article headers have 3 overlapping
ones"; covers "lack the detail" of Opening Bell Daily and SemiAnalysis; "the news articles can be just in the news, the
feed should be similar to stock story like topics or carbon finance type topics, we can have our own articles in the
news too"; and "stockstory type buttons to add stocks to users wishlist that they want to follow" in different places.

- **Times** (`rel_text`, `ago`; app.js `rel`): always how long ago, never a clock time: "Just now", "12 min ago",
  "4 hours ago", "3 days ago", the date after two weeks; "4h ago" in narrow places. They tick every 30 seconds; the exact
  time is in the tooltip. Story bylines say "4 hours ago" with the New pill under six hours.
- **Logos** (`logos`, `.lgs`): every story shows the stocks it is about as up to three overlapping round logos, the
  first on top, each ringed in the colour behind it, and "+N" for the rest. On rows they lead the kicker (two on
  phones); on shelf cards, edition boxes and The Daily's top stories they sit on the cover's corner; the top card's
  kicker and the story header (40 px) have them too. A story's logos are its tickers, else the companies it names most
  (`named_tickers`: headline, then dek, then body; company names from the universe plus `ALIASES`, minus
  `NOT_A_COMPANY` such as "Nasdaq" and "Dow"; `EXTRA` companies outside the universe, such as Okta, Samsung, OpenAI and
  Binance, with logos from their own site icons), else the topic's icon (the Fed, oil, bonds, crypto, the economy).
- **Watchlist** (`follow_btn`; app.js), StockStory's control: an outline star that fills with our yellow once the stock
  is on your watchlist, everywhere a stock appears: the story header's row of its stocks (`.spills`: logo, ticker,
  name, star), the top card ("Add Cameco"), the story's rail and end box ("Add to watchlist" / "On your watchlist"),
  stock pages (the button, plus a round star that floats bottom-right once you scroll, as on StockStory), Discover
  cards and search results. All the stars for a stock stay in step; the header's star shows how many stocks you follow
  and opens **/watchlist/** (`watchlist_page`): a search box to add any stock, then each stock with its price, change and
  our latest story on it, and the stocks in our stories this week. The list stays in this browser until sign-in exists.
- **Feed vs News**: the feed (`FEED`) is StockStory and Carbon Finance topics: why it moved, earnings, previews,
  analysis, breakdowns, the big story, bulls vs bears, picks, charts, the economy, the close and The Daily. News items
  (`NEWS_TYPES`: "brief") leave the feed and its top card. They post in Top news as Mostly Markets ("Our story"), beside
  the newsrooms' headlines, and on the new **/news/** page (`news_page`): the day's biggest headline, then every post a
  day at a time, newest first, with all our news stories in the right column. "News" joined the nav.

## 3 Nov 2026: a smaller top card, no News in the header

- **Top card** (`.hc`): the owner said it took more than half the screen (634 px on a 1440 x 900 laptop, 70%; the whole
  screen on a phone). It is now about 394 px (44% at 1440 x 900, 49% at 1280 x 800): cover and text split 1 : 1 (the
  cover then shows near its own 16:10), a 30-32 px headline clamped to three lines, a two-line dek, the "More on" links
  one line each (two links under 1180 px), tighter padding. Under 900 px the cover is 2:1 (cropped toward its top,
  where the lettered signs are) and the links drop, so a phone shows about 475 px (56% at 390 x 844).
- **Nav**: "News" left the header (`NAV`: Feed, The Daily, Discover, Earnings). /news/ stays, linked from the footer;
  Top news on the home page carries the headlines.
