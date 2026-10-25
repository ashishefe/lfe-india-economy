#!/usr/bin/env python3
"""Fetch the numbers behind the India economy dashboard into data/india.json.

Standard library only, so a scheduled job can run it with a bare Python.
Each source is fetched on its own. If one fails, its last good copy is kept
and marked stale, so the page can say so instead of showing an old number
as if it were new.

Sources (all public, no keys):
  MoSPI eSankhyiki API   CPI, PLFS jobs, national accounts
  RBI weekly supplement  foreign-exchange reserves, bank credit
  FRED (St Louis Fed)    rupee per dollar, Brent crude
  BIS                    rupee against a basket of 64 currencies

Usage:  python3 scripts/fetch_data.py

Exit codes: 0 all sources fetched; 2 some sources failed and their last good
copies were kept, marked stale; anything else is a crash.
"""

from __future__ import annotations

import csv
import datetime as dt
import html
import io
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "india.json"
CACHE = ROOT / "cache"
# An honest name. FRED stalls requests that claim to be a desktop browser.
# Name your own project here (or set INDIA_ECONOMY_USER_AGENT) if you fork this.
UA = os.environ.get("INDIA_ECONOMY_USER_AGENT", "LFE-India-Dashboard/0.1 (+https://lfe.econforeverybody.com)")

# MoSPI's server still uses an old TLS renegotiation that Python refuses by
# default. We allow only that; certificate checks stay on.
MOSPI_CTX = ssl.create_default_context()
MOSPI_CTX.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def get(url: str, ctx: ssl.SSLContext | None = None, tries: int = 3) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as exc:  # network errors are retried, then raised
            if attempt == tries - 1:
                raise
            log(f"  retry {attempt + 1} for {url[:90]}: {exc}")
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")


def series(label, unit, freq, source, url, points, **extra):
    return {"label": label, "unit": unit, "freq": freq, "source": source,
            "source_url": url, "points": points, **extra}


# --------------------------------------------------------------------------
# FRED and BIS: plain CSV
# --------------------------------------------------------------------------

def fred(series_id: str, start: str) -> list:
    # The full-history download is quicker and more reliable than a date-filtered one.
    text = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}")
    rows = list(csv.reader(io.StringIO(text)))[1:]
    return [[d, round(float(v), 4)] for d, v in rows if d >= start and v not in (".", "")]


def bis_eer(kind: str, start: str) -> list:
    # kind: "N" nominal or "R" real; "B" = broad basket of 64 economies; 2020 = 100
    url = (f"https://stats.bis.org/api/v2/data/dataflow/BIS/WS_EER/1.0/M.{kind}.B.IN"
           f"?format=csv&startPeriod={start}")
    rows = list(csv.DictReader(io.StringIO(get(url))))
    return [[r["TIME_PERIOD"], float(r["OBS_VALUE"])] for r in rows if r.get("OBS_VALUE")]


# --------------------------------------------------------------------------
# MoSPI eSankhyiki API
# --------------------------------------------------------------------------

def mospi(path: str, **params) -> dict:
    params.setdefault("Format", "JSON")
    url = f"https://api.mospi.gov.in/api/{path}?{urllib.parse.urlencode(params)}"
    return json.loads(get(url, ctx=MOSPI_CTX))


def cpi_new_month(year: int, month: int) -> list:
    """All-India, rural+urban rows of the 2024-base CPI for one month.

    The API lists All-India rows first, so we page until another state appears.
    """
    rows, page = [], 1
    while True:
        d = mospi("cpi/getCPIData", base_year="2024", series="Current", year=year,
                  month_code=month, sector_code=3, limit=100, page=page)
        data = d.get("data") or []
        india = [x for x in data if x["state"] == "All India"]
        rows += india
        if len(india) < len(data) or page >= (d.get("meta_data") or {}).get("totalPages", 1):
            return rows
        page += 1


def cpi_old_headline(years: list[int]) -> dict:
    """Headline and food inflation from the 2012-base CPI (used up to Dec 2025)."""
    out = {"general": [], "food": []}
    for y in years:
        page = 1
        while True:
            d = mospi("cpi/getCPIIndex", base_year="2012", series="Current", year=y, limit=100, page=page)
            for x in d.get("data") or []:
                if x["state"] != "All India" or x["sector"] != "Combined" or x["inflation"] is None:
                    continue
                key = {"General-Overall": "general", "Consumer Food Price-Overall": "food"}.get(x["subgroup"])
                if key:
                    m = MONTHS.index(x["month"]) + 1
                    out[key].append([f"{x['year']}-{m:02d}", float(x["inflation"])])
            if page >= (d.get("meta_data") or {}).get("totalPages", 1):
                break
            page += 1
    for k in out:
        out[k] = sorted(set(map(tuple, out[k])))
        out[k] = [list(p) for p in out[k]]
    return out


# Finer CPI codes the page quotes: electricity, household gas, diesel, petrol, jewellery.
FINE_CODES = {"04.5.1", "04.5.2", "07.2.2", "07.2.2.1", "07.2.2.2", "13.2.1"}


def fetch_cpi(today: dt.date) -> dict:
    # Old series: 2024 and 2025. New series: every month from January 2026 on.
    old = cpi_old_headline([2024, 2025])
    new_rows = {}
    for y in range(2026, today.year + 1):
        for m in range(1, 13):
            if dt.date(y, m, 1) > today:
                break
            rows = cpi_new_month(y, m)
            if not rows:
                break  # this month is not out yet
            new_rows[f"{y}-{m:02d}"] = rows
            time.sleep(0.3)
    if not new_rows:
        raise ValueError("no 2024-base CPI rows returned")
    latest = max(new_rows)

    def pick(rows, code):
        for x in rows:
            if (x["code"] or "") == code:
                return x
        return None

    def track(code):
        pts = []
        for ym, rows in sorted(new_rows.items()):
            x = pick(rows, code)
            if x and x["inflation"] is not None:
                pts.append([ym, float(x["inflation"])])
        return pts

    groups = []
    for x in new_rows[latest]:
        code = x["code"] or ""
        if x["division"] == "CPI (General)" or re.fullmatch(r"\d\d(\.\d)?", code) or code in FINE_CODES:
            name = x["sub_class"] or x["class"] or x["group"] or x["division"]
            groups.append({"code": code or "00", "name": name, "division": x["division"],
                           "index": float(x["index"]), "inflation": float(x["inflation"])})

    url = "https://esankhyiki.mospi.gov.in/"
    return {
        "cpi_headline_old": series("CPI inflation, 2012 base", "% y/y", "M", "MoSPI (NSO)", url, old["general"]),
        "cpi_food_old": series("Consumer food price inflation, 2012 base", "% y/y", "M", "MoSPI (NSO)", url, old["food"]),
        "cpi_headline": series("CPI inflation, 2024 base", "% y/y", "M", "MoSPI (NSO)", url, track("")),
        "cpi_food": series("Food and beverages, 2024 base", "% y/y", "M", "MoSPI (NSO)", url, track("01")),
        "cpi_groups": {"label": "CPI by division and group, 2024 base", "month": latest,
                       "source": "MoSPI (NSO)", "source_url": url, "rows": groups},
    }


def fetch_plfs(today: dt.date) -> dict:
    url = "https://esankhyiki.mospi.gov.in/"

    def monthly(indicator, **codes):
        pts = []
        for y in range(2025, today.year + 1):
            d = mospi("plfs/getData", indicator_code=indicator, frequency_code=3, year=y,
                      state_code=99, limit=100, **codes)
            for x in d.get("data") or []:
                if x.get("value") in (None, "", "-"):
                    continue
                m = MONTHS.index(x["month"]) + 1
                pts.append([f"{x['year']}-{m:02d}", float(x["value"])])
        return sorted(pts)

    base = dict(gender_code=3, sector_code=3, age_code=1)
    out = {
        "ur": series("Unemployment rate, age 15+", "%", "M", "MoSPI PLFS (monthly)", url, monthly(3, **base)),
        "ur_youth": series("Unemployment rate, age 15–29", "%", "M", "MoSPI PLFS (monthly)", url,
                           monthly(3, gender_code=3, sector_code=3, age_code=2)),
        "ur_rural": series("Unemployment rate, rural, age 15+", "%", "M", "MoSPI PLFS (monthly)", url,
                           monthly(3, gender_code=3, sector_code=1, age_code=1)),
        "ur_urban": series("Unemployment rate, urban, age 15+", "%", "M", "MoSPI PLFS (monthly)", url,
                           monthly(3, gender_code=3, sector_code=2, age_code=1)),
        "ur_female": series("Unemployment rate, women, age 15+", "%", "M", "MoSPI PLFS (monthly)", url,
                            monthly(3, gender_code=2, sector_code=3, age_code=1)),
        "lfpr": series("Labour force participation rate, age 15+", "%", "M", "MoSPI PLFS (monthly)", url, monthly(1, **base)),
        "wpr": series("Worker population ratio, age 15+", "%", "M", "MoSPI PLFS (monthly)", url, monthly(2, **base)),
        "lfpr_female": series("Labour force participation rate, women, age 15+", "%", "M", "MoSPI PLFS (monthly)", url,
                              monthly(1, gender_code=2, sector_code=3, age_code=1)),
    }
    return out


def fetch_nas() -> dict:
    url = "https://esankhyiki.mospi.gov.in/"
    qorder = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}

    def quarterly(indicator):
        d = mospi("nas/getNASData", base_year="2022-23", series="Current", frequency_code="Quarterly",
                  indicator_code=indicator, limit=100)
        rows = []
        for x in d.get("data") or []:
            if x.get("constant_price") in (None, ""):
                continue
            rows.append({"fy": x["year"], "q": x["quarter"], "revision": x.get("revision"),
                         "real": float(x["constant_price"]), "nominal": float(x["current_price"])})
        rows.sort(key=lambda r: (r["fy"], qorder[r["q"]]))
        return rows

    def label(r):
        return f"{r['fy']} {r['q']}"

    def growth_from_levels(rows):
        by = {(r["fy"], r["q"]): r["real"] for r in rows}
        pts = []
        for r in rows:
            start = int(r["fy"][:4]) - 1
            prev = by.get((f"{start}-{str(start + 1)[2:]}", r["q"]))
            if prev:
                pts.append([label(r), round(100 * (r["real"] / prev - 1), 1)])
        return pts

    gdp = quarterly(22)
    pfce = quarterly(10)
    gfcf = quarterly(9)
    return {
        "gdp_growth": series("Real GDP growth", "% y/y", "Q", "MoSPI national accounts, 2022-23 base", url,
                             [[label(r), r["real"]] for r in gdp],
                             nominal=[[label(r), r["nominal"]] for r in gdp]),
        "pfce_growth": series("Real private consumption growth", "% y/y", "Q",
                              "MoSPI national accounts, 2022-23 base (our calculation from levels)", url,
                              growth_from_levels(pfce)),
        "gfcf_growth": series("Real investment (fixed capital) growth", "% y/y", "Q",
                              "MoSPI national accounts, 2022-23 base (our calculation from levels)", url,
                              growth_from_levels(gfcf)),
    }


# --------------------------------------------------------------------------
# RBI Weekly Statistical Supplement (plain HTML extract pages)
# --------------------------------------------------------------------------

WSS_LIST = "https://www.rbi.org.in/Scripts/BS_viewWssExtract.aspx?SelectedDate={d}"


def wss_text(release: dt.date) -> str | None:
    """Text of one weekly extract. Past weeks are cached; the newest is always refetched."""
    CACHE.mkdir(exist_ok=True)
    f = CACHE / f"wss-{release.isoformat()}.txt"
    if f.exists() and (dt.date.today() - release).days > 14:
        return f.read_text()
    raw = get(WSS_LIST.format(d=release.strftime("%m/%d/%Y")))
    raw = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S)
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))
    if "Total Reserves" not in text:
        return None  # no release on this date (holiday) or page changed
    f.write_text(text)
    return text


def parse_date(s: str) -> str:
    s = re.sub(r"\bSept\b", "Sep", s.replace(".", ""))
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return dt.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(s)


NUM = r"(-?[\d.]+)"


def parse_wss(text: str) -> dict:
    out = {}
    m = re.search(r"Foreign Exchange Reserves\* Item As on ([A-Z][a-z]+\.? \d+, \d{4})", text)
    if m:
        out["fx_date"] = parse_date(m.group(1))
        for key, pat in (("total", r"1 Total Reserves"), ("fca", r"1\.1 Foreign Currency Assets #?"),
                         ("gold", r"1\.2 Gold")):
            r = re.search(pat + r" " + " ".join([NUM] * 4), text)
            if r:
                out[key] = int(r.group(2))          # US$ million
                out[key + "_week"] = int(r.group(4))
    m = re.search(r"Outstanding as on ([A-Z][a-z]+\.? \d+, \d{4})", text)
    c = re.search(r"7\.1a Growth \(Per cent\) " + " ".join([NUM] * 5), text)
    if m and c:
        out["credit_date"] = parse_date(m.group(1))
        out["credit_yoy"] = float(c.group(5))
        out["credit_yoy_prev"] = float(c.group(4))  # RBI's own figure for a year earlier
    d = re.search(r"2\.1a Growth \(Per cent\) " + " ".join([NUM] * 5), text)
    if m and d:
        out["deposit_yoy"] = float(d.group(5))
        out["deposit_yoy_prev"] = float(d.group(4))
    return out


def fetch_rbi(today: dt.date, weeks: int = 60) -> dict:
    # Releases come out on Fridays; a holiday moves one, so try Thursday too.
    friday = today - dt.timedelta(days=(today.weekday() - 4) % 7)
    weekly = {}
    credit = {}
    for i in range(weeks):
        day = friday - dt.timedelta(weeks=i)
        text = None
        for d in (day, day - dt.timedelta(days=1)):
            try:
                text = wss_text(d)
            except Exception as exc:
                log(f"  WSS {d}: {exc}")
            if text:
                break
            time.sleep(0.4)
        if not text:
            log(f"  WSS: no release found for week of {day}")
            continue
        p = parse_wss(text)
        if "total" in p:
            weekly[p["fx_date"]] = p
        if "credit_yoy" in p:
            credit[p["credit_date"]] = (p["credit_yoy"], p.get("deposit_yoy"),
                                        p["credit_yoy_prev"], p.get("deposit_yoy_prev"))
        time.sleep(0.4)
    dates = sorted(weekly)
    url = "https://www.rbi.org.in/Scripts/BS_viewWssExtract.aspx"
    return {
        "reserves": series("Foreign-exchange reserves", "US$ bn", "W", "RBI Weekly Statistical Supplement", url,
                           [[d, round(weekly[d]["total"] / 1000, 2)] for d in dates]),
        "reserves_fca": series("Foreign currency assets", "US$ bn", "W", "RBI Weekly Statistical Supplement", url,
                               [[d, round(weekly[d]["fca"] / 1000, 2)] for d in dates if "fca" in weekly[d]]),
        "reserves_gold": series("Gold reserves", "US$ bn", "W", "RBI Weekly Statistical Supplement", url,
                                [[d, round(weekly[d]["gold"] / 1000, 2)] for d in dates if "gold" in weekly[d]]),
        "credit_yoy": series("Bank credit growth", "% y/y", "F", "RBI Weekly Statistical Supplement", url,
                             [[d, credit[d][0]] for d in sorted(credit)],
                             year_earlier=[[d, credit[d][2]] for d in sorted(credit)]),
        "deposit_yoy": series("Bank deposit growth", "% y/y", "F", "RBI Weekly Statistical Supplement", url,
                              [[d, credit[d][1]] for d in sorted(credit) if credit[d][1] is not None],
                              year_earlier=[[d, credit[d][3]] for d in sorted(credit) if credit[d][3] is not None]),
    }


# --------------------------------------------------------------------------

def fetch_iip(today: dt.date) -> dict:
    """Index of industrial production, 2022-23 base (published from 2026)."""
    pts = []
    for y in range(2025, today.year + 1):
        page = 1
        while True:
            d = mospi("iip/getIIPMonthly", base_year="2022-23", year=y, limit=200, page=page)
            for x in d.get("data") or []:
                if x["type"] == "General" and x["category"] == "General" and x.get("growth_rate") not in (None, ""):
                    pts.append([f"{x['year']}-{MONTHS.index(x['month']) + 1:02d}", float(x["growth_rate"])])
            if page >= (d.get("meta_data") or {}).get("totalPages", 1):
                break
            page += 1
    pts = [list(p) for p in sorted(set(map(tuple, pts)))]
    return {"iip": series("Industrial production growth", "% y/y", "M", "MoSPI IIP, 2022-23 base",
                          "https://esankhyiki.mospi.gov.in/", sorted(pts))}


def fetch_fred(today: dt.date) -> dict:
    start = (today - dt.timedelta(days=800)).isoformat()
    return {
        "usdinr": series("Rupees per US dollar", "₹", "D", "FRED (Federal Reserve H.10, noon New York)",
                         "https://fred.stlouisfed.org/series/DEXINUS", fred("DEXINUS", start)),
        "brent": series("Brent crude", "US$ per barrel", "D", "FRED (US EIA)",
                        "https://fred.stlouisfed.org/series/DCOILBRENTEU", fred("DCOILBRENTEU", start)),
    }


def fetch_bis(today: dt.date) -> dict:
    start = (today - dt.timedelta(days=800)).isoformat()
    return {
        "neer": series("Rupee against 64 currencies, nominal", "index, 2020 = 100", "M", "BIS effective exchange rates",
                       "https://data.bis.org/topics/EER", bis_eer("N", start[:7])),
        "reer": series("Rupee against 64 currencies, adjusted for inflation", "index, 2020 = 100", "M",
                       "BIS effective exchange rates", "https://data.bis.org/topics/EER", bis_eer("R", start[:7])),
    }


def main() -> int:
    today = dt.date.today()
    old = json.loads(OUT.read_text()) if OUT.exists() else {"series": {}}
    result = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "series": {}, "errors": {}}
    jobs = [("fred", lambda: fetch_fred(today)), ("bis", lambda: fetch_bis(today)),
            ("rbi", lambda: fetch_rbi(today)), ("cpi", lambda: fetch_cpi(today)),
            ("plfs", lambda: fetch_plfs(today)), ("nas", fetch_nas), ("iip", lambda: fetch_iip(today))]
    for name, job in jobs:
        log(f"fetching {name} …")
        try:
            got = job()
            # An empty series is a failure too, so the last good copy is kept.
            empty = [k for k, v in got.items() if "points" in v and not v["points"]]
            if empty:
                raise ValueError(f"no data for {', '.join(empty)}")
            for k, v in got.items():
                v["fetched_at"] = result["generated_at"]
                v["stale"] = False
            result["series"].update(got)
        except Exception as exc:
            log(f"  {name} FAILED: {exc!r}; keeping last good copy")
            result["errors"][name] = repr(exc)
            for k, v in old["series"].items():
                if v.get("group") == name:
                    result["series"][k] = {**v, "stale": True}
            continue
        for k in got:
            result["series"][k]["group"] = name
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    log(f"wrote {OUT} ({len(result['series'])} series, {len(result['errors'])} errors)")
    return 2 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
