"""Inline SVG charts in the Mostly Markets v2 style (docs/DESIGN.md, "Charts grammar").

Each chart renders twice, a desktop variant and a 360-wide phone variant, so labels stay legible; CSS shows one.
Charts that sit in a two-column grid use size="half" so their desktop text isn't shrunk. Colours come from CSS
custom properties, so charts follow the theme. Every point carries a tooltip (static/app.js)."""
from __future__ import annotations

import datetime as dt
import html
import itertools
import json
import math

SIZES = {"full": {"d": (680, 300, 12.5), "m": (360, 240, 11.5)},
         "wide": {"d": (740, 320, 12.5), "m": (360, 240, 11.5)},
         "half": {"d": (400, 250, 11.5), "m": (360, 240, 11.5)}}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_ids = itertools.count(1)


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def nice_ticks(lo: float, hi: float, n: int = 4) -> list[float]:
    if hi == lo:
        hi, lo = hi + 1, lo - 1
    span = hi - lo
    step = 10 ** math.floor(math.log10(span / n))
    for m in (1, 2, 2.5, 5, 10):
        if span / (step * m) <= n:
            step *= m
            break
    start = math.floor(lo / step) * step
    ticks = []
    v = start
    while v <= hi + step * 0.001:
        if v >= lo - step * 0.001:
            ticks.append(round(v, 10))
        v += step
    return ticks


def fmt(v: float, unit: str = "", digits: int | None = None) -> str:
    if v is None:
        return "–"
    neg = v < 0
    a = abs(v)
    if unit == "%":
        d = 1 if digits is None else digits
        s = f"{a:,.{d}f}%"
    elif unit == "$bn":
        d = (1 if a < 100 else 0) if digits is None else digits
        s = f"${a:,.{d}f}bn"
    elif unit == "$m":
        d = 0 if digits is None else digits
        s = f"${a:,.{d}f}m"
    elif unit == "$":
        d = (2 if a < 1000 else 0) if digits is None else digits
        s = f"${a:,.{d}f}"
    elif unit == "x":
        d = 1 if digits is None else digits
        s = f"{a:,.{d}f}x"
    else:
        d = (2 if a < 10 else 1 if a < 100 else 0) if digits is None else digits
        s = f"{a:,.{d}f}{unit}"
    return ("−" if neg else "") + s


def axis_fmt(v: float, unit: str, step: float) -> str:
    digits = 0 if step >= 1 else (1 if step >= 0.1 else 2)
    if unit == "$" and step >= 1:
        return f"${v:,.0f}"
    if unit == "$bn" and step >= 1:
        return f"${v:,.0f}bn"
    return fmt(v, unit, digits)


def figure(inner: str, title: str, subtitle: str = "", source: str = "", extra_head: str = "", cls: str = "") -> str:
    head = f'<figcaption><span class="ct">{esc(title)}</span>'
    if subtitle:
        head += f'<span class="cs">{esc(subtitle)}</span>'
    head += "</figcaption>"
    foot = f'<div class="csrc">{esc(source)}</div>' if source else ""
    return f'<figure class="chart{(" " + cls) if cls else ""}">{extra_head}{head}{inner}{foot}</figure>'


def both(render, size: str = "full") -> str:
    return "".join(render(k, *SIZES[size][k]) for k in ("d", "m"))


def human(d: str) -> str:
    x = dt.date.fromisoformat(d)
    return f"{x.day} {MONTHS[x.month - 1]} {x.year}"


def _src(spec):
    s = spec.get("source", "")
    return s if not s or s.lower().startswith("source") else f"Source: {s}"


def _tw(text: str, fs: float) -> float:
    return len(text) * fs * 0.6


# ------------------------------------------------------------------ line / area

def _date_ticks(dates: list[str], max_ticks: int) -> list[tuple[int, str]]:
    first, last = dt.date.fromisoformat(dates[0]), dt.date.fromisoformat(dates[-1])
    span = (last - first).days
    out = []
    if span <= 45:
        step = max(1, len(dates) // max_ticks)
        for i in range(0, len(dates), step):
            d = dt.date.fromisoformat(dates[i])
            out.append((i, f"{d.day} {MONTHS[d.month - 1]}"))
        return out[1:] if len(out) > 1 else out
    every = 1 if span <= 200 else 2 if span <= 400 else 12
    seen = set()
    for i, ds in enumerate(dates):
        d = dt.date.fromisoformat(ds)
        key = (d.year, d.month)
        if key in seen or i == 0:
            seen.add(key)
            continue
        seen.add(key)
        if every == 12:
            if d.month == 1:
                out.append((i, str(d.year)))
        elif (d.month - 1) % every == 0:
            out.append((i, str(d.year) if d.month == 1 else MONTHS[d.month - 1]))
    while len(out) > max_ticks:
        out = out[::2]
    return out


def line_svg(key: str, W: int, H: int, fs: float, dates: list[str], series: list[dict], unit: str,
             mark: str | None = None, area: bool = True, date_axis: bool = True, labels: list[str] | None = None,
             zero: bool = False, tone: str = "", avg: float | None = None, band: tuple | None = None,
             avg_label: str = "", notes: list | None = None) -> str:
    l, r, t, b = 4, (58 if key == "d" else 48), (16 + (fs * 1.6 if notes else 0)), 26
    pw, ph = W - l - r, H - t - b
    vals = [v for s in series for v in s["values"] if v is not None]
    extra = [x for x in ((band or ()) + ((avg,) if avg is not None else ())) if x is not None]
    lo, hi = min(vals + extra), max(vals + extra)
    if zero:
        lo = min(lo, 0)
    pad = (hi - lo) * 0.08 or abs(hi) * 0.05 or 1
    ticks = nice_ticks(lo - pad * 0.5, hi + pad * 0.5, 4 if key == "d" else 3)
    y0, y1 = min(ticks[0], lo), max(ticks[-1], hi)
    n = len(dates)
    gid = f"g{next(_ids)}"

    def X(i):
        return l + pw * (i / max(1, n - 1))

    def Y(v):
        return t + ph * (1 - (v - y0) / ((y1 - y0) or 1))
    parts = [f'<svg class="cv {key}{(" " + tone) if tone else ""}" viewBox="0 0 {W} {H}" role="img" '
             f'preserveAspectRatio="xMidYMid meet" style="--fs:{fs}px" data-g="{l},{l + pw}">']
    parts.append(f'<defs><linearGradient id="{gid}" x1="0" x2="0" y1="0" y2="1">'
                 f'<stop offset="0" stop-color="currentColor" stop-opacity=".22"/>'
                 f'<stop offset="1" stop-color="currentColor" stop-opacity="0"/></linearGradient></defs>')
    step = ticks[1] - ticks[0] if len(ticks) > 1 else 1
    s0v = series[0]["values"]
    y_last = Y([v for v in s0v if v is not None][-1])
    for tv in ticks:
        y = Y(tv)
        parts.append(f'<line class="g" x1="{l}" x2="{l + pw}" y1="{y:.1f}" y2="{y:.1f}"/>')
        if abs(y - y_last) > fs * 1.5:
            parts.append(f'<text x="{W - 2}" y="{y + fs * 0.35:.1f}" text-anchor="end">{esc(axis_fmt(tv, unit, step))}</text>')
    if band:
        parts.append(f'<rect class="band" x="{l}" y="{Y(band[1]):.1f}" width="{pw}" height="{max(0, Y(band[0]) - Y(band[1])):.1f}"/>')
    if avg is not None:
        ya = Y(avg)
        parts.append(f'<line class="avg" x1="{l}" x2="{l + pw}" y1="{ya:.1f}" y2="{ya:.1f}"/>')
        if avg_label:
            parts.append(f'<text class="avgl" x="{l + 6}" y="{ya - 6:.1f}">{esc(avg_label)}</text>')
    if date_axis:
        xt = _date_ticks(dates, 7 if key == "d" and W > 500 else 4)
    else:
        lab = labels or dates
        k = max(1, math.ceil(n / (7 if key == "d" else 4)))
        xt = [(i, lab[i]) for i in range(0, n, k)]
    for i, lab in xt:
        x = X(i)
        parts.append(f'<text x="{x:.1f}" y="{H - 6}" text-anchor="middle">{esc(lab)}</text>')
    colour = {"up": "var(--ch-up)", "down": "var(--ch-down)"}.get(tone, "var(--ch-line)")
    for si, s in enumerate(series):
        pts = [(X(i), Y(v)) for i, v in enumerate(s["values"]) if v is not None]
        if not pts:
            continue
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        if area and si == 0 and len(series) == 1:
            parts.append(f'<path d="{d} L{pts[-1][0]:.1f},{t + ph} L{pts[0][0]:.1f},{t + ph} Z" fill="url(#{gid})" '
                         f'style="color:{colour}"/>')
        parts.append(f'<path class="ln s{si}" d="{d}"/>')
        lx, ly = pts[-1]
        if len(series) > 1:
            parts.append(f'<text class="sl s{si}" x="{min(lx + 4, W - r + 4):.1f}" y="{ly - 6:.1f}">{esc(s["name"])}</text>')
    s0 = series[0]["values"]
    li = max(i for i, v in enumerate(s0) if v is not None)
    lx, ly = X(li), Y(s0[li])
    parts.append(f'<circle class="halo" cx="{lx:.1f}" cy="{ly:.1f}" r="{10 if key == "d" else 8}"/>'
                 f'<circle class="dot" cx="{lx:.1f}" cy="{ly:.1f}" r="{4.5 if key == "d" else 4}"/>')
    lab = fmt(s0[li], unit)
    tw = _tw(lab, fs) + 12
    parts.append(f'<g class="pill"><rect x="{W - tw:.1f}" y="{ly - fs * 0.9:.1f}" width="{tw:.1f}" height="{fs * 1.8:.1f}" rx="{fs * 0.9:.1f}"/>'
                 f'<text x="{W - 6:.1f}" y="{ly + fs * 0.36:.1f}" text-anchor="end">{esc(lab)}</text></g>')
    if mark and mark not in ("last",):
        idx = None
        if mark == "high":
            idx = max(range(n), key=lambda i: s0[i] if s0[i] is not None else -1e18)
        elif mark == "low":
            idx = min(range(n), key=lambda i: s0[i] if s0[i] is not None else 1e18)
        elif mark in dates:
            idx = dates.index(mark)
        if idx is not None and idx != li:
            mx, my = X(idx), Y(s0[idx])
            d = dt.date.fromisoformat(dates[idx]) if date_axis else None
            txt = (f"{d.day} {MONTHS[d.month - 1]}: " if d else "") + fmt(s0[idx], unit)
            anchor = "end" if mx > l + pw * 0.7 else "start"
            dx = -8 if anchor == "end" else 8
            ty = my - 10 if my > t + 20 else my + 18
            parts.append(f'<circle class="mk" cx="{mx:.1f}" cy="{my:.1f}" r="4"/>'
                         f'<text class="ml" x="{mx + dx:.1f}" y="{ty:.1f}" text-anchor="{anchor}">{esc(txt)}</text>')
    if notes:
        parts.append(_notes(notes, X, lambda i: Y(s0[i]) if s0[i] is not None else None, l, pw, t, ph, fs))
    parts.append(f'<g class="hv"><line class="hl" y1="{t}" y2="{t + ph}"/><circle class="hd" r="4.5"/></g>')
    parts.append("</svg>")
    return "".join(parts)


def _notes(notes, X, Yi, l, pw, t, ph, fs) -> str:
    """Event annotations: a dashed rule at each dated note, a ring on the line, and the label above the plot.
    Labels that would collide drop to a second row."""
    out, rows = [], [[], []]
    for idx, label in sorted(notes):
        x = X(idx)
        anchor = "end" if x > l + pw * 0.62 else "start"
        w = _tw(label, fs * 0.95) + 10
        x0, x1 = (x - w, x) if anchor == "end" else (x, x + w)
        row = 0 if all(x1 < a or x0 > b for a, b in rows[0]) else 1
        rows[row].append((x0, x1))
        ty = t - fs * 0.55 - (0 if row == 0 else -fs * 1.25)
        out.append(f'<line class="nt-l" x1="{x:.1f}" x2="{x:.1f}" y1="{ty + 3:.1f}" y2="{t + ph}"/>')
        y = Yi(idx)
        if y is not None:
            out.append(f'<circle class="nt-d" cx="{x:.1f}" cy="{y:.1f}" r="4.5"/>')
        dx = -5 if anchor == "end" else 5
        out.append(f'<text class="nt-t" x="{x + dx:.1f}" y="{ty:.1f}" text-anchor="{anchor}">{esc(label)}</text>')
    return "".join(out)


def hover_data(dates: list[str], values: list[float], unit: str) -> str:
    return esc(json.dumps({"d": dates, "v": [round(v, 2) if v is not None else None for v in values], "u": unit},
                          separators=(",", ":")))


RANGE_LABEL = {"1m": "1 month", "3m": "3 months", "6m": "6 months", "1y": "1 year", "5y": "5 years", "ytd": "the year to date"}


def price_chart(bars: list[dict], rng: str, end: str | None, title: str, subtitle: str = "",
                mark: str | None = "last", cls: str = "", size: str = "full", notes: list | None = None) -> str:
    if end:
        bars = [b for b in bars if b["date"] <= end]
    if not bars:
        return ""
    last = dt.date.fromisoformat(bars[-1]["date"])
    start = {"1m": last - dt.timedelta(days=31), "3m": last - dt.timedelta(days=92),
             "6m": last - dt.timedelta(days=183), "1y": last - dt.timedelta(days=366),
             "5y": last - dt.timedelta(days=366 * 5 + 2), "ytd": dt.date(last.year - 1, 12, 31)}.get(rng, last - dt.timedelta(days=366))
    sel = [b for b in bars if b["date"] >= start.isoformat()]
    if rng == "5y":
        sel = sel[::5] + ([sel[-1]] if (len(sel) - 1) % 5 else [])
    dates = [b["date"] for b in sel]
    vals = [b["close"] for b in sel]
    chg = (vals[-1] / vals[0] - 1) * 100 if vals[0] else 0
    tone = "up" if chg >= 0 else "down"
    head = f'<span class="crng {tone}">{"▲" if chg >= 0 else "▼"} {abs(chg):.1f}% over {RANGE_LABEL.get(rng, rng)}</span>'
    nts = _note_idx(dates, notes)
    inner = both(lambda k, W, H, fs: line_svg(k, W, H, fs, dates, [{"name": "", "values": vals}], "$", mark=mark, tone=tone,
                                              notes=nts), size)
    return (f'<div class="hov" data-h="{hover_data(dates, vals, "$")}">' +
            figure(inner, title, subtitle or f"Daily close, $, to {human(dates[-1])}", "Source: Nasdaq daily closes", head, cls)
            + "</div>")


def _note_idx(dates: list[str], notes) -> list:
    """[{date, label}] -> [(index, label)] at the first trading day on or after each date."""
    out = []
    for n in notes or []:
        i = next((j for j, d in enumerate(dates) if d >= str(n.get("date", ""))), None)
        if i is not None and n.get("label"):
            out.append((i, str(n["label"])))
    return out


def line_chart(spec: dict) -> str:
    x = spec["x"]
    series = spec["series"]
    unit = spec.get("unit", "")
    is_dates = all(len(str(v)) == 10 and str(v)[4] == "-" for v in x)
    inner = both(lambda k, W, H, fs: line_svg(k, W, H, fs, [str(v) for v in x], series, unit, mark=spec.get("mark"),
                                              area=len(series) == 1, date_axis=is_dates, labels=[str(v) for v in x],
                                              zero=spec.get("zero", False), tone=spec.get("tone", "")),
                 spec.get("size", "full"))
    hov = f' data-h="{hover_data([str(v) for v in x], series[0]["values"], unit)}"' if len(series) == 1 else ""
    return f'<div class="hov"{hov}>' + figure(inner, spec["title"], spec.get("subtitle", ""), _src(spec)) + "</div>"


def pe_history_chart(dates: list[str], pes: list[float], title: str, subtitle: str, source: str, size: str = "half") -> str:
    """P/E over time against its own average and a ±1 standard deviation band."""
    vals = [v for v in pes if v is not None]
    avg = sum(vals) / len(vals)
    sd = (sum((v - avg) ** 2 for v in vals) / len(vals)) ** 0.5
    band = (max(0.0, avg - sd), avg + sd)
    inner = both(lambda k, W, H, fs: line_svg(k, W, H, fs, dates, [{"name": "", "values": pes}], "x", area=False,
                                              avg=avg, band=band, avg_label=f"Average {avg:.1f}x"), size)
    legend = ('<div class="clg"><span><i style="background:var(--ch-line)"></i>P/E</span>'
              '<span><i style="background:var(--accent);opacity:.25"></i>Usual range (±1 s.d.)</span></div>')
    return f'<div class="hov" data-h="{hover_data(dates, pes, "x")}">' + figure(legend + inner, title, subtitle, source) + "</div>"


# ------------------------------------------------------------------ bars

def _bar_path(x, y, w, h, r, up=True):
    r = min(r, w / 2, h)
    if h <= 0.5:
        return f"M{x:.1f},{y:.1f}h{w:.1f}"
    if up:
        return (f"M{x:.1f},{y + h:.1f}V{y + r:.1f}Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f}H{x + w - r:.1f}"
                f"Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f}V{y + h:.1f}Z")
    return (f"M{x:.1f},{y:.1f}V{y + h - r:.1f}Q{x:.1f},{y + h:.1f} {x + r:.1f},{y + h:.1f}H{x + w - r:.1f}"
            f"Q{x + w:.1f},{y + h:.1f} {x + w:.1f},{y + h - r:.1f}V{y:.1f}Z")


def bars_svg(key, W, H, fs, labels, values, unit, compare=None, highlight=-1, tone="", tips=None):
    l, r, t, b = 4, (50 if key == "d" else 44), 22, 26
    pw, ph = W - l - r, H - t - b
    allv = [v for v in values if v is not None] + [v for v in (compare or []) if v is not None]
    hi = max(allv + [0])
    lo = min(allv + [0])
    ticks = nice_ticks(lo, hi, 4 if key == "d" else 3)
    y0, y1 = min(ticks[0], lo), max(ticks[-1], hi)
    n = len(values)
    gap = 0.3 if n > 6 else 0.4
    slot = pw / n
    bw = slot * (1 - gap)

    def Y(v):
        return t + ph * (1 - (v - y0) / ((y1 - y0) or 1))
    hl = (highlight % n) if highlight is not None else None
    out = [f'<svg class="cv {key}" viewBox="0 0 {W} {H}" role="img" style="--fs:{fs}px">']
    step = ticks[1] - ticks[0] if len(ticks) > 1 else 1
    for tv in ticks:
        y = Y(tv)
        out.append(f'<line class="{"g0" if tv == 0 else "g"}" x1="{l}" x2="{l + pw}" y1="{y:.1f}" y2="{y:.1f}"/>')
        out.append(f'<text x="{W - 2}" y="{y + fs * 0.35:.1f}" text-anchor="end">{esc(axis_fmt(tv, unit, step))}</text>')
    if 0 not in ticks:
        out.append(f'<line class="g0" x1="{l}" x2="{l + pw}" y1="{Y(0):.1f}" y2="{Y(0):.1f}"/>')
    every = 1 if slot >= fs * 4.2 else 2
    rad = min(5, bw / 4)
    for i, v in enumerate(values):
        x = l + slot * i + slot * gap / 2
        if v is None:
            continue
        top, bot = Y(max(v, 0)), Y(min(v, 0))
        on = i == hl
        if tone == "sign":
            c = ("bph" if on else "bp") if v >= 0 else ("bnh" if on else "bn")
        else:
            c = "bh" if on else ("bn" if v < 0 else "b")
        tip = (tips[i] if tips else f"{labels[i]}: {fmt(v, unit)}")
        out.append(f'<g class="bar" data-tip="{esc(tip)}"><rect class="hit" x="{l + slot * i:.1f}" y="{t}" width="{slot:.1f}" height="{ph}"/>'
                   f'<path class="{c}" d="{_bar_path(x, top, bw, max(1.0, bot - top), rad, v >= 0)}"/></g>')
        if compare and i < len(compare) and compare[i] is not None:
            cy = Y(compare[i])
            out.append(f'<line class="est" x1="{x - 2:.1f}" x2="{x + bw + 2:.1f}" y1="{cy:.1f}" y2="{cy:.1f}"/>')
        if on:
            vy = (top - 7) if v >= 0 else (bot + fs + 3)
            out.append(f'<text class="bv on" x="{x + bw / 2:.1f}" y="{vy:.1f}" text-anchor="middle">{esc(fmt(v, unit))}</text>')
        if i % every == 0 or on or i == n - 1:
            if every == 2 and i == n - 2:
                continue
            out.append(f'<text x="{x + bw / 2:.1f}" y="{H - 6}" text-anchor="middle">{esc(labels[i])}</text>')
    out.append("</svg>")
    return "".join(out)


def bars_chart(spec: dict) -> str:
    labels, values = spec["labels"], spec["values"]
    unit = spec.get("unit", "")
    comp = spec.get("compare")
    legend = ""
    if comp:
        legend = (f'<div class="clg"><span><i style="background:var(--accent)"></i>{esc(spec.get("label", "Actual"))}</span>'
                  f'<span><i style="background:var(--ink);height:2px;border-radius:0"></i>{esc(spec.get("compare_label", "Estimate"))}</span></div>')
    inner = both(lambda k, W, H, fs: bars_svg(k, W, H, fs, labels, values, unit, comp, spec.get("highlight", -1),
                                              spec.get("tone", ""), spec.get("tips")), spec.get("size", "full"))
    return figure(legend + inner, spec["title"], spec.get("subtitle", ""), _src(spec))


def hbars_svg(key, W, H_unused, fs, labels, values, unit, highlight=None, median=None, median_label="", neutral=False):
    n = len(values)
    row = fs * 2.5
    t, b = 6, (fs * 2.2 if median is not None else 6)
    H = int(t + b + row * n)
    lab_w = max(_tw(str(x), fs) for x in labels) + 12
    lab_w = min(lab_w, W * 0.42)
    vals = [v for v in values if v is not None]
    val_w = max(fs * 4.8, max([_tw(("+" if v > 0 else "") + fmt(v, unit), fs) for v in vals] or [0]) + 12)
    mx = max([abs(v) for v in vals] + ([abs(median)] if median is not None else [])) or 1
    has_neg = any(v < 0 for v in vals)
    has_pos = any(v > 0 for v in vals)
    pw = W - lab_w - val_w * (2 if has_neg and has_pos else 1)
    if has_neg and has_pos:
        span = max(vals) - min(vals)
        zero_x, scale = lab_w + val_w + pw * (-min(vals) / span), pw / span
    elif has_neg:
        zero_x, scale = lab_w + val_w + pw, pw / mx
    else:
        zero_x, scale = lab_w, pw / mx
    out = [f'<svg class="cv {key}" viewBox="0 0 {W} {H}" role="img" style="--fs:{fs}px">']
    out.append(f'<line class="g0" x1="{zero_x:.1f}" x2="{zero_x:.1f}" y1="{t}" y2="{t + row * n}"/>')
    for i, (lab, v) in enumerate(zip(labels, values)):
        y = t + row * i
        bh = row * 0.56
        cy = y + row / 2
        on = i == highlight
        out.append(f'<text class="hl1{" on" if on else ""}" x="0" y="{cy + fs * 0.35:.1f}">{esc(lab)}</text>')
        if v is None:
            out.append(f'<text class="hv1 nt" x="{zero_x + 6:.1f}" y="{cy + fs * 0.35:.1f}">n/a</text>')
            continue
        w = max(abs(v) * scale, 1.5)
        x = zero_x if v >= 0 else zero_x - w
        cls = "bs" if on else ("b" if neutral else ("bu" if v >= 0 else "bd"))
        out.append(f'<g class="bar" data-tip="{esc(lab)}: {esc(fmt(v, unit))}"><rect class="hit" x="0" y="{y:.1f}" width="{W}" height="{row:.1f}"/>'
                   f'<rect class="{cls}" x="{x:.1f}" y="{cy - bh / 2:.1f}" width="{w:.1f}" height="{bh:.1f}" rx="{min(4, bh / 3):.1f}"/></g>')
        tx = x + w + 6 if v >= 0 else x - 6
        anchor = "start" if v >= 0 else "end"
        sign = "+" if v > 0 and not neutral else ""
        vc = "on" if on else ("nt" if neutral else ("up" if v >= 0 else "down"))
        out.append(f'<text class="hv1 {vc}" x="{tx:.1f}" y="{cy + fs * 0.35:.1f}" text-anchor="{anchor}">{sign}{esc(fmt(v, unit))}</text>')
    if median is not None:
        mxp = zero_x + median * scale
        out.append(f'<line class="med" x1="{mxp:.1f}" x2="{mxp:.1f}" y1="{t - 2}" y2="{t + row * n + 4:.1f}"/>')
        out.append(f'<text class="medl" x="{mxp:.1f}" y="{H - 4:.1f}" text-anchor="middle">{esc(median_label)}</text>')
    out.append("</svg>")
    return "".join(out)


def hbars_chart(spec: dict) -> str:
    inner = both(lambda k, W, H, fs: hbars_svg(k, W, H, fs, spec["labels"], spec["values"], spec.get("unit", ""),
                                               spec.get("highlight"), spec.get("median"), spec.get("median_label", ""),
                                               spec.get("neutral", False)), spec.get("size", "full"))
    return figure(inner, spec["title"], spec.get("subtitle", ""), _src(spec))


# ------------------------------------------------------------------ quality vs price quadrant

def declutter(pts: list[dict], min_d: float = 0.17, iters: int = 60) -> None:
    """Push points apart (in −1…+1 space) so logos don't overlap at rest. The stock itself moves least."""
    for _ in range(iters):
        moved = False
        for a, b in itertools.combinations(pts, 2):
            dx, dy = b["px"] - a["px"], b["py"] - a["py"]
            d = math.hypot(dx, dy)
            if d >= min_d:
                continue
            if d < 1e-6:
                dx, dy, d = 0.01, 0.013, 0.0164
            push = (min_d - d) / 2
            ux, uy = dx / d, dy / d
            wa = 0.25 if a.get("me") else 1.0
            wb = 0.25 if b.get("me") else 1.0
            a["px"] -= ux * push * wa
            a["py"] -= uy * push * wa
            b["px"] += ux * push * wb
            b["py"] += uy * push * wb
            moved = True
        for p in pts:
            p["px"] = max(-0.76, min(0.76, p["px"]))
            p["py"] = max(-0.74, min(0.74, p["py"]))
        if not moved:
            break


def quadrant(points: list[dict], left: str, right: str, top: str = "Stronger business", bottom: str = "Weaker business") -> str:
    """points: {t, x, y, me, url, logo, tip}. x = value score (+ cheaper), y = quality score (+ stronger), both −1…+1."""
    for p in points:
        p["px"], p["py"] = max(-0.76, min(0.76, p["x"])), max(-0.74, min(0.74, p["y"]))
    declutter(points, 0.2)
    bg = ('<svg class="bgq" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><defs>'
          '<radialGradient id="qg" cx="100%" cy="0%" r="75%"><stop offset="0" style="stop-color:var(--ch-up);stop-opacity:.20"/>'
          '<stop offset="1" style="stop-color:var(--ch-up);stop-opacity:0"/></radialGradient>'
          '<radialGradient id="qr" cx="0%" cy="100%" r="75%"><stop offset="0" style="stop-color:var(--ch-down);stop-opacity:.16"/>'
          '<stop offset="1" style="stop-color:var(--ch-down);stop-opacity:0"/></radialGradient></defs>'
          '<rect width="100" height="100" fill="url(#qr)"/><rect width="100" height="100" fill="url(#qg)"/></svg>')
    pts = []
    for p in sorted(points, key=lambda p: p.get("me", False)):
        left_pc = 50 + p["px"] * 50
        top_pc = 50 - p["py"] * 50
        tag = "div" if p.get("me") or not p.get("url") else "a"
        href = f' href="{esc(p["url"])}"' if tag == "a" else ""
        pts.append(f'<{tag} class="pt{" me" if p.get("me") else ""}"{href} style="left:{left_pc:.1f}%;top:{top_pc:.1f}%" '
                   f'data-tip="{esc(p.get("tip", p["t"]))}" aria-label="{esc(p.get("tip", p["t"]))}">{p["logo"]}<i class="lab">{esc(p["t"])}</i></{tag}>')
    return (f'<div class="quad" role="img" aria-label="Business quality against valuation, compared with peers">{bg}'
            f'<div class="cross-h"></div><div class="cross-v"></div>'
            f'<span class="ax t">{esc(top)} ↑</span><span class="ax b">↓ {esc(bottom)}</span>'
            f'<span class="ax l">← {esc(left)}</span><span class="ax r">{esc(right)} →</span>'
            f'<span class="cn tl">Stronger, pricier</span><span class="cn tr">Stronger, cheaper</span>'
            f'<span class="cn bl">Weaker, pricier</span><span class="cn br">Weaker, cheaper</span>'
            f'{"".join(pts)}</div>')


# ------------------------------------------------------------------ sparkline (cards, tables)

def spark(values: list[float], w: int = 96, h: int = 28) -> str:
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    pts = [(w * i / (len(vals) - 1), h - 2 - (h - 4) * ((v - lo) / ((hi - lo) or 1))) for i, v in enumerate(vals)]
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    tone = "up" if vals[-1] >= vals[0] else "down"
    return (f'<svg class="spk {tone}" viewBox="0 0 {w} {h}" preserveAspectRatio="none" width="{w}" height="{h}" aria-hidden="true">'
            f'<path d="{d}" vector-effect="non-scaling-stroke"/></svg>')


# ------------------------------------------------------------------ compare (rebased % change, several lines)

def _spread(ys: list[float], gap: float, lo: float, hi: float) -> list[float]:
    """Nudge end labels apart vertically, keeping their order and staying inside lo..hi."""
    order = sorted(range(len(ys)), key=lambda i: ys[i])
    out = list(ys)
    for _ in range(40):
        moved = False
        for a, b in zip(order, order[1:]):
            if out[b] - out[a] < gap:
                mid = (out[a] + out[b]) / 2
                out[a], out[b] = mid - gap / 2, mid + gap / 2
                moved = True
        for i in order:
            out[i] = min(hi, max(lo, out[i]))
        if not moved:
            break
    return out


def compare_svg(key, W, H, fs, dates, series, highlight=None) -> str:
    labs = [f"{s['name']} {'+' if s['values'][-1] >= 0 else '−'}{abs(s['values'][-1]):.1f}%" for s in series]
    l, t, b = 4, 14, 26
    r = max(_tw(x, fs) for x in labs) + 18
    pw, ph = W - l - r, H - t - b
    vals = [v for s in series for v in s["values"] if v is not None] + [0]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.06 or 1
    ticks = nice_ticks(lo - pad, hi + pad, 4 if key == "d" else 3)
    y0, y1 = min(ticks[0], lo), max(ticks[-1], hi)
    n = len(dates)

    def X(i):
        return l + pw * (i / max(1, n - 1))

    def Y(v):
        return t + ph * (1 - (v - y0) / ((y1 - y0) or 1))
    step = ticks[1] - ticks[0] if len(ticks) > 1 else 1
    out = [f'<svg class="cv {key}" viewBox="0 0 {W} {H}" role="img" style="--fs:{fs}px">']
    for tv in ticks:
        y = Y(tv)
        out.append(f'<line class="{"g0" if abs(tv) < 1e-9 else "g"}" x1="{l}" x2="{l + pw}" y1="{y:.1f}" y2="{y:.1f}"/>')
        out.append(f'<text x="{l + 2}" y="{y - 4:.1f}">{esc(axis_fmt(tv, "%", step))}</text>')
    for i, lab in _date_ticks(dates, 6 if key == "d" else 3):
        out.append(f'<text x="{X(i):.1f}" y="{H - 6}" text-anchor="middle">{esc(lab)}</text>')
    hl = highlight if highlight is not None else None
    order = [i for i in range(len(series)) if i != hl] + ([hl] if hl is not None else [])
    ends = []
    for si in order:
        s = series[si]
        pts = [(X(i), Y(v)) for i, v in enumerate(s["values"]) if v is not None]
        cls = f"s{si}" if hl is None else ("s0 on" if si == hl else "q")
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        out.append(f'<path class="ln {cls}" d="{d}"/>')
        out.append(f'<circle class="ed {cls}" cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="3.5"/>')
        ends.append((si, pts[-1][1], cls))
    ys = _spread([e[1] for e in ends], fs * 1.35, t + fs * 0.5, t + ph)
    for (si, _, cls), y in zip(ends, ys):
        out.append(f'<text class="sl {cls}" x="{l + pw + 8:.1f}" y="{y + fs * 0.35:.1f}">{esc(labs[si])}</text>')
    out.append("</svg>")
    return "".join(out)


def compare_chart(dates: list[str], series: list[dict], title: str, subtitle: str, source: str = "Source: Nasdaq daily closes",
                  highlight=None, size: str = "full") -> str:
    inner = both(lambda k, W, H, fs: compare_svg(k, W, H, fs, dates, series, highlight), size)
    return figure(inner, title, subtitle, source)


# ------------------------------------------------------------------ market map (squarified treemap)

def _worst(row, side):
    s = sum(row)
    return max(max(side * side * r / (s * s), (s * s) / (side * side * r)) for r in row)


def squarify(vals: list[float], x: float, y: float, w: float, h: float) -> list[tuple]:
    """Bruls et al. squarified layout. vals sorted descending and summing to w*h."""
    rects, vals = [], list(vals)
    while vals:
        if w <= 0 or h <= 0:
            rects += [(x, y, 0, 0)] * len(vals)
            break
        side = min(w, h)
        row, i = [vals[0]], 1
        while i < len(vals) and _worst(row + [vals[i]], side) <= _worst(row, side):
            row.append(vals[i])
            i += 1
        s = sum(row)
        if w >= h:
            rw, yy = s / h, y
            for v in row:
                rects.append((x, yy, rw, v / rw))
                yy += v / rw
            x, w = x + rw, w - rw
        else:
            rh, xx = s / w, x
            for v in row:
                rects.append((xx, y, v / rh, rh))
                xx += v / rh
            y, h = y + rh, h - rh
        vals = vals[i:]
    return rects


SHORT_SECTOR = {"Information Technology": "Tech", "Communication Services": "Communication", "Consumer Discretionary": "Discretionary",
                "Consumer Staples": "Staples", "Health Care": "Health care", "Real Estate": "Real estate"}

HEAT = [(-3, (246, 53, 56)), (-2, (191, 64, 69)), (-1, (139, 68, 78)), (0, (65, 69, 84)),
        (1, (53, 118, 78)), (2, (47, 158, 79)), (3, (48, 204, 90))]


def heat(v: float, scale: float = 3.0) -> str:
    x = max(-3.0, min(3.0, v * 3.0 / scale))
    for (a, ca), (b, cb) in zip(HEAT, HEAT[1:]):
        if x <= b:
            f = (x - a) / (b - a)
            return "#%02x%02x%02x" % tuple(round(ca[k] + (cb[k] - ca[k]) * f) for k in range(3))
    return "#30cc5a"


def treemap_svg(key, W, H, fs, groups, scale=3.0) -> str:
    groups = [g for g in groups if g["items"]]
    tot = sum(i["w"] for g in groups for i in g["items"]) or 1
    gs = sorted(groups, key=lambda g: -sum(i["w"] for i in g["items"]))
    grects = squarify([sum(i["w"] for i in g["items"]) / tot * W * H for g in gs], 0, 0, W, H)
    head = fs * 1.45
    out = [f'<svg class="cv tm {key}" viewBox="0 0 {W} {H}" role="img" style="--fs:{fs}px">']
    for g, (gx, gy, gw, gh) in zip(gs, grects):
        show_head = gw > fs * 5 and gh > head * 2.6
        ix, iy, iw, ih = gx + 1, gy + (head if show_head else 1), gw - 2, gh - (head if show_head else 1) - 1
        items = sorted(g["items"], key=lambda i: -i["w"])
        gt = sum(i["w"] for i in items) or 1
        if show_head:
            name = SHORT_SECTOR.get(g["name"], g["name"])
            name = name if _tw(name.upper(), fs * 0.82) < gw - 8 else ""
            out.append(f'<text class="tmh" x="{gx + 4:.1f}" y="{gy + head * 0.72:.1f}">{esc(name.upper())}</text>')
        for it, (x, y, w, h) in zip(items, squarify([i["w"] / gt * iw * ih for i in items], ix, iy, iw, ih)):
            if w < 0.5 or h < 0.5:
                continue
            tip = f'{it["t"]} · {it.get("name", "")}: {"+" if it["v"] >= 0 else "−"}{abs(it["v"]):.2f}%'
            out.append(f'<g class="tile" data-tip="{esc(tip)}"><rect x="{x + .5:.1f}" y="{y + .5:.1f}" width="{max(0, w - 1):.1f}" '
                       f'height="{max(0, h - 1):.1f}" fill="{heat(it["v"], scale)}"/>')
            tsz = min(fs * 2.4, w / (len(it["t"]) * 0.68 + 0.6), h / 2.5)
            if tsz >= fs * 0.78:
                cy = y + h / 2
                two = h >= tsz * 2.5
                out.append(f'<text class="tmt" x="{x + w / 2:.1f}" y="{cy + (-tsz * 0.12 if two else tsz * 0.35):.1f}" '
                           f'text-anchor="middle" style="font-size:{tsz:.1f}px">{esc(it["t"])}</text>')
                if two:
                    vs = max(fs * 0.72, tsz * 0.62)
                    out.append(f'<text class="tmv" x="{x + w / 2:.1f}" y="{cy + tsz * 0.95:.1f}" text-anchor="middle" '
                               f'style="font-size:{vs:.1f}px">{"+" if it["v"] >= 0 else "−"}{abs(it["v"]):.1f}%</text>')
            out.append("</g>")
    out.append("</svg>")
    return "".join(out)


def treemap_chart(groups, title, subtitle, source, scale=3.0) -> str:
    sizes = {"d": (680, 440, 12.5), "m": (360, 500, 11.5)}
    inner = "".join(treemap_svg(k, *sizes[k], groups, scale) for k in ("d", "m"))
    stops = "".join(f'<i style="background:{heat(v, 3)}"><b>{"+" if v > 0 else "−" if v < 0 else ""}{abs(v * scale / 3):g}%</b></i>'
                    for v in (-3, -2, -1, 0, 1, 2, 3))
    legend = f'<div class="tml">{stops}</div>'
    return figure(inner + legend, title, subtitle, source, cls="tmap")


# ------------------------------------------------------------------ big numbers

def stat_cards(items: list[dict]) -> str:
    """items: {value, label, note, tone (up/down/''), logo (html), spark (svg)}."""
    cells = []
    for it in items:
        tone = it.get("tone", "")
        note = f'<span class="nt">{esc(it["note"])}</span>' if it.get("note") else ""
        cells.append(f'<div class="sb {tone}"><span class="l">{it.get("logo", "")}{esc(it.get("label", ""))}</span>'
                     f'<b class="v">{esc(it["value"])}</b>{note}{it.get("spark", "")}</div>')
    return f'<div class="bigstats n{min(len(items), 3)}">{"".join(cells)}</div>'
