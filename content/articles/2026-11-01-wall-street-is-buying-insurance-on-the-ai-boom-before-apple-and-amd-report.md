+++
title = "Wall Street Is Buying Insurance on the AI Boom Before Apple and AMD Report"
dek = "CoreWeave lost 37% in October as traders bought record numbers of its put options. This week Apple, AMD, the midterms and the jobs report test the selloff."
type = "daily"
published = 2026-11-01T10:45:00-05:00
author = "nora-whitfield"
tickers = ["CRWV", "ORCL", "AAPL", "AMD", "NBIS"]
themes = ["ai-capex", "fed-rates"]
event = "daily-2026-11-01"
moves = [
  { ticker = "CRWV", price = 54.87, change_pct = -9.66, session = "close", asof = 2026-10-30T16:00:00-04:00 },
  { ticker = "ORCL", price = 130.67, change_pct = -6.37, session = "close", asof = 2026-10-30T16:00:00-04:00 },
  { ticker = "AMD", price = 504.8, change_pct = -10.88, session = "close", asof = 2026-10-30T16:00:00-04:00 },
]
cover_brief = "In the centre of a dim, wood-panelled insurance office at night, a tall glowing server rack wrapped in thick gold chains stands under a warm gold desk lamp, with 'AI' stamped in white block capitals on its front panel. Beside it hangs a big glowing sign reading 'INSURANCE'. A grey-haired broker in a navy waistcoat stamps a thick plain policy, and a young woman in a dark suit anxiously signs it. Behind them a queue of adult buyers in coats waits in shadow, a plain wall calendar shows November, a ballot box sits on a side table, a barrel of crude oil stands in a corner, and a plain apple rests on the broker's desk"
cover_alt = "A chained server rack marked AI stands beside an Insurance sign as buyers queue to sign policies in a dim office"
cover_text = ["AI", "INSURANCE"]
sources = [
  "https://www.wsj.com/finance/stocks/ai-investors-are-racing-to-get-insurance-on-the-biggest-market-bet-in-history-a60e296f",
  "https://finance.yahoo.com/markets/options/articles/ai-investors-rush-hedge-against-030211499.html",
  "https://www.investing.com/news/stock-market-news/investors-hedge-ai-boom-with-credit-default-swaps-on-tech-debt-93CH-4959158",
  "https://www.wsj.com/articles/investors-are-hedging-against-the-risks-of-the-ai-boom-603203d5",
  "https://www.cnbc.com/2026/10/19/oracle-debt-faces-an-ai-stress-test-why-some-investors-arent-worried-.html",
  "https://www.securitasglobal.com/risk-perspectives/oracle-cds-record-288-basis-points-ai-debt/",
  "https://www.gurufocus.com/news/9124975/credit-default-swaps-surge-for-us-tech-firms-amid-ai-sector-strain-oracle-orcl-spreads-hit-record-high",
  "https://whtc.com/2026/10/22/metas-credit-risk-indicator-jumps-to-record-high-after-results/",
  "https://www.cnbc.com/2026/10/31/opec-oil-output-targets-december.html",
  "https://www.tradingview.com/news/reuters.com,2026:newsml_L5N46H06B:0-opec-set-to-keep-production-targets-unchanged-in-december-source-says/",
  "https://www.oilandgas360.com/tag/december-output-targets/",
  "https://finimize.com/content/stocks-have-rallied-after-every-midterm-election-for-50-years",
  "https://www.schaeffersresearch.com/content/analysis/2022/10/26/what-election-day-means-for-the-s-p-500",
  "https://www.bls.gov/news.release/archives/empsit_10022026.htm",
  "https://investinglive.com/news/us-september-non-farm-payrolls-29k-vs-90k-expected/",
  "https://macdailynews.com/2026/07/30/macdailynews-presents-live-notes-from-apples-q326-conference-call-260730/",
  "https://uk.finance.yahoo.com/news/apple-stock-slides-nearly-10-as-cook-warns-of-memory-shortage-impact-115246491.html",
  "https://finance.yahoo.com/markets/stocks/articles/apples-q4-earnings-loom-buy-173000032.html",
  "https://finance.yahoo.com/quote/AMD/analysis/",
  "https://www.sec.gov/Archives/edgar/data/0000002488/000000248826000121/q22026991.htm",
  "https://finance.yahoo.com/economy/policy/live/fed-meeting-live-updates-federal-reserve-october-meeting-kevin-warsh-161129201.html",
]
+++

Over the weekend, The Wall Street Journal reported that investors are racing to buy protection against the AI boom going wrong: put options, which pay out if a stock falls, and credit-default swaps, which pay out if a borrower defaults. The most popular bet against CoreWeave ($CRWV), a company that rents out Nvidia chips, pays off if its shares fall to $35 by 2028; they closed Friday at $54.87, after **falling 37.0%** in October.

That is the argument this week will test. Apple ($AAPL) reports on Monday, AMD ($AMD) on Election Day, and Qualcomm ($QCOM) and Arm ($ARM) on Wednesday, after a week in which Intel ($INTC), Alphabet ($GOOGL) and Amazon ($AMZN) left investors asking who pays for all the AI spending and who gets squeezed by it ([the week in eight charts](/daily/2026-10-31/)).

## This week in seven takes

### The AI borrowers fell hardest in October

```chart
{"kind": "moves", "tickers": ["CRWV", "NBIS", "GOOGL", "META", "NVDA", "ORCL", "AMZN", "MSFT"], "from": "2026-09-30", "to": "2026-10-30", "names": true,
 "title": "The companies that borrow to build AI fell the most",
 "subtitle": "Share price change, 30 September close to 30 October close, %"}
```

CoreWeave and Nebius ($NBIS), which borrow heavily to fill data centers with rented-out chips, each lost more than a third of their value in October. Microsoft ($MSFT), whose cloud growth sped up to 48% last quarter, rose 1.8% ([full story](/news/2026-10-28/microsoft-msft-beats-q1-estimates-as-azure-growth-speeds-up-to-48/)).

### Traders bought record protection against CoreWeave

Trading in CoreWeave put options reached its highest level on record in October, according to Cboe data cited by the Journal, and Investing.com reported that the cost of insuring its debt against default hit records this month ([our story on AI debt](/news/2026-10-31/the-ai-build-outs-debt-is-cracking-at-the-edges-starting-with-coreweave-crwv/)).

```chart
{"kind": "price", "ticker": "CRWV", "range": "1y", "end": "2026-10-30", "title": "CoreWeave is down 60% in a year",
 "subtitle": "CoreWeave, daily close, $", "mark": "last"}
```

The Journal also noted that demand for protection is still small next to the size of the AI investment boom.

### Insuring Oracle's debt now costs about 2.95% a year

Oracle's ($ORCL) five-year credit-default swap traded at about **295 basis points** on 27 October, up 287% in a year, CNBC reported, after a record on 15 October in S&P Global and LSEG data.

```stat
[{"value": "295bp", "label": "Oracle 5-year default insurance", "note": "Annual cost per $100 insured, 27 October", "tone": "down"},
 {"ticker": "ORCL", "metric": "ytd", "date": "2026-10-30", "label": "Oracle this year", "note": "Half its 52-week high"},
 {"ticker": "CRWV", "metric": "month", "date": "2026-10-30", "label": "CoreWeave, last month", "note": "Closed at $54.87 on Friday"}]
```

Oracle borrows to build data centers for OpenAI and is rated BBB-, the lowest investment grade, which is why traders use it as a stand-in for the AI build-out's credit risk. Reuters reported that Meta's ($META) default insurance hit a record on 22 October, the day after its results.

### Soap and power stocks gained 10% or more in October

```chart
{"kind": "moves", "tickers": ["LYB", "EXC", "CHD", "CL", "D", "KVUE", "NVDA", "AMD"], "from": "2026-09-30", "to": "2026-10-30", "names": true,
 "title": "Soap, power and chemicals beat the chipmakers in October",
 "subtitle": "Share price change, 30 September close to 30 October close, %"}
```

While AMD **fell 17.5%** in October, Colgate-Palmolive ($CL), Church & Dwight ($CHD), Exelon ($EXC) and Dominion Energy ($D) each rose 10% to 14%, by our count: makers of toothpaste and baking soda and power utilities, whose sales don't ride on AI spending. All four reported on Friday.

### Apple reports on Monday from a record high

```chart
{"kind": "price", "ticker": "AAPL", "range": "ytd", "end": "2026-10-30", "title": "Apple is the Magnificent Seven's best stock this year",
 "subtitle": "Apple, daily close, $", "notes": [{"date": "2026-07-30", "label": "Warned on memory costs"}]}
```

Apple closed Thursday at a record and is **up 26.8%** this year. In July, Tim Cook, then chief executive, said Apple expected "to pay even higher memory costs," the same squeeze that sank Intel, so the gross margin is the number to watch ([our preview](/news/2026-10-29/what-to-expect-from-apples-aapl-q4-earnings/)).

### AMD has to promise its biggest jump in sales

```stat
[{"value": "$16.15bn", "label": "AMD December-quarter sales, analysts' average", "note": "About $3 billion above the September quarter, per Yahoo Finance"},
 {"ticker": "AMD", "metric": "month", "date": "2026-10-30", "label": "AMD, last month", "note": "Still more than double since January"}]
```

That gain would be twice the biggest quarterly increase in AMD's filings since 2023, by our count, so we think a forecast that merely matches the average may not be enough for a stock still **up 135.7%** this year ([our preview](/news/2026-10-29/amd-amd-reports-earnings-on-tuesday-what-to-watch/)).

### Oil producers are holding output, and oil is above $100

```stat
[{"value": "$102.95", "label": "US crude (WTI), Friday", "note": "Up 0.9% on the day"},
 {"value": "$113.43", "label": "Brent crude", "note": "The global benchmark"},
 {"value": "4.93%", "label": "10-year Treasury yield", "note": "Friday's close"}]
```

OPEC+ agreed in principle to keep its December output targets unchanged, CNBC and Reuters reported on Saturday, citing people familiar with the talks, so no extra barrels are coming to cool prices ([our story on oil and the Fed](/news/2026-10-31/the-story-wall-street-is-telling-about-100-oil-and-the-fed/)). Friday's jobs report then decides whether the Fed hikes in December: after September's 29,000 jobs, futures put the odds at about 85%, according to Bloomberg data cited by Yahoo Finance.

## What's next

All times ET. Full calendar in [our week ahead](/news/2026-10-31/the-week-ahead-for-stocks-apple-amd-the-midterms-and-the-jobs-report/).

- **Monday, 2 November:** Apple and Palantir ($PLTR) report after the close ([Palantir preview](/news/2026-10-29/what-to-expect-from-palantirs-pltr-q3-earnings/)). The ISM factory survey comes at 10 a.m.
- **Tuesday, 3 November:** the midterm elections; the S&P 500 has risen in the six months after each of the last 13 midterms, Finimize found. Shopify ($SHOP) reports before the open ([preview](/news/2026-10-29/what-to-expect-from-shopifys-shop-q3-earnings/)), AMD after the close.
- **Wednesday, 4 November:** Uber ($UBER) before the open ([preview](/news/2026-10-29/what-to-expect-from-ubers-uber-q3-earnings/)), Qualcomm and Arm after the close.
- **Thursday, 5 November:** ConocoPhillips ($COP) before the open, Airbnb ($ABNB) and Cloudflare ($NET) after the close.
- **Friday, 6 November:** the October jobs report at 8:30 a.m.

## The numbers

| Market | Friday close | Change |
|---|---|---|
| S&P 500 | 7,580.07 | -1.82% |
| Nasdaq Composite | 25,437.00 | -2.86% |
| Dow Jones Industrial Average | 51,770.31 | -1.09% |
| Russell 2000 | 2,811.84 | -1.66% |
| VIX | 19.42 | +12.91% |
| 10-year Treasury yield | 4.93% | -0.06 point |
| US crude (WTI) | $102.95 | +0.93% |
| Gold | $3,884.90 | -3.63% |
| Bitcoin (8:22 a.m. ET Sunday) | $77,848 | +0.52% |
