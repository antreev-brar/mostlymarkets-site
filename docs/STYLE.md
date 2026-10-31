# Mostly Markets house style

Mostly Markets explains why stocks move, in plain English, minutes to hours after it happens. Our readers aren't professionals. They own a few stocks, they already know the Dow is up, and they come for **the story**: who did what, what was said, and what it means for the price.

We publish StockStory's kinds of stories, but written by people who explain: one clear idea per paragraph, named people, real quotes, and numbers that carry their basis.

And we go further than the news. A reader should be able to come to Mostly Markets and know **everything that matters in the market today**: what happened and why, the story Wall Street is building, the evidence for and against it, who is arguing what, and what we think. The moat is the research and the analysis. Every story must leave the reader knowing something they didn't, and feeling it's new: say what changed, when, and what we'll learn next.

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
- **Open on a dated trigger.** The first sentence of every story, analysis included, carries this week's fact and when it happened ("On Thursday, TSMC said ...", "after the close on Friday"). Show the change, not only the level: "guidance went from $X to $Y", "analysts expected X; the company said Y".
- **Counts, streaks and records** tell a reader a story is building: "the third chipmaker this week to raise its outlook", "the first time since 2022". They come only from `facts.py`, our price files or two outlets.
- **Say what isn't known yet, and when it will be:** "Its call starts at 5 p.m. ET."
- **At most two figures in a paragraph of prose.** Tables, `stat` and `highlights` blocks carry the rest.
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

### `list` ("3 Stocks We Like and 1 We'd Skip", or the reverse)
The event says which way round. Titles: "3 {Theme} Stocks We Like and 1 We'd Skip", "3 {Theme} Stocks We'd Skip and 1 We Like", "1 {Theme} Stock We Like and 3 We'd Pass On", "3 {Theme} Stocks We'd Pass On After {Event}, and 1 We'd Keep" (themes: cash machines, AI infrastructure, earnings-season winners, dividend payers, under $50, beaten-down quality...). We always name the stock we like, never as a riddle. We say "like" and "skip", never "buy" or "sell", and give no price targets.

```
Intro: 2 short paragraphs: why the theme matters now, with the dated news peg, and the screen we used (say exactly what it measured, over what period, from which data).
```picks
skip: A, B, C
like: D
```
## 3 stocks we'd skip            (or "## 3 stocks we like")
### 1. {Name} ($TKR)
**{Screen metric}: {value, dated}**. One-sentence description of what the company does.
2–3 numbered reasons, each a number + a comparison + a judgment ("Sales grew 3% a year over five years, a third of its sector's pace").
**The price:** one line on the multiple against its own history or peers.
**What would change our mind:** one line, with a metric or a date.
(× 3)
## 1 stock we like               (or "## 1 stock we'd skip")
### {Name} ($TKR)
The same block, with **What could go wrong:** in place of what would change our mind.
```chart (compare: the four stocks over 1 year, the one we like highlighted)```
Closing line: when we'll revisit the list, and a link to our breakdown of the stock we like if there is one.
```

Numbers in lists come from SEC filings (`data/fundamentals/<T>.json` when present) or the company's latest release, and are dated ("trailing 12 months to September 2026").

### `macro`
Title: "{The thing} {did what}: {what it means}", for example "The Fed Held Rates, but Two Officials Wanted a Hike".
It leads with the decision or the number against expectations, then the quotes, then what markets did, then what's next (the next meeting or release date).

### `chart`
Title: the insight as a sentence. One chart block, then 80–180 words explaining it, ending with what to watch.

### `daily` (Mostly Markets Daily)
The newsletter edition, published at `/daily/<date>/`, fronted on the home page and played as tap-through Stories. It's the most-read thing we publish, so it has to be **the best few minutes of a reader's morning**: a story, then sharp, visual takes they'd screenshot and share.

An edition every day:
- **Morning**, every trading day except Monday, before 9:30 a.m. ET: the last session's story and today's setup.
- **Monday**: the weekend's news and what this week will decide.
- **Saturday** (`edition = "weekend"`): the week in eight charts.
- **Sunday**: the argument that will decide the coming week, the weekend's news, and the week's big tests.
- **Holidays**: when the market is shut on a weekday, the story Wall Street is chewing on.

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

**Pictures:** each take's chart or stat block is the proof, and the first one opens the edition on the Daily page.


### The analysis types: the evidence ladder and the verdict words

`narrative`, `viewpoints` and `breakdown` are our moat. Use the highest rung of evidence you can, and every rung still needs two sources:
1. Company filings, releases, guidance and call transcripts (one source, which outranks the press).
2. Government and agency data (BLS, BEA, the Fed, the EIA, the Census Bureau).
3. What suppliers and customers said on their own calls: TSMC on AI demand is evidence for an Nvidia story.
4. Named analysts, fund managers and investors, as reported by two outlets or in their own note, post or interview.
5. Our own computed data: `facts.py`, `compare`, `moves` and `contrib` charts.

Never "sources say" without two outlets, never an unnamed "analysts think", never a figure we can't date. No price targets of our own and no "we'd buy below $X": write what the price assumes instead. Analysts' targets can be quoted with name, firm and date.

| Story | Verdict words (bold, in "Our read" or "Our verdict") |
|---|---|
| `narrative` | **The evidence supports it** · **Partly supported** · **The evidence is thin** |
| `breakdown`, the business | **Strong** · **Solid** · **Mixed** · **Weak** |
| `breakdown`, the price | **Below its usual price** · **About its usual price** · **Above its usual price**, against its own history (with the number) |
| `list` | **We like** · **We'd skip** |

### `narrative` ("The story Wall Street is telling")
Our flagship, every day. Titles: "The Story Wall Street Is Telling About {Theme}", "{The thesis as a claim}: What the Evidence Says", "Why Wall Street Thinks {Claim}", "Wall Street Is Betting {Claim}. {N} Numbers Will Decide It", "{Theme} After {Event}: Is the Story Still True?". Dek: the claim, plus two or three pieces of evidence, plus the open question. Set `themes` (see "Story log").

```
Lede (2 short paragraphs): the story as investors tell it, in one plain sentence, and who is telling it (a named CEO, fund manager or analyst, and where they said it). Then the news peg: the dated fact this week that put the story in play.
The stakes in one line: which stocks have moved on this story and by how much (facts.py).
```stat or chart  (the 1–3 numbers that are the story; this leads the page)```
## The story in one sentence
> The thesis, as said by a named person, with the date and venue (the story's one quote).
One paragraph on the chain of cause and effect: "If A, then B, which means C for these companies."
## The evidence for it
### 1. {Evidence stated as a fact, under 70 characters}
1–3 sentences: the number, its basis, who said or filed it, and when.
```chart (one for every one or two items)```
### 2. ... (3 to 5 items, strongest first)
| Signal | Latest | A year ago | Source and date |   (3–6 gauges a reader can check again later)
## The case against it
Who doubts it, by name and where they said it, then 2–3 numbered counter-points held to the same standard. Say which is strongest.
## What would change minds
3 bullets, each an observable event with a date or a threshold ("{Company} reports on Wednesday 4 November; a cut to its capex outlook would be the first crack").
## The stocks exposed
| Company | How it's exposed | Stock this year |   ("Most exposed if the story holds" / "if it breaks")
```chart (compare: the exposed stocks since the story began, the leader highlighted)```
## Our read
**{Verdict words}.** 2–4 sentences: what's well supported, the weakest link, the one number we'll watch.
```

### `viewpoints` ("Bulls vs bears")
Titles: "Bulls vs Bears on {Company} ({TKR}): {The Question}", "{N} Investors on {Company} ({TKR}) After {Event}", "The Debate Over {Theme}: {Name} Says {A}, {Name} Says {B}". Dek: the question and the number both sides are arguing about.

```
Lede (2 short paragraphs): the question and why it's open now (the dated trigger), then the number at the center of the argument.
```stat (the contested number, and the stock's move since the trigger)```
## The bull case
### {Full name}, {role}, {firm}
**Their claim, in one sentence.** 2–3 sentences: their argument in our words, the number they lean on, where and when they said it ("in a note on 28 October, reported by CNBC and Bloomberg"; "in a post on X on 29 October"). One short direct quote at most. Embed the post if it was on X.
### {Second bull}   (2–3 bulls)
## The bear case
### {Full name}, {role}, {firm}   (2–3 bears; at least one documented view on each side)
## Where they agree
## The number that decides it
One paragraph: the metric or event that will settle it, and when we'll see it next.
| Who | Side | Their key number | Said where, when |
## Our read
2–4 sentences: which argument the evidence favors today, in numbers. "Too early to tell" is allowed, with the date that will tell.
```
Only documented, attributable positions: a published note, an interview, a filing, a call, a public post with a link. Reported notes need two outlets. People on X are named with their handle and role, and only when they're credible on the subject (a fund manager, an analyst, a former industry executive, a researcher, a reporter). Never an anonymous account, never a made-up composite ("some investors worry").

### `breakdown` ("Is {Company} a good business?")
Carbon Finance's way of taking a stock apart, at about half the length, with the detail in tables. Titles: "Is {Company} ({TKR}) a Good Business? Our Breakdown", "{Company} ({TKR}) Is Down {x}% From Its High. Is the Business Broken?", "How {Company} ({TKR}) Makes Money, and Whether It Lasts", "{Company} ({TKR}): {a Tension in 4–7 Words}". Dek: the tension plus one number.

```
*{Our verdict in one italic sentence: business quality + what the price assumes + the condition that decides it.}*
```stat (business verdict · price verdict with its multiple · the stock against its high)```
## How it got here
3 short paragraphs: the founding idea, the turning points, what changed this week or quarter. End on **one bold question** the piece will answer.
## The business in one line
Who pays it, for what, and how often.
## How it makes money
| Segment | What it sells | Share of sales | Growth, latest year |
```chart (bars: revenue by quarter or by segment)```
## The numbers that matter
### Growth / ### Profitability / ### Cash / ### Returns / ### Balance sheet  (4–6 short subsections, one figure each, judged against peers or the sector; data/fundamentals/<T>.json, dated)
## Why the stock is where it is
Numbered drivers from the worried investor's angle (2–5), then ```chart (price with notes marking each driver)```
## Testing the worry
For each driver: temporary or lasting? contained or spreading? Use peers, management's actions and filings. Say which worry survives.
## The moat
2–4 named advantages, each with one piece of evidence, and the rivals with one comparable number each.
## The risks we'd watch
3 company-specific risks, sized with simple arithmetic where possible.
## What the price assumes
| Measure | Now | Its history | Peers |   (P/E, forward P/E, price to free cash flow; no price targets)
## Our verdict
**Business: {Strong|Solid|Mixed|Weak}. Price: {Below|About|Above} its usual price.** 3–5 sentences: why, the one thing that would change our mind, and the next date that could. End on one plain line that states the tension.
```

### `brief` (fresh news)
Titles: the event in the past tense with its number: "{Company} ({TKR}) {Raises|Cuts} {Thing} to {X}", "{Company} ({TKR}) Agrees to Buy {Target} for {$X}", "{Agency} {Action}, {Consequence}". Never "Breaking:"; the time stamp does that job. Dek: the number and the reason. 120–250 words, no headings.

```
{What just happened, 1–2 sentences: who did what, the number with its basis, when (to the minute where it matters), attributed inline.}
{Why it matters, 2 sentences: the stake in one number; if it's part of a running story, say which and link our narrative.}
{What's next, 1 sentence: the next dated event, or what isn't known yet.}
```stat (optional: one number)```
```
If the stock moves 4% or more on it with a clear cause, the brief becomes, or links to, a why-it-moved story.

## Voices from X

The best market analysis often appears first on X. When a named analyst, fund manager, executive, economist or reporter makes a real argument or breaks real news there, we can quote them and embed the post:

```tweet
https://x.com/<handle>/status/<id>
```

- Introduce them first: "Bernstein's Stacy Rasgon argued on X on Thursday that ..." Then the embed.
- Only analysis or reporting, never hype, memes or price calls without reasons. One to three posts per story.
- The post is a source like any other: a claim in it needs our usual second source before we state it as fact. Find post URLs in the articles that cite them or by search; don't guess a URL.

## Story log (running stories)

Readers come back for stories that are still moving. Give a story the running themes it belongs to:

```toml
themes = ["ai-capex", "memory-cycle"]
```

Use short, stable keys (`ai-capex`, `memory-cycle`, `hbm-pricing`, `fed-rates`, `oil-shock`, `chip-selloff`, `tariffs`...). Reuse an existing key when it fits: `grep -h '^themes' content/articles/*.md | sort | uniq -c`. A `narrative` page lists every story that shares its themes as a dated story log, and every story in a theme links back to the newest narrative on it. Briefs and why-it-moved stories should carry a theme whenever they're part of a bigger story.
