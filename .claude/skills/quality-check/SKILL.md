---
name: quality-check
description: Judging a company the StockStory way, in the owner's write-article Format C (research report) - the metrics that decide quality in its industry, each read in plain words against its peers over the long run first, the right valuation multiple for the industry, and a two-part verdict (the business, then what the price assumes). Use for list stories ("3 stocks we like and 1 we'd skip"), the "numbers that matter" in a breakdown, and the context line in a why-it-moved.
---

# Quality check (StockStory's method, write-article's Format C)

StockStory judges every company on two separate questions:
- **quality:** is it a good business?
- **value:** is the price fair for that business?

Every badge it shows is just where the stock sits on those two axes:
- a quality score of 40+ is High Quality, 20–40 Investable, below 20 Underperform;
- Timely Buy is a value score above 0 on an Investable-or-better business.

Two-thirds of its 1,364 stocks fail the quality bar. That selectivity is the point: a "we'd skip" with reasons is as useful as a "we like".

Start with `python3 pipeline/analyse.py <TICKER>`. It prints the numbers below with the peer median and the stock's rank (stock-analysis: the numbers).

## 1. Pick the metrics that decide quality in this industry

Don't walk every metric: that's StockStory's boilerplate. Choose the **4–6 that decide quality in this company's industry**, from what StockStory's ratings actually reward. These are rank correlations with its quality score (out of 1), across its sectors:

| StockStory sector | What decides quality (strongest first) |
|---|---|
| Software (SaaS) | Revenue growth over 2 years (.91), next year's expected growth (.77), 5-year growth (.66); debt counts against (−.43); margins barely count (~.1) |
| Consumer internet | Next year's expected growth (.73), free cash flow margin (.43), operating margin (.33); debt against (−.35) |
| Industrials | 5-year EPS growth (.75), operating margin gain over 5 years (.68), revenue growth (.59–.62) |
| Business services | 5-year EPS growth (.65), 2-year and 5-year revenue growth (.62, .50) |
| Healthcare | Return on capital (.71), 5-year EPS growth (.62), revenue growth (.54–.59); debt against (−.43) |
| Banks | 5-year EPS growth (.60), return on equity (.56), tangible book value per share growth (.55), revenue growth (.50) |
| Diversified financials | 5-year EPS growth (.81), revenue growth (.49–.50) |
| Insurance | 5-year revenue growth (.82), 2-year growth (.61), return on equity (.57), EPS growth (.54) |
| Energy | Free cash flow margin (.66), gross and operating margins (.56–.59), recent growth (.44) |
| Consumer staples | Operating margin (.82), return on capital (.79), free cash flow margin (.53); debt against (−.42) |
| Consumer retail | Operating margin (.91), 5-year EPS growth (.80), return on capital (.69); debt heavily against (−.69) |
| Consumer discretionary | Nothing separates: 139 of 140 fail the bar, mostly on slow growth |
| Chips, restaurants, REITs, utilities | No measured set. Use the general rule below, plus the industry KPI |

The general rule, from the strongest signals across all of them: **a good business compounds per-share earnings, is growing now, is getting more profitable, and doesn't need debt to do it, judged against its own industry.** Gross margin by itself separates little.

## 2. Each metric: define it, give the number, say what it means, judge it

This is write-article's Format C ("define the metric, give the number, render a verdict"), with StockStory's four beats for the ones that have a history.

**Revenue and EPS** get all four beats:
1. why it matters (half a sentence, only if the reader needs it);
2. the 5-year figure against peers;
3. the 2-year figure against the 5-year (faster means momentum is building; slower means the story is fading);
4. this quarter and next year's expected figure (sourced).

**Margins, cash and returns** get the level against peers and the direction (the 5-year operating margin change; the 12-month figure against the 2-year one).

**Respect the two-figures rule:** one or two numbers in the sentence, and the rest in a table:

> Revenue rose **37% a year** over five fiscal years, more than twice the median chipmaker's 14%, and the last two years ran faster still as AI servers needed more memory.

| Revenue growth | Micron | Chipmaker median |
|---|---|---|
| 5 years, a year | 36.9% | 14.2% |
| 2 years, a year | 130.3% | 20.5% |
| Latest quarter vs a year earlier | 379.3% | 36.5% |

*Verdict: the fastest grower in its group, on every horizon.*

(Micron, from `analyse.py MU` on 1 November 2026.)

## 3. The checklist (StockStory's report order) and the industry swaps

| Metric (analyse.py) | What it answers | Swaps by industry (from StockStory's reports) |
|---|---|---|
| Revenue: 5-year, 2-year, latest quarter; next 12 months (sourced) | Is demand compounding, and is it still? | Acquirers: organic growth (release). Staples: split into price and volume |
| **The industry KPI** (release or 10-Q) | The number the business actually runs on | Semis: product demand, inventory days. Retail and restaurants: same-store sales, store count. Banks: net interest income share, efficiency ratio, tangible book value per share. Insurance: premiums earned, book value per share. SaaS: billings, annual recurring revenue, net revenue retention, customers over $100k, CAC payback. Internet: users, revenue per user, sales and marketing share of gross profit. Autos: deliveries, selling price. Travel: bookings, nights. Energy: production a day. Industrials: backlog, organic and volume growth |
| Gross margin, 2 years | Can it charge more than its costs? | Banks and insurers: skip |
| Operating margin, 12 months, and its 5-year change | Is it getting more profitable as it grows? | Banks: efficiency ratio, pre-tax margin |
| EPS, 5-year growth against revenue's; diluted shares, 2 years | Does growth reach the owner? If EPS grows faster than revenue, it's margins or buybacks: say which | Software: StockStory often skips EPS and ROIC, and leans on revenue and cash. Banks: tangible book value per share |
| Free cash flow margin, 2 years and 12 months | Are the profits real cash? | Energy and staples: the deciding metric |
| Return on capital (approx.), or return on equity | Does each dollar invested earn its keep? | Banks and insurers: return on equity |
| Net cash, or net debt in years of operating profit | Could it survive a bad year? | Banks and insurers: capital and book value, not net debt |

## 4. The words: from the rank among peers

Pick the judgement word from the rank `analyse.py` prints, and always show the comparison with it:
- **top tenth:** "the fastest of the 25 chipmakers we cover";
- **top quarter:** "strong", "well above its peers";
- **above the median:** "better than most";
- **below the median:** "behind most peers";
- **bottom quarter:** "weak", "among the thinnest".

Name the group ("chipmakers", or "tech stocks" when the group is the broad sector). Write our own sentences: not StockStory's stock phrases ("cash is king", "well-oiled machine") or its tier openers.

The reason line, the unit of a list item or a summary bullet, runs **judgement + number + metric + period + what it means for the business**:

> Weak: free cash flow was 6.3% of revenue over the past 12 months, the lowest of the 16 stocks we screened, which leaves little room to pay for the new factories its turnaround needs.

## 5. The price, separately

1. **Pick the industry's multiple** (StockStory picks one per industry):
   - **Default:** forward P/E.
   - **Software:** forward price to sales, even when profitable.
   - **Banks and insurers:** price to book. `analyse.py` prints it.
   - **Internet platforms and asset-heavy companies:** EV/EBITDA. It isn't in our data, so quote it from two sources.
   - **REITs:** price to funds from operations, also from two sources.
   - **Everyone:** price to free cash flow (`analyse.py`).
2. **Compare like with like:**
   - the forward multiple against peers' forward multiples (`analyse.py` does this);
   - the trailing P/E against the stock's own trailing history (`analyse.py` prints both on the same basis).
   - Never set a forward P/E against a trailing history.
3. **Weigh it against the quality.** Say whether the premium or discount matches how far the business sits above or below its peers on the section 1 metrics. In StockStory's data, high-quality stocks it rates timely trade at about half the multiple of high-quality ones it doesn't. Never put a number on what the stock "deserves".
4. **Say what the price assumes, never what it's worth.** "At 86 times expected earnings, earnings would have to grow 3.7-fold for the multiple to fall to the median of the stocks we screened" (Arm, in our 31 October chip list, where that median was 23.4 times).

## 6. The verdict: two sentences, kept apart

- **The business:** against its industry's bar, from the deciding metrics.
- **The price:** the multiple against peers and its own history, and whether the quality earns the gap.

Use our words:
- the business: **Strong / Solid / Mixed / Weak**;
- the price: **Below / About / Above its usual price**;
- in lists: **We like / We'd skip**.

StockStory's quadrants are a check on the logic, not words to print:
- a good business that's fairly priced;
- a good business that's expensive;
- a middling business that's cheap;
- a weak business, where the price doesn't matter.

Never "wait", "not now" or "below $X".

The site's own labels (`analyse.py`, "Our site's labels") come from a simpler model: equal-weighted sector ranks of 12-month growth and margins. Where your verdict differs, the deciding metrics win. Say why in the story if a reader would notice.

## 7. List stories

1. **The screen:** one metric, its period and its source, in the intro ("16 chip stocks that fell 5% or more on Friday, ranked on growth, margins and price"). The queue's themes and their deciding metric:
   - cash machines: free cash flow margin;
   - dividend payers: the yield, and free cash flow covering the dividend (dividends paid from the filing);
   - momentum: the 6-month return (`facts.py`);
   - beaten-down quality: distance from the 52-week high against the deciding metrics.
2. **Run `analyse.py` on every stock in the screen.** Choose the three and the one on the deciding metrics, not on the screen metric alone.
3. **Each item:**
   - the screen metric in bold, dated;
   - what the company does, in one sentence;
   - 2–3 reason lines (section 4), each against peers or the screen's median, with the long run first;
   - **The price:** one line (section 5);
   - **What would change our mind:** a metric and a date.

   Reasons that use guidance, consensus or a CEO's words need their sources (stock-analysis rule 7), even though check.py doesn't ask lists for them.
4. **The stock we like** is named, with the same block and a sized **What could go wrong**.

StockStory's own handpicked "Stock of the Month" argues three points:
- the moat or market position;
- the trend or catalyst behind it;
- why the price is reasonable.

That's a good check on the one we like.

## 8. Context in one line (why-it-moved)

After the move and its cause, one long-run line so the reader can scale it:
- "Even after Friday's 28% drop, Intel is up 78% this year."
- "Its sales have grown 4% a year over five years, a third of its peers' pace, which is why one weak forecast hits this hard."

## What StockStory does that we don't

- A teaching sentence at the top of every section, every time. We teach only when the reader needs it.
- Every metric for every company. We pick the ones that decide quality in the industry.
- A riddle "stock to buy instead" behind sign-up. We name it, with reasons.
- Their lists and "reasons" pieces carry no news. Ours always say why the stock matters this week. (Their full reports do open with the latest headlines.)

## Where this comes from (on the owner's machine)

- `~/Desktop/articlemaker/STYLE.md`: Format C, the research report.
- `~/Desktop/Projects/brarfinance/research/stockstory/`:
  - `STOCKSTORY_PLAYBOOK.md`: the report anatomy, the four beats, the industry modules, valuation by industry;
  - `universe/QUALITY_VALUE_DECODED.md`: the badge rules read off the two axes, and the value fit;
  - `universe/quality_drivers_by_sector.json`: the table in section 1, from about 1,300 parsed reports;
  - `universe/UNIVERSE_ANALYSIS.md`: tier medians, sector pass rates, bullet grammar.
- Our format: `docs/STYLE.md` (`list`). Example: `content/articles/2026-10-31-3-chip-stocks-wed-skip-and-1-we-like-after-fridays-rout.md`.
