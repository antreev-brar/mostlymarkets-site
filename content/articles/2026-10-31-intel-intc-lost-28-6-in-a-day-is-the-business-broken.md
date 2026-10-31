+++
title = "Intel (INTC) Lost 28.6% in a Day. Is the Business Broken?"
dek = "Intel fell 28.6% on Friday, its worst day since 1974, after a weak forecast. Its servers grew 78% while PCs shrank. We test whether the business is broken, and what the price still assumes."
type = "breakdown"
published = 2026-10-31T10:28:03-04:00
author = "dev-malhotra"
tickers = ["INTC", "AMD", "NVDA", "QCOM", "ARM"]
themes = ["intel-turnaround", "chip-selloff"]
sources = [
  "https://www.intc.com/news-events/press-releases/detail/1786/intel-reports-third-quarter-2026-financial-results",
  "https://www.sec.gov/Archives/edgar/data/50863/000005086326000188/q326earningsrelease.htm",
  "https://data.sec.gov/api/xbrl/companyconcept/CIK0000050863/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json",
  "https://www.globalbankingandfinance.com/intel-signals-slower-growth-pc-market-remains-pressure/",
  "https://finance.yahoo.com/technology/article/intel-to-report-q3-earnings-as-chip-stocks-continue-to-rebound-221713961.html",
  "https://thenextweb.com/news/intel-q3-2026-outlook-pc-slump-memory-shortage",
  "https://www.benzinga.com/markets/tech/26/10/62749985/chip-stocks-1-trillion-wipeout-intel-nvidia-amd-tsmc-broadcom",
  "https://www.cnn.com/2026/10/30/investing/us-stocks-ai-investment",
  "https://www.nbcnews.com/business/markets/tech-stocks-nasdaq-ai-boom-fears-deepen-rcna606512",
  "https://www.investing.com/news/stock-market-news/intel-warning-sparks-chip-rout-as-pc-weakness-clouds-turnaround-4987123",
  "https://finance.yahoo.com/markets/stocks/articles/stock-market-today-nasdaq-p-123540419.html",
  "https://finance.yahoo.com/markets/stocks/articles/intel-now-150-ytd-prompting-161016085.html",
  "https://letsdatascience.com/news/amd-and-intel-reach-record-highs-on-ai-demand-9880551d",
  "https://www.staradvertiser.com/2026/10/30/breaking-news/tech-stocks-tumble-as-amazon-intel-fuel-ai-spending-fears/",
  "https://www.trendforce.com/presscenter/news/20260930-13258.html",
  "https://news.skhynix.com/en/q3-2026-business-results/",
  "https://247wallst.com/investing/2026/10/28/sk-hynixs-profit-jumped-632-as-ai-eats-the-worlds-memory/",
  "https://www.koreajoongangdaily.com/business/samsungs-record-804b-q3-profit-fails-to-impress-investors/12944742",
]
+++

*Intel is a mixed business with a booming server arm, priced at 5.8 times sales as if its turnaround were already done; it needs that server growth to outrun a PC slump it expects to last at least until mid-2027.*

```stat
[{"value": "Mixed", "label": "The business", "note": "Servers up 78%, PCs down 5% in Q3"},
 {"value": "5.8x sales", "label": "The price", "note": "Above its usual: the five-year median is about 2.3x"},
 {"value": "-53.3%", "label": "Below its June high", "note": "$65.76 on Friday against $140.94 on 22 June", "tone": "down"}]
```

## How it got here

Intel ($INTC), founded in 1968, designs the processors inside PCs and servers and makes chips in its own factories, which it reports as a separate business, Intel Foundry. Its sales peaked at **$79.0 billion** in 2021, according to its filings.

Then the model cracked. Sales shrank four years in a row, to $52.9 billion in 2025, and Intel lost $18.8 billion in 2024. Its free cash flow was negative every year from 2022 to 2025.

In August 2025 the US government took a stake of about 10% and became Intel's largest shareholder, Reuters reported, and NBC News also named it the largest holder.

In 2026 the story flipped. Software "agents" that plan and run tasks on their own need far more ordinary processors alongside AI chips, 24/7 Wall St reported, and Lets Data Science reported that rising demand for processors lifted chip stocks. Intel's data-center sales growth sped up from 22% in the first quarter, according to 24/7 Wall St, to 78% in the third, according to Intel.

The stock **jumped 23.6%** on 24 April, the day after first-quarter sales beat estimates, and closed at a peak of $140.94 on 22 June.

Then came Thursday's forecast: fourth-quarter revenue of $15.0 billion to $16.0 billion, well short of estimates ([our recap](/news/2026-10-29/intel-intc-q3-profit-tops-estimates-shares-plunge-on-a-weak-forecast/)). On Friday the stock **plunged 28.6%**, its worst day since 1974, Benzinga and CNN reported. That leaves one question: **is the business broken, or did the price run too far ahead of it?**

## The business in one line

PC makers and data-center operators buy Intel's processors chip by chip, in orders that rise and fall with PC sales and server spending, while Intel Foundry makes chips almost entirely for Intel itself.

## How it makes money

Two units bring in almost all the money, and in the third quarter they went in opposite directions, according to Intel's results release.

| Segment | What it sells | Share of Q3 sales | Growth in Q3, year on year |
|---|---|---|---|
| Client Computing and Physical AI | Processors for laptops and desktops | 49% ($8.1 billion) | -5% |
| Data Center and AI | Xeon processors for servers | 44% ($7.3 billion) | +78% |
| Intel Foundry | Chipmaking, almost all of it for Intel's own products | $6.7 billion, nearly all internal | +58% |
| All other | Mobileye's car chips and smaller businesses | 4% ($0.7 billion) | -30%; last year's figure included Altera until 11 September 2025 |

Revenue sat near **$13 billion a quarter** for two years before jumping in the second quarter of 2026.

```chart
{"kind": "bars", "labels": ["Q4 23", "Q1 24", "Q2 24", "Q3 24", "Q4 24", "Q1 25", "Q2 25", "Q3 25", "Q4 25", "Q1 26", "Q2 26", "Q3 26"],
 "values": [15.41, 12.72, 12.83, 13.28, 14.26, 12.67, 12.86, 13.65, 13.67, 13.58, 16.13, 16.51], "unit": "$bn", "highlight": -1,
 "title": "Intel's sales broke out of two flat years in mid-2026",
 "subtitle": "Quarterly revenue, $bn (Q4 2026 guidance: $15.0-16.0bn)",
 "source": "Intel 10-Q and 10-K filings, via SEC XBRL"}
```

## The numbers that matter

### Growth: up 12%, a third of AMD's pace

Revenue rose **12.1%** to $59.9 billion in the 12 months to September 2026, after four straight years of falling sales.

AMD ($AMD) grew 39.5% and Nvidia ($NVDA) 83.4% over their latest 12 months, according to their filings. Intel is growing again, but well behind its rivals.

### Profitability: better, from a low base

Intel kept **15.3%** of its third-quarter revenue as operating profit, up from 5.0% a year earlier, according to its filings.

Over the past 12 months its gross margin, the share of sales left after making the chips, was 39.9%, below AMD's 53.2% and below Nvidia's, Qualcomm's and Arm's.

It's heading down again. Intel expects its adjusted gross margin to fall to 38.0% in the fourth quarter, from 44.1% in the third.

### Where the profit is: servers earn it, the factories lose it

The server unit earned **$3.04 billion** of operating profit in the third quarter, more than 40 cents on each dollar of sales, according to the release.

The PC unit earned $2.29 billion. Intel Foundry lost $1.85 billion, a loss Investopedia also put at nearly $1.9 billion.

```chart
{"kind": "hbars", "labels": ["Data Center and AI", "PCs (Client Computing)", "All other", "Corporate costs", "Intel Foundry"],
 "values": [3.04, 2.29, 0.18, -1.06, -1.85], "unit": "$bn",
 "title": "Servers earn Intel's profit, and its factories lose it",
 "subtitle": "Operating income by segment, Q3 2026, $bn (internal eliminations of -$0.07bn not shown)",
 "source": "Intel Q3 2026 results release"}
```

### Cash: thin, and spending is rising

Free cash flow, the cash left after spending on plants and equipment, was **$3.8 billion** in the 12 months to September, 6.3% of sales and less than a third of AMD's rate.

Spending is rising to fix supply. Capital spending was $4.0 billion in the third quarter, up 66% from a year earlier, by our count from Intel's cash-flow statements.

### Balance sheet: a little more cash than debt

Intel ended September with $54.0 billion of cash and short-term investments against **$50.1 billion** of debt, according to the release. The balance sheet isn't the problem.

## Why the stock is where it is

Here is the case against Intel as a worried investor would put it.

1. **The forecast went backwards.** Intel guided fourth-quarter revenue to $15.0 billion to $16.0 billion, below the $17.07 billion analysts expected, according to LSEG data cited by Reuters.
2. **PCs are shrinking because AI is taking the memory.** On the call, Chief Executive Lip-Bu Tan pointed to "the unprecedented memory crunch and the resulting softness in PC demand," NBC News reported. Chief Financial Officer David Zinsner said in the release that he sees the PC slowdown "continuing at least through the first half of next year."
3. **Intel can't make enough of what's selling.** "I'm disappointed that we were not able to meet strong customer demand in this quarter," Tan said on the call, according to NBC. Jay Goldberg of Seaport Research Partners told Reuters that Intel is making too many PC chips and too few server chips: "Bad planning is the cause."
4. **An accident at a factory.** A deadly explosion in October at Intel's plant in Kiryat Gat, Israel, will cut about $300 million from fourth-quarter revenue, Reuters and Yahoo Finance reported.
5. **The price had run far ahead.** At its June peak, Intel was valued at about 13 times its sales, by our calculation from its filings and our prices, against a five-year median of 2.3. Morgan Stanley analysts, who cut their price target, pointed to "how expensive the stock is on next-year numbers," Investopedia reported.

```chart
{"kind": "price", "ticker": "INTC", "range": "ytd", "end": "2026-10-30",
 "title": "Intel nearly quadrupled by June, then lost over half",
 "subtitle": "Intel, daily close, $",
 "notes": [{"date": "2026-04-24", "label": "Q1 beat: +23.6%"}, {"date": "2026-06-22", "label": "Peak: $140.94"},
           {"date": "2026-10-30", "label": "Q4 forecast: -28.6%"}]}
```

## Testing the worry

**The accident is temporary, and small.** It accounts for about $300 million, less than a fifth of the $1.6 billion gap between the midpoint of Intel's forecast and what analysts expected.

**The PC slump is lasting, and it's spreading.** SK hynix expects memory demand to outrun supply through 2030, and TrendForce forecast on 30 September that contract prices for ordinary DRAM would rise another 10% to 15% this quarter. It said notebook makers' inventories increasingly reflect higher component costs.

The damage isn't Intel's alone. Dell ($DELL) fell 10.8% and HP ($HPQ) 9.6% on Friday, and Samsung's phone business swung to an operating loss on pricier memory, the Korea JoongAng Daily reported. That makes it an industry problem; AMD's report on Tuesday will show how its PC chips are holding up.

**The supply shortfall looks temporary, if the spending works.** Demand isn't the problem in servers, where sales grew 78%. Intel raised capital spending 66% from a year earlier to make more chips, and Zinsner said it will keep investing "to increase supply and support future growth." Goldberg's "bad planning" charge is fixable, but the fix costs cash, and Intel's free cash flow is thin.

**The valuation survives the test.** Even after Friday, Intel trades at 5.8 times sales, two and a half times its five-year median. The business isn't broken; the price still assumes it's fixed.

## The moat

Intel has three real advantages, and rivals beat it on the numbers that measure them.

- **Scale in PCs.** Its PC unit still brought in $8.1 billion in a bad quarter for PCs and earned 28 cents of operating profit per dollar.
- **Servers in the AI-agent boom.** Data-center sales grew 78% in the third quarter, Intel's "strongest data center revenue growth in 15 years," Zinsner said in the release.
- **Its own factories, and Washington as a shareholder.** Intel Foundry's sales grew 58%, and the US government's stake was still worth about 280% more than when it was taken, even after Friday, NBC News reported. Its chipmaking rival, Taiwan Semiconductor ($TSM), is worth about $2.1 trillion, six times Intel's market value.

| Company | Revenue growth, latest 12 months | Gross margin, latest 12 months | Forward P/E |
|---|---|---|---|
| Intel | +12.1% (to September 2026) | 39.9% | 38.4 |
| AMD | +39.5% (to June 2026) | 53.2% | 44.8 |
| Nvidia | +83.4% (to July 2026) | 74.7% | 16.9 |
| Qualcomm | +1.9% (to June 2026) | 54.2% | 17.8 |
| Arm | +25.1% (to June 2026) | 97.5% | 86.3 |

Revenue and margins come from the companies' SEC filings; forward P/E ratios are from our quote data at Friday's close. Intel has the lowest gross margin of the five, so none of its advantages shows up yet as pricing power.

## The risks we'd watch

1. **PCs are half the business.** The PC unit brought in about half of third-quarter revenue, so each further 10% fall in its sales would cost about $0.8 billion a quarter.
2. **The factories keep losing money.** Had Intel Foundry broken even in the third quarter, Intel's operating profit would have been $4.4 billion, not $2.5 billion.
3. **Cash could turn negative again.** Free cash flow was negative $2.5 billion in the first quarter of 2026, and capital spending is rising. Another quarter like that would erase two-thirds of the past year's total.

## What the price assumes

Intel's losses in 2024 and 2025 leave no useful history for its price-to-earnings ratio, so we also measure it against sales and cash flow.

| Measure | Now | Its history | Peers |
|---|---|---|---|
| Forward P/E | 38.4 | No useful history: losses in 2024 and 2025 | Nvidia 16.9, Qualcomm 17.8, AMD 44.8 |
| Price to sales | 5.8 | Five-year median 2.3; about 13 at the June peak | Qualcomm 3.9, Nvidia 16.3, AMD 20.0 |
| Price to free cash flow | 92 | Negative free cash flow every year from 2022 to 2025 | Qualcomm 16.6, Nvidia 38.8, AMD 98.1 |

The forward P/E is from our quote data. The other ratios are our calculations from SEC filings, our price history and Friday's market values.

The price assumes a full recovery in profit. Intel's market value is about **$348 billion**, 5.8 times its sales over the past year.

Suppose Intel made 2018's net margin, its best in our records back to 2016, on the past year's sales. That's about $17.8 billion of profit, and the stock would still trade at about 20 times it.

In other words, today's price already pays for Intel's best margins in a decade. Nvidia, whose sales grew 83%, trades at 17 times forward earnings.

## Our verdict

**Business: Mixed. Price: Above its usual price.**

The business isn't broken. Its servers grew 78% and earn most of its profit, and it holds a little more cash than debt. But half its sales come from PCs, which Intel expects to stay weak until at least mid-2027, its factories still lose money, and the cash it keeps is thin. At 5.8 times sales against a five-year median of 2.3, the price assumes the turnaround is finished.

What would change our mind is proof that the supply fix works: server growth with the gross margin back above the third quarter's 44.1%, or a big outside customer for Intel Foundry. AMD's report on Tuesday, 3 November, is the first test of whether the PC slump is Intel's problem or everyone's.

A business that's getting better, priced as if it had already gotten there.
