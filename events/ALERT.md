# ALERT: Sandisk (SNDK) price history is not split-adjusted

Written by the writer run on Saturday 21 November 2026, about 10:40 a.m. ET.

Sandisk's 8-for-1 split took effect at the open on Friday 20 November. `data/prices/SNDK.csv` is split-adjusted only
from about 13 November (13 Nov close 110.63 = 885.01 / 8); earlier rows are still on the pre-split basis
(31 Dec 2025 close 237.38, 25 June 2026 close 2,335.00). As a result:

- `pipeline/facts.py SNDK` reports a wrong year to date (-66.6%) and a wrong distance from the 52-week high (-96.6%);
- `analyse.py SNDK` shows a forward P/E of 0.3x and price to book of 0.6x (per-share data on mixed bases);
- any `price` or `compare` chart of SNDK over more than a week, and the `picks` card's 1-year move, would be wrong.

What the writer did: left SNDK out of long-range charts and year-to-date figures; used only the week from 13 November.
Needed: back-adjust SNDK history before 20 November by 1/8 (and its per-share fundamentals).
