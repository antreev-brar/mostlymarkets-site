---
name: earnings-review
description: How to analyse a company's quarter for Mostly Markets, in the owner's write-article Format A (earnings recap) - StockStory's lede and highlights against estimates, short metric sections that say what each number means and end in a verdict, Carbon Finance's one debate that matters, and balanced takeaways with the stock's reaction. Use for earnings-recap and earnings-preview stories, and the earnings parts of breakdowns and the Daily.
---

# Earnings review (write-article's Format A: StockStory's speed, Carbon's judgement)

The owner's `write-article` Format A was distilled from StockStory's Freshworks recap. It runs:
1. **A lede:** the company, the beat or miss on revenue, growth, guidance against estimates, EPS against consensus, in 2–3 sentences.
2. **A highlights list:** each metric against the estimate, with the beat or miss and the change from a year earlier.
3. **2–4 short metric sections:** what the metric means, the number, what it says about the business.
4. **Key takeaways:** what impressed, what disappointed, the overall verdict, and the stock's reaction.

The two references read a quarter differently, and we use both:
- **StockStory** measures it against **expectations**, and publishes within minutes.
- **Carbon Finance** measures it against **last year and the thesis**. Its "Quarter at a Glance" box gives GAAP figures with year-on-year change and a driver. Then it spends its words on the **one debate that matters**, framed in the subtitle as a tension ("The moat is finally being tested").

## Where it goes in our template (STYLE.md `earnings-recap`, 380–750 words)

| Our heading | What goes there |
|---|---|
| Lede (no heading) | StockStory's facts (step 1) and the reaction, with the session |
| `chart` | The revenue or key-segment bars, early |
| `highlights` | Every line against the estimate (step 2) |
| `## What stood out` | 2–3 short metric sections (step 3), then the one debate (step 4) |
| `## The outlook` | Guidance as a change (step 5) |
| `## Our take` | The balanced takeaway, the reaction explained, the thesis check, the next date (step 6) |

**Before writing:**
- **The release:** the event pack's `release_text` (the 8-K exhibit), or the company's IR page. It's the primary source for the company's figures.
- **Consensus:** an outlet that names the provider (LSEG via Reuters, FactSet, Visible Alpha via Bloomberg, Zacks), confirmed by a second outlet. If they differ, quote one and say whose. Watch the basis: the pack's calendar consensus (Nasdaq) is sometimes GAAP while the press quotes adjusted.
- **The call:** coverage from two outlets, or the transcript.
- **History:** `python3 pipeline/analyse.py <TICKER>` gives growth, margins and the peer bar. The quarter-by-quarter series for the chart is in `data/fundamentals/<T>.json`.
- **The reaction:** `python3 pipeline/facts.py <TICKER> --asof <date>`.
- **What we wrote last quarter:** `grep -l '"<TICKER>"' content/articles/*.md`.

## The recap, step by step

### 1. The lede: StockStory's facts, then the reaction
In 2–3 sentences:
- revenue, its change from a year earlier, and against consensus;
- adjusted EPS against consensus (and GAAP if they differ a lot, labelled);
- guidance against consensus;
- the stock's reaction with the session: "fell 9% in after-hours trading", "closed up 4%".

### 2. The highlights box (`highlights` block)
- **Every line is the actual against the estimate, the beat or miss as a percentage, and the change from a year earlier.**
- **The lines:**
  - revenue;
  - EPS;
  - **the 1–3 numbers investors watch for this company** (quality-check §3's industry KPIs: net revenue retention and billings for software, same-store sales for retailers, data-centre revenue for chips, net interest income for banks);
  - operating margin;
  - free cash flow;
  - guidance;
  - market value.
- **No consensus for a line:** give the change from a year earlier and say so. Never invent an estimate.
- **Label GAAP and adjusted** the first time they appear.

### 3. "What stood out": short metric sections
2–3 of them, each in write-article's pattern:
- what the metric means, in a few plain words;
- the number;
- what it says about the business;
- an italic verdict line.

> Net revenue retention was 104%: existing customers spent 4% more than a year earlier, so revenue would have grown even with no new customers.
> *Verdict: {one judgement, e.g. solid, but slower than last year's if the release shows it}.*

(The retention line is Freshworks, the example in write-article's STYLE.md; the braces are where our judgement goes.)

Include the drivers: which segments grew or shrank and why (a named executive, quoted), margins in percentage points and the reason (mix, pricing, costs, a one-off), and free cash flow and where it went (buybacks, dividends, capex). Keep to two figures per paragraph; the box carries the rest.

### 4. The one debate (Carbon's core)
Every quarter, one question decides what the stock does next. Carbon's devices:
- **State the consensus view and where it may be wrong.** FICO: the overwhelming view was that it was a bargain, which is exactly where Carbon thought investors needed care.
- **Name the one fact that changed.** For FICO, it was the rival scorer's share "in the 20s" against 9% in May.

Typical debates:
- **Is the moat being tested?** Share, pricing, a rival's number.
- **Is growth peaking?** Growth rates quarter by quarter.
- **Are the margins sustainable?** Mix, input costs, the one-off.
- **Is the spending paying off?** Capex against revenue growth.

Use the call: which named analysts pressed on it, the answer, and whether it settled anything.

### 5. The outlook: guidance as a change
- **Old against new:** "raised its full-year revenue forecast to $X–Y from $A–B".
- **New against consensus.**
- **The CFO's reason,** quoted.
- **If there's no guidance,** say so, and what management said instead.

### 6. "Our take": the balanced takeaway
In write-article's shape: "We were impressed by X. On the other hand, Y. Overall, …". Then:
- **The reaction, explained:**
  - **Which number did it?** Usually guidance or the KPI, more than the headline beat.
  - **What was priced in?** The move into the report, and the options-implied move if two sources give it.
  - **Was the beat even news?** The median revenue surprise in StockStory's universe is about 2–4% at every quality tier, so a small beat isn't news, and a beat with a guidance cut reads as a miss.
- **The thesis check:**
  - Does this quarter change the long-run picture in `analyse.py` (5-year and 2-year growth, margins against peers)?
  - StockStory's ratings show that one quarter rarely does: the 2–5-year record sets their rating.
  - Say whether this one did.
- **The next date** to watch, and the number that will matter then.

## The preview (STYLE.md `earnings-preview`, 260–480 words)
StockStory's preview covers:
- the report date;
- last quarter's result and the stock's reaction;
- this quarter's consensus against a year earlier;
- **how estimates moved in the last 30 days**;
- **how often the company beat or missed over the last two years**;
- how peers that already reported did;
- the stock's run into the print.

Ours, with Carbon's question added:
1. **The date and session**, and last quarter: what happened and how the stock reacted (a price chart with a `notes` marker).
2. **What analysts expect**: revenue, EPS and the key KPI against a year earlier, with the provider named. Include the 30-day estimate revisions and the two-year record of beats and misses if two outlets report them.
3. **The one debate this report settles** (step 4), stated as a question.
4. **What to watch**: 3 bullets, each a number with its threshold ("{the KPI} above {level}, which {the guidance / the consensus} implies").
5. **Peers that already reported**: what their numbers say about this one.
6. **How the stock has done** (`facts.py`): this year, the past month, against the 52-week high.

## Rules
- Company figures come from the release; consensus is attributed to its provider and outlet; "beat" and "miss" are against the named consensus. Without a consensus, say "up X% from a year earlier".
- Name fiscal quarters the company's way, with the calendar months when they differ ("fiscal Q1, the three months to August").
- **No filler:**
  - no "investors will be watching";
  - no "remains to be seen";
  - no restating the box in prose.
- **No targets of our own.** Analysts' rating or target changes after the print go in with the name, firm and date.

## Where this comes from (on the owner's machine)
- `~/Desktop/articlemaker/STYLE.md`, Format A. Examples: `articles/sofi-q2-2026`, `articles/nike-q1-fy2027`.
- StockStory:
  - `~/Desktop/Projects/brarfinance/research/stockstory/STOCKSTORY_PLAYBOOK.md` §2 (the update section, the highlights box, key takeaways) and §5B (earnings articles);
  - `universe/UNIVERSE_ANALYSIS.md` §2 (beat sizes by tier, and how little the latest quarter moves the rating);
  - `~/Desktop/Projects/mostlymarkets/research/2026-10-16-stockstory-structure/STOCKSTORY_STRUCTURE.md` §6.6–6.8 (the preview, the recap, the call).
- Carbon Finance: `~/Desktop/Projects/brarfinance/research/carbonfinance/CARBONFINANCE_PLAYBOOK.md` §4, and the earnings reviews in `posts/` (FICO: the consensus framing and the one changed fact).
- Our templates: `docs/STYLE.md` (`earnings-recap`, `earnings-preview`).
