# ALERT: daily price history is missing 29 October 2026

Raised by the writer run at 7:53 a.m. ET on Friday, 30 October 2026. No stories were written on this run.

## What broke
- The data branch (pulled "data 2026-10-30 06:23 ET") has no 2026-10-29 bar in any of the 582 files in `data/prices/`. The last bar everywhere is 2026-10-28.
- `data/quotes/refresh_marks.json` is `{"calendar": "2026-10-30", "fundamentals": "2026-10-30"}`: there is no `history` or `history-catchup` mark, so the evening history refresh on 29 October and the morning catch-up on 30 October either did not run or did not record a run.
- The quote fallback in `marketdata.read_prices` can't fill the gap: in `data/quotes/latest.json` every quote has `prev_close` equal to `price` (e.g. SYK price 311.75, prev_close 311.75, change_pct 2.55; open/high/low 0.0), so the "quote follows our last bar" test fails and no 29 October bar is appended.

## Effect
- `pipeline/facts.py TKR --asof 2026-10-29` returns 28 October numbers, so the "What the market is telling us" sentences, YTD and 52-week figures, and price charts would all be a session behind.
- 14 earnings-recap events for 29 and 30 October (SYK, SBUX, MO, BMY, SNDK, CVX, DASH, ICE, AJG, MDLZ, TT, HWM, RSG, PWR) are left in the queue. They expire at 8 p.m. ET today.

## To fix
Re-run `python3 pipeline/marketdata.py history` (or the `data` workflow), check that 2026-10-29 bars land in `data/prices/`, and look at why `prev_close` in the quotes feed equals the last price. Then delete this file; the next writer run will pick up the queue.
