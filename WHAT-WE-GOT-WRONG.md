# What we got wrong

Every error below was in a working draft of this page in October 2026, and was caught before or soon after release by an independent review: a fresh AI reviewer that had not built the page, checking numbers against the sources and reading the code for bugs. They are here because how a mistake was caught teaches more than the finished page.

## Claims

**"MoSPI's data service does not yet carry the new industrial production series."** False. It did, under a different endpoint. We had looked in the wrong place and written down a guess as a fact. *Lesson: "I could not find it" is not "it does not exist".*

**The reserves story was built on one strange week.** The first draft measured the fall in reserves from their peak in the past year. That peak was set by a single week in which the RBI's foreign currency assets jumped $47.5 billion, for reasons its weekly figures do not give. Measured from just before that week, the fall was much smaller, and reserves were *up* on the year, which the page's own table showed. The page now names the jump and measures from it. *Lesson: before you measure from a peak, ask what made the peak.*

**"A weaker rupee feeds straight into gold and fuel prices."** Overclaimed. Crude oil cost 104% more in rupees than a year earlier, but petrol cost only 7.5% more and diesel 8.4% more, because pump prices in India are set mostly by state-run oil companies and by taxes. Electricity, priced by state regulators, fell. Jewellery rose 43%, far more than the rupee fell. The page now reports the price moves and leaves the causes to the evidence. *Lesson: a mechanism in a textbook is a hypothesis about a country until the data agree.*

**"The fastest rise was in jewellery."** True only at one level of detail. At finer levels, onions (108%) and silver jewellery (88%) rose faster. And the sentence was typed by hand, on a page that promises every claim comes from data. *Lesson: superlatives need the same checking as numbers.*

**"Bank credit grew 11.4% a year earlier."** We estimated the year-earlier figure from the nearest week we had. The RBI prints its own figure in the same table: 11.6%. *Lesson: if the source gives you the comparison, use it.*

## Code

**The page would have broken in January.** The script fetched consumer prices only for the current year and jobs data only for 2025 and 2026. On 1 January 2027 the inflation section would have failed and the jobs section would have stopped updating, silently.

**Industrial production showed half its months.** MoSPI's API returns results in pages. The script read only the first page, so January to July 2025 and January to March 2026 were missing. The headline number happened to be right, by luck. Once the year-earlier month moved to page two, the "year earlier" figure would quietly have compared the wrong months.

**An empty answer was treated as success.** If a source returned no data rather than an error, the script stored an empty series and the page crashed, instead of keeping the last good copy and flagging it.

**"Sepember".** A one-line fix to turn "Sept." into "Sep" also turned "September" into "Sepember", and the RBI parser failed on every page from that month.

**Pretending to be a browser backfired.** FRED quietly stalls requests whose user agent claims to be Chrome. Naming the script honestly fixed it.
