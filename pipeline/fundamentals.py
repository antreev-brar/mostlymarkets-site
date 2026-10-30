"""Company fundamentals from SEC XBRL companyfacts -> data/fundamentals/<T>.json (BRK.B -> BRK-B.json).

  python3 pipeline/fundamentals.py              # the whole universe: 6 threads, under 8 SEC requests a second
  python3 pipeline/fundamentals.py AAPL JPM     # just these tickers

Standard library only. The site builder reads the files with load(ticker), which needs no network.
The file format and the rules behind every number are in docs/DATA.md.

How a quarter is built
  * Every value is a 3-month figure. 10-Qs report 3-month income-statement facts directly; the fourth quarter
    is the 10-K's full year minus the 9-month year-to-date, and cash-flow items (reported 3, 6, 9 and 12 months
    year-to-date) are de-cumulated the same way (Q2 = 6M - 3M, Q3 = 9M - 6M, Q4 = 12M - 9M).
  * The fiscal calendar comes from the annual (350-380 day) periods; a quarter is placed by its end date relative
    to the fiscal year that contains it, never by the fy/fp of the filing that happened to carry the fact.
  * Each period is deduplicated by (start, end), keeping the most recently filed (restated) value. Tags that
    mean the same thing are merged period by period, the higher-priority tag winning.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _stdlib_queue() -> None:
    """pipeline/storyqueue.py (the story queue) shadows the standard library's queue module, which ThreadPoolExecutor
    imports, whenever this directory is on sys.path (it is sys.path[0] when a script here is run)."""
    q = sys.modules.get("queue")
    if q is not None and hasattr(q, "SimpleQueue"):
        return
    saved = sys.path[:]
    sys.path[:] = [p for p in saved if Path(p or ".").resolve() != _HERE]
    try:
        sys.modules.pop("queue", None)
        import queue  # noqa: F401  - the standard library's, now that pipeline/ is off the path
    finally:
        sys.path[:] = saved


_stdlib_queue()
from concurrent.futures import ThreadPoolExecutor  # noqa: E402

sys.path.insert(0, str(_HERE))
from marketdata import DATA, now_et, sec_get_json, universe  # noqa: E402

OUT = DATA / "fundamentals"
SOURCE = "SEC XBRL companyfacts"
COMPANYFACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
N_QUARTERS = 12
N_YEARS = 10
WORKERS = 6
MAX_RPS = 6.5  # SEC asks for at most 10 a second; we stay under 8

# A company that moved its filings to a new registrant (a holding-company reorganisation) keeps its history
# under the old CIK. Those facts are merged in; the newest filing still wins for any period both report.
PREDECESSORS = {
    "XOM": ["0000034088"],  # ExxonMobil Holdings Corp (2026) took over from Exxon Mobil Corp
}

ANNUAL_FORMS = {"10-K", "10-K/A", "10-KT", "10-KT/A", "20-F", "20-F/A", "40-F", "40-F/A"}
# Financial statements come from periodic reports (and 8-K/6-K recasts). Proxy statements (pay-versus-performance
# tables), registration statements and prospectuses also carry a few us-gaap facts; those are ignored.
REPORT_FORMS = ("10-K", "10-Q", "20-F", "40-F", "6-K", "8-K")
BANK_INDUSTRIES = {"Diversified Banks", "Regional Banks"}

# ------------------------------------------------------------------ tags
# A source is a tag name, or ("+", a, b) for a value built as a + b where both are reported for the period.
GAAP = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax",
                "RegulatedAndUnregulatedOperatingRevenue"],  # utilities that tag no total of their own
    # Insurers, REITs and other financials book much of their revenue outside ASC 606, so "Revenues" comes first;
    # then net revenue as banks build it, then the ASC 606 tags, and a REIT's rental income as the last resort.
    "revenue_fin": ["Revenues", "RevenuesNetOfInterestExpense", ("+", "InterestIncomeExpenseNet", "NoninterestIncome"),
                    "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
                    "RevenueFromContractWithCustomerIncludingAssessedTax", "OperatingLeaseLeaseIncome"],
    # Banks: total net revenue, the figure their releases lead with (net interest income + noninterest income).
    "revenue_bank": ["Revenues", "RevenuesNetOfInterestExpense", ("+", "InterestIncomeExpenseNet", "NoninterestIncome")],
    "gross_profit": ["GrossProfit"],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"],
    "eps_diluted": ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted", "EarningsPerShareBasic"],
    "eps_numerator": ["NetIncomeLossAvailableToCommonStockholdersDiluted",
                      "NetIncomeLossAvailableToCommonStockholdersBasic"],
    "shares_diluted": ["WeightedAverageNumberOfDilutedSharesOutstanding",
                       "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
                       "WeightedAverageNumberOfSharesOutstandingBasic"],
    "shares_basic": ["WeightedAverageNumberOfSharesOutstandingBasic",
                     "WeightedAverageNumberOfShareOutstandingBasicAndDiluted"],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    # balance sheet (instants)
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "Cash",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "CashAndDueFromBanks"],
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "debt_total": ["LongTermDebt", "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
                   "DebtLongtermAndShorttermCombinedAmount", "DebtInstrumentCarryingAmount"],
    "debt_noncurrent": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations", "LongTermNotesPayable",
                        "SeniorLongTermNotes", "ConvertibleDebtNoncurrent", "ConvertibleNotesPayable"],
    "debt_current_ltd": ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent",
                         "ConvertibleDebtCurrent", "ConvertibleNotesPayableCurrent"],
    "debt_current": ["DebtCurrent"],
    "debt_short": ["ShortTermBorrowings", "CommercialPaper", "OtherShortTermBorrowings"],
    "shares_out_bs": ["CommonStockSharesOutstanding"],
}
IFRS = {
    "revenue": ["Revenue", "RevenueFromContractsWithCustomers", "RevenueAndOperatingIncome", "RevenueFromSaleOfGoods"],
    "revenue_fin": ["Revenue", "RevenueAndOperatingIncome", "RevenueFromContractsWithCustomers"],
    "revenue_bank": ["RevenueAndOperatingIncome", "Revenue"],
    "gross_profit": ["GrossProfit"],
    "cost_of_revenue": ["CostOfSales"],
    "operating_income": ["ProfitLossFromOperatingActivities"],
    "net_income": ["ProfitLossAttributableToOwnersOfParent", "ProfitLoss"],
    "eps_diluted": ["DilutedEarningsLossPerShare", "BasicEarningsLossPerShare", "BasicAndDilutedEarningsLossPerShare",
                    "DilutedEarningsLossPerShareFromContinuingOperations"],
    "eps_numerator": ["ProfitLossAttributableToOrdinaryEquityHoldersOfParentEntityIncludingDilutiveEffects",
                      "ProfitLossAttributableToOrdinaryEquityHoldersOfParentEntity"],
    "shares_diluted": ["AdjustedWeightedAverageShares", "WeightedAverageShares"],
    "shares_basic": ["WeightedAverageShares"],
    "ocf": ["CashFlowsFromUsedInOperatingActivities", "CashFlowsFromUsedInOperations"],
    "capex": ["PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
              "PurchaseOfPropertyPlantAndEquipment",
              "PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets"],
    "cash": ["CashAndCashEquivalents", "Cash"],
    "equity": ["EquityAttributableToOwnersOfParent", "Equity"],
    "debt_total": ["Borrowings"],
    "debt_noncurrent": ["NoncurrentPortionOfNoncurrentBorrowings", "LongtermBorrowings", "NoncurrentBorrowings"],
    "debt_current_ltd": ["CurrentPortionOfLongtermBorrowings", "CurrentPortionOfNoncurrentBorrowings"],
    "debt_current": ["CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings"],
    "debt_short": ["ShorttermBorrowings", "CurrentBorrowings"],
    "shares_out_bs": ["NumberOfSharesOutstanding"],
}
TAXONOMY = {"us-gaap": GAAP, "ifrs-full": IFRS}

# Durations (end minus start, in days) of a period covering 1-4 fiscal quarters. A 3-month value is 80-100 days.
# Year-to-date periods (which start on the first day of the fiscal year) are allowed more slack, since some
# retailers have uneven quarters: Kroger and Cava a 16-week first quarter, Costco 12-12-12-16 weeks.
SPAN = {1: (80, 100), 2: (170, 200), 3: (260, 290), 4: (350, 380)}
SPAN_YTD = {1: (80, 120), 2: (155, 205), 3: (245, 295), 4: (350, 380)}
QDAYS = 91.31


def _d(s: str | None) -> dt.date | None:
    return dt.date.fromisoformat(s) if s else None


def _shift(day: str, days: int) -> str:
    return (dt.date.fromisoformat(day) + dt.timedelta(days=days)).isoformat()


_NICE = sorted({1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 25, 30, 40, 50, 100}
               | {1 / x for x in (1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50, 100)})


def _nice_ratio(r: float) -> float | None:
    if 0.95 < r < 1.05:
        return None
    for n in _NICE:
        if abs(r / n - 1) < 0.02:
            return n
    return None


def _num(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ SEC fetch, rate-limited across threads

class _RateLimit:
    def __init__(self, per_sec: float):
        self.gap = 1.0 / per_sec
        self.lock = threading.Lock()
        self.next = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            at = max(now, self.next)
            self.next = at + self.gap
        if at > now:
            time.sleep(at - now)


_LIMIT = _RateLimit(MAX_RPS)


def fetch_companyfacts(cik: str) -> dict:
    _LIMIT.wait()
    return sec_get_json(COMPANYFACTS.format(cik=str(cik).zfill(10)))


# ------------------------------------------------------------------ facts

class Rec:
    """One reporting period of one tag: the latest-filed value plus who first reported the period."""
    __slots__ = ("s", "e", "val", "filed", "form", "tag", "accn",
                 "first_filed", "first_form", "first_fy", "first_fp", "first_accn", "restated")

    def __init__(self, s, e, val, filed, form, tag, accn, fy, fp):
        self.s, self.e, self.val, self.filed, self.form, self.tag, self.accn = s, e, val, filed, form, tag, accn
        self.first_filed, self.first_form, self.first_fy, self.first_fp, self.first_accn = filed, form, fy, fp, accn
        self.restated = False  # some filing reported a materially different value for the same period

    @property
    def days(self) -> int | None:
        return (self.e - self.s).days if self.s else None


def _rank(s, e, form: str, filed: str, accn: str) -> tuple:
    """Which of two filings' values for one period wins: the latest filed, except that an interim report never
    displaces an annual report's figure for a full-year period."""
    interim_year = bool(s) and (e - s).days >= SPAN[4][0] and form.startswith(("10-Q", "6-K"))
    return (not interim_year, filed, accn)


class Facts:
    def __init__(self, facts_dicts: list[dict]):
        self.raw: dict[tuple[str, str], dict[str, list]] = defaultdict(lambda: defaultdict(list))
        for fd in facts_dicts:
            for tax, concepts in (fd or {}).items():
                for tag, body in concepts.items():
                    for unit, rows in (body.get("units") or {}).items():
                        self.raw[(tax, tag)][unit].extend(rows)
        self._cache: dict = {}
        # Stock splits: per-share and share-count facts filed before a split are put on the latest basis.
        self.splits: list[tuple[str, str, float]] = []
        self._split_units: set[str] = set()

    def detect_splits(self, tax: str, eps_tags: list[str], share_tags: list[str], cur: str) -> None:
        """Find splits from periods that later filings restate by a round ratio (2:1, 3:1, 10:1, 1:20 ...).

        Each candidate says "between filing dates lo and hi the basis changed by n"; candidates with the same
        ratio and overlapping windows are one event, and an event needs two candidates, one from share counts.
        """
        cands = []
        for tags, unit, inverse in ((eps_tags, f"{cur}/shares", False), (share_tags, "shares", True)):
            for tag in tags:
                byp: dict[tuple, dict] = defaultdict(dict)
                for f in self.units(tax, tag).get(unit, []):
                    v = _num(f.get("val"))
                    if not v or not f.get("start") or not f.get("filed"):
                        continue
                    if not (f.get("form") or "").startswith(REPORT_FORMS):
                        continue
                    if not inverse and abs(v) < 0.10:
                        continue  # cents-level EPS restatements look like ratios
                    byp[(f["start"], f["end"])].setdefault(f["filed"], v)
                for seq in byp.values():
                    seq = sorted(seq.items())
                    for (f1, v1), (f2, v2) in zip(seq, seq[1:]):
                        if v1 * v2 <= 0:
                            continue
                        n = _nice_ratio(v2 / v1 if inverse else v1 / v2)
                        if n:
                            cands.append((f1, f2, n, inverse))
        events: list[dict] = []
        for f1, f2, n, is_shares in sorted(cands, key=lambda c: (c[1], c[0])):
            for ev in events:
                if ev["n"] == n and f1 < ev["hi"] and f2 > ev["lo"]:
                    ev["lo"], ev["hi"] = max(ev["lo"], f1), min(ev["hi"], f2)
                    ev["count"] += 1
                    ev["shares"] += is_shares
                    break
            else:
                events.append({"lo": f1, "hi": f2, "n": n, "count": 1, "shares": int(is_shares)})
        events = [e for e in events if e["count"] >= 2 and e["shares"]]
        # Filings between the last restated-before and first restated-after dates (a quarter not yet restated)
        # are placed by their share counts: nearer the old level means filed before the split.
        for ev in events:
            pre, post, mid = [], [], []
            for tag in share_tags:
                for f in self.units(tax, tag).get("shares", []):
                    v, filed = _num(f.get("val")), f.get("filed") or ""
                    if not v or v <= 0 or not f.get("start"):
                        continue
                    if filed <= ev["lo"] and filed >= _shift(ev["lo"], -400):
                        pre.append(v)
                    elif filed >= ev["hi"] and filed <= _shift(ev["hi"], 400):
                        post.append(v)
                    elif ev["lo"] < filed < ev["hi"]:
                        mid.append((filed, v))
            if pre and post:
                a, b = sorted(pre)[len(pre) // 2], sorted(post)[len(post) // 2]
                for filed, v in mid:
                    if abs(math.log(v / a)) < abs(math.log(v / b)):
                        ev["lo"] = max(ev["lo"], filed)
        self.splits = sorted((e["lo"], e["hi"], e["n"]) for e in events)
        self._split_units = {f"{cur}/shares", "shares"}
        self._cache.clear()

    def split_factor(self, filed: str) -> float:
        """How many of today's shares one share was when this fact was filed."""
        k = 1.0
        for lo, _hi, n in self.splits:
            if filed <= lo:
                k *= n
        return k

    def has(self, tax: str, tag: str) -> bool:
        return (tax, tag) in self.raw

    def units(self, tax: str, tag: str) -> dict[str, list]:
        return self.raw.get((tax, tag), {})

    def periods(self, tax: str, tag: str, unit: str) -> dict[tuple, Rec]:
        """{(start, end): Rec}, start None for instants. Latest filing wins; first filing is remembered."""
        key = (tax, tag, unit)
        if key in self._cache:
            return self._cache[key]
        out: dict[tuple, Rec] = {}
        adjust = self.splits and unit in self._split_units and tax != "dei"
        for f in self.units(tax, tag).get(unit, []):
            val = _num(f.get("val"))
            if val is None or not f.get("end"):
                continue
            if tax != "dei" and not (f.get("form") or "").startswith(REPORT_FORMS):
                continue
            s, e = _d(f.get("start")), _d(f["end"])
            filed = f.get("filed") or ""
            if adjust:
                k = self.split_factor(filed)
                if k != 1.0:
                    val = val * k if unit == "shares" else val / k
            k = (s, e)
            r = out.get(k)
            if r is None:
                out[k] = Rec(s, e, val, filed, f.get("form") or "", tag, f.get("accn") or "", f.get("fy"), f.get("fp"))
                continue
            if abs(val - r.val) > 0.01 * max(abs(val), abs(r.val)):
                r.restated = True
            # A 10-Q has no business reporting a full fiscal year; when one does (Comfort Systems' Q1 2026 10-Q
            # tags Q1 revenue with a full-year context), the annual report's value stands.
            if (_rank(s, e, f.get("form") or "", filed, f.get("accn") or "")
                    > _rank(s, e, r.form, r.filed, r.accn)):
                r.val, r.filed, r.form, r.accn = val, filed, f.get("form") or "", f.get("accn") or ""
            if (filed, f.get("accn") or "") < (r.first_filed, r.first_accn):
                r.first_filed, r.first_form, r.first_fy, r.first_fp = filed, f.get("form") or "", f.get("fy"), f.get("fp")
                r.first_accn = f.get("accn") or ""
        self._cache[key] = out
        return out

    def merged(self, tax: str, sources: list, unit: str) -> dict[tuple, Rec]:
        """Merge several tags period by period; for each period the first source in the list that has it wins."""
        out: dict[tuple, Rec] = {}
        for src in sources:
            if isinstance(src, tuple):
                _, a, b = src
                pa, pb = self.periods(tax, a, unit), self.periods(tax, b, unit)
                for k, ra in pa.items():
                    rb = pb.get(k)
                    if rb is None or k in out:
                        continue
                    r = Rec(ra.s, ra.e, ra.val + rb.val, max(ra.filed, rb.filed), ra.form, f"{a}+{b}", ra.accn,
                            ra.first_fy, ra.first_fp)
                    r.first_filed, r.first_form, r.first_accn = ra.first_filed, ra.first_form, ra.first_accn
                    r.restated = ra.restated or rb.restated
                    out[k] = r
            else:
                for k, r in self.periods(tax, src, unit).items():
                    out.setdefault(k, r)
        return out


# ------------------------------------------------------------------ fiscal calendar

class FY:
    """A fiscal year. Quarters are numbered from `anchor`, which is the start except in the short transition
    period of a company that moved its year end (FedEx's June-December 2026 counts quarters from 1 January)."""
    __slots__ = ("start", "end", "num", "known", "anchor", "transition")

    def __init__(self, start: dt.date, end: dt.date, known: bool, anchor: dt.date | None = None,
                 transition: bool = False):
        self.start, self.end, self.known, self.num = start, end, known, None
        self.anchor, self.transition = anchor or start, transition

    def __repr__(self):
        return f"FY{self.num}({self.start}..{self.end}{'' if self.known else '?'}{'T' if self.transition else ''})"


def _add_year(d: dt.date, n: int = 1) -> dt.date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:  # 29 February
        return d.replace(year=d.year + n, day=28)


def _month_end(d: dt.date, months: int) -> dt.date:
    """Last day of the month `months` after d's month."""
    y, m = divmod(d.month - 1 + months + 1, 12)  # first day of the month after the target month
    return dt.date(d.year + y, m + 1, 1) - dt.timedelta(days=1)


def _label_year(fy_end: dt.date) -> int:
    # A year ending on 2 January belongs with the one ending on 31 December.
    return (fy_end - dt.timedelta(days=15)).year


MISALIGNED = 0.28  # a period end this far (in quarters) from a fiscal-quarter end belongs to another calendar


class Calendar:
    def __init__(self, years: list[FY]):
        self.years = years

    @staticmethod
    def _extend(years: list[FY], limit: dt.date) -> None:
        while years[-1].end < limit:
            last = years[-1]
            length = (last.end - last.anchor).days
            end = _add_year(last.end) if 360 <= length <= 366 else last.end + dt.timedelta(days=364)
            years.append(FY(last.end + dt.timedelta(days=1), end, False))

    @classmethod
    def build(cls, maps: list[dict[tuple, Rec]], latest: dt.date | None) -> "Calendar":
        support: Counter = Counter()
        for m in maps:
            for (s, e), r in m.items():
                if s is None:
                    continue
                d = (e - s).days
                if SPAN[4][0] <= d <= SPAN[4][1]:
                    support[(s, e)] += 3 if (r.form in ANNUAL_FORMS or r.first_form in ANNUAL_FORMS) else 1
        kept: list[tuple] = []
        for c in sorted(support, key=lambda x: (x[1], x[0])):
            if kept and (c[1] - kept[-1][1]).days < 300:
                if support[c] > support[kept[-1]]:
                    kept[-1] = c
                continue
            kept.append(c)
        years = [FY(s, e, True) for s, e in kept]
        if not years:
            # No annual report yet (a recent listing): fiscal-year starts from year-to-date periods.
            starts: Counter = Counter()
            for m in maps:
                for (s, e), r in m.items():
                    if s is None:
                        continue
                    d = (e - s).days
                    if SPAN[2][0] <= d <= SPAN[3][1] or (SPAN[1][0] <= d <= SPAN[1][1] and r.first_fp == "Q1"):
                        starts[s] += 1
            if not starts:
                return cls([])
            s0 = starts.most_common(1)[0][0]
            years = [FY(s0, _add_year(s0) - dt.timedelta(days=1), False)]
        # Extend a few years back and forward (the year in progress has no 10-K yet).
        for _ in range(3):
            first = years[0]
            years.insert(0, FY(_add_year(first.start, -1), first.start - dt.timedelta(days=1), False))
        limit = (latest or years[-1].end) + dt.timedelta(days=200)
        cls._extend(years, limit)
        cal = cls(years)

        # A changed fiscal year end: 3-month periods after the last annual report that don't line up with the
        # old calendar. The latest one's own filing says which quarter it is (fp), which fixes the new year end.
        known = [y for y in years if y.known]
        if known:
            last = known[-1]
            odd = []
            for m in maps:
                for (s, e), r in m.items():
                    if s is None or e <= last.end or not (SPAN[1][0] <= (e - s).days <= SPAN[1][1]):
                        continue
                    loc = cal.locate(e)
                    if loc is None or loc[2] > MISALIGNED:
                        odd.append(r)
            k = None
            if odd:
                r = max(odd, key=lambda r: (r.e, r.first_filed))
                k = {"Q1": 1, "Q2": 2, "Q3": 3}.get(r.first_fp or "")
            if k:
                new_end = _month_end(r.e, (4 - k) * 3)
                anchor = _add_year(new_end, -1) + dt.timedelta(days=1)
                t_start = last.end + dt.timedelta(days=1)
                years = [y for y in years if y.end <= last.end]
                if anchor > t_start + dt.timedelta(days=20):
                    years.append(FY(t_start, anchor - dt.timedelta(days=1), False, transition=True))
                    years.append(FY(anchor, new_end, False))
                else:
                    years.append(FY(t_start, new_end, False, anchor=anchor))
                cls._extend(years, limit)
                cal = cls(years)
        return cal

    def locate(self, e: dt.date) -> tuple[int, int, float] | None:
        """(year index, quarter 1-4, misalignment in quarters) for a period ending on e."""
        best = None
        for i, y in enumerate(self.years):
            if e < y.start + dt.timedelta(days=25) or e > y.end + dt.timedelta(days=20):
                continue
            x = ((e - y.anchor).days + 1) / QDAYS
            if 0.5 <= x <= 4.6:
                k = min(4, max(1, round(x)))
                err = abs(x - k)
                if best is None or err < best[0]:
                    best = (err, i, k)
        return (best[1], best[2], best[0]) if best else None

    def number(self, filings: dict[str, tuple]) -> None:
        """Name each fiscal year (fy) from the fy the filings themselves report, using the most common offset
        among the latest 16 filings (some filers changed convention years ago; a few report a stale fy now
        and then, which the majority outvotes). A transition period takes the number after the year before it."""
        votes: Counter = Counter()
        recent = sorted(filings.items(), key=lambda kv: kv[1][2])[-16:]
        for accn, (fy, end, _filed) in recent:
            if not isinstance(fy, int):
                continue
            loc = self.locate(end)
            if loc is None or loc[2] > MISALIGNED:
                continue
            votes[fy - _label_year(self.years[loc[0]].end)] += 1
        off = votes.most_common(1)[0][0] if votes else 0
        for i, y in enumerate(self.years):
            y.num = self.years[i - 1].num + 1 if (y.transition and i) else _label_year(y.end) + off


# ------------------------------------------------------------------ building one company

def _round(v, nd=None):
    if v is None:
        return None
    if nd is None:
        return int(round(v))
    return round(v, nd)


def _pct(a, b):
    if a is None or b is None or b == 0:
        return None
    return round(a / b * 100, 1)


class Builder:
    def __init__(self, ticker: str, meta: dict, facts: Facts, name: str):
        self.ticker, self.meta, self.f, self.name = ticker, meta, facts, name
        industry = meta.get("industry") or ""
        self.kind = ("bank" if industry in BANK_INDUSTRIES else
                     "fin" if (meta.get("sector") in ("Financials", "Real Estate") or "REIT" in industry
                               or "Insurance" in industry) else "std")
        self.tax = self._pick_taxonomy()
        self.T = TAXONOMY[self.tax]
        self.cur = self._pick_currency()

    # -- which taxonomy and currency

    def _key_tags(self, tax):
        T = TAXONOMY[tax]
        tags = []
        for k in ("revenue", "revenue_fin", "revenue_bank", "net_income", "eps_diluted"):
            for s in T[k]:
                tags.extend(s[1:] if isinstance(s, tuple) else [s])
        return list(dict.fromkeys(tags))

    def _pick_taxonomy(self) -> str:
        best, best_end = "us-gaap", ""
        for tax in ("us-gaap", "ifrs-full"):
            end = ""
            for tag in self._key_tags(tax):
                for rows in self.f.units(tax, tag).values():
                    for r in rows:
                        if r.get("start") and (r.get("end") or "") > end:
                            end = r["end"]
            if end > best_end:
                best, best_end = tax, end
        return best

    def _pick_currency(self) -> str:
        cnt: Counter = Counter()
        rows_all = []
        for tag in self._key_tags(self.tax):
            for unit, rows in self.f.units(self.tax, tag).items():
                cur = unit.split("/")[0]
                if len(cur) == 3 and cur.isalpha() and cur.isupper():
                    rows_all.extend((r.get("filed") or "", cur) for r in rows)
        if not rows_all:
            return "USD"
        latest = max(f for f, _ in rows_all)
        cutoff = (_d(latest) - dt.timedelta(days=800)).isoformat() if latest else ""
        for filed, cur in rows_all:
            if filed >= cutoff:
                cnt[cur] += 1
        if not cnt:
            return "USD"
        top = cnt.most_common()
        if len(top) > 1 and top[0][1] == top[1][1] and "USD" in (top[0][0], top[1][0]):
            return "USD"
        return top[0][0]

    # -- period maps

    def money(self, key: str) -> dict[tuple, Rec]:
        return self.f.merged(self.tax, self.T[key], self.cur)

    def revenue_map(self) -> dict[tuple, Rec]:
        key = {"bank": "revenue_bank", "fin": "revenue_fin"}.get(self.kind, "revenue")
        m = dict(self.money(key))
        if self.tax == "us-gaap" and self.kind == "std":
            # The ASC 606 tag often covers only contract sales; the income statement's total ("total revenues":
            # Walmart's membership income, Exxon's equity-affiliate income, Caterpillar's financial products,
            # lessors' rent) is tagged "Revenues". That total is the headline, so it wins whenever it's larger.
            tot = self.f.periods(self.tax, "Revenues", self.cur)
            for k, r in list(m.items()):
                t = tot.get(k)
                if t is not None and r.tag != "Revenues" and r.val > 0 and t.val > r.val * 1.005:
                    m[k] = t
        return m

    def gross_profit_map(self, rev: dict) -> dict[tuple, Rec]:
        gp = dict(self.money("gross_profit"))
        if self.kind == "std":
            # Companies that don't print a gross-profit line: revenue minus cost of revenue for the same period.
            cost = self.money("cost_of_revenue")
            for k, c in cost.items():
                if k not in gp and k in rev:
                    r = rev[k]
                    g = Rec(r.s, r.e, r.val - c.val, max(r.filed, c.filed), r.form, "revenue-cost", r.accn,
                            r.first_fy, r.first_fp)
                    g.first_filed, g.first_form, g.first_accn = r.first_filed, r.first_form, r.first_accn
                    gp[k] = g
        return gp

    # -- quarter / year values

    def slotify(self, cal: Calendar, m: dict[tuple, Rec]):
        """Split a period map into 3-month values and year-to-date values by (year index, quarter)."""
        q3: dict[tuple, Rec] = {}
        cum: dict[tuple, Rec] = {}
        for (s, e), r in m.items():
            if s is None:
                continue
            d = (e - s).days
            loc = cal.locate(e)
            if loc is None or loc[2] > MISALIGNED:
                continue
            i, k, _ = loc
            loc = (i, k)
            if SPAN[1][0] <= d <= SPAN[1][1]:
                old = q3.get(loc)
                if old is None or r.filed > old.filed:
                    q3[loc] = r
            if abs((s - cal.years[i].start).days) <= 7 and SPAN_YTD[k][0] <= d <= SPAN_YTD[k][1]:
                old = cum.get(loc)
                if old is None or r.filed > old.filed:
                    cum[loc] = r
        return q3, cum

    @staticmethod
    def quarter_values(q3, cum, i: int, flow: bool = True):
        """Value of each quarter 1-4 of fiscal year i: direct 3-month facts, else year-to-date differences."""
        memo = {}

        def c(k):  # year-to-date through quarter k
            if k == 0:
                return 0.0
            if k in memo:
                return memo[k]
            v = None
            if (i, k) in cum:
                v = cum[(i, k)].val
            elif (i, k) in q3:
                p = c(k - 1)
                v = None if p is None else p + q3[(i, k)].val
            memo[k] = v
            return v

        out = {}
        for k in (1, 2, 3, 4):
            if (i, k) in q3:
                out[k] = (q3[(i, k)].val, False)
            elif flow:
                a, b = c(k), c(k - 1)
                out[k] = (a - b, True) if a is not None and b is not None else (None, False)
            elif k == 1 and (i, 1) in cum:  # a long (16-week) first quarter is its own year-to-date
                out[k] = (cum[(i, 1)].val, False)
            else:
                out[k] = (None, False)
        return out

    def build(self) -> dict:
        f = self.f
        f.detect_splits(self.tax, self.T["eps_diluted"], self.T["shares_diluted"], self.cur)
        rev = self.revenue_map()
        maps = {
            "revenue": rev,
            "gross_profit": self.gross_profit_map(rev),
            "operating_income": self.money("operating_income"),
            "net_income": self.money("net_income"),
            "eps_diluted": f.merged(self.tax, self.T["eps_diluted"], f"{self.cur}/shares"),
            "shares_diluted": f.merged(self.tax, self.T["shares_diluted"], "shares"),
            "ocf": self.money("ocf"),
            "capex": self.money("capex"),
        }
        if self.kind == "bank" and self.tax == "us-gaap":
            maps["gross_profit"] = {}
        key_maps = [maps["revenue"], maps["net_income"], maps["eps_diluted"], maps["ocf"]]
        latest = max((k[1] for m in key_maps for k in m if k[0] is not None), default=None)
        cal = Calendar.build(key_maps, latest)

        # Name the fiscal years from the filings' own fy, using each filing's period end.
        filings: dict[str, list] = {}
        for m in key_maps:
            for (s, e), r in m.items():
                if s is None or not (r.first_form in ANNUAL_FORMS or r.first_form.startswith("10-Q")):
                    continue
                # a filing's fy describes the filing, whose own period ends at the latest end it reports
                cur = filings.get(r.first_accn)
                if cur is None or e > cur[1]:
                    filings[r.first_accn] = [r.first_fy, e, r.first_filed]
        cal.number({k: tuple(v) for k, v in filings.items()})

        slots: dict[str, tuple] = {k: self.slotify(cal, m) for k, m in maps.items()}

        # A 3-month fourth quarter tagged with the full year's value (L3Harris's 10-K does this) is a tagging
        # error: drop it, and the quarter is derived as full year minus nine months like everyone else's.
        # Likewise a fourth-quarter revenue larger than the first nine months put together.
        for name, (q3, cum) in slots.items():
            for (i, k), r in list(q3.items()):
                y, c3 = cum.get((i, 4)), cum.get((i, 3))
                if k != 4 or c3 is None:
                    continue
                if ((y is not None and abs(r.val - y.val) <= 0.001 * abs(y.val) and abs(c3.val) > 0.01 * abs(y.val))
                        or (name == "revenue" and c3.val > 0 and r.val > c3.val)):
                    del q3[(i, k)]

        # ---- quarters
        n_years = len(cal.years)
        qvals: dict[tuple, dict] = {}
        for i in range(n_years):
            per_metric = {}
            for k, (q3, cum) in slots.items():
                per_metric[k] = self.quarter_values(q3, cum, i, flow=(k != "shares_diluted"))
            for q in (1, 2, 3, 4):
                row = {k: per_metric[k][q] for k in per_metric}
                if all(v is None for v, _ in row.values()):
                    continue
                qvals[(i, q)] = row

        # When a year was restated (discontinued operations), the 10-K's full year can be on the new basis while
        # the 9-month figure is still the old one, and full year minus nine months is meaningless. If any of the
        # year's revenue figures was restated and the derived Q4 is far from the year's other quarters, Q4's
        # continuing-operations lines (revenue, gross profit, operating income) are left unknown.
        rq3, rcum = slots["revenue"]
        for (i, q), row in qvals.items():
            v, derived = row["revenue"]
            if q != 4 or not derived or v is None:
                continue
            recs = [r for r in [rq3.get((i, j)) for j in (1, 2, 3)] + [rcum.get((i, j)) for j in (2, 3, 4)] if r]
            others = [qvals.get((i, j), {}).get("revenue", (None, False))[0] for j in (1, 2, 3)]
            if any(r.restated for r in recs) and all(o and o > 0 for o in others):
                mean = sum(others) / 3
                if not 0.4 * mean <= v <= 2.5 * mean:
                    for k in ("revenue", "gross_profit", "operating_income"):
                        row[k] = (None, False)

        # Q4 share counts and EPS are not additive, so they are rebuilt rather than subtracted.
        #   Shares: a year's weighted average is (in practice) the mean of its quarters' averages, so
        #   Q4 = 4 x year - (Q1 + Q2 + Q3); with uneven quarters (a 16-week Q1) the mean is day-weighted. In a loss
        #   quarter diluted shares equal basic shares, so basic counts are used.
        #   EPS: Q4 earnings for common holders over those Q4 shares. Full-year EPS minus Q1-Q3 EPS is the
        #   fallback, also used when the rebuild is more than 25% away from it. Tested on ~3,700 fiscal years whose
        #   10-K printed Q4 EPS, this hits the cent 70% of the time (89% within a cent) against 44% (77%) for
        #   the subtraction alone.
        q3e, cume = slots["eps_diluted"]
        numer = slots["eps_numerator"] = self.slotify(cal, f.merged(self.tax, self.T["eps_numerator"], self.cur))
        basic = self.slotify(cal, f.merged(self.tax, self.T["shares_basic"], "shares"))

        def q4_shares(i, share_slots):
            q3s, cums = share_slots
            yr = cums.get((i, 4))
            parts = [q3s.get((i, j)) or (cums.get((i, 1)) if j == 1 else None) for j in (1, 2, 3)]
            if yr is None or not all(parts):
                return None
            edges = [cal.years[i].start - dt.timedelta(days=1)] + [p.e for p in parts] + [yr.e]
            days = [(b - a).days for a, b in zip(edges, edges[1:])]
            if min(days) <= 0:
                return None
            if max(days) / min(days) > 1.2:
                v = ((yr.e - edges[0]).days * yr.val - sum(d * p.val for d, p in zip(days, parts))) / days[3]
            else:
                v = 4 * yr.val - sum(p.val for p in parts)
            return v if 0.8 * yr.val <= v <= 1.25 * yr.val and plausible(v) else None

        def numerator(i, q, row):
            n = self.quarter_values(*numer, i)[q][0]
            return row["net_income"][0] if n is None else n

        # Share counts must be on the right scale: a few filers tag them without it (McDonald's in millions,
        # Tempus in thousands). A quarter's count more than 2.5x away from the cover page's latest count is
        # dropped; without a cover-page count, the counts must agree with the reported EPS.
        dei = f.periods("dei", "EntityCommonStockSharesOutstanding", "shares")
        ref = dei[max(dei, key=lambda k: (k[1], dei[k].filed))].val if dei else None

        def plausible(v):
            return bool(v) and (ref is None or 0.4 * ref <= v <= 2.5 * ref)
        for row in qvals.values():
            if row["shares_diluted"][0] and not plausible(row["shares_diluted"][0]):
                row["shares_diluted"] = (None, False)
        ratios = sorted(numerator(i, q, row) / row["shares_diluted"][0] / row["eps_diluted"][0]
                        for (i, q), row in qvals.items()
                        if row["shares_diluted"][0] and row["eps_diluted"][0] and not row["eps_diluted"][1]
                        and abs(row["eps_diluted"][0]) >= 0.05 and numerator(i, q, row))
        shares_ok = not ratios or 0.5 <= ratios[len(ratios) // 2] <= 2
        if not shares_ok:
            for row in qvals.values():
                row["shares_diluted"] = (None, False)
        else:
            # ...and with the shares trusted, a reported EPS a world away from earnings / shares is a scale slip
            # in the EPS tag (Bloom Energy's Q3 2024: -60.0 for -$0.07).
            for (i, q), row in qvals.items():
                e, sh = row["eps_diluted"][0], row["shares_diluted"][0]
                n = numerator(i, q, row)
                if e is not None and sh and n is not None:
                    implied = n / sh
                    if abs(e - implied) > 0.10 and not (1 / 3 <= (e / implied if implied else 0) <= 3):
                        row["eps_diluted"] = (implied, True)

        for (i, q), row in qvals.items():
            if q != 4:
                continue
            n4 = numerator(i, 4, row)
            if (i, 4) not in slots["shares_diluted"][0] and shares_ok:
                sh = q4_shares(i, basic) if n4 is not None and n4 < 0 else None
                if sh is None:
                    sh = q4_shares(i, slots["shares_diluted"])
                row["shares_diluted"] = (sh, sh is not None)
            if (i, 4) in q3e:
                continue
            sh = row["shares_diluted"][0]
            by_ni = n4 / sh if sh and n4 is not None else None
            by_diff = None
            if (i, 4) in cume and all(qvals.get((i, j), {}).get("eps_diluted", (None,))[0] is not None
                                      for j in (1, 2, 3)):
                by_diff = cume[(i, 4)].val - sum(qvals[(i, j)]["eps_diluted"][0] for j in (1, 2, 3))
            if by_ni is not None and (by_diff is None or abs(by_ni - by_diff) <= 0.05 + 0.25 * abs(by_diff)):
                row["eps_diluted"] = (by_ni, True)
            else:  # no rebuild, or one far off (earnings for common holders aren't net income): subtract
                row["eps_diluted"] = (by_diff, by_diff is not None)
        # Some filers' EPS reaches companyfacts only with a share-class dimension (so not at all here). Where a
        # quarter has diluted shares but no EPS, EPS is earnings for common holders over diluted shares.
        for (i, q), row in qvals.items():
            if row["eps_diluted"][0] is None and row["shares_diluted"][0]:
                n = numerator(i, q, row)
                if n is not None:
                    row["eps_diluted"] = (n / row["shares_diluted"][0], True)

        def meta_for(i, q):
            """End date and the filing that first reported the quarter."""
            best, end3, endc = None, None, None
            for k in ("revenue", "net_income", "eps_diluted", "operating_income", "ocf"):
                q3, cum = slots[k]
                for r, is3 in ((q3.get((i, q)), True), (cum.get((i, q)), False)):
                    if r is None:
                        continue
                    if is3 and end3 is None:
                        end3 = r.e
                    if not is3 and endc is None:
                        endc = r.e
                    if best is None or (r.first_filed, r.first_accn) < (best.first_filed, best.first_accn):
                        best = r
            return end3 or endc, best

        rows = []
        for (i, q) in sorted(qvals):
            row = qvals[(i, q)]
            if all(row[k][0] is None for k in ("revenue", "net_income", "eps_diluted", "operating_income")):
                continue  # cash-flow-only slot
            end, first = meta_for(i, q)
            y = cal.years[i]
            ocf, capex = row["ocf"][0], row["capex"][0]
            capex = abs(capex) if capex is not None else None
            eps = row["eps_diluted"][0]
            eps_nd = 2 if row["eps_diluted"][1] else 4
            rows.append({
                "end": (end or y.end).isoformat(),
                "fy": y.num, "fp": f"Q{q}", "label": f"Q{q} FY{y.num % 100:02d}",
                "filed": first.first_filed if first else None,
                "form": first.first_form if first else None,
                "revenue": _round(row["revenue"][0]),
                "gross_profit": _round(row["gross_profit"][0]),
                "operating_income": _round(row["operating_income"][0]),
                "net_income": _round(row["net_income"][0]),
                "eps_diluted": _round(eps, eps_nd),
                "ocf": _round(ocf),
                "capex": _round(capex),
                "fcf": _round(ocf - capex) if ocf is not None and capex is not None else None,
                "shares_diluted": _round(row["shares_diluted"][0]),
            })
        rows.sort(key=lambda r: r["end"])
        if rows:
            # The window ends at the latest quarter or the latest fiscal year, whichever is later, so a foreign
            # filer whose quarterly XBRL stopped years ago doesn't show those old quarters as current.
            last_end = dt.date.fromisoformat(rows[-1]["end"])
            for i in range(n_years):
                for k in ("revenue", "net_income"):
                    r = slots[k][1].get((i, 4))
                    if r is not None and r.e > last_end:
                        last_end = r.e
            cutoff = (last_end - dt.timedelta(days=1046)).isoformat()  # 12 quarter ends span 11 gaps of ~91 days
            rows = [r for r in rows if r["end"] > cutoff][-N_QUARTERS:]
        quarters = rows

        def consecutive(rs):
            ends = [dt.date.fromisoformat(r["end"]) for r in rs]
            return all(75 <= (b - a).days <= 116 for a, b in zip(ends, ends[1:]))  # a 16-week Q1 is 112 days

        # ---- ttm
        ttm = None
        if len(quarters) >= 4 and consecutive(quarters[-4:]):
            last4 = quarters[-4:]

            def tsum(k, rs=last4, nd=None):
                vals = [r[k] for r in rs]
                if any(v is None for v in vals):
                    return None
                return round(sum(vals), nd) if nd else sum(vals)
            prev4 = quarters[-8:-4] if len(quarters) >= 8 and consecutive(quarters[-8:-3]) else None
            r_now = tsum("revenue")
            r_prev = tsum("revenue", prev4) if prev4 else None
            ttm = {
                "end": quarters[-1]["end"],
                "revenue": r_now,
                "revenue_growth_yoy_pct": (round((r_now / r_prev - 1) * 100, 1)
                                           if r_now is not None and r_prev and r_prev > 0 else None),
                "gross_margin_pct": _pct(tsum("gross_profit"), r_now) if r_now and r_now > 0 else None,
                "operating_margin_pct": _pct(tsum("operating_income"), r_now) if r_now and r_now > 0 else None,
                "net_margin_pct": _pct(tsum("net_income"), r_now) if r_now and r_now > 0 else None,
                "eps_diluted": tsum("eps_diluted", nd=2),
                "ocf": tsum("ocf"),
                "fcf": tsum("fcf"),
                "fcf_margin_pct": _pct(tsum("fcf"), r_now) if r_now and r_now > 0 else None,
            }

        # ---- annual
        annual = []
        for i, y in enumerate(cal.years):
            def yv(k):
                r = slots[k][1].get((i, 4))
                return r.val if r is not None else None
            vals = {k: yv(k) for k in ("revenue", "operating_income", "net_income", "eps_diluted", "ocf", "capex",
                                       "shares_diluted", "eps_numerator")}
            if vals["revenue"] is None and vals["net_income"] is None:
                continue
            if vals["eps_diluted"] is None and vals["shares_diluted"]:
                n = vals["eps_numerator"] if vals["eps_numerator"] is not None else vals["net_income"]
                if n is not None:
                    vals["eps_diluted"] = round(n / vals["shares_diluted"], 2)
            end = next((slots[k][1][(i, 4)].e for k in ("revenue", "net_income") if (i, 4) in slots[k][1]), y.end)
            capex = abs(vals["capex"]) if vals["capex"] is not None else None
            annual.append({
                "fy": y.num, "end": end.isoformat(),
                "revenue": _round(vals["revenue"]),
                "operating_income": _round(vals["operating_income"]),
                "net_income": _round(vals["net_income"]),
                "eps_diluted": _round(vals["eps_diluted"], 4),
                "fcf": _round(vals["ocf"] - capex) if vals["ocf"] is not None and capex is not None else None,
            })
        annual = annual[-N_YEARS:]

        return {
            "ticker": self.ticker,
            "cik": str(self.meta.get("cik") or "").zfill(10),
            "name": self.name,
            "currency": self.cur,
            "updated": now_et().date().isoformat(),
            "source": SOURCE,
            "quarters": quarters,
            "ttm": ttm,
            "annual": annual,
            "balance": self.balance(),
        }

    # -- balance sheet

    def balance(self) -> dict | None:
        f, cur = self.f, self.cur

        def inst(key, unit=cur):
            return {e: r for (s, e), r in f.merged(self.tax, self.T[key], unit).items() if s is None}
        equity, cash = inst("equity"), inst("cash")
        dates = sorted(set(equity) | set(cash))
        if not dates:
            return None
        as_of = dates[-1]

        def at(key, unit=cur):
            r = inst(key, unit).get(as_of)
            return r.val if r is not None else None
        total, noncur = at("debt_total"), at("debt_noncurrent")
        cur_ltd, cur_all, short = at("debt_current_ltd"), at("debt_current"), at("debt_short")
        if total is not None:
            debt = total + (short or 0)
        elif noncur is not None:
            debt = noncur + (cur_all if cur_all is not None else (cur_ltd or 0) + (short or 0))
        elif cur_all is not None or short is not None:
            debt = cur_all if cur_all is not None else short
        else:
            debt = None

        # Shares outstanding: the cover page's latest count (dei), else the balance sheet's.
        so = None
        dei = f.periods("dei", "EntityCommonStockSharesOutstanding", "shares")
        if dei:
            latest_e = max(e for (_, e) in dei)
            if latest_e >= as_of - dt.timedelta(days=120):
                same = [r for (s, e), r in dei.items() if e == latest_e]
                so = same[0].val
        if so is None:
            so = at("shares_out_bs", "shares")
        if so is None:
            # Multi-class filers tag share counts only per class, which companyfacts leaves out; their basic
            # weighted-average count for the latest quarter (all classes) is the nearest stand-in.
            wb = [r for (s, e), r in f.merged(self.tax, self.T["shares_basic"], "shares").items()
                  if s is not None and SPAN[1][0] <= (e - s).days <= SPAN[1][1] and e >= as_of - dt.timedelta(days=120)]
            if wb:
                so = max(wb, key=lambda r: r.e).val
        return {
            "as_of": as_of.isoformat(),
            "cash": _round(at("cash")),
            "debt": _round(debt),
            "equity": _round(at("equity")),
            "shares_outstanding": _round(so),
        }


# ------------------------------------------------------------------ public API

def out_path(ticker: str) -> Path:
    return OUT / f"{ticker.replace('.', '-')}.json"


def load(ticker: str) -> dict | None:
    """The fundamentals file for a ticker, or None when there isn't one. No network."""
    p = out_path(ticker)
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def build_one(ticker: str, meta: dict, companyfacts: list[dict]) -> dict:
    """Build the fundamentals dict from one or more companyfacts documents (current CIK first)."""
    facts = Facts([cf.get("facts") for cf in companyfacts])
    name = (companyfacts[0] or {}).get("entityName") or meta.get("legal_name") or meta.get("name")
    return Builder(ticker, meta, facts, name).build()


def status_of(d: dict) -> tuple[str, str]:
    q, ttm = d.get("quarters") or [], d.get("ttm")
    if not q and not d.get("annual") and not d.get("balance"):
        return "failed", "no data"
    why = []
    if len(q) < N_QUARTERS:
        why.append(f"{len(q)}q")
    if not ttm:
        why.append("no ttm")
    else:
        for k in ("revenue", "eps_diluted", "net_margin_pct"):
            if ttm.get(k) is None:
                why.append(f"no ttm {k}")
    if q:
        age = (now_et().date() - dt.date.fromisoformat(q[-1]["end"])).days
        if age > 200:
            why.append(f"stale {q[-1]['end']}")
    return ("partial", ", ".join(why)) if why else ("ok", "")


def update(ticker: str, meta: dict) -> tuple[str, str]:
    try:
        docs = [fetch_companyfacts(meta["cik"])]
        for pc in PREDECESSORS.get(ticker, []):
            try:
                docs.append(fetch_companyfacts(pc))
            except Exception as e:  # noqa: BLE001 - the current registrant alone is still worth writing
                print(f"  {ticker}: predecessor {pc} failed: {str(e)[:120]}", file=sys.stderr)
        d = build_one(ticker, meta, docs)
    except Exception as e:  # noqa: BLE001 - one bad company never stops the run
        return "failed", f"{type(e).__name__}: {str(e)[:160]}"
    st, why = status_of(d)
    if st != "failed":
        p = out_path(ticker)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")
    return st, why


def main(argv: list[str]) -> None:
    univ = {u["ticker"]: u for u in universe()}
    tickers = [t.upper() for t in argv] if argv else list(univ)
    tickers = [t if t in univ else t.replace("-", ".") for t in tickers]  # BRK-B -> BRK.B
    unknown = [t for t in tickers if t not in univ]
    tickers = [t for t in tickers if t in univ]
    started = time.monotonic()
    results: dict[str, tuple[str, str]] = {t: ("failed", "not in universe") for t in unknown}
    with ThreadPoolExecutor(WORKERS) as ex:
        for t, res in zip(tickers, ex.map(lambda t: update(t, univ[t]), tickers)):
            results[t] = res
            if len(argv) and len(argv) <= 20:
                print(f"  {t:6} {res[0]:7} {res[1]}")
    counts = Counter(s for s, _ in results.values())
    print(f"fundamentals: {counts['ok']} ok / {counts['partial']} partial / {counts['failed']} failed "
          f"of {len(results)} in {time.monotonic() - started:.0f}s -> {OUT.relative_to(DATA.parent)}/")
    if not argv or len(argv) > 20:
        for t, (s, why) in sorted(results.items()):
            if s == "partial":
                print(f"  partial {t:6} {why}")
    for t, (s, why) in sorted(results.items()):
        if s == "failed":
            print(f"  FAILED  {t:6} {why}")


if __name__ == "__main__":
    main(sys.argv[1:])
