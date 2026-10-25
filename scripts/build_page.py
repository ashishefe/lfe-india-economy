#!/usr/bin/env python3
"""Turn data/india.json into site/india/index.html.

The page is plain HTML with inline SVG charts, so it is complete with
JavaScript off. The only script is the house theme toggle. Each chart is
drawn twice, wide and narrow, and CSS shows the one that fits the screen.

Usage:  python3 scripts/build_page.py
"""

from __future__ import annotations

import datetime as dt
import html
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "india.json"
OUT = ROOT / "site" / "experiments" / "india-economy" / "index.html"

MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH = ["January", "February", "March", "April", "May", "June", "July", "August",
         "September", "October", "November", "December"]
FY_Q = {"Q1": ("Apr", "Jun", 5, 0), "Q2": ("Jul", "Sep", 8, 0), "Q3": ("Oct", "Dec", 11, 0), "Q4": ("Jan", "Mar", 2, 1)}

esc = html.escape


# --------------------------------------------------------------------------
# Dates and numbers
# --------------------------------------------------------------------------

def to_date(label: str) -> dt.date:
    """Daily 'YYYY-MM-DD', monthly 'YYYY-MM', or Indian fiscal quarter 'YYYY-YY Qn'."""
    if " Q" in label:
        fy, q = label.split()
        mid, plus = FY_Q[q][2], FY_Q[q][3]
        return dt.date(int(fy[:4]) + plus, mid, 15)
    if len(label) == 7:
        return dt.date(int(label[:4]), int(label[5:]), 15)
    return dt.date.fromisoformat(label)


def say_date(label: str) -> str:
    if " Q" in label:
        fy, q = label.split()
        a, b, _, plus = FY_Q[q]
        return f"{a}–{b} {int(fy[:4]) + plus}"
    d = to_date(label)
    if len(label) == 7:
        return f"{MONTH[d.month - 1]} {d.year}"
    return f"{d.day} {MON[d.month - 1]} {d.year}"


def short_month(label: str) -> str:
    d = to_date(label)
    return f"{MON[d.month - 1]} {d.year}"


def at_or_before(points: list, when: dt.date):
    best = None
    for p in points:
        if to_date(p[0]) <= when:
            best = p
    return best


def year_ago(points: list):
    """The same period a year earlier. Monthly series need the exact month;
    daily and weekly ones take the nearest observation on or before."""
    last = points[-1][0]
    if len(last) == 7:
        want = f"{int(last[:4]) - 1}{last[4:]}"
        return next((p for p in points if p[0] == want), None)
    return at_or_before(points, to_date(last) - dt.timedelta(days=364))


def pct(new: float, old: float) -> float:
    return 100 * (new / old - 1)


def f1(x: float) -> str:
    return f"{x:.1f}".replace("-", "−")


def rose(x: float) -> str:
    return f"{'rose' if x >= 0 else 'fell'} {f1(abs(x))}%"


def more_less(x: float) -> str:
    return f"{f1(abs(x))}% {'more' if x >= 0 else 'less'}"


def grew(x: float) -> str:
    return f"{'grew' if x >= 0 else 'shrank'} {f1(abs(x))}%"


def signed(x: float, unit: str = "") -> str:
    s = f"{abs(x):.1f}{unit}"
    return ("+" if x > 0 else "−" if x < 0 else "") + s


def inr(x: float) -> str:
    """Indian digit grouping: 1,23,456."""
    s = f"{round(x):d}"
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


# --------------------------------------------------------------------------
# Charts (inline SVG, house chart classes from lfe.css)
# --------------------------------------------------------------------------

def nice_ticks(lo: float, hi: float, n: int = 5):
    span = hi - lo or 1
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    step = min((s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw), default=10 * mag)
    start = math.floor(lo / step) * step
    ticks = []
    t = start
    while t <= hi + step * 0.01:
        ticks.append(round(t, 6))
        t += step
    if ticks[-1] < hi:
        ticks.append(round(ticks[-1] + step, 6))
    return ticks


def month_ticks(start: dt.date, end: dt.date, every: int):
    out = []
    y, m = start.year, start.month
    while dt.date(y, m, 1) <= end:
        if (m - 1) % every == 0 and dt.date(y, m, 1) >= start:
            out.append((dt.date(y, m, 1), f"{MON[m - 1]} {str(y)[2:]}" if every < 12 else str(y)))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def chart(lines, *, wide: bool, title: str, y_unit: str = "", band=None, refs=(), breaks=(),
          bars=None, x_start=None, x_end=None, y_floor=None, y_ceil=None, tick_every=(3, 6)):
    """lines: list of dicts {points, cls, label}. bars: {points, label} for a bar series."""
    w, h = (760, 330) if wide else (380, 300)
    ml, mr, mt, mb = (46, 112, 16, 30) if wide else (38, 104, 14, 30)
    every = tick_every[0] if wide else tick_every[1]
    series_pts = [p for ln in lines for p in ln["points"] if p is not None] + (bars["points"] if bars else [])
    dates = [to_date(p[0]) for p in series_pts]
    x0 = x_start or min(dates)
    x1 = x_end or max(dates)
    if bars:  # leave half a bar of room either side
        x0 -= dt.timedelta(days=46)
        x1 += dt.timedelta(days=46)
    vals = [p[1] for p in series_pts] + [r[0] for r in refs] + (list(band) if band else [])
    lo = min(vals) if y_floor is None else y_floor
    hi = max(vals) if y_ceil is None else y_ceil
    if bars:
        lo = min(lo, 0)
    yt = nice_ticks(lo, hi, 5 if wide else 4)
    y0, y1 = yt[0], yt[-1]
    pw, ph = w - ml - mr, h - mt - mb
    span = (x1 - x0).days or 1

    def X(d):
        return ml + pw * (d - x0).days / span

    def Y(v):
        return mt + ph * (1 - (v - y0) / (y1 - y0))

    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}" class="{"chart-wide" if wide else "chart-narrow"}">']
    if band:
        out.append(f'<rect class="clock-band" x="{ml}" y="{Y(band[1]):.1f}" width="{pw}" height="{Y(band[0]) - Y(band[1]):.1f}"/>')
    for t in yt:
        out.append(f'<line class="grid-line" x1="{ml}" x2="{ml + pw}" y1="{Y(t):.1f}" y2="{Y(t):.1f}"/>')
        lab = f"{t:g}{y_unit}"
        out.append(f'<text class="tick-label" x="{ml - 8}" y="{Y(t) + 4:.1f}" text-anchor="end">{esc(lab)}</text>')
    for d, lab in month_ticks(x0, x1, every):
        if X(d) - ml < 18:
            continue  # would sit under the y-axis labels
        out.append(f'<line class="axis-line" x1="{X(d):.1f}" x2="{X(d):.1f}" y1="{mt + ph}" y2="{mt + ph + 5}"/>')
        out.append(f'<text class="tick-label" x="{X(d):.1f}" y="{mt + ph + 19}" text-anchor="middle">{esc(lab)}</text>')
    ref_labels = []
    for v, lab in refs:
        out.append(f'<line class="marker-rule" x1="{ml}" x2="{ml + pw}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"/>')
        ref_labels.append([Y(v) + 4, ml + pw + 7, lab, "chart-annot-sub"])
    for d, lab in breaks:
        bx = X(d)
        out.append(f'<line class="axis-line break-rule" x1="{bx:.1f}" x2="{bx:.1f}" y1="{mt}" y2="{mt + ph}"/>')
        out.append(f'<text class="chart-annot-sub" x="{bx + 5:.1f}" y="{mt + 12}">{esc(lab)}</text>')
    if bars:
        n = len(bars["points"])
        bw = max(4, min(26, pw / max(n, 1) * 0.55))
        for p in bars["points"]:
            bx = X(to_date(p[0]))
            top, base = Y(max(p[1], 0)), Y(min(p[1], 0))
            out.append(f'<rect class="bar" x="{bx - bw / 2:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{base - top:.1f}"/>')
        last = bars["points"][-1]
        out.append(f'<text class="legend-label" x="{X(to_date(last[0])) + bw / 2 + 6:.1f}" y="{Y(last[1]) + 4:.1f}">{esc(bars["label"])}</text>')
    end_labels = []
    for ln in lines:
        segs, cur = [], []
        for p in ln["points"]:
            if p is None:
                segs.append(cur)
                cur = []
            else:
                cur.append(p)
        segs.append(cur)
        for seg in segs:
            if len(seg) > 1:
                pts = " ".join(f"{X(to_date(p[0])):.1f},{Y(p[1]):.1f}" for p in seg)
                out.append(f'<polyline class="{ln["cls"]}" points="{pts}"/>')
            elif len(seg) == 1:
                p = seg[0]
                out.append(f'<circle class="marker-dot" cx="{X(to_date(p[0])):.1f}" cy="{Y(p[1]):.1f}" r="3"/>')
        real = [p for p in ln["points"] if p is not None]
        if real and ln.get("label"):
            p = real[-1]
            end_labels.append([Y(p[1]) + 4, X(to_date(p[0])) + 7, ln["label"], "legend-label"])
            out.append(f'<circle class="marker-dot" cx="{X(to_date(p[0])):.1f}" cy="{Y(p[1]):.1f}" r="3.5"/>')
    end_labels += ref_labels
    end_labels.sort()
    for i in range(1, len(end_labels)):  # keep end labels from overlapping
        if end_labels[i][0] - end_labels[i - 1][0] < 15:
            end_labels[i][0] = end_labels[i - 1][0] + 15
    for y, x, lab, cls in end_labels:
        out.append(f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}">{esc(lab)}</text>')
    out.append("</svg>")
    return "".join(out)


def figure(title: str, caption: str, table_rows, table_head, **kw):
    wide = chart(wide=True, title=title, **kw)
    narrow = chart(wide=False, title=title, **kw)
    rows = "".join("<tr>" + "".join(f"<td>{esc(str(c))}</td>" for c in r) + "</tr>" for r in table_rows)
    head = "".join(f"<th scope=\"col\">{esc(c)}</th>" for c in table_head)
    return (f'<figure class="chart"><p class="chart-title">{esc(title)}</p>{wide}{narrow}'
            f'<figcaption>{caption}</figcaption>'
            f'<details class="chart-data"><summary>Numbers behind this chart</summary>'
            f'<table class="num-table"><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></details>'
            f'</figure>')


def month_end(points: list) -> list:
    """Last observation of each month, for the data tables under daily or weekly charts."""
    by = {}
    for p in points:
        by[p[0][:7]] = p
    return [by[k] for k in sorted(by)]


# --------------------------------------------------------------------------
# Freshness
# --------------------------------------------------------------------------

MAX_AGE = {"D": 12, "W": 16, "F": 35, "M": 75, "Q": 170}


def freshness(s: dict, today: dt.date) -> str | None:
    """A warning if the series is stale or older than its usual release lag."""
    last = s["points"][-1][0]
    age = (today - to_date(last)).days
    if s.get("stale"):
        return f"The last update failed; this is the figure for {say_date(last)}."
    if age > MAX_AGE[s["freq"]]:
        return f"Older than usual: latest is {say_date(last)}."
    return None


# --------------------------------------------------------------------------
# The page
#
# A few fixed facts are written into the text, checked by hand on 25 Oct 2026:
# food and beverages weigh 36.75% in the 2024-base CPI (MoSPI); the new CPI
# and the 2022-23-base GDP were first published in February 2026; the BIS
# broad index covers 64 economies. Re-check them if MoSPI or BIS change.
# --------------------------------------------------------------------------

def build(data: dict) -> str:
    S = data["series"]
    today = dt.date.fromisoformat(data["generated_at"][:10])
    # The old CPI series ended on purpose in December 2025, so it is never "late".
    warnings = {k: freshness(v, today) for k, v in S.items()
                if isinstance(v, dict) and v.get("points") and not k.endswith("_old")}

    # ---- the rupee -------------------------------------------------------
    usd = S["usdinr"]["points"]
    usd_last, usd_ago = usd[-1], year_ago(usd)
    usd_yoy = pct(usd_last[1], usd_ago[1])
    neer, reer = S["neer"]["points"], S["reer"]["points"]
    neer_yoy = pct(neer[-1][1], year_ago(neer)[1])
    reer_yoy = pct(reer[-1][1], year_ago(reer)[1])
    res, fca = S["reserves"]["points"], S["reserves_fca"]["points"]
    res_yoy = res[-1][1] - year_ago(res)[1]
    brent = S["brent"]["points"]
    br_last, br_ago = brent[-1], year_ago(brent)
    br_inr = br_last[1] * at_or_before(usd, to_date(br_last[0]))[1]
    br_inr_ago = br_ago[1] * at_or_before(usd, to_date(br_ago[0]))[1]
    # Only true one-week changes count (the fetch can skip a week it could not read).
    jumps = [(fca[i][1] - fca[i - 1][1], fca[i][0]) for i in range(1, len(fca))
             if (to_date(fca[i][0]) - to_date(fca[i - 1][0])).days == 7
             and to_date(fca[i][0]) >= to_date(fca[-1][0]) - dt.timedelta(days=182)]
    big_jump = max(jumps) if jumps else (0, None)
    # Window: from an unusual one-week jump if there was one in the past six months
    # (so the reader sees it named), otherwise the past six weeks.
    fca_label = "Foreign currency assets, the part of the reserves the RBI sells when it supports the rupee,"
    if big_jump[0] > 20 and big_jump[1] == fca[-1][0]:
        since = None
        pressure = (f"{fca_label} rose ${big_jump[0]:.1f} billion in the latest week alone. "
                    f"The RBI’s weekly figures do not say why.")
    elif len(fca) < 7:
        since = None
        pressure = f"{fca_label} stood at ${fca[-1][1]:.1f} billion on {say_date(fca[-1][0])}."
    elif big_jump[0] > 20:
        since = big_jump[1]
        opening = (f"{fca_label} jumped ${big_jump[0]:.1f} billion in the single week to {say_date(since)}. "
                   f"The RBI’s weekly figures do not say why. Since then")
    else:
        since = at_or_before(fca, to_date(fca[-1][0]) - dt.timedelta(weeks=6))[0]
        opening = (f"Foreign currency assets are the part of the reserves the RBI sells when it supports the rupee. "
                   f"Since {say_date(since)}")
    if since:
        fca_chg = fca[-1][1] - at_or_before(fca, to_date(since))[1]
        usd_chg = pct(at_or_before(usd, to_date(fca[-1][0]))[1], at_or_before(usd, to_date(since))[1])
        pressure = (f"{opening} they have {'fallen' if fca_chg < 0 else 'risen'} ${abs(fca_chg):.1f} billion, "
                    f"while a dollar came to cost {f1(abs(usd_chg))}% {'more' if usd_chg >= 0 else 'less'} in rupees.")
        if fca_chg < -10 and abs(usd_chg) < 2:
            pressure += (" A rupee that holds steady while these assets fall is a sign that the RBI is selling dollars. "
                         "It is a sign, not proof: the dollar value of the other currencies and bonds it holds moves too.")

    # ---- inflation -------------------------------------------------------
    cpi, food = S["cpi_headline"]["points"], S["cpi_food"]["points"]
    cpi_old, food_old = S["cpi_headline_old"]["points"], S["cpi_food_old"]["points"]
    groups = {r["code"]: r for r in S["cpi_groups"]["rows"]}
    cpi_last, cpi_first = cpi[-1], cpi[0]
    where = ("inside the RBI's band of 2–6%" if 2 <= cpi_last[1] <= 6 else
             "above the RBI's upper limit of 6%" if cpi_last[1] > 6 else "below the RBI's lower limit of 2%")
    vs_target = "above" if cpi_last[1] > 4 else "below" if cpi_last[1] < 4 else "at"
    divisions = sorted([r for r in S["cpi_groups"]["rows"] if "." not in r["code"] and r["code"] != "00"],
                       key=lambda r: -r["inflation"])

    # ---- growth ----------------------------------------------------------
    gdp = S["gdp_growth"]["points"]
    gdp_last = gdp[-1]
    gdp_ago = next((p for p in gdp if p[0] == f"{int(gdp_last[0][:4]) - 1}-{str(int(gdp_last[0][:4]))[2:]} {gdp_last[0][-2:]}"), None)
    nominal = dict(S["gdp_growth"]["nominal"])
    pfce, gfcf = S["pfce_growth"]["points"], S["gfcf_growth"]["points"]
    credit, deposit = S["credit_yoy"]["points"], S["deposit_yoy"]["points"]
    credit_ago = S["credit_yoy"]["year_earlier"][-1]   # RBI's own year-earlier figure
    deposit_ago = S["deposit_yoy"]["year_earlier"][-1]
    iip = S["iip"]["points"]

    # ---- jobs ------------------------------------------------------------
    ur, youth = S["ur"]["points"], S["ur_youth"]["points"]
    ur_ago = year_ago(ur)

    def latest_row(key, unit="%"):
        p = S[key]["points"]
        a = year_ago(p)
        return [S[key]["label"], f"{f1(p[-1][1])}{unit}", f"{f1(a[1])}{unit}" if a else "–"]

    # ---- key numbers -----------------------------------------------------
    keys = [
        ("Rupees per dollar", f"₹{usd_last[1]:.2f}", f"{signed(usd_yoy, '%')} on a year ago", say_date(usd_last[0]), "usdinr"),
        ("Foreign-exchange reserves", f"${res[-1][1]:.1f} bn", f"{signed(res_yoy)} bn on a year ago".replace("+", "+$").replace("−", "−$"), say_date(res[-1][0]), "reserves"),
        ("Consumer inflation", f"{f1(cpi_last[1])}%", f"Target 4%, band 2–6%", say_date(cpi_last[0]), "cpi_headline"),
        ("Food and beverages inflation", f"{f1(food[-1][1])}%", f"Headline {f1(cpi_last[1])}%", say_date(food[-1][0]), "cpi_food"),
        ("Real GDP growth", f"{f1(gdp_last[1])}%", f"{f1(gdp_ago[1])}% a year earlier" if gdp_ago else "", say_date(gdp_last[0]), "gdp_growth"),
        ("Unemployment, age 15+", f"{f1(ur[-1][1])}%", f"{f1(ur_ago[1])}% a year earlier" if ur_ago else "", say_date(ur[-1][0]), "ur"),
        ("Brent crude in rupees", f"₹{inr(br_inr)}", f"{signed(pct(br_inr, br_inr_ago), '%')} on a year ago, a barrel", say_date(br_last[0]), "brent"),
        ("Bank credit growth", f"{f1(credit[-1][1])}%", f"{f1(credit_ago[1])}% a year earlier" if credit_ago else "", say_date(credit[-1][0]), "credit_yoy"),
    ]
    key_html = "".join(
        f'<div class="key"><dt>{esc(a)}</dt><dd class="key-value">{esc(b)}</dd>'
        f'<dd class="key-compare">{esc(c)}</dd><dd class="key-date">{esc(d)}'
        + (f' <span class="stale">· {esc(warnings[k])}</span>' if warnings.get(k) else "")
        + "</dd></div>"
        for a, b, c, d, k in keys)

    # ---- charts ----------------------------------------------------------
    usd_start = to_date(usd_last[0]) - dt.timedelta(days=730)
    usd2 = [p for p in usd if to_date(p[0]) >= usd_start]
    fig_rupee = figure(
        "Rupees per US dollar, daily",
        f"Higher means a weaker rupee. Latest {say_date(usd_last[0])}. Source: Federal Reserve noon rates in New York, via FRED; "
        f"these differ slightly from the RBI's own reference rate.",
        [[short_month(p[0]), f"{p[1]:.2f}"] for p in month_end(usd2)], ["Month end", "₹ per $"],
        lines=[{"points": usd2, "cls": "line-primary", "label": f"₹{usd_last[1]:.2f}"}],
        tick_every=(3, 6))

    fig_reserves = figure(
        "Foreign-exchange reserves, weekly, US$ billion",
        f"Total reserves and the part held as foreign currency, which is what the RBI sells when it supports the rupee. "
        f"Gold makes up most of the rest. Latest week {say_date(res[-1][0])}. Source: RBI Weekly Statistical Supplement.",
        [[say_date(p[0]), f"{p[1]:.1f}", (lambda q: f"{q[1]:.1f}" if q else "–")(at_or_before(fca, to_date(p[0])))] for p in res[-16:]],
        ["Week", "Total", "Foreign currency"],
        lines=[{"points": res, "cls": "line-primary", "label": f"Total ${res[-1][1]:.0f}bn"},
               {"points": fca, "cls": "line-reference", "label": f"Currency ${fca[-1][1]:.0f}bn"}],
        tick_every=(2, 3))

    cpi_line = cpi_old + [None] + cpi
    food_line = food_old + [None] + food
    fig_cpi = figure(
        "Consumer inflation, % on a year earlier",
        "The shaded band is the RBI's 2–6% range; the dotted line is the 4% target. The vertical line marks the switch "
        "from the old CPI (2012 base) to the new one (2024 base), first published in February 2026. The two series use "
        "different baskets and weights, so the join is not seamless. Food is the consumer food price index in the old "
        "series and the food and beverages division in the new one. Source: MoSPI.",
        [[short_month(p[0]), f1(p[1]), f1(f[1])] for p, f in zip(cpi_old + cpi, food_old + food)],
        ["Month", "All items", "Food"],
        lines=[{"points": cpi_line, "cls": "line-primary", "label": f"All items {f1(cpi_last[1])}%"},
               {"points": food_line, "cls": "line-reference", "label": f"Food {f1(food[-1][1])}%"}],
        band=(2, 6), refs=[(4, "Target")], breaks=[(dt.date(2026, 1, 1), "New CPI")], tick_every=(3, 6))

    fig_gdp = figure(
        "Real GDP growth, % on the same quarter a year earlier",
        f"Quarters follow India's April–March financial year. Latest: {say_date(gdp_last[0])}. "
        "Source: MoSPI national accounts, 2022-23 base.",
        [[say_date(p[0]), f1(p[1]), f1(nominal.get(p[0], float('nan')))] for p in gdp],
        ["Quarter", "Real", "Nominal"],
        lines=[], bars={"points": gdp, "label": f"{f1(gdp_last[1])}%"}, tick_every=(6, 12))

    fig_jobs = figure(
        "Unemployment rate, monthly, %",
        f"People who looked for work but found none in the week surveyed, as a share of those working or looking. "
        f"Latest: {say_date(ur[-1][0])}. Source: MoSPI Periodic Labour Force Survey, monthly bulletin.",
        [[short_month(p[0]), f1(p[1]), f1(y[1])] for p, y in zip(ur, youth)],
        ["Month", "Age 15+", "Age 15–29"],
        lines=[{"points": ur, "cls": "line-primary", "label": f"Age 15+ {f1(ur[-1][1])}%"},
               {"points": youth, "cls": "line-reference", "label": f"Age 15–29 {f1(youth[-1][1])}%"}],
        y_floor=0, tick_every=(3, 6))

    # ---- tables ----------------------------------------------------------
    def tr(cells, head=False):
        tag = "th" if head else "td"
        return "<tr>" + "".join(f'<{tag}{" scope=col" if head else ""}>{esc(str(c))}</{tag}>' for c in cells) + "</tr>"

    rupee_table = "".join([
        tr(["", "Latest", "Year earlier", "Change"], head=True),
        tr(["Rupees per dollar", f"{usd_last[1]:.2f}", f"{usd_ago[1]:.2f}", signed(usd_yoy, "%")]),
        tr(["Rupee against 64 currencies (index)", f"{neer[-1][1]:.1f}", f"{year_ago(neer)[1]:.1f}", signed(neer_yoy, "%")]),
        tr(["… adjusted for inflation (index)", f"{reer[-1][1]:.1f}", f"{year_ago(reer)[1]:.1f}", signed(reer_yoy, "%")]),
        tr(["Reserves, US$ bn", f"{res[-1][1]:.1f}", f"{year_ago(res)[1]:.1f}", signed(res[-1][1] - year_ago(res)[1])]),
        tr(["Brent crude, $ a barrel", f"{br_last[1]:.1f}", f"{br_ago[1]:.1f}", signed(pct(br_last[1], br_ago[1]), "%")]),
        tr(["Brent crude, ₹ a barrel", inr(br_inr), inr(br_inr_ago), signed(pct(br_inr, br_inr_ago), "%")]),
    ])
    cpi_table = tr(["Division of the CPI basket", f"{say_date(cpi_last[0])}"], head=True) + tr(["All items", f"{f1(cpi_last[1])}%"]) + "".join(
        tr([r["name"], f"{f1(r['inflation'])}%"]) for r in divisions)
    growth_rows = [
        ["Real GDP", f"{f1(gdp_last[1])}%", f"{f1(gdp_ago[1])}%" if gdp_ago else "–", say_date(gdp_last[0])],
        ["Nominal GDP (before adjusting for prices)", f"{f1(nominal[gdp_last[0]])}%",
         f"{f1(nominal[gdp_ago[0]])}%" if gdp_ago and gdp_ago[0] in nominal else "–", say_date(gdp_last[0])],
        ["Private consumption, real", f"{f1(pfce[-1][1])}%", f"{f1(year_ago(pfce)[1])}%" if year_ago(pfce) else "–", say_date(pfce[-1][0])],
        ["Investment in fixed assets, real", f"{f1(gfcf[-1][1])}%", f"{f1(year_ago(gfcf)[1])}%" if year_ago(gfcf) else "–", say_date(gfcf[-1][0])],
        ["Bank credit", f"{f1(credit[-1][1])}%", f"{f1(credit_ago[1])}%" if credit_ago else "–", say_date(credit[-1][0])],
        ["Bank deposits", f"{f1(deposit[-1][1])}%", f"{f1(deposit_ago[1])}%", say_date(deposit[-1][0])],
        ["Industrial production", f"{f1(iip[-1][1])}%", f"{f1(year_ago(iip)[1])}%" if year_ago(iip) else "–", say_date(iip[-1][0])],
    ]
    growth_table = tr(["Growth on a year earlier", "Latest", "Year before", "Period"], head=True) + "".join(tr(r) for r in growth_rows)
    jobs_table = tr(["", short_month(ur[-1][0]), "Year earlier"], head=True) + "".join(
        tr(latest_row(k)) for k in ("ur", "ur_rural", "ur_urban", "ur_female", "ur_youth", "lfpr", "lfpr_female", "wpr"))

    # ---- sources ---------------------------------------------------------
    src_rows = [
        ("MoSPI eSankhyiki API", "Consumer prices, jobs survey, national accounts, industrial production", "https://esankhyiki.mospi.gov.in/",
         ["cpi_headline", "ur", "gdp_growth", "iip"]),
        ("RBI Weekly Statistical Supplement", "Reserves, bank credit and deposits", "https://www.rbi.org.in/Scripts/BS_viewWssExtract.aspx",
         ["reserves", "credit_yoy"]),
        ("FRED, Federal Reserve Bank of St Louis", "Rupees per dollar; Brent crude (from the US EIA)", "https://fred.stlouisfed.org/series/DEXINUS",
         ["usdinr", "brent"]),
        ("Bank for International Settlements", "Rupee against a basket of 64 currencies", "https://data.bis.org/topics/EER",
         ["neer"]),
    ]
    src_html = "".join(
        f'<tr><td><a href="{u}">{esc(n)}</a></td><td>{esc(w)}</td><td>'
        + "; ".join(f"{esc(S[k]['label'])}: {esc(say_date(S[k]['points'][-1][0]))}" for k in ks)
        + "</td></tr>" for n, w, u, ks in src_rows)
    stale_list = [f"{S[k]['label']}: {w}" for k, w in warnings.items() if w]
    stale_html = ("<p class=\"stale-note\">" + " ".join(esc(s) for s in stale_list) + "</p>") if stale_list else ""

    g = groups
    jewel = g["13.2.1"]["inflation"]
    petrol, diesel = g["07.2.2.2"]["inflation"], g["07.2.2.1"]["inflation"]
    elec = g["04.5.1"]["inflation"]
    eat = g["11.1"]["inflation"]

    updated = say_date(data["generated_at"][:10])

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>India Economy Dashboard</title>
  <meta name="description" content="Four questions about India's economy, answered with the latest official numbers: the rupee, inflation, growth and jobs.">
  <script src="../../assets/lfe-theme.js"></script>
  <link rel="stylesheet" href="../../assets/lfe.css">
  <link rel="stylesheet" href="../../assets/lfe-topics.css">
  <link rel="stylesheet" href="india.css">
</head>
<body>
  <a class="skip" href="#main">Skip to content</a>
  <header class="site-bar"><div class="bar-inner">
    <a class="wordmark" href="../../index.html">Learn For Everybody</a>
    <nav aria-label="Topics"><a href="../../econofai/index.html">Economics of AI</a><a href="../../power/index.html">Power</a><a href="../../minds/index.html">Minds</a></nav>
    <button class="theme-toggle icon-toggle" id="themeToggle" type="button" aria-label="Dark mode"><span aria-hidden="true">◐</span><span class="tip" id="themeLabel" aria-hidden="true">Dark mode</span></button>
  </div></header>
  <div class="topic-bar"><div class="bar-inner"><a class="topic-name" href="../index.html">Experiments</a><nav aria-label="Experiments"><a href="../index.html">All experiments</a><a href="index.html" aria-current="page">India economy</a><a href="../india-development/index.html">India development</a><a href="../run-with-it/index.html">Run with it</a></nav></div></div>

  <header class="shell mast">
    <h1>How is India’s economy doing?</h1>
    <p class="intro">Four questions, answered with the latest official numbers.<br>Updated {esc(updated)}.</p>
    <p class="stale-banner" id="staleBanner" hidden></p>
  </header>

  <main class="shell" id="main">
    <section aria-labelledby="keys-title">
      <h2 id="keys-title" class="visually-hidden">Key numbers</h2>
      <dl class="keys panel">{key_html}</dl>
      {stale_html}
    </section>

    <section class="q" id="rupee" aria-labelledby="q1">
      <div class="q-text">
        <h2 id="q1"><span class="q-num">1</span> What is the rupee telling us?</h2>
        <p>A dollar cost <strong>₹{usd_last[1]:.2f}</strong> on {esc(say_date(usd_last[0]))}, {esc(f1(abs(usd_yoy)))}% {"more" if usd_yoy > 0 else "less"} than a year earlier. Against a basket of 64 currencies the rupee was {esc(f1(abs(neer_yoy)))}% {"weaker" if neer_yoy < 0 else "stronger"} than a year earlier in {esc(say_date(neer[-1][0]))}, and {esc(f1(abs(reer_yoy)))}% {"weaker" if reer_yoy < 0 else "stronger"} after allowing for the gap between Indian and foreign inflation.</p>
        <p>Reserves stood at <strong>${res[-1][1]:.1f} billion</strong> on {esc(say_date(res[-1][0]))}, ${esc(f1(abs(res_yoy)))} billion {"more" if res_yoy >= 0 else "less"} than a year earlier.</p>
        <p>{esc(pressure)}</p>
        <p>India buys most of its oil abroad. Brent crude cost ${br_last[1]:.0f} a barrel on {esc(say_date(br_last[0]))}, {esc(more_less(pct(br_last[1], br_ago[1])))} than a year earlier. {"Because the rupee also fell" if usd_yoy > 0 else "With the rupee's move"}, a barrel cost {esc(more_less(pct(br_inr, br_inr_ago)))} in rupees (at the latest exchange rate we have, for {esc(say_date(at_or_before(usd, to_date(br_last[0]))[0]))}).</p>
      </div>
      <div class="q-charts">{fig_rupee}{fig_reserves}<table class="num-table">{rupee_table}</table></div>
    </section>

    <section class="q" id="inflation" aria-labelledby="q2">
      <div class="q-text">
        <h2 id="q2"><span class="q-num">2</span> Is inflation inside the RBI’s band, and what is driving it?</h2>
        <p>Consumer prices {rose(cpi_last[1]).split()[0]} <strong>{esc(f1(abs(cpi_last[1])))}%</strong> in the year to {esc(say_date(cpi_last[0]))}, up from {esc(f1(cpi_first[1]))}% in {esc(say_date(cpi_first[0]))}. That is {where}, and {vs_target} its 4% target.</p>
        <p>Food and beverages, about 37% of the basket, {rose(food[-1][1])}. Eating out {rose(eat)}. Jewellery and watches {rose(jewel)}.</p>
        <p>Fuel tells a different story. Petrol cost {esc(f1(abs(petrol)))}% {"more" if petrol >= 0 else "less"} than a year earlier and diesel {esc(f1(abs(diesel)))}% {"more" if diesel >= 0 else "less"}, while a barrel of crude cost {esc(more_less(pct(br_inr, br_inr_ago)))} in rupees. Pump prices in India are set mostly by the state-run oil companies and by taxes, and they have risen far less than crude.</p>
        <p>Electricity, mostly generated from coal and priced by state regulators, cost {esc(f1(abs(elec)))}% {"less" if elec < 0 else "more"} than a year earlier.</p>
        <p class="note">India publishes no official “core” inflation, the measure without food and fuel that many central banks watch. We do not yet split the whole index into food, fuel and the rest: that needs the weights of each item in the basket, which we have not added yet.</p>
      </div>
      <div class="q-charts">{fig_cpi}<table class="num-table">{cpi_table}</table></div>
    </section>

    <section class="q" id="growth" aria-labelledby="q3">
      <div class="q-text">
        <h2 id="q3"><span class="q-num">3</span> Is growth reaching people?</h2>
        <p>The economy {grew(gdp_last[1]).split()[0]} <strong>{esc(f1(abs(gdp_last[1])))}%</strong> in {esc(say_date(gdp_last[0]))} after adjusting for prices{f", against {f1(gdp_ago[1])}% a year earlier" if gdp_ago else ""}.</p>
        <p>Private consumption, the closest thing we have to a measure of whether growth reaches households, {grew(pfce[-1][1])}. Investment {grew(gfcf[-1][1])}. Bank credit {grew(credit[-1][1])} in the year to {esc(say_date(credit[-1][0]))}. Industrial production {grew(iip[-1][1])} in the year to {esc(say_date(iip[-1][0]))}.</p>
        <p class="note">There is no good monthly measure yet of whether growth reaches people: wages, rural spending and the like come late and patchily. These GDP figures are on MoSPI’s new 2022-23 base, first published in February 2026, and each quarter is revised several times. Industrial production is on its new 2022-23 base too.</p>
      </div>
      <div class="q-charts">{fig_gdp}<table class="num-table">{growth_table}</table></div>
    </section>

    <section class="q" id="jobs" aria-labelledby="q4">
      <div class="q-text">
        <h2 id="q4"><span class="q-num">4</span> Are jobs being created?</h2>
        <p>Unemployment was <strong>{esc(f1(ur[-1][1]))}%</strong> in {esc(say_date(ur[-1][0]))} for people aged 15 and over{f", against {f1(ur_ago[1])}% a year earlier" if ur_ago else ""}. Among 15 to 29-year-olds it was {esc(f1(youth[-1][1]))}%.</p>
        <p>Only {esc(f1(S["lfpr_female"]["points"][-1][1]))}% of women aged 15 and over were working or looking for work, against {esc(f1(S["lfpr"]["points"][-1][1]))}% of all adults.</p>
        <p class="note">Read these with care. The monthly survey began only in April 2025, so there is little history. It counts anyone who worked for at least an hour in the survey week as employed, so it says little about the quality of jobs. Moves of a few tenths of a point from month to month are mostly noise.</p>
      </div>
      <div class="q-charts">{fig_jobs}<table class="num-table">{jobs_table}</table></div>
    </section>

    <section class="left-out aside-rule" aria-labelledby="left-out">
      <h2 id="left-out">What we left out, and why</h2>
      <p><strong>Government finances.</strong> Monthly figures for the Centre swing with the timing of tax transfers to the states and with one large payment, the RBI’s dividend to the government. Borrowing outside the budget, one-off schemes and the split between the Centre and the states make any single monthly number misleading. We will write about it once a year, around the Budget, where there is room for the caveats.</p>
      <p><strong>Forecasts.</strong> The RBI’s Monetary Policy Committee publishes projections for growth and inflation every two months, and the RBI’s monthly Bulletin carries its staff’s estimates for the current quarter. Neither comes in a form we can fetch automatically yet, and we have not tried to make our own.</p>
    </section>

    <section class="sources" aria-labelledby="sources">
      <h2 id="sources">Where the numbers come from</h2>
      <p>A script fetches every number on this page from the sources below and rebuilds the page each day. Every changing number comes from these sources; a few fixed facts, such as the food weight in the price index, were checked by hand on 25 October 2026. If a source fails, the page keeps its last good figure and says so. The code is open, under the MIT licence: <a href="https://github.com/ashishefe/lfe-india-economy">github.com/ashishefe/lfe-india-economy</a>.</p>
      <table class="num-table src-table"><thead><tr><th scope="col">Source</th><th scope="col">What we take</th><th scope="col">Latest data</th></tr></thead><tbody>{src_html}</tbody></table>
    </section>
  </main>

  <footer class="shell sketch-footer">
    <div><span>Built by Ashish Kulkarni. Built to be argued with.</span><nav aria-label="Footer"><a href="https://econforeverybody.com/">Blog ↗</a><a href="mailto:ashish@econforeverybody.com">Email me</a></nav></div>
    <p>Data fetched {esc(data["generated_at"].replace("T", " ").replace("+00:00", " UTC"))}.</p>
  </footer>
  <script>
    // If the daily refresh stops, say so: compare the fetch time with the reader's clock.
    (function () {{
      var fetched = new Date("{data["generated_at"]}");
      var days = (Date.now() - fetched.getTime()) / 86400000;
      if (days > 3) {{
        var b = document.getElementById("staleBanner");
        b.textContent = "These numbers were last fetched " + Math.floor(days) + " days ago. The daily update may have stopped.";
        b.hidden = false;
      }}
    }})();
  </script>
</body>
</html>
"""


REQUIRED = ["usdinr", "brent", "neer", "reer", "reserves", "reserves_fca", "credit_yoy", "deposit_yoy",
            "cpi_headline", "cpi_food", "cpi_headline_old", "cpi_food_old", "cpi_groups", "ur", "ur_youth",
            "gdp_growth", "pfce_growth", "gfcf_growth", "iip"]


def main() -> None:
    data = json.loads(DATA.read_text())
    missing = [k for k in REQUIRED if k not in data["series"]]
    if missing:
        raise SystemExit(f"Not building: no data yet for {', '.join(missing)}. Run fetch_data.py again.")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(data))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
