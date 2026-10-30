# Data files

## Fundamentals: `data/fundamentals/<TICKER>.json`

Financial history for each universe company, built from SEC XBRL "companyfacts" by `pipeline/fundamentals.py`. A `.` in a ticker becomes `-` in the file name (`BRK-B.json`).

```
python3 pipeline/fundamentals.py              # whole universe: 6 threads, under 8 SEC requests a second (~10 min)
python3 pipeline/fundamentals.py AAPL JPM     # just these
```

Python standard library only. The site builder calls `fundamentals.load(ticker)`, which returns the dict, or `None` if there's no file, and never touches the network. The run prints `ok / partial / failed` counts:

- **ok**: 12 quarters, a TTM block with revenue, EPS and net margin, and a latest quarter no more than 200 days old.
- **partial**: written, but something is missing. The reason is printed: `9q`, `no ttm`, `stale <date>` (SEC hasn't posted a newer 10-Q) and so on.
- **failed**: nothing usable. When a fetch fails, the previous file is kept.

### Schema

Values are in plain units: currency amounts in `currency`, EPS per share in `currency`, and share counts as share counts. A value is `null` when it's unknown.

| Key | Contents |
|---|---|
| `ticker`, `cik`, `name` | `name` is the SEC `entityName`. It can be odd: BAC's is "BofA Finance LLC". |
| `currency` | Taken from the XBRL unit. Usually `USD`, but TSM is `TWD`, NVO `DKK`, SAP `EUR`, BABA `CNY` and TM `JPY`. |
| `updated`, `source` | The New York date of the run, and `"SEC XBRL companyfacts"`. |
| `quarters[]` | The last 12 fiscal quarters, oldest first. Each has `end`, `fy`, `fp` (`Q1`–`Q4`), `label` (`"Q3 FY26"`), `filed` and `form` (the filing that first reported the quarter: a 10-Q, or the 10-K for Q4), then `revenue`, `gross_profit`, `operating_income`, `net_income`, `eps_diluted`, `ocf`, `capex`, `fcf` and `shares_diluted`. |
| `ttm` | The sum of the last 4 quarters. It's `null` unless those 4 quarters are consecutive. `revenue_growth_yoy_pct` compares against the 4 quarters before them. Margins are a % of TTM revenue, rounded to 1 decimal. A field is `null` when any of its quarters is missing. |
| `annual[]` | Up to 10 fiscal years, oldest first: `fy`, `end`, `revenue`, `operating_income`, `net_income`, `eps_diluted` and `fcf`. |
| `balance` | The latest balance sheet: `as_of`, `cash`, `debt`, `equity` and `shares_outstanding`. |

### How the numbers are built

**Quarters**
- Every quarter is a 3-month value: a fact whose start-to-end span is 80–100 days.
- Q4 is the full year minus the 9-month year-to-date.
- Cash-flow items are reported year-to-date, so they're de-cumulated the same way: Q2 = 6M − 3M, Q3 = 9M − 6M, Q4 = 12M − 9M.
- A 16-week first quarter (Kroger, Cava) is its own year-to-date figure.

**Fiscal calendar**
- The calendar comes from the 10-K's annual periods. A fact is placed in a quarter by its end date relative to the fiscal year end, never by the fy/fp of the filing that carried it. Some filers' fy/fp are simply wrong: PPL, MTD and AES.
- `fy` follows the company's own convention, taken from its latest filings. NVDA's year ending January 2026 is FY26, while TJX's year ending February 2025 is FY25.
- When a company changes its year end, its quarters follow the new calendar. FedEx moved from May to December in 2026, and Ferguson from July to December in 2025.

**Duplicates and tags**
- For each (start, end) period, the most recently filed value wins, so restatements win.
- Only periodic reports (10-K, 10-Q, 20-F, 40-F, 6-K and 8-K recasts) count. Proxy statements are ignored.
- Tags that mean the same thing are merged period by period, with the higher-priority tag winning.

**Revenue**
- Most companies: `RevenueFromContractWithCustomerExcludingAssessedTax`, then `Revenues`, `SalesRevenueNet` and `RevenueFromContractWithCustomerIncludingAssessedTax`, in that order. Utilities fall back to `RegulatedAndUnregulatedOperatingRevenue`.
- When `Revenues` is larger than the ASC 606 figure for the same period, `Revenues` wins. That's the income statement's total, and it's what releases lead with: Walmart's total revenues include membership income, Exxon's include equity-affiliate income, Caterpillar's include financial products and lessors' include rent.
- **Banks** (Diversified and Regional Banks) use total net revenue: `Revenues`, else `RevenuesNetOfInterestExpense`, else `InterestIncomeExpenseNet` + `NoninterestIncome`. This is the "net revenue" a bank's release leads with, and it matches JPM's to the dollar. Gross interest income plus noninterest income would be roughly 1.5–2 times that, so it isn't used. Banks get no gross profit, and operating income only if they tag `OperatingIncomeLoss`, which most don't.
- **Insurers, REITs and other financials** try `Revenues` first, then the bank construction, then the ASC 606 tags. A REIT's `OperatingLeaseLeaseIncome` is the last resort.
- The release's figure is what we match. For example, Exxon's "total revenues and other income".

**Other lines**
- **Gross profit:** `GrossProfit`, or else revenue minus `CostOfRevenue`/`CostOfGoodsAndServicesSold` (not for financials).
- **Operating income:** `OperatingIncomeLoss`.
- **Net income:** `NetIncomeLoss` (attributable to the parent).
- **Capex:** `PaymentsToAcquirePropertyPlantAndEquipment`, else `PaymentsToAcquireProductiveAssets`, always positive. FCF = OCF − capex.

**EPS and share counts**
- **Q4 EPS** is Q4 earnings for common holders over Q4 diluted shares. Q4 shares are 4 × the year's weighted average − (Q1 + Q2 + Q3); uneven quarters are day-weighted, and a loss quarter uses basic shares. Full-year EPS minus Q1–Q3 EPS is the fallback, used when the rebuild can't be made or is more than 25% away from it (when earnings for common holders differ from net income, as at TransDigm). Tested on ~3,700 fiscal years whose 10-K printed Q4 EPS, this hits the cent 70% of the time (89% within a cent); plain subtraction manages 44% (77%).
- Some multi-class filers' EPS reaches companyfacts only per share class, which means it isn't there at all (ABNB, MNST). Their EPS is then earnings over diluted shares.
- **Stock splits** are detected from restated per-share and share-count facts, and every quarter is put on today's share basis. For example, NVDA's 10-for-1 in 2024 and BKNG's 25-for-1 in 2026.

**Data-quality guards**
- A Q4 3-month fact equal to the full year (L3Harris's 10-K) or larger than the first nine months is treated as a tagging error.
- A full-year value from a 10-Q never displaces the 10-K's (Comfort Systems tagged a quarter with a full-year context).
- Share counts more than 2.5× away from the cover-page count are dropped, because a few filers tag shares without their scale (McDonald's in millions, Tempus in thousands). A reported EPS far from earnings over trusted shares is replaced by that figure (Bloom Energy's Q3 2024 tag reads −60.0 for −$0.07).
- When a restated year (discontinued operations) leaves full year minus nine months far from the other quarters, Q4 revenue, gross profit and operating income are left `null`. OXY and IP have such years.

**Balance sheet**
- **Cash:** `CashAndCashEquivalentsAtCarryingValue`.
- **Debt:** `LongTermDebt` (which includes current maturities) plus short-term borrowings or commercial paper, or else noncurrent debt plus current debt. It's `null` when nothing is tagged, which includes debt-free companies.
- **Equity:** `StockholdersEquity`.
- **Shares outstanding:** the cover-page count (dei), else the balance sheet's, else the latest quarter's basic weighted average (multi-class companies such as META).

**Foreign filers**
- Filers of 20-F and 40-F reports use the `ifrs-full` taxonomy: `Revenue` (banks use `RevenueAndOperatingIncome`), `ProfitLossFromOperatingActivities`, `ProfitLossAttributableToOwnersOfParent` (else `ProfitLoss`), `DilutedEarningsLossPerShare`, `CashFlowsFromUsedInOperatingActivities` and `PurchaseOfPropertyPlantAndEquipment…`.
- Their 6-K interim reports mostly carry no XBRL, so `annual` is filled and `quarters` is partial or empty. ARM is the exception: its 6-Ks are tagged.
- Their EPS is per ordinary share, not per ADR.

**History under an old CIK**
- History filed under an old CIK is merged in through `PREDECESSORS`. XOM moved to ExxonMobil Holdings Corp (CIK 2115436) in July 2026, and its history is under CIK 34088.

### Known gaps

- SEC's companyfacts sometimes lags or skips a filing. In late October 2026, ABT, V, C, CLX, CAH and about 20 utilities and REITs had no XBRL for their latest 10-Q, so they show as `stale`.
- Quarters around a large divestiture can mix restated and as-reported figures until the next 10-K restates the whole year. HON's 2025–2026 spin-offs are an example.
