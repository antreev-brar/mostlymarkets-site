---
name: company-deep-dive
description: Taking one company apart the Carbon Finance way, in the owner's write-article Format B (deep dive / thesis) - a one-sentence thesis, how it makes money, why the stock is where it is, each worry tested as temporary or lasting, the biggest risk sized, the moat with evidence, what the market is assuming at today's price, and a verdict. Use for breakdown stories ("Is X a good business?"), and for testing claims in viewpoints and narratives.
---

# Company deep dive (Carbon Finance's method, write-article's Format B)

The owner's `write-article` Format B was distilled from Carbon Finance's Adobe report. It runs:
1. a provocative title and a one-sentence thesis;
2. history and how the company makes money;
3. context: what's driving the stock and what the market is assuming;
4. stress-test the bear case;
5. valuation in plain language;
6. the final take.

Carbon's five public research reports run 3,500–7,700 words with 19–48 charts:
- Lululemon;
- UnitedHealth;
- Novo Nordisk;
- Meta;
- Adobe.

Our `breakdown` (docs/STYLE.md) follows the same path in **1,100–2,300 words** (check.py's range), with the detail in tables. This skill is how to do each step well; the template gives the headings.

**Before writing:**
- `python3 pipeline/analyse.py <TICKER>` for the numbers, the peer group and the peer table (quality-check for reading them).
- `python3 pipeline/facts.py <TICKER>` for the price moves.
- The latest results release (in a scheduled run, the event pack's `release_text`, or the company's 8-K) for segments and guidance.
- Coverage from two outlets for anything else. WebFetch may be blocked in the cloud, so work from search results and the release.
- What we wrote before: `grep -l '"<TICKER>"' content/articles/*.md`.

## The path, step by step

### 1. The thesis in one sentence (our italic verdict line)
All five Carbon reports open with one italic sentence that states a valuation stance and the condition it depends on. Adobe's argues the stock is priced as if decline were inevitable, while modest steady growth would be enough.

Ours has three parts: the business quality, what the price assumes, and the condition that decides it. STYLE.md wants this week's dated fact in the opening, so put the news peg in the thesis line or in the first paragraph under it.

> *After Friday's 5% fall, Micron is a business earning record margins on a shortage, priced for a crash it hasn't had: what decides it is how long the contracts hold prices.*

### 2. How it got here: from history to the question
Carbon's introduction runs:
1. the history;
2. why it mattered;
3. what went wrong, or what changed;
4. the question;
5. a roadmap.

Novo's question: "Has Novo lost its prescription for growth, or is it just facing short-term symptoms?" Ours is three short paragraphs ending in **one bold question**: a real one the evidence could answer either way.

### 3. The business, plainly
- **Who pays, for what, how often**, in one line.
- **Segments as a share of sales**, with growth: `| Segment | What it sells | Share | Growth |`, from the release or 10-K.
- **The long run of the whole company**, from `data/fundamentals/<T>.json` (10 fiscal years):
  - revenue over 10 years against the last 5;
  - EPS growth against revenue growth;
  - free cash flow and the capex trend.

  Carbon reads every chart in the paragraph after it: do the same, in one or two sentences.
- **End with a verdict line:** *Verdict: the engine is lending, and it's running hot; the tech business is the weak spot.* (That's write-article's SoFi piece; use this device in every section.)

### 4. Why the stock is where it is: numbered drivers
Carbon lists the forces behind a move from the worried investor's side: **"the major drivers behind the decline", 1/ to 5/**. They include:
- competition, with head-to-head numbers such as share, prices and trial data;
- guidance cuts;
- leadership;
- policy.

Ours: 2–5 drivers, strongest first, each with a number. Then a price chart with a `notes` marker on each driver's date.

### 5. Testing the worry: temporary or lasting?
This is where Carbon earns trust: it frames each worry **"from the most adverse angle"**, then tests it. For each driver, ask:
- **Structural or temporary?** Is it the business model and market structure, or a cycle, a one-off, an inventory swing?
- **Contained or spreading?** One product or region, or the whole franchise?
- **What do peers show?** The same problem at competitors means it's the industry; if they don't have it, it's the company.
- **What is management doing about it?** Price cuts, capex, buybacks or new products, with dates and money.

Say plainly which worry survives the test. Give the **bull case the same arithmetic**: Carbon's Novo "Opportunity" section sizes the market it's betting on with named outside numbers.

### 6. The risks, with the biggest one sized
Carbon names 3–5 company-specific risks. Where it can, it sizes one with back-of-envelope arithmetic, labels the result a worst case, lists the offsets, and closes the section by putting the risks in proportion. Meta's report calls that a "risk-closing bridge". Novo's:

> US revenue $28bn × 80% from GLP-1 drugs × 15% Medicare share × a 50% price cut ≈ **$1.7bn, about 6% of US sales** (3–4% of group sales). It's a "worst-case estimate", since Medicare doesn't cover obesity-only prescriptions.

Do this for **the biggest risk**:
- the exposure;
- the plausible hit;
- the result as a share of sales or EPS, with every input sourced or ours and the arithmetic in one line.

Then the offsets, then one line putting it in proportion. Name the other risks with one sentence of evidence each.

### 7. The moat, with evidence
Carbon's moat sections look at:
- network effects;
- data that improves the product;
- switching costs;
- management's record and insider ownership;
- the economics that show the moat working, such as pricing power (gross margin against peers) and low capital needs.

Name 2–4 advantages, each with one piece of evidence, and each rival with one comparable number. Carbon's filter, from its investment philosophy: "will this business still be here, and stronger, in 10 years?" Answer it in one sentence.

### 8. What the market is assuming
Carbon values a company several ways:
- the forward P/E against its own 10-year median, as a min-median-max band;
- against the market and peers ("15x vs the S&P's 23x and Lilly's 30x");
- a DCF on normalised free cash flow;
- a returns matrix;
- **a reverse DCF: "the market is effectively assuming…"** (the investment-philosophy post describes it; the Adobe report uses it).

We keep the comparisons and the reverse view, and we **never publish the DCF fair value or the returns matrix**: they're a price target and an entry price.
- **Against its own history:** `analyse.py` prints the trailing P/E median and range on one basis (2–3 years of our data). For a longer history, quote two sources and say the period.
- **Against peers:** the peer median on the same basis, and the peer table.
- **What the price assumes**, with the arithmetic shown:
  - "At 5 times expected earnings, Micron would still trade below its peers' median if those earnings fell by three-quarters."
  - "At 86 times, earnings must grow 3.7-fold to reach the median."
  - On normalised margins: "on its five-year average margin, not today's, the stock trades at about X times."

Our table (STYLE.md): `| Measure | Now | Its history | Peers |`. The history column exists for trailing P/E only; price to free cash flow is now and peers.

### 9. The verdict
Carbon ends on:
- "temporary or structural";
- the advantages;
- the risks that remain;
- valuation against the market and peers;
- a position.

We never take a position: we're pen names.

Ours: **Business: Strong / Solid / Mixed / Weak. Price: Below / About / Above its usual price.** Then:
- 3–5 sentences on why;
- the one thing that would change our mind;
- the next date that could change it;
- one plain closing line that states the tension.

## Carbon's lenses (from its investment-philosophy post; for judging, not for quoting)
- Revenue growth drives long-run returns more than a rising multiple. Organic growth beats bought growth.
- Prefer the proven business over the disruptive story.
- Look for simple, good unit economics, strong management, a durable moat, pricing power, low capital needs and a solid balance sheet.
- Loss asymmetry: a 50% fall needs a 100% gain to recover, so the downside case matters more.
- Carbon avoids banks, airlines, autos, utilities and telecom. We cover them, held to their own industry's bar (quality-check §1).

Any research figure from these lenses that goes into a story needs its own two sources.

## Checks before publishing
- [ ] The thesis line, the dek and "Our verdict" say the same thing with the same numbers, and the opening carries this week's dated fact.
- [ ] Every section ends with a one-line verdict.
- [ ] Every worry has a test and an outcome; the bull case has its arithmetic too.
- [ ] The biggest risk is sized, with offsets and the arithmetic shown, or named as unsizeable with the reason.
- [ ] Valuation says what the price assumes; there's no fair value, target, entry price or "would be $X".
- [ ] Every chart is read in the paragraph after it, with at most two figures in a prose paragraph.
- [ ] Two sources for every fact not in a filing or our data; every figure dated; 1,100–2,300 words.

## Where this comes from (on the owner's machine)
- `~/Desktop/articlemaker/STYLE.md`, Format B. Its examples: `articles/sofi-q2-2026` (section verdict lines, "what the market is pricing in") and the Carbon Adobe piece it was distilled from.
- `~/Desktop/Projects/brarfinance/research/carbonfinance/`:
  - `CARBONFINANCE_PLAYBOOK.md` §5–6;
  - the reports in `posts/`: Novo, the risk arithmetic and the Opportunity section; Meta, the risk-closing bridge; Adobe, "the market is effectively assuming"; the philosophy post, the reverse DCF.
- Our template: `docs/STYLE.md` (`breakdown`). Examples:
  - `content/articles/2026-10-31-micron-mu-earns-87-gross-margins-is-this-the-top.md`
  - `content/articles/2026-10-31-intel-intc-lost-28-6-in-a-day-is-the-business-broken.md`
