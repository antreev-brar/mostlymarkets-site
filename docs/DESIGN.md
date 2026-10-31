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
