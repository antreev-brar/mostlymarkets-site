# ALERT: list event has no data (2026-10-29, 6:51 p.m. ET)

- Event `list-2026-10-29` ("3 Under-the-Radar Stocks We Love and 1 We Hate", screen: operating margin among companies worth $5-30 billion) arrived with `pack.candidates = []`.
- `data/fundamentals/` does not exist on the `data` branch (latest data commit d2e15cc, "data 2026-10-29 17:09 ET" holds only calendar, prices and quotes), so there are no SEC-filing numbers to build the picks from.
- The writer did not build its own screen or use outside numbers. The event was skipped as "no candidates in pack; data/fundamentals missing".

Fix: check the fundamentals step of `.github/workflows/data.yml` and the list-event pack builder, then requeue the list.
