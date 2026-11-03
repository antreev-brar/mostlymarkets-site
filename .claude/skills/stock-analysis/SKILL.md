---
name: stock-analysis
description: How Mostly Markets analyses a stock - the owner's own write-article method (StockStory and Carbon Finance style), deepened with research on how both actually judge companies. Use before writing any story that judges a company (breakdown, list, earnings-recap, earnings-preview, viewpoints, narrative, or a why-it-moved that needs context). Routes to quality-check, company-deep-dive and earnings-review and holds the rules all three share.
---

# Stock analysis: the index

**Where this comes from.** The owner already had a skill for this: `write-article` (in `~/Desktop/articlemaker`, August 2026). Its voice and four formats were distilled from three pieces the owner likes:
- Carbon Finance's Adobe deep dive;
- StockStory's Freshworks earnings recap;
- StockStory's Freshworks research report.

These skills carry that method into Mostly Markets and deepen it with measured research:
- StockStory's 160 reports and all 1,364 of its ratings, decoded;
- Carbon Finance's 216 posts.

They are adapted to our house rules. The source files live on the owner's machine (paths at the end), but everything a writer needs is in these four skills.

## The voice (from write-article; it applies to every analysis)

- **Plain language wrapped around real numbers.** Every metric gets one sentence that says what it means in everyday words: "Net revenue retention was 104%: existing customers spent 4% more this year, so revenue would have grown even with no new customers." Numbers never speak for themselves.
- **Teach as you go.** Define a term in a few words the first time it appears: billings ("cash revenue"), operating margin ("the share of each sale left after running the business"). Write for a smart reader who isn't a professional.
- **Verdict-forward.** Every section ends with a judgement. In breakdowns and recaps, that's one italic line: *Verdict: solid growth, partly diluted away.* Readers always know what we think.
- **Balanced.** Wins and concerns side by side ("We were impressed by X. On the other hand, Y…"), and the bear case is stated fairly before it's answered.
- **Rhythm.** Short declarative sentences ("Leverage isn't an issue here.") alternate with longer analytical ones.
- **No hype, no hedged mush.** Commit to a view, then name the risk.

## Which skill for which story

| Story type (docs/STYLE.md) | write-article format | Skill |
|---|---|---|
| `earnings-recap`, `earnings-preview`, `preview-roundup` | A: earnings recap | **earnings-review** |
| `breakdown` ("Is X a good business?") | B: deep dive / thesis | **company-deep-dive** (+ quality-check for "The numbers that matter") |
| `list` (our picks: 3 we like / 1 we'd skip, 2 and 1, 1 and 3; after earnings) | C: research report, per stock | **quality-check** |
| `why-it-moved` | — | quality-check §8 (one long-run line for scale) |
| `narrative`, `viewpoints` | B and D | company-deep-dive §5–6 (testing a claim, sizing a risk). On technology, write-article's Format D rules (below) |

**Format D (technical deep dives, SemiAnalysis style)**, for narratives about chips, memory, networking or power:
- the subject is the protagonist, and sources are named in the intro and when quoted, not in every sentence;
- open each section with a declaration, not a rhetorical question, and use at most one rhetorical question in the piece;
- walk the stack layer by layer (silicon, memory, networking, power, economics), letting each section set up the next.

Our templates' headings (including "Our read") stay.

## The numbers: one command

```
python3 pipeline/analyse.py MU            # metric panel, peer medians and ranks, valuation, peers
python3 pipeline/analyse.py MU INTC QCOM  # a list's stocks, one after another
python3 pipeline/analyse.py MU --json     # the same, with peer medians, ranks and the peer list, for scripts
python3 pipeline/facts.py MU              # price moves: today, this year, 1 year, against the 52-week high
```

What `analyse.py` prints, from `data/fundamentals/<T>.json` (SEC filings) and `data/quotes/latest.json` (CNBC):
- **Revenue** in four beats: 5 fiscal years, 2 years annualised, the latest quarter against a year earlier, and the rank.
- **Margins, cash flow and returns** as 2-year or 12-month figures.
- Each figure with the **peer median and the stock's rank**. Peers are a StockStory-like group (chipmakers, software companies, banks, insurers, drugmakers…) when it has 10 members, otherwise the GICS sector. It says which.
- **Balance sheet** and **price to book**.
- **Valuation:** the multiple against peers on the same basis, the stock's own trailing P/E history (US filers only), and price to free cash flow.
- **A peer table.**

The quarter-by-quarter series for charts is in the JSON file itself.

These are **our data**. Cite them as "our analysis of SEC filings" with the period ("the 12 months to September 2026"); they need no second source. Read its warnings first:
- **Stale:** a missing 10-Q; take later quarters from the filing.
- **Amounts in another currency:** foreign filers.
- **No quarters:** a yearly filer.

Check three things by eye:
- a 5-year EPS growth rate from a near-zero base (look at the endpoints);
- a 2-year share-count jump that is really an IPO;
- a P/E range distorted by a one-off quarter.

**Not in our data:** consensus estimates and beats or misses, guidance, segment revenue, industry KPIs (same-store sales, net revenue retention, backlog, net interest margin), EBITDA, P/FFO for REITs, analysts' ratings and targets. Get them like this:
- **The company's own figures** (results, guidance, segments, KPIs): from its release or filing, which is the primary source and counts on its own (STYLE.md, the evidence ladder). In a scheduled run, the event pack's `release_text` is the release.
- **Consensus:** from an outlet that names the provider (LSEG, FactSet, Visible Alpha, Zacks), confirmed by a second outlet.
- **Analysts' views and targets:** the named analyst, firm and date, reported by two outlets or in the analyst's own published note.

## The rules every analysis follows

1. **The long run first, then the trend, then this quarter.** A quarter is news; five years is the business. Direction matters as much as level: a 12% margin rising from 5% beats a 15% margin falling from 25%. (StockStory: "we place the most emphasis on long-term growth". Its ratings barely move with one quarter.)
2. **Judge against peers, never in absolute terms.** "Sales grew 6% a year" means nothing. "6% a year, half the median chipmaker's pace" is a judgement. Use the peer median and rank `analyse.py` prints, name the group, and when the group is a broad sector, compare with the closest named peers as well.
3. **Two questions, kept apart: is it a good business, and what does the price assume?** A great company can be expensive and a cheap one cheap for a reason. Never let the price argue for the quality, or the other way round.
4. **Every claim is a number, a comparison and what it means**: "Free cash flow was 6.3% of revenue over the past 12 months, the lowest of the 16 stocks we screened, which leaves little room to pay for the new factories its turnaround needs."
5. **The bear case gets the same evidence as the bull case.** Name who holds it, give their number, test it.
6. **No advice, no targets, no timing.** None of these, ever, even dressed up:
   - "buy", "sell", "wait for a better price", "not now", "would be $X if priced like peers";
   - a fair value, an entry price or a returns matrix.

   Write what the price assumes ("at 38 times expected earnings, profits need to roughly double by 2028 for the multiple to look ordinary"). Analysts' targets can be quoted, attributed. Verdicts are descriptive: STYLE.md's verdict words, and "we like" / "we'd skip" in lists, each with reasons. A skipped stock gets a dated "what would change our mind"; the stock we like gets a sized "what could go wrong".
7. **Two independent sources per fact, or our own data, or the company's own filing for its own figures.**
8. **No filler** (STYLE.md). The plain-language reading of a number counts as explaining it.
   - At most two figures in a prose paragraph; the rest go in tables, `stat` and `highlights` blocks.
   - The key number in bold.
   - Keep within the type's word range: recap 380–750, preview 260–480, list 550–1,000, breakdown 1,100–2,300.
9. **We are pen names with no positions.** Write "we", never "I". There's no "I am long", no "adding to a position", no portfolio: those are Carbon's and the old write-article's, not ours. The site carries the disclaimer, so no per-story "not financial advice" line.
10. **Check what we said last time.** `grep -l '"MU"' content/articles/*.md` lists our earlier stories on the stock. If our view has changed, say so and why. Link the earlier story.
11. **Date everything**: the period of every figure, the price's date and session, and the next date that could change the verdict.
12. **Name names.** In lists, the stock we like is named, never a riddle. Elsewhere, don't bolt on a tip we haven't analysed.

## Where this comes from (on the owner's machine; not needed to follow these skills)

- The owner's skill: `~/Desktop/articlemaker/.claude/skills/write-article/SKILL.md` and `~/Desktop/articlemaker/STYLE.md`. Examples: `articles/sofi-q2-2026`, `articles/nike-q1-fy2027`.
- StockStory:
  - `~/Desktop/Projects/brarfinance/research/stockstory/STOCKSTORY_PLAYBOOK.md`;
  - `universe/UNIVERSE_ANALYSIS.md`;
  - `universe/QUALITY_VALUE_DECODED.md`;
  - `universe/quality_drivers_by_sector.json`;
  - `reports_text/` (160 reports).
- Carbon Finance:
  - `~/Desktop/Projects/brarfinance/research/carbonfinance/CARBONFINANCE_PLAYBOOK.md`;
  - `posts/`, which holds the five public research reports (Lululemon, UnitedHealth, Novo Nordisk, Meta, Adobe) and the earnings reviews.
- Both, as story structures: `~/Desktop/Projects/mostlymarkets/research/2026-11-01-analysis-style/STYLE_MEMO.md`.
