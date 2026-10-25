# How is India's economy doing?

A one-page dashboard that answers four questions with the latest official numbers:

1. What is the rupee telling us?
2. Is inflation inside the RBI's band, and what is driving it?
3. Is growth reaching people?
4. Are jobs being created?

Live at **https://lfe.econforeverybody.com/experiments/india-economy/**, part of the [Experiments](https://lfe.econforeverybody.com/experiments/) on Learn For Everybody. The idea came from Jason Furman's [econvitals.org](https://econvitals.org/) for the US; the questions are India's own.

This repo exists so you can take it and do better. See [Do better](#do-better) below.

## Run it

You need Python 3.10 or newer. Nothing to install: the scripts use only the standard library.

```bash
python3 scripts/fetch_data.py
python3 scripts/build_page.py
python3 -m http.server 8000 --directory site
```

Then open http://localhost:8000/experiments/india-economy/

The first fetch takes a few minutes: it reads about 60 weekly RBI pages, politely, one at a time, and caches them in `cache/`.

The links in the top bars point to the rest of Learn For Everybody, so they only work on the live site, not on your computer.

## How it works

```
scripts/fetch_data.py  →  data/india.json                      every number, with its source and date
scripts/build_page.py  →  site/experiments/india-economy/index.html   plain HTML, charts drawn as SVG
```

The page needs no JavaScript to show its numbers and charts. If a source fails, the fetcher keeps the last good copy and marks it stale, and the page says so instead of passing an old number off as new.

| Source | What we take |
|---|---|
| MoSPI eSankhyiki API (`api.mospi.gov.in`) | Consumer prices (2024 base, and the 2012 base to December 2025), the monthly jobs survey (PLFS), quarterly GDP (2022-23 base), industrial production (2022-23 base) |
| RBI Weekly Statistical Supplement (`www.rbi.org.in`) | Foreign-exchange reserves, bank credit and deposits |
| FRED, Federal Reserve Bank of St Louis | Rupees per dollar (series DEXINUS), Brent crude (DCOILBRENTEU) |
| Bank for International Settlements | The rupee against a basket of 64 currencies, nominal and real |

Things that will save you an afternoon:

- MoSPI's server uses an old TLS handshake that Python refuses by default. `fetch_data.py` allows only that, and keeps certificate checks on.
- MoSPI's API pages its results. Always loop over `totalPages`; one bug here hid months of data.
- FRED stalls requests that pretend to be a web browser. Name your script honestly in the user agent.
- The RBI's document server (`rbidocs.rbi.org.in`) runs a bot check. Do not try to get round it. The plain web pages on `www.rbi.org.in` carry the same weekly tables.
- Change the user agent in `fetch_data.py` to name your own project.

## Do better

These are real gaps, found while building and reviewing this page. Each would make a good project.

1. **Split inflation into food, fuel and the rest.** India publishes no official "core" inflation. Doing it properly needs the weight of each item in the 2024-base basket, which this page does not yet use.
2. **Measure pressure on the rupee properly.** The page reads the rupee and the RBI's foreign currency assets side by side. An exchange-market-pressure index would combine them, after removing changes in the dollar value of the other currencies and bonds the RBI holds.
3. **Nowcast this quarter's growth.** The US has several free, regularly updated estimates of current-quarter GDP. India has none in a form a script can read.
4. **Is growth reaching people?** The page admits it has no good monthly answer. Wages, rural spending and two-wheeler sales are candidates.
5. **Government finances.** Left out on purpose: off-budget borrowing, one-off schemes, the RBI's dividend and the Centre–state split make any single monthly number misleading. Can you build an honest yearly view?
6. **A question the page leaves for you:** why can't the RBI hold the rupee steady, set its own interest rates and let money move freely across borders, all at once? Economists call this the impossible trinity. The rupee section shows it happening.

## What we got wrong

See [WHAT-WE-GOT-WRONG.md](WHAT-WE-GOT-WRONG.md). The corrections teach more about checking work than the finished page does.

## How this was made

Ashish Kulkarni chose the questions and made the judgment calls (making the rupee a question, leaving government finances out). Claude, an AI model, wrote the code and the first draft of the text. Independent AI reviewers, which had not built it, checked the numbers against the sources and hunted for bugs, and found real errors. That loop, build, steer, check, is the method.

## Licence

- **Code** (everything in `scripts/`, and the CSS and JavaScript in `site/`): [MIT](LICENSE).
- **Words** (this README, the other documents here, and the page's sentences, even where they sit inside `scripts/build_page.py`): [CC BY 4.0](LICENSE-TEXT.md). Reuse them with credit to Ashish Kulkarni / Learn For Everybody.
- **Data** belongs to its publishers: MoSPI, the Reserve Bank of India, the Federal Reserve Bank of St Louis (FRED) and the US EIA, and the BIS. This repo holds the code that fetches it, not copies of it. Follow each source's terms and credit them.

The page's look comes from the Learn For Everybody house style (`site/assets/`), included so the page renders. Feel free to replace it with your own.
