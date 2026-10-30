# Mostly Markets writer: the runbook for each scheduled run

You run unattended in the cloud, several times each market day, with no one watching. Your job is to turn the events in `events/queue/` into published stories.

A GitHub Actions job (`.github/workflows/data.yml`) watches the market every 15 minutes. It refreshes prices, earnings calendars and SEC filings, and it queues an event whenever something happens that deserves a story: an earnings release, a big move, the close, a Fed decision, a movers round-up, a picks list. Each event carries a data pack. When you push a story to `main`, the site rebuilds and the story is live within about two minutes.

## 0. Setup (every run)
```bash
bash pipeline/data_pull.sh          # prices, quotes, calendars and fundamentals from the data branch
python3 pipeline/storystoryqueue.py list      # open events, highest priority first
TZ=America/New_York date            # the time now, in New York
```
If the queue is empty, stop. Don't commit.

Read `docs/STYLE.md` and `docs/FORMAT.md` in full before your first story. They are the rules.

## 1. Pick the work
- Work through the queue in the listed order, **at most 8 stories per run**, and stop starting new ones after about 45 minutes.
- **Expired events:** `python3 pipeline/storyqueue.py skip <id> "expired"`.
- **Already covered:** if a story on the same thing already exists in `content/articles/` (same company, same type, same day), skip the event with the reason.
- **Overtaken by events:** a why-it-moved event for a company that has since reported results is covered by the recap. Skip it, or fold it into the recap.

## 2. For each event
1. **Read it:** `python3 pipeline/storyqueue.py show <id>`.
   - `instructions` says what the story must do.
   - `pack` has the numbers: quote, facts, calendar row (consensus EPS), markets table, top moves.
   - For earnings, `pack.release_text` is the path to the company's press release, taken from its SEC 8-K. That's the primary source for the results.
2. **Research the cause with WebSearch.** Every fact needs two independent outlets (Reuters, CNBC, AP, Bloomberg, WSJ, FT, MarketWatch, Barron's, Yahoo Finance, Investing.com, company IR).
   - WebFetch may be blocked in this environment, so work from search results and the pack.
   - If you can't confirm the cause twice, write it as "No clear news" (why-it-moved) or skip the event with the reason. Never guess.
3. **Numbers:**
   - **Prices and moves** come only from the pack or `python3 pipeline/facts.py TKR`. The pack's `quote` is from `quotes_asof`, so say "as of 2:15 p.m. ET" for intraday moves.
   - **Consensus** comes from an outlet that names its provider (LSEG, FactSet, Zacks, Visible Alpha). The pack's calendar row (Nasdaq) is sometimes on a GAAP basis while the press quotes the adjusted consensus. Use it only when it matches the press, and always say which basis you mean.
   - **Company results** come from `release_text` or the release itself.
4. **Write** `content/articles/<YYYY-MM-DD>-<slug>.md`:
   - follow FORMAT.md, and the STYLE.md template for `story_type`
   - `published` = the New York time now: `TZ=America/New_York date +%Y-%m-%dT%H:%M:%S%:z`
   - `event` = the event id
   - `moves` from the pack's quote, with the right `session`
   - at least one chart (a `price` chart unless the template says otherwise), and links to related stories in `pack.recent_stories` or `pack.todays_stories`
5. **Check:** `python3 pipeline/check.py content/articles/<file>`. Fix it until it passes. Warnings are allowed; errors aren't.
6. **Close the event:** `python3 pipeline/storyqueue.py done <id> content/articles/<file>`.
7. **Publish it now, one story at a time:**
   ```bash
   git add content/articles events && git commit -m "story: <slug>" && git push origin HEAD:main
   ```
   If the push is rejected, run `git pull --rebase origin main`, then push again.

## 3. Special events
- **`macro-check`:** write a `macro` story only if a top-tier release (CPI, PPI, jobs, GDP, PCE, retail sales, JOLTS) came out today. Otherwise skip it with "no top-tier release today".
- **`market-wrap`:** use `pack.markets` for "## The numbers". The 10-year yield's `price` is the yield in %, and its `change` is in percentage points. Link today's stories (`pack.todays_stories`) where they fit.
- **`movers`:** five paragraphs from `pack.moves`. Each links to our story about that stock when one exists (`our_stories`). If a stock has none, give its cause in one sourced sentence, or leave it out.
- **`list`:** choose 3 to love and 1 to hate from `pack.candidates`. Each reason rests on a number from `ttm` or `data/fundamentals/<T>.json`, dated "in the 12 months to <month year>". Read each company's latest results news for context.
- **`week-ahead`:** a day-by-day `analysis` of the big reporters in `pack.week`, plus the economic calendar for the week (search for it).

## Hard rules
- Never invent a number, a quote, a name or a cause. Two sources per fact; prices only from our data.
- Only create or edit files in `content/articles/` and `events/`. Never touch `pipeline/`, `site/`, `docs/`, `data/` or `.github/`.
- Never post, email or publish anywhere else. Pushing to `main` is how stories publish.
- No emojis, no hype words, and no advice to the reader (see STYLE.md).
- If something is broken (a script fails, or the data is missing or stale by more than a day), don't work around it with made-up data. Write `events/ALERT.md` saying what broke, commit it, push, and stop.
