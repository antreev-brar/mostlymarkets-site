"""analyse.py: the numbers behind a stock analysis, from our own data (SEC filings and CNBC quotes), judged against the
stock's sector the way StockStory judges every metric. Used by the analysis skills (.claude/skills/quality-check,
company-deep-dive, earnings-review).

    python3 pipeline/analyse.py MU            # one stock: the metric panel, valuation and peers
    python3 pipeline/analyse.py MU INTC QCOM  # several, one after another
    python3 pipeline/analyse.py MU --json     # the same as JSON

Every metric comes in the four beats the skills ask for: the long run (5 fiscal years), the recent run (2 years),
the latest quarter, and where it ranks among its peers (median and percentile): a StockStory-like group such as
chipmakers, software companies or banks when it has 10 members, otherwise the GICS sector. Numbers are ours (data/fundamentals,
built from SEC XBRL), so a story can cite "our analysis of SEC filings"; consensus estimates, guidance and industry
KPIs are not in our data and must come from the company's release and two outside sources.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

_TMP = tempfile.TemporaryDirectory(prefix="mm-analyse-")  # removed at exit (mkdtemp left one empty folder per run)
os.environ.setdefault("MM_DIST", _TMP.name)  # build.py never writes on import; belt and braces
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "site"))
import build as B  # noqa: E402
from marketdata import ADJUSTMENTS  # noqa: E402  (spin-offs: old prices are scaled, old EPS isn't)

TAX = 0.21  # US federal rate, for an approximate after-tax return on capital
TWIN = {"GOOG": "GOOGL", "FOX": "FOXA", "NWS": "NWSA"}  # second share classes: same company, same filings as the twin
STALE_DAYS = 140  # a US filer's latest quarter is never older than this unless a 10-Q/10-K is missing from our data


def cagr(a, b, years):
    if a is None or b is None or a <= 0 or b <= 0 or years <= 0:
        return None
    return ((b / a) ** (1 / years) - 1) * 100


def pct(a, b):
    return None if a in (None, 0) or b is None else (b / a - 1) * 100


def ratio(n, d):
    return None if n is None or not d else n / d * 100


def ssum(qs, k):
    vals = [q.get(k) for q in qs]
    return None if any(v is None for v in vals) or not vals else sum(vals)


def consecutive(qs) -> bool:
    """No missing, doubled or half-year 'quarter' in the run: each ends 80-120 days after the one before
    (a retailer's 16- or 17-week quarter is 112-119 days)."""
    ends = [date.fromisoformat(q["end"]) for q in qs]
    return all(80 <= (b - a).days <= 120 for a, b in zip(ends, ends[1:]))


def pe_series(t: str):
    """Daily close over the trailing-12-month diluted EPS known that day: build.pe_history without the chart's
    every-third-day thinning (which drops the real highs and lows), and only on four consecutive quarters."""
    qs = [q for q in (B.FUND.get(t) or {}).get("quarters", []) if q.get("eps_diluted") is not None and q.get("filed")]
    wins = [(qs[i]["filed"], qs[i]["end"], sum(q["eps_diluted"] for q in qs[i - 3:i + 1]))
            for i in range(3, len(qs)) if consecutive(qs[i - 3:i + 1])]
    if len(wins) < 3:
        return None
    out = []
    for bar in B.prices(t):
        seen = [w for w in wins if w[0] <= bar["date"]]
        if not seen:
            continue
        eps = max(seen, key=lambda w: w[1])[2]  # the latest period filed by then (a later 10-Q can re-file older quarters)
        if eps <= 0:
            return None
        out.append((bar["date"], bar["close"] / eps))
    return out if len(out) >= 120 else None


def metrics(t: str) -> dict:
    """The panel for one stock. None where our data can't give a number (say so in the story, or source it)."""
    f = B.FUND.get(t) or {}
    qs = f.get("quarters") or []
    yrs = f.get("annual") or []
    tt = f.get("ttm") or {}
    bal = f.get("balance") or {}
    cur = f.get("currency") or "USD"
    m: dict = {"ticker": t, "updated": f.get("updated"), "currency": cur, "latest_quarter": qs[-1]["label"] if qs else None,
               "latest_quarter_end": qs[-1]["end"] if qs else None}
    # Revenue: 5-year CAGR (fiscal years), 2-year annualised (TTM now vs TTM two years earlier), latest quarter YoY
    last = yrs[-1] if yrs else {}
    base = next((y for y in yrs if last.get("fy") is not None and y.get("fy") == last["fy"] - 5), None)  # by number: a missing year must not stretch the span
    if base:
        m["rev_cagr_5y"] = cagr(base.get("revenue"), last.get("revenue"), 5)
        m["eps_cagr_5y"] = cagr(base.get("eps_diluted"), last.get("eps_diluted"), 5)
        om0, om1 = ratio(base.get("operating_income"), base.get("revenue")), ratio(last.get("operating_income"), last.get("revenue"))
        m["op_margin_change_5y_pp"] = None if om0 is None or om1 is None else om1 - om0
        m["fy_span"] = f'FY{base.get("fy")}–FY{last.get("fy")}'
    if len(qs) >= 12 and consecutive(qs[-12:]):
        now, before = ssum(qs[-4:], "revenue"), ssum(qs[-12:-8], "revenue")
        m["rev_growth_2y_ann"] = cagr(before, now, 2)
    if len(qs) >= 5 and consecutive(qs[-5:]):
        m["rev_growth_last_q_yoy"] = pct(qs[-5].get("revenue"), qs[-1].get("revenue"))
        m["eps_last_q_yoy"] = pct(qs[-5].get("eps_diluted"), qs[-1].get("eps_diluted")) if (qs[-5].get("eps_diluted") or 0) > 0 else None
    m["rev_growth_ttm_yoy"] = tt.get("revenue_growth_yoy_pct")
    # Margins: TTM, and the two-year view (sum over the last 8 quarters)
    for k in ("gross_margin_pct", "operating_margin_pct", "net_margin_pct", "fcf_margin_pct"):
        m[k + "_ttm"] = tt.get(k)
    if len(qs) >= 8 and consecutive(qs[-8:]):
        rev8 = ssum(qs[-8:], "revenue")
        m["gross_margin_pct_2y"] = ratio(ssum(qs[-8:], "gross_profit"), rev8)
        m["fcf_margin_pct_2y"] = ratio(ssum(qs[-8:], "fcf"), rev8)
    # Per share: dilution over two years
    if len(qs) >= 9 and consecutive(qs[-9:]) and qs[-9].get("shares_diluted") and qs[-1].get("shares_diluted"):
        m["shares_change_2y_pct"] = pct(qs[-9]["shares_diluted"], qs[-1]["shares_diluted"])
    for k in ("rev_cagr_5y", "eps_cagr_5y", "op_margin_change_5y_pp", "rev_growth_2y_ann", "rev_growth_last_q_yoy", "eps_last_q_yoy",
              "shares_change_2y_pct"):
        if m.get(k) is not None and abs(m[k]) >= 1000:
            m[k] = None  # growth off a near-zero base, or a unit slip in the filing data: no number and no rank
    m["eps_ttm"] = tt.get("eps_diluted")
    # Returns and balance sheet (approximate ROIC: TTM operating profit after a 21% tax over equity + debt - cash)
    last4 = qs[-4:] if len(qs) >= 4 and consecutive(qs[-4:]) else None
    op_ttm = ssum(last4, "operating_income") if last4 else None
    ni_ttm = ssum(last4, "net_income") if last4 else None
    cash, debt, eq = bal.get("cash"), bal.get("debt"), bal.get("equity")
    cap = None if None in (cash, debt, eq) else eq + debt - cash
    # negative equity (buybacks past book value) shrinks 'capital' toward zero and ROIC toward infinity (MCK 1,579%): no number, like ROE
    m["roic_approx_pct"] = None if op_ttm is None or not cap or cap <= 0 or eq <= 0 else op_ttm * (1 - TAX) / cap * 100
    m["roe_pct"] = None if ni_ttm is None or not eq or eq <= 0 else ni_ttm / eq * 100
    m["net_cash"] = None if cash is None or debt is None else cash - debt
    m["net_debt_to_op_income"] = None if m["net_cash"] is None or not op_ttm or op_ttm <= 0 or m["net_cash"] >= 0 else -m["net_cash"] / op_ttm
    if (B.UMAP.get(t) or {}).get("sector") == "Financials":  # deposits and policy reserves make 'net debt' meaningless
        m["net_cash"] = m["net_debt_to_op_income"] = None
    m["balance_as_of"] = bal.get("as_of")
    m["equity"] = eq
    # Valuation: the multiple, its sector median and rank, and its own history (trailing P/E from our prices and EPS)
    q = B.Q.get(t) or {}
    kind, mult = B.multiple(t)
    if kind is None and cur == "USD" and (tt.get("eps_diluted") or 0) > 0 and q.get("price"):  # CNBC sends no P/E for FOX, NWS: profitable all the same
        kind, mult = "pe", q["price"] / tt["eps_diluted"]
    m.update({"price": q.get("price"), "quote_time": q.get("time"), "mktcap": q.get("mktcap"), "mktcap_usd": q.get("cap"),
              "multiple_kind": kind, "multiple": mult, "fwd_pe": q.get("fpe"), "trailing_pe": q.get("pe"), "yr_high": q.get("yr_high")})
    m["off_52w_high_pct"] = pct(q.get("yr_high"), q.get("price"))
    usd, capusd = cur == "USD", q.get("cap")
    fcf_ttm = ssum(last4, "fcf") if last4 else None
    m["price_to_book"] = capusd / eq if usd and capusd and eq and eq > 0 else None
    m["price_to_fcf"] = capusd / fcf_ttm if usd and capusd and fcf_ttm and fcf_ttm > 0 else None
    ps = pe_series(t) if usd and t not in ADJUSTMENTS else None  # EPS in another currency, or before a spin-off, can't divide today's price
    if ps:
        hist = sorted(p for _, p in ps)
        m["pe_own_median"] = hist[len(hist) // 2]
        m["pe_own_range"] = (hist[0], hist[-1])
        m["pe_own_since"] = ps[0][0]
        m["pe_own_now"] = ps[-1][1]
    sc = B.SCORES.get(t) or {}
    m["quality_score"], m["value_score"] = sc.get("q"), sc.get("v")
    m["labels"] = [lab for _, _, lab in B.ratings(t)]
    return m


# The ladder we use to judge a number against its peers (our own words; StockStory's are theirs).
LADDER = ((.9, "top tenth"), (.75, "top quarter"), (.5, "above the median"), (.25, "below the median"), (0, "bottom quarter"))


LOWER_IS_BETTER = {"shares_change_2y_pct"}


def ladder(p):
    if p is None:
        return ""
    if abs(p - .5) < 1e-9:
        return "at the median"
    return next(w for cut, w in LADDER if p >= cut)


# The groups we rank within, like StockStory's own sectors: chipmakers apart from software, banks apart from
# insurers and payment networks. A group needs 10 stocks; below that we rank within the GICS sector.
GROUPS = {
    "chipmakers": ("Semiconductors", "Semiconductor Materials & Equipment", "Semiconductor Equipment"),
    "software companies": ("Application Software", "Systems Software"),
    "hardware makers": ("Technology Hardware, Storage & Peripherals", "Communications Equipment", "Electronic Manufacturing Services",
                        "Electronic Equipment & Instruments", "Electronic Components", "Computer Hardware", "Technology Distributors"),
    "IT services and internet infrastructure": ("IT Consulting & Other Services", "Internet Services & Infrastructure",
                                                "Data Processing & Outsourced Services"),
    "consumer internet companies": ("Interactive Media & Services", "Broadline Retail", "Interactive Home Entertainment"),
    "banks": ("Diversified Banks", "Regional Banks"),
    "insurers and insurance brokers": ("Property & Casualty Insurance", "Life & Health Insurance", "Multi-line Insurance",
                                       "Reinsurance", "Insurance Brokers"),
    "payments, asset managers, exchanges and brokers": ("Transaction & Payment Processing Services", "Asset Management & Custody Banks",
                                                        "Financial Exchanges & Data", "Investment Banking & Brokerage",
                                                        "Consumer Finance", "Multi-Sector Holdings", "Diversified Capital Markets"),
    "drugmakers": ("Pharmaceuticals", "Biotechnology"),
    "medical device makers": ("Health Care Equipment", "Health Care Supplies"),
    "health care services, insurers and distributors": ("Health Care Services", "Managed Health Care", "Health Care Distributors",
                                                        "Health Care Facilities", "Health Care Technology"),
}
GROUP_OF = {ind: g for g, inds in GROUPS.items() for ind in inds}


def peer_group(t: str) -> tuple[str, list[str]]:
    """(label, tickers): the stock's group if it has 10 members, else its GICS sector. Each company once: the class
    asked for stands in for its twin (GOOG for GOOGL)."""
    x = B.UMAP[t]
    g = GROUP_OF.get(x["industry"])
    members = [u["ticker"] for u in B.UNIV if g and GROUP_OF.get(u["industry"]) == g]
    label = g
    if len(members) < 10:
        members = [u["ticker"] for u in B.UNIV if u["sector"] == x["sector"]]
        label = f'{x["sector"].lower()} stocks'
    members = [m for m in members if m not in TWIN and m != TWIN.get(t)] + ([t] if t in TWIN else [])
    return label, members


def sector_view(t: str, keys: list[str]) -> dict:
    """Median and this stock's percentile for each metric across its peer group (peer_group), from the same
    calculations. Multiples are compared like with like: forward P/Es with forward P/Es."""
    label, peers = peer_group(t)
    rows = {p: metrics(p) for p in peers}
    me_row = rows.get(t) or metrics(t)
    out = {"_group": {"label": label, "n": len(peers)}}
    for k in keys:
        vals = sorted(v[k] for v in rows.values() if v.get(k) is not None
                      and (k != "multiple" or v.get("multiple_kind") == me_row.get("multiple_kind")))
        me = me_row.get(k)
        if len(vals) < 8 or me is None:
            continue
        below = sum(1 for v in vals if v < me)
        same = sum(1 for v in vals if v == me) - 1
        out[k] = {"median": B.median(vals), "pct": (below + same / 2) / (len(vals) - 1) if len(vals) > 1 else .5, "n": len(vals)}
    return out


def fmt(v, kind="pct"):
    if v is None:
        return "n/a"
    if kind == "pct":  # a change
        return f"{v:+.1f}%" if abs(v) < 1000 else "n/a"
    if kind == "lvl":  # a level: a margin or a return
        return f"{v:.1f}%"
    if kind == "pp":
        return f"{v:+.1f} pts"
    if kind == "x":
        return f"{v:.1f}x"
    if kind == "money":
        return B.big_money(v)
    return f"{v:.2f}"


ROWS = [  # (key, label, kind, what it tells you)
    ("rev_cagr_5y", "Revenue, 5-year annual growth", "pct", "durability: has demand compounded through a cycle?"),
    ("rev_growth_2y_ann", "Revenue, 2-year annualised growth", "pct", "momentum: is it still growing now?"),
    ("rev_growth_last_q_yoy", "Revenue, latest quarter vs a year earlier", "pct", "this quarter"),
    ("gross_margin_pct_2y", "Gross margin, last 2 years","lvl", "pricing power"),
    ("operating_margin_pct_ttm", "Operating margin, last 12 months","lvl", "profitability"),
    ("op_margin_change_5y_pp", "Operating margin, change over 5 years", "pp", "is it getting more profitable?"),
    ("eps_cagr_5y", "EPS, 5-year annual growth", "pct", "per-share compounding"),
    ("shares_change_2y_pct", "Diluted shares, change over 2 years", "pct", "buybacks (falling) or dilution (rising); lower is better"),
    ("fcf_margin_pct_2y", "Free cash flow margin, last 2 years","lvl", "cash, not accounting profit"),
    ("fcf_margin_pct_ttm", "Free cash flow margin, last 12 months", "lvl", "its direction: against the 2-year figure"),
    ("roic_approx_pct", "Return on capital (approx.)","lvl", "returns on the money tied up in it"),
    ("roe_pct", "Return on equity","lvl", "banks and insurers: their returns measure"),
]


def report(t: str) -> str:
    m = metrics(t)
    sv = sector_view(t, [k for k, *_ in ROWS] + ["multiple"])
    x = B.UMAP[t]
    cur = m["currency"]
    money = (lambda v: fmt(v, "money")) if cur == "USD" else (lambda v: fmt(v, "money").replace("$", "") + f" {cur}")
    lq = f"{m['latest_quarter']} to {m['latest_quarter_end']}" if m["latest_quarter"] else "none in our data"
    lines = [f"## {x['name']} (${t}): {x['industry']}, {x['sector']}", "Rank among peers: percentile, best-first (for share count, fewer is better).",
             f"Data: SEC filings via data/fundamentals/{t.replace('.', '-')}.json (updated {m['updated']}, latest quarter {lq}, "
             f"fiscal years {m.get('fy_span', 'n/a')}{'' if cur == 'USD' else f', amounts in {cur}'}); quote {m['price']} at {m['quote_time']} (CNBC)."]
    if not m["latest_quarter_end"]:
        lines.append("**No quarters in our data** (" + ("a foreign filer that reports yearly" if m["updated"] else "no data/fundamentals file")
                     + "): the 2-year, latest-quarter and 12-month rows are missing.")
    elif (date.fromisoformat(str(m["quote_time"] or date.today())[:10]) - date.fromisoformat(m["latest_quarter_end"])).days > STALE_DAYS:
        lines.append(f"**Stale:** our newest quarter ended {m['latest_quarter_end']}, so a 10-Q or 10-K is missing from data/fundamentals; "
                     "take the later quarters from the filings before quoting a 12-month or latest-quarter figure.")
    g = sv.get("_group") or {}
    lines += [f"Peers: ranked against {g.get('n', 0)} {g.get('label', 'stocks')} in our coverage.",
              "", "| Metric | Value | Peer median | Rank among peers | What it tells you |", "|---|---|---|---|---|"]
    for k, lab, kind, why in ROWS:
        v = m.get(k)
        if v is None:
            continue
        s = sv.get(k) or {}
        rank = (1 - s["pct"]) if s and k in LOWER_IS_BETTER else s.get("pct")  # the ladder always reads best-first
        # The peer text is built first: nesting s['n'] in an f-string only parses on Python 3.12+, and the cloud
        # writer runs 3.11.
        peer = f" ({int(rank * 100)}%, n={s['n']})" if s else ""
        lines.append(f"| {lab} | {fmt(v, kind)} | {fmt(s.get('median'), kind) if s else ''} | "
                     f"{ladder(rank)}{peer} | {why} |")
    nc = m.get("net_cash")  # None for Financials (metrics)
    lines += ["", f"**Balance sheet** ({m['balance_as_of']}): " + ("judge a bank or insurer on return on equity and book value, not net debt" if x["sector"] == "Financials" else "") + (
        f"net cash {money(nc)}" if nc is not None and nc >= 0 else
        f"net debt {money(-nc)}" + (f", {m['net_debt_to_op_income']:.1f} years of operating profit" if m.get('net_debt_to_op_income') else "")
        if nc is not None else ("" if x["sector"] == "Financials" else "n/a"))
        + (f"; book value {money(m['equity'])}, price to book {fmt(m['price_to_book'], 'x')}" if m.get("price_to_book") else "")]
    s = sv.get("multiple") or {}
    own = (f"; its own trailing P/E since {m['pe_own_since']}: median {m['pe_own_median']:.1f}x, range "
           f"{m['pe_own_range'][0]:.1f}x–{m['pe_own_range'][1]:.1f}x, now {m['pe_own_now']:.1f}x on the same basis") if m.get("pe_own_median") else ""
    lines += [f"**Valuation**: {('forward P/E ' if m['multiple_kind'] == 'fpe' else 'trailing P/E ') + fmt(m['multiple'], 'x') if m['multiple_kind'] else 'no P/E (no profits)'}"
              + (f", peer median {fmt(s['median'], 'x')} ({ladder(1 - s['pct'])} for cheapness)" if s else "") + own
              + (f"; price to free cash flow {fmt(m['price_to_fcf'], 'x')}" if m.get("price_to_fcf") else "")
              + (f"; {fmt(m['off_52w_high_pct'])} from its 52-week high" if m.get("off_52w_high_pct") is not None else "") + ".",
              f"**Our site's labels**: {', '.join(m['labels']) or 'none'} (quality score {fmt(m['quality_score'], 'n')}, value score {fmt(m['value_score'], 'n')}; −1 to +1, sector-relative)."]
    peers = [p for p in B.peers_of(t) if p != TWIN.get(t)]
    if peers:
        lines += ["", "**Peers** (same industry first, by market value)", "",
                  "| Stock | Revenue 2y ann. | Op margin TTM | FCF margin 2y | EPS 5y | Multiple |", "|---|---|---|---|---|---|"]
        for p in [t] + peers:
            pm = metrics(p)
            lines.append(f"| {'**' + p + '**' if p == t else p} | {fmt(pm.get('rev_growth_2y_ann'))} | {fmt(pm.get('operating_margin_pct_ttm'), 'lvl')} | "
                         f"{fmt(pm.get('fcf_margin_pct_2y'), 'lvl')} | {fmt(pm.get('eps_cagr_5y'))} | "
                         f"{fmt(pm.get('multiple'), 'x')}{' fwd' if pm.get('multiple_kind') == 'fpe' else ''} |")
    lines += ["", "Not in our data (get from the release and two outside sources): consensus estimates and the beat or miss, guidance, "
              "segment revenue, industry KPIs (same-store sales, net revenue retention, backlog, net interest margin...), EBITDA."]
    return "\n".join(lines)


def main(argv: list[str]) -> None:
    ts = [a.upper() for a in argv if not a.startswith("-")]
    ts = [t.replace("-", ".") if t not in B.UMAP and t.replace("-", ".") in B.UMAP else t for t in ts]  # BRK-B → BRK.B
    if not ts:
        sys.exit(__doc__)
    B.compute_sector_medians()
    bad = [t for t in ts if t not in B.UMAP]
    if bad:
        sys.exit(f"not in our universe: {', '.join(bad)}")
    if any(a.lower() == "--json" for a in argv):  # the same panel as the text: metrics plus peer medians and ranks, and the peers
        keys = [k for k, *_ in ROWS] + ["multiple"]
        print(json.dumps({t: {**metrics(t), "sector_view": sector_view(t, keys), "peers": [p for p in B.peers_of(t) if p != TWIN.get(t)]}
                          for t in ts}, indent=1, default=str))
        return
    print("\n\n".join(report(t) for t in ts))


if __name__ == "__main__":
    main(sys.argv[1:])
