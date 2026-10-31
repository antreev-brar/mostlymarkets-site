# Mostly Markets house style

Mostly Markets explains why stocks move, in plain English, minutes to hours after it happens. Our readers aren't professionals. They own a few stocks, they already know the Dow is up, and they come for **the story**: who did what, what was said, and what it means for the price.

We publish StockStory's kinds of stories, but written by people who explain: one clear idea per paragraph, named people, real quotes, and numbers that carry their basis.

## The rules that never bend

1. **Every fact has two independent sources**, written into `sources`. Company releases and SEC filings count as one source and outrank the press. Prices come from our own files (`pipeline/facts.py`, `data/quotes/latest.json`), never from memory.
2. **Never invent a number, a quote or a name.** If a figure can't be confirmed, leave it out. If the cause of a move can't be found in two outlets, the reason is "No clear news" and the story says so plainly.
3. **Attribute inline:** "said in the results release", "told Reuters", "according to LSEG data cited by CNBC". There's no sources list at the end.
4. **Label each number's basis:** adjusted or GAAP, year on year or quarter on quarter, close-to-close, after-hours, as of when. "Up 12%" alone is never enough.
5. **No emojis, hype or filler.** None of "skyrocket", "to the moon", "massive", "insane", "game-changer", "buckle up", "in conclusion", "it's worth noting", "delve".
6. **No advice to the reader.** Never "you should buy". Opinions belong to us ("we like", "we'd avoid") and always come with the reasons in numbers. Every page carries the not-advice line automatically.
7. **Times are New York times, written "4:05 p.m. ET".** Dates are written "29 October" and weekdays in full.
8. **US spelling** ("favorite", "program"), with a comma before "and" in lists of three or more.

## Voice

- Lead with the answer. The first sentence says what moved, by how much, and why.
- Short sentences. One idea per paragraph, and three sentences at most per paragraph.
- People are named once in full with their role ("Chief Executive Andy Jassy"), then by surname.
- Use one strong quote per story when one exists, from the call, the release or an interview.
- Explain any jargon in the same sentence: "AWS, Amazon's cloud-computing arm, ...".
- Verbs scale with the move. Up: edged up (<1%), rose (1–4%), jumped (4–8%), soared (8%+). Down: slipped (<1%), fell (1–4%), slid or sank (4–8%), plunged (8%+), "worst day since ..." when `facts.py` supports it.
- Write "Nvidia ($NVDA)" on first mention in the body and "Nvidia" after that.
- **Point at the number.** Each section is about one figure. Bold it, with its verb: "Intel **plunged 28.6%**", "revenue of **$15.0 billion to $16.0 billion**". The page marks bold figures like a highlighter, so bold one or two per section, never a whole sentence of numbers. If a paragraph that opens the story or a section has no bold, the build marks its price move (or else its first figure) for you.

## Bylines (pen names, from `data/authors.json`)

| id | Name | Beat |
|---|---|---|
| `nora-whitfield` | Nora Whitfield | Markets editor: market wraps, big movers, the Fed and the economy |
| `marcus-lindqvist` | Marcus Lindqvist | Big tech and earnings |
| `dev-malhotra` | Dev Malhotra | Chips, AI and software |
| `claire-okafor` | Claire Okafor | Consumer, retail and health care |
| `theo-park` | Theo Park | Banks, energy, industrials and our stock lists |

## Templates

### `why-it-moved`
Title: "Why {Name} ({TKR}) Stock Is {Up|Down|Soaring|Falling|Sinking} Today", or "{Name} ({TKR}) Shares {Jump|Slide} After {short cause}". For a basket: "{A}, {B} and {C} Shares {Slide|Jump}: What Happened".

```
## What happened
Shares of {one-line description} {Name} ($TKR) {verb} {x.x}% {when: in the morning session / on Thursday / after hours} after {cause}.
1–2 paragraphs on the cause: who said what, the numbers behind it, sourced inline.
If the session is over: "The shares closed at $X, {up|down} Y% from the previous close."

## Why it matters
1–2 paragraphs: what the news changes for the business, and how it fits the story investors were already telling.

## What the market is telling us
Use the sentences from `python3 pipeline/facts.py TKR --asof YYYY-MM-DD`: how often it moves 5%, the last move this big, the year to date, the distance from the 52-week high, and $1,000 five years ago. Then one sentence of our own judgment.

```chart  (price, 6m or 1y, mark last)
```

### `earnings-recap`
Title: "{Name} ({TKR}) {Beats|Misses|Tops} Q3 Estimates as {driver}" or "{Name} ({TKR}) Q3: {Result}, {Stock reaction}".

```
Lede: {Name} ($TKR) reported {quarter} revenue of $X, {up/down Y% year on year}, {beating/missing} the $Z analysts expected. {Adjusted EPS line.} {The stock's reaction, with the session.}

```highlights  (revenue, EPS, the 1–3 numbers investors watch for this company, guidance, market value)
```

## What stood out
The driver: segment numbers, margins, the one line from the CEO or CFO that explains it.

## The outlook
Guidance against expectations; what management said about next quarter.

```chart  (bars: the last 8 quarters of revenue or the key segment; highlight the latest)
```

## Our take
2–3 sentences: good, bad, and what to watch next quarter.
```

### `earnings-preview`
Title: "What to Expect From {Name}'s ({TKR}) Q3 Earnings" or "{Name} ({TKR}) Reports Earnings {Tomorrow|on Tuesday}: What to Watch".

```
{Name} ($TKR) reports {quarter} results {before the open / after the close} on {weekday, date}.
Last quarter: what happened and how the stock reacted.
## What analysts expect
Consensus revenue and EPS (name the data provider: LSEG, FactSet or Zacks via the outlet that reported it), against a year ago.
## What to watch
3 bullets: the numbers or comments that will move the stock.
## How the stock has done
facts.py: YTD, 1-month, against the 52-week high.
```chart (price, 6m)```
```

### `market-wrap` ("Stock Market Today")
Title: "Stock Market Today: {the story of the day, in plain words}".

```
Lede: the day's story in 2–3 sentences: the cause, the S&P 500/Nasdaq/Dow close, the one stock everyone talked about.
## {Story 1 headline}  ... ## {Story 2} ... (2–4 sections, each 1–3 paragraphs, linking to the day's why-it-moved stories)
## The numbers
A table at the end: S&P 500, Nasdaq Composite, Dow, Russell 2000, 10-year yield, oil (WTI), bitcoin, with close and % change.
```

### `movers`
Title: "Stocks Making the Biggest Moves {Today|After Hours|This Week}: {A}, {B}, {C}, {D} and {E}".
Five paragraphs: "**{Name} ($TKR)**, {x.x}%: {one-sentence cause}. [Full story](/news/...)". No headings.

### `list` ("3 Stocks We Love and 1 We Hate")
Title: "3 {Theme} Stocks We Love and 1 We Hate" (themes: cash machines, AI infrastructure, earnings-season winners, dividend payers, under $50, beaten-down quality...).

```
Intro: 2 short paragraphs: why the theme matters now, and the screen we used (say exactly what it measured).
```picks
love: A, B, C
hate: D
```
## 3 stocks we love
### 1. {Name} ($TKR)
**{Screen metric}: {value}**. One-sentence description. 2–3 numbered reasons, each a number plus a judgment. One valuation line.
(× 3)
## 1 stock we hate
### {Name} ($TKR)
The same block, with 2–3 reasons we'd stay away.
Closing line: when we'll revisit the list.
```

Numbers in lists come from SEC filings (`data/fundamentals/<T>.json` when present) or the company's latest release, and are dated ("trailing 12 months to September 2026").

### `macro`
Title: "{The thing} {did what}: {what it means}", for example "The Fed Held Rates, but Two Officials Wanted a Hike".
It leads with the decision or the number against expectations, then the quotes, then what markets did, then what's next (the next meeting or release date).

### `chart`
Title: the insight as a sentence. One chart block, then 80–180 words explaining it, ending with what to watch.

### `daily` (Mostly Markets Daily)
The newsletter edition, published at `/daily/<date>/`, fronted on the home page and played as tap-through Stories. It's the most-read thing we publish, so it has to be **the best few minutes of a reader's morning**: a story, then sharp, visual takes they'd screenshot and share.

Three editions:
- **Morning**, every trading day except Monday, before 9:30 a.m. ET: the last session's story and today's setup.
- **Monday**: the weekend's news and what this week will decide.
- **Weekend** (`edition = "weekend"`), after Friday's close: the week in eight charts.

**Title:** the finding, as a sentence ("Intel's Worst Day Since 1974 Capped the Nasdaq's Worst Month Since March 2025"). **Dek:** the main number and a promise ("The week in eight charts.").

**Shape:**
```
{Lede: 2 short paragraphs. The story of the session as a narrative: what happened, to whom, and why. No index-move list here.}
## {The thread's heading, e.g. "The week in eight charts" or "Yesterday in six takes"}
### {Take 1: one claim, stated as a fact, under 70 characters}
{1–3 sentences with the evidence and the cause, linked to our full story.}
```chart or ```stat block
### {Take 2} ...            (6 to 8 takes; weekend edition 7 or 8)
## What's next
{Today's or this week's reporters, data and events as a short list, each linked to our preview when one exists.}
## The numbers
{The markets table from pack.markets, like the market wrap.}
```

**What makes a take X-worthy** (our version of the best market threads, with our sourcing rules):
1. **One claim per take, and the headline is the claim.** "Nvidia did more damage to the S&P 500 than Intel", not "Chip stocks".
2. **Context makes the number land:** a record or "worst since", a rank ("the S&P 500's worst performer"), a comparison ("more than Intel"), or a twist ("Even after Friday, Intel is up 78% this year"). Each must come from `facts.py`, our price files or two outlets.
3. **Every take has one picture**, and the picture is the proof: a `price` chart with a `notes` marker on the event, a `compare` or `moves` chart computed from our prices, the `treemap` market map, the `contrib` chart of who moved the index, or a `stat` block of big numbers. Prefer the computed kinds: their numbers are right by construction.
4. **Mix the pictures.** No more than three price charts in a thread; use at least one market-wide picture (`treemap` or `contrib`) after a big market day.
5. **Short.** A take's text is at most three sentences. Detail lives in the linked story.
6. **Twists beat summaries.** If the obvious take is "X fell", look for the surprising one: the stock that rose against the tide, the record hidden in the drop, the bigger company that mattered more.
7. Still no advice, no hype words and no emojis. "We think" is allowed once per edition, with the reason in numbers.

**Cover:** see "Covers" below.


## Covers (every story)

Every story gets its own illustrated cover. The art is free (FLUX.1 schnell on AI Horde) and is drawn automatically after you push. Write two front-matter fields:

- `cover_brief`: **one sentence, under 35 words, describing one physical scene.** Put the subject first, then the action, then the setting. The house style (a mixed-media collage of photo cut-outs and torn navy, cobalt and yellow paper, with a paper sun and a photographic backdrop) is added for you, so don't describe colours or style.
- `cover_alt`: a plain description of that scene for screen readers.

Rules for the brief:
1. **Show the story with objects, not charts.** The model draws chart lines going up whatever you ask, so show a fall physically: something cracking, toppling, sinking, deflating or melting. Show a rise as something launching, climbing or blooming.
2. **Use symbols of the business, not its brand:** a cracked microchip, cardboard parcels, a giant pill bottle, an oil derrick, a jet engine, a shopping cart, server racks, a bank vault door.
3. **Never** real people, faces, logos, brand products, flags of companies, or any text, numbers or tickers.
4. **One subject and one action**, plus at most one background element. Busy briefs come out muddy.
5. **Say "plain" or "unmarked" for anything that normally carries printing** (jet engines, camera lenses, memory cards, packaging, computer cases). Otherwise the model invents garbled lettering on it.
6. **Don't add a sun or a sky.** The house style already adds a paper sun and a backdrop; a second one gives two suns.

Good: "A giant microchip cracking in half and falling off a cliff edge, shards flying, a storm of paper clouds behind it."
Good: "A towering stack of cardboard parcels toppling over in a warehouse aisle."
Bad: "Intel stock chart falling 28% with the Intel logo and CEO Lip-Bu Tan looking worried."
