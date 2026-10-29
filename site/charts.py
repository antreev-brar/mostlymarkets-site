"""Inline SVG charts in the Mostly Markets style. Each chart renders twice (desktop 680 wide, phone 360 wide) so
labels stay legible; CSS shows one. Colours come from CSS custom properties, so charts follow the theme."""
from __future__ import annotations

import datetime as dt
import html
import json
import math

SIZES = {"d": (680, 300, 13), "m": (360, 230, 11.5)}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


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
    elif unit == "$":
        d = (2 if a < 1000 else 0) if digits is None else digits
        s = f"${a:,.{d}f}"
    elif unit == "x":
        s = f"{a:,.1f}x"
    else:
        d = (2 if a < 10 else 1 if a < 100 else 0) if digits is None else digits
        s = f"{a:,.{d}f}{unit}"
    return ("−" if neg else "") + s


def axis_fmt(v: float, unit: str, step: float) -> str:
    digits = 0 if step >= 1 else (1 if step >= 0.1 else 2)
    if unit == "$" and step >= 1:
        return f"${v:,.0f}"
    return fmt(v, unit, digits)


def figure(inner: str, title: str, subtitle: str = "", source: str = "", extra_head: str = "", cls: str = "") -> str:
    head = f'<figcaption><span class="ct">{esc(title)}</span>'
    if subtitle:
        head += f'<span class="cs">{esc(subtitle)}</span>'
    head += "</figcaption>"
    foot = f'<div class="csrc">{esc(source)}</div>' if source else ""
    return f'<figure class="chart {cls}">{extra_head}{head}{inner}{foot}</figure>'


def both(render) -> str:
    return "".join(render(k, *SIZES[k]) for k in ("d", "m"))


# ------------------------------------------------------------------ price / line

def _date_ticks(dates: list[str], max_ticks: int) -> list[tuple[int, str]]:
    first, last = dt.date.fromisoformat(dates[0]), dt.date.fromisoformat(dates[-1])
    span = (last - first).days
    out = []
    if span <= 45:
        step = max(1, len(dates) // max_ticks)
        for i in range(0, len(dates), step):
            d = dt.date.fromisoformat(dates[i])
            out.append((i, f"{d.day} {MONTHS[d.month - 1]}"))
        return out
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
             zero: bool = False) -> str:
    l, r, t, b = 6, (60 if key == "d" else 50), 18, 26
    pw, ph = W - l - r, H - t - b
    vals = [v for s in series for v in s["values"] if v is not None]
    lo, hi = min(vals), max(vals)
    if zero:
        lo = min(lo, 0)
    pad = (hi - lo) * 0.08 or abs(hi) * 0.05 or 1
    ticks = nice_ticks(lo - pad * 0.5, hi + pad * 0.5, 4 if key == "d" else 3)
    y0, y1 = min(ticks[0], lo), max(ticks[-1], hi)
    n = len(dates)

    def X(i):
        return l + pw * (i / max(1, n - 1))

    def Y(v):
        return t + ph * (1 - (v - y0) / (y1 - y0))
    parts = [f'<svg class="cv {key}" viewBox="0 0 {W} {H}" role="img" preserveAspectRatio="xMidYMid meet" '
             f'style="--fs:{fs}px">']
    step = ticks[1] - ticks[0] if len(ticks) > 1 else 1
    for tv in ticks:
        y = Y(tv)
        parts.append(f'<line class="g" x1="{l}" x2="{l + pw}" y1="{y:.1f}" y2="{y:.1f}"/>')
        parts.append(f'<text class="ya" x="{W - 2}" y="{y + fs * 0.35:.1f}" text-anchor="end">{esc(axis_fmt(tv, unit, step))}</text>')
    if date_axis:
        xt = _date_ticks(dates, 7 if key == "d" else 4)
    else:
        lab = labels or dates
        k = max(1, math.ceil(n / (7 if key == "d" else 4)))
        xt = [(i, lab[i]) for i in range(0, n, k)]
    for i, lab in xt:
        x = X(i)
        parts.append(f'<line class="tk" x1="{x:.1f}" x2="{x:.1f}" y1="{t + ph}" y2="{t + ph + 4}"/>')
        parts.append(f'<text class="xa" x="{x:.1f}" y="{H - 6}" text-anchor="middle">{esc(lab)}</text>')
    for si, s in enumerate(series):
        pts = [(X(i), Y(v)) for i, v in enumerate(s["values"]) if v is not None]
        if not pts:
            continue
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        if area and si == 0 and len(series) == 1:
            parts.append(f'<path class="ar" d="{d} L{pts[-1][0]:.1f},{t + ph} L{pts[0][0]:.1f},{t + ph} Z"/>')
        parts.append(f'<path class="ln s{si}" d="{d}"/>')
        lx, ly = pts[-1]
        if len(series) > 1:
            parts.append(f'<text class="sl s{si}" x="{min(lx + 4, W - r + 4):.1f}" y="{ly - 6:.1f}">{esc(s["name"])}</text>')
    # last-value marker on the first series
    s0 = series[0]["values"]
    li = max(i for i, v in enumerate(s0) if v is not None)
    lx, ly = X(li), Y(s0[li])
    parts.append(f'<circle class="dot" cx="{lx:.1f}" cy="{ly:.1f}" r="{4.5 if key == "d" else 4}"/>')
    lab = fmt(s0[li], unit)
    tw = len(lab) * fs * 0.62 + 10
    parts.append(f'<g class="pill"><rect x="{W - tw - 1:.1f}" y="{ly - fs * 0.85:.1f}" width="{tw:.1f}" height="{fs * 1.6:.1f}" rx="3"/>'
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
            parts.append(f'<circle class="mk" cx="{mx:.1f}" cy="{my:.1f}" r="3.5"/>'
                         f'<text class="ml" x="{mx + dx:.1f}" y="{ty:.1f}" text-anchor="{anchor}">{esc(txt)}</text>')
    parts.append(f'<g class="hv"><line class="hl" y1="{t}" y2="{t + ph}"/><circle class="hd" r="4"/></g>')
    parts.append("</svg>")
    return "".join(parts)


def hover_data(dates: list[str], values: list[float], unit: str, W_d=680, r_d=60, W_m=360, r_m=50) -> str:
    return esc(json.dumps({"d": dates, "v": [round(v, 2) if v is not None else None for v in values], "u": unit,
                           "g": {"d": [6, W_d - 6 - r_d], "m": [6, W_m - 6 - r_m]}}, separators=(",", ":")))


def price_chart(bars: list[dict], rng: str, end: str | None, title: str, subtitle: str = "",
                mark: str | None = "last", cls: str = "") -> str:
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
    head = (f'<span class="crng {"up" if chg >= 0 else "down"}">{"+" if chg >= 0 else "−"}{abs(chg):.1f}% '
            f'over {RANGE_LABEL.get(rng, rng)}</span>')
    inner = both(lambda k, W, H, fs: line_svg(k, W, H, fs, dates, [{"name": "", "values": vals}], "$", mark=mark))
    return (f'<div class="hov" data-h="{hover_data(dates, vals, "$")}">' +
            figure(inner, title, subtitle or f"Daily close, $, to {human(dates[-1])}", "Source: Nasdaq daily closes", head, cls)
            + "</div>")


RANGE_LABEL = {"1m": "1 month", "3m": "3 months", "6m": "6 months", "1y": "1 year", "5y": "5 years", "ytd": "the year to date"}


def human(d: str) -> str:
    x = dt.date.fromisoformat(d)
    return f"{x.day} {MONTHS[x.month - 1]} {x.year}"


def line_chart(spec: dict) -> str:
    x = spec["x"]
    series = spec["series"]
    unit = spec.get("unit", "")
    is_dates = all(len(str(v)) == 10 and str(v)[4] == "-" for v in x)
    inner = both(lambda k, W, H, fs: line_svg(k, W, H, fs, [str(v) for v in x], series, unit, mark=spec.get("mark"),
                                              area=len(series) == 1, date_axis=is_dates, labels=[str(v) for v in x],
                                              zero=spec.get("zero", False)))
    hov = f' data-h="{hover_data([str(v) for v in x], series[0]["values"], unit)}"' if len(series) == 1 else ""
    return f'<div class="hov"{hov}>' + figure(inner, spec["title"], spec.get("subtitle", ""), _src(spec)) + "</div>"


def _src(spec):
    s = spec.get("source", "")
    return s if not s or s.lower().startswith("source") else f"Source: {s}"


# ------------------------------------------------------------------ bars

def bars_svg(key, W, H, fs, labels, values, unit, compare=None, highlight=-1):
    l, r, t, b = 6, 6, 26, 26
    pw, ph = W - l - r, H - t - b
    allv = [v for v in values if v is not None] + [v for v in (compare or []) if v is not None]
    hi = max(allv + [0])
    lo = min(allv + [0])
    n = len(values)
    gap = 0.28
    bw = pw / n * (1 - gap)

    def Y(v):
        return t + ph * (1 - (v - lo) / ((hi - lo) or 1))
    hl = (highlight % n) if highlight is not None else None
    out = [f'<svg class="cv {key}" viewBox="0 0 {W} {H}" role="img" style="--fs:{fs}px">']
    out.append(f'<line class="g0" x1="{l}" x2="{l + pw}" y1="{Y(0):.1f}" y2="{Y(0):.1f}"/>')
    skip = 1 if (key == "d" or n <= 8) else 2
    for i, v in enumerate(values):
        x = l + pw / n * i + pw / n * gap / 2
        if v is None:
            continue
        y, y0 = Y(max(v, 0)), Y(min(v, 0))
        c = "bh" if i == hl else ("bn" if v < 0 else "b")
        out.append(f'<rect class="{c}" x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{max(1, y0 - y):.1f}"/>')
        if compare and i < len(compare) and compare[i] is not None:
            cy = Y(compare[i])
            out.append(f'<line class="est" x1="{x - 2:.1f}" x2="{x + bw + 2:.1f}" y1="{cy:.1f}" y2="{cy:.1f}"/>')
        if i % skip == 0 or i == hl:
            vy = (y - 6) if v >= 0 else (y0 + fs + 2)
            show = key == "d" or n <= 6 or i == hl
            if show:
                out.append(f'<text class="bv{" on" if i == hl else ""}" x="{x + bw / 2:.1f}" y="{vy:.1f}" text-anchor="middle">{esc(fmt(v, unit))}</text>')
            out.append(f'<text class="xa" x="{x + bw / 2:.1f}" y="{H - 6}" text-anchor="middle">{esc(labels[i])}</text>')
    out.append("</svg>")
    return "".join(out)


def bars_chart(spec: dict) -> str:
    labels, values = spec["labels"], spec["values"]
    unit = spec.get("unit", "")
    comp = spec.get("compare")
    legend = ""
    if comp:
        legend = (f'<div class="clg"><span class="k1"></span>{esc(spec.get("label", "Actual"))}'
                  f'<span class="k2"></span>{esc(spec.get("compare_label", "Estimate"))}</div>')
    inner = both(lambda k, W, H, fs: bars_svg(k, W, H, fs, labels, values, unit, comp, spec.get("highlight", -1)))
    return figure(legend + inner, spec["title"], spec.get("subtitle", ""), _src(spec))


def hbars_svg(key, W, H_unused, fs, labels, values, unit):
    n = len(values)
    row = fs * 2.3
    t, b = 6, 6
    H = int(t + b + row * n)
    lab_w = max(len(str(x)) for x in labels) * fs * 0.62 + 10
    lab_w = min(lab_w, W * 0.42)
    val_w = fs * 4.6
    pw = W - lab_w - val_w * 2
    mx = max(abs(v) for v in values if v is not None) or 1
    has_neg = any(v < 0 for v in values if v is not None)
    has_pos = any(v > 0 for v in values if v is not None)
    if has_neg and has_pos:
        zero_x = lab_w + val_w + pw * (max(-min(values), 0) / (max(values) - min(values)))
        scale = pw / (max(values) - min(values))
    elif has_neg:
        zero_x, scale = lab_w + val_w + pw, pw / mx
    else:
        zero_x, scale = lab_w + 2, (W - lab_w - val_w - 4) / mx
    out = [f'<svg class="cv {key}" viewBox="0 0 {W} {H}" role="img" style="--fs:{fs}px">']
    out.append(f'<line class="g0" x1="{zero_x:.1f}" x2="{zero_x:.1f}" y1="{t}" y2="{H - b}"/>')
    for i, (lab, v) in enumerate(zip(labels, values)):
        y = t + row * i
        bh = row * 0.58
        cy = y + row / 2
        out.append(f'<text class="hl1" x="0" y="{cy + fs * 0.35:.1f}">{esc(lab)}</text>')
        if v is None:
            continue
        w = abs(v) * scale
        x = zero_x if v >= 0 else zero_x - w
        out.append(f'<rect class="{"bu" if v >= 0 else "bd"}" x="{x:.1f}" y="{cy - bh / 2:.1f}" width="{max(w, 1):.1f}" height="{bh:.1f}"/>')
        tx = x + w + 6 if v >= 0 else x - 6
        anchor = "start" if v >= 0 else "end"
        sign = "+" if v > 0 else ""
        out.append(f'<text class="hv1 {"up" if v >= 0 else "down"}" x="{tx:.1f}" y="{cy + fs * 0.35:.1f}" text-anchor="{anchor}">{sign}{esc(fmt(v, unit))}</text>')
    out.append("</svg>")
    return "".join(out)


def hbars_chart(spec: dict) -> str:
    inner = both(lambda k, W, H, fs: hbars_svg(k, W, H, fs, spec["labels"], spec["values"], spec.get("unit", "")))
    return figure(inner, spec["title"], spec.get("subtitle", ""), _src(spec))


# ------------------------------------------------------------------ sparkline (cards, tables)

def spark(values: list[float], w: int = 96, h: int = 28) -> str:
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    pts = [(w * i / (len(vals) - 1), h - 2 - (h - 4) * ((v - lo) / ((hi - lo) or 1))) for i, v in enumerate(vals)]
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    tone = "up" if vals[-1] >= vals[0] else "down"
    return f'<svg class="spk {tone}" viewBox="0 0 {w} {h}" width="{w}" height="{h}" aria-hidden="true"><path d="{d}"/></svg>'
