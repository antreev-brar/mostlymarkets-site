+++
title = "TSMC (TSM) Is 18% Below Its High After the Chip Rout. Is the Business Broken?"
dek = "TSMC's US shares closed 17.9% below their October record on Friday, days after it booked a record NT$586.9 billion month. The business is not the problem; the risk is how much of it rides on AI."
type = "breakdown"
published = 2026-11-14T15:39:14-05:00
author = "dev-malhotra"
tickers = ["TSM", "NVDA", "INTC"]
event = "breakdown-2026-11-14-2"
themes = ["ai-capex", "chip-selloff"]
moves = [
  { ticker = "TSM", price = 398.73, change_pct = -1.67, session = "close", asof = 2026-11-13T16:00:00-05:00 },
]
sources = [
  "https://www.sec.gov/Archives/edgar/data/0001046179/000104617926000726/a3q26e_withguidancexfinal.htm",
  "https://fourweekmba.com/ai-tsmc-q3-revenue-rises-to-46-7b-with-a-66-4-gross-margin/",
  "https://www.crnasia.com/news/2026/components-and-peripherals/tsmc-third-quarter-revenue-tops-guidance-as-ceo-says-ai-dema",
  "https://cryptobriefing.com/tsmc-q3-2026-earnings-revenue-up-41/",
  "https://xenospectrum.com/en/tsmc-q3-2026-revenue-2nm-margin/",
  "https://www.sec.gov/Archives/edgar/data/0001046179/000104617926000796/tsm-revenue20261110.htm",
  "https://pr.tsmc.com/english/news/3349",
  "https://focustaiwan.tw/business/202611100014",
  "https://hwbusters.com/?p=122399",
  "https://cryptobriefing.com/tsmc-capex-64-billion-ai-demand/",
  "https://bits-chips.com/article/tsmc-raises-2026-capex-to-as-much-as-64b/",
  "https://www.morningstar.com/news/dow-jones/20260115161/tsmc-ends-2025-with-a-bang-as-ai-keeps-boosting-profits",
  "https://telecomlead.com/semiconductor/tsmc-delivers-record-2025-revenue-and-profit-as-ai-chip-demand-fuels-growth-us-expansion-accelerates-124150",
  "https://www.heygotrade.com/en/news/tsmc-tsm-stock-news-november-6-2026/",
  "https://www.tikr.com/ja/blog/tsmc-sinks-10-umc-down-16-as-chip-rout-deepens-after-democrats-midterm-wins",
  "https://fourweekmba.com/ai-tsmc-opens-limit-down-as-taiwans-ai-stocks-lose-182b/",
  "https://focustaiwan.tw/business/202609090025",
  "https://www.trendforce.com/presscenter/news/20260909-13225.html",
  "https://evertiq.com/design/2026-09-10-smic-narrows-gap-with-samsung-as-global-foundry-revenue-hits-record-5349-billion",
  "https://www.tikr.com/blog/tsmc-is-up-30-in-a-year-and-19-off-its-high-take-profits-or-buy-more",
  "https://www.sec.gov/Archives/edgar/data/0001045810/000104581026000082/nvidiaannouncesceotransiti.htm",
  "https://www.cnbc.com/2026/11/12/nvidia-nvda-jensen-huang-second-affair.html",
]
cover_brief = "A busy maximalist cartoon of a crowded old harbour quayside at dawn, packed edge to edge with grey-haired dockers in overalls and balding middle-aged traders in suits: in the centre a giant spotless chip factory shaped like a white warehouse sits on the quay, still humming with steam from its vents, with one very wide flat white board half the frame wide fixed straight across its front, in plain black block capitals reading 'TSMC', while directly above it hangs a huge flat yellow banner in plain black block capitals reading 'RECORD MONTH', while all around traders on the quay run away from the factory dropping papers, cranes keep loading crates of plain silicon wafers onto a plain unmarked cargo ship, a bearded engineer in a white suit waves calmly from a doorway, a grey-haired accountant stacks coins on a barrel, a forklift carries a wafer box, a chip-shaped boat bobs in the water, an empty office chair floats past, gulls circle, a news crew films from a van roof and a pigeon perches on a bollard; every other sign is blank"
cover_alt = "A cartoon of a humming TSMC chip factory on a quay under a RECORD MONTH banner as traders run away from it"
cover_text = ["TSMC", "RECORD MONTH"]
+++

*TSMC is the strongest business in chips, and after Friday it sells for about 19 times expected earnings, close to its usual multiple: what decides it is whether AI spending holds up long enough to fill the factories it is building.*

```stat
[{"ticker": "TSM", "metric": "ytd", "date": "2026-11-13", "label": "TSMC this year", "note": "17.9% below its 5 October record close"},
 {"value": "NT$586.9bn", "label": "October revenue", "note": "A monthly record, up 59.7% on a year earlier", "tone": "up"},
 {"value": "19.4x", "label": "Forward P/E", "note": "Against a chipmaker median of 22.3x"}]
```

```highlights
The short version
- **What's happening:** TSMC's US shares closed at $398.73 on Friday, 13 November, **17.9% below** their 5 October record, even though it reported a record month on 10 November.
- **Why it matters:** TSMC makes about seven in ten of the world's contract-made chips, so its stock is the market's bet on AI spending as a whole.
- **Our read:** Business: Strong. Price: About its usual price. The worry that survives is concentration: 68% of its sales now come from high-performance computing.
```

## How it got here

Taiwan Semiconductor Manufacturing makes chips that other companies design: Nvidia's AI processors, Apple's phone chips, AMD's and Broadcom's accelerators. It owns no chip brand of its own, which is why nearly every chip designer trusts it with its blueprints.

AI turned it from a phone-chip supplier into the factory floor of the data-centre boom. Revenue rose from NT$1.07 trillion in 2019 to **NT$3.81 trillion** in 2025, and TSMC expects about 44% more in US dollars in 2026, it said on 15 October.

Then the stock turned. It fell 10.8% on 5 November in a chip rout, and again after Nvidia's founder Jensen Huang resigned as CEO on 12 November. **Is the 18% fall a warning about the business, or a price the business doesn't deserve?**

```chart
{"kind": "bars", "labels": ["2019", "2020", "2021", "2022", "2023", "2024", "2025"], "values": [1.07, 1.34, 1.59, 2.26, 2.16, 2.89, 3.81], "unit": "NT$tn", "highlight": -1,
 "title": "TSMC's revenue has more than tripled since 2019", "subtitle": "Annual revenue, NT$ trillion", "source": "TSMC filings with the SEC; 2025 from its January release"}
```

## The business in one line

Chip designers pay TSMC per silicon wafer, at prices set by how advanced the process is, and they come back every product cycle because moving a design to another factory takes years.

## How it makes money

| Platform | What it makes | Share of Q3 2026 revenue | A quarter earlier |
|---|---|---|---|
| High-performance computing | AI accelerators, data-centre and PC processors | 68% | 66% |
| Smartphone | Phone processors and modems | 21% | 22% |
| Everything else (cars, connected devices, consumer) | Microcontrollers, sensors, connectivity | 11% (the remainder) | 12% |

By process, chips at 3 nanometres made 33% of its wafer revenue in the third quarter, 5nm 28% and the new 2nm 8%, up from 3% a quarter earlier, its results and Crypto Briefing reported. Nodes at 7nm and below made 79%.

*Verdict: the engine is AI, and the leading-edge processes are where the money is.*

## The numbers that matter

### Growth
Third-quarter revenue rose **41.2%** on a year earlier to $46.72 billion, above the $44.6 billion to $45.8 billion it had guided, TSMC's report said. It guided the fourth quarter to $52.3 billion to $54.3 billion. Over the five fiscal years to 2024, revenue grew 22.0% a year, above the 14.2% median of the 25 chipmakers we compare it with.

### Profitability
Its gross margin was **66.4%** in the third quarter and its operating margin 58.7%, CRN Asia and FourWeekMBA reported from its release. Its operating margin was 34.8% in 2019 and 45.7% in 2024, according to its SEC filings: it earns more on each dollar as it grows, not less.

### Cash
Free cash flow was NT$870 billion in 2024, 30% of revenue. That is about to shrink as a share: TSMC kept its 2026 capital budget at **$60 billion to $64 billion** in October, against $40.9 billion spent in 2025, according to its releases reported by Crypto Briefing and Bits & Chips.

### Balance sheet
It held net cash of NT$2.04 trillion at the end of 2024. It can pay for the building spree without borrowing.

*Verdict: growth, margins and cash are all at or near the best in its industry.*

## Why the stock is where it is

1. **The AI trade cracked.** The stock fell 10.8% on Thursday, 5 November, as the Nasdaq dropped 5.5%; TIKR and Gotrade reported no TSMC news that day, and tied the rout to fears of slower AI building after the midterm elections. TSMC opened limit-down in Taipei the next day, FourWeekMBA reported.
2. **Its biggest customer lost its founder.** Huang resigned as Nvidia's CEO on 12 November after an internal investigation, Nvidia said in an SEC filing, with CFO Colette Kress as interim CEO.
3. **Margins have peaked for now.** The third-quarter gross margin slipped from 67.7% in the second quarter, which TSMC put down mainly to the early 2nm ramp, and it guided 65% to 67% for the fourth.

```chart
{"kind": "price", "ticker": "TSM", "range": "6m", "end": "2026-11-13", "mark": "last",
 "notes": [{"date": "2026-10-05", "label": "Record close"}, {"date": "2026-10-15", "label": "Q3 results"}, {"date": "2026-11-05", "label": "Chip rout"}, {"date": "2026-11-12", "label": "Huang resigns"}],
 "title": "TSMC gave back its autumn run in five weeks", "subtitle": "Daily close of the US shares, $"}
```

## Testing the worry

**The rout is a sentiment worry, and the numbers so far contradict it.** Five days after the 5 November fall, TSMC reported October revenue of **NT$586.9 billion**, up 59.7% on a year earlier and a record by NT$72 billion, its 10 November filing and Focus Taiwan reported. October alone is about a third of its fourth-quarter guidance.

**Nvidia's leadership change is contained so far.** TSMC makes chips for Nvidia's rivals too, so an order that moved to AMD or Broadcom would still run through its factories. Nvidia's report after the close on Tuesday, 17 November is the first test of whether demand moved at all.

**The margin dip is temporary by design.** New processes always start at lower margins and rise as yields improve: 2nm is now 8% of wafer revenue. Overseas fabs are a slower drag, because they cost more to run than its Taiwan plants.

*The worry that survives is not any of these: it is how much of TSMC now depends on one kind of customer.*

## The moat

- **Scale at the leading edge.** TSMC held a record 72.5% of the contract chip market in the second quarter, TrendForce said, reported by Focus Taiwan and Evertiq. Samsung, the second-largest, held 5.9%.
- **Pricing power.** A 66.4% gross margin is the margin of a company that sets its prices. Intel, which wants to compete as a contract maker, earned an operating margin of 2.9% over the last 12 months in our data.
- **Trust.** It doesn't sell chips of its own, so Apple, Nvidia and AMD can share designs without feeding a rival.

Will it still be here, and stronger, in 10 years? Every process it adds widens the gap, and nobody else is spending $60 billion a year to close it.

## The risks we'd watch

**The biggest: an AI spending pause.** High-performance computing was 68% of third-quarter revenue, about $31.8 billion. A worst case in which that business shrank by a fifth for a year would take about $6.4 billion a quarter, roughly 14% of third-quarter revenue, while the cost of new factories keeps rising. The offsets: phone and car chips would not fall with it, and capital spending can be slowed within a year. In proportion, that is a bad year, not a broken business.

**Taiwan.** Most of its leading-edge capacity is on one island, and no arithmetic sizes a conflict; the Arizona fabs are the hedge, at a margin cost.

**Overbuilding.** Capital spending of up to $64 billion this year, against $40.9 billion last year, is the right bet only if orders keep pace into 2028.

## What the price assumes

| Measure | Now | Its history | Peers |
|---|---|---|---|
| Forward P/E | 19.4x | About 18x on average over five years, according to TIKR | 22.3x (chipmaker median) |
| Stock against its record | 17.9% below | Record close of $485.80 on 5 October | |
| Year to date | Up 31.2% | | |

At 19.4 times expected earnings, TSMC sits below the median of the chipmakers we compare it with. If its next year's earnings came in 15% below forecasts, the stock would trade at about 22.8 times them, still roughly the peer median: the price assumes a lot of AI demand, but not perfection.

## Our verdict

**Business: Strong. Price: About its usual price.** TSMC is growing revenue by about 44% this year at a 58.7% operating margin, holds net cash and seven in ten dollars of its market, and its October sales gave no sign of the slowdown the stock priced in on 5 November. What would change our mind is a cut to its 2026 or 2027 spending plans from its biggest customers, because a 68% share from one platform cuts both ways. The next date that could do it is Nvidia's report on Tuesday, 17 November, and TSMC's November sales around 10 December.

The factory is running at a record pace; the stock is pricing in the chance its customers stop ordering.
