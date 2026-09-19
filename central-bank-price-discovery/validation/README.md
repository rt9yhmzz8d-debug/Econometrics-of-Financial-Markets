# Round 4 validation and one-meeting example

This layer checks the acquisition at commit
e5928a751856e59816342085dd76f33a8ac5ee79 before any estimation.
It leaves the original downloader, cached HTML and six result CSVs intact.

The research question is whether earlier changes in one market improve
prediction of subsequent changes in the other. The first requirement is a
defensible pair of measurements for the same policy event.

## Run

From the repository root, using Python 3.9 or later:

    python3 central-bank-price-discovery/validation/audit_round4.py
    python3 -m unittest discover -s central-bank-price-discovery/validation -p 'test_*.py' -v

The audit uses only the Python standard library. To make a downstream job
stop while econometrics is unapproved:

    python3 central-bank-price-discovery/validation/audit_round4.py --require-ready

An ordinary audit exits 0 after generating the diagnostics. The required-ready
command currently exits 2. This scaffold has no path that authorizes estimation:
it documents unresolved checks and does not fit models.

## Reproduced acquisition facts

| Check | Result |
| --- | ---: |
| HTTP-successful monthly requests | 312 |
| Requests containing rows | 196 |
| Raw / clean observations | 31,668 / 31,667 |
| Contracts | 353 |
| Families in total | 113 |
| Meeting-interval families | 107 |
| Quarterly families | 6 |
| Rows in quarterly families | 5,262 |
| Ordinary meeting-interval families after excluding quarterly and split families | 101 |
| Rows in those 101 families | 24,977 |
| Zero reported quantity rows | 19,510 |
| Zero-quantity rows with changed last price | 263 |
| Contracts affected by those changes | 98 |

The six quarterly families retain the Q suffix and have their own comparison
horizon. They cannot be silently counted as ordinary single-interval contracts.
The parser also retains distinct market IDs and recognizes the quarterly
dwn/sam spellings.

There are four families with no positive reported quantity anywhere:
51:0717, 51:0917, 51:1017 and 51:1217. This does not establish their meeting
mapping or prove that the source volume field is complete.

## An unresolved issue in the source, not just the CSV

The cached October 2001 HTML defines LastPrice as the last trade before midnight.
Nevertheless, on 4 October, the three pilot contracts show zero Units and zero
Dollar Volume, while their last prices change from the preceding day's values:

| Contract | 3 October | 4 October | Reported units on 4 October |
| --- | ---: | ---: | ---: |
| FRdown1101 | 0.550 | 0.571 | 0 |
| FRsame1101 | 0.550 | 0.485 | 0 |
| FRup1101 | 0.065 | 0.002 | 0 |

These values are present in the cached IEM HTML. They require clarification of
the historical price/volume fields. They are not proof that no trades occurred,
and a reported zero cannot safely establish freshness.

The expanded anomaly register separates 16 old quarterly contracts that
reappear on 1 June 2016 as all-zero rows after gaps of 566 to 1,357 days. Those
are excluded with the quarterly horizon rather than treated as fresh price
events. The other 247 changed-price rows are meeting-interval contracts. All
263 report zero dollar volume, while 208 also report a nonzero daily low or
high. That combination confirms a source-field interpretation problem: it
cannot be repaired by relabelling every zero-unit row as a simple carry-forward.

## Market-rule boundary

The IEM prospectus states that FedPolicyB replaced FedPolicy, which operated
from October 1999 through August 2001, and that the two markets differ in their
treatment of inter-meeting target changes. For FedPolicyB, the same prospectus
defines the outcome using the cumulative target change from the day after the
preceding scheduled meeting through the period-ending scheduled meeting, and
uses the midpoint when the target is an interval.

The surviving FedPolicyB document does not state the earlier FedPolicy rule.
Therefore the 15 Market 20 families remain excluded until the original
prospectus or an equivalent contemporaneous IEM source is found. Applying the
FedPolicyB rule retrospectively would create an unsupported mapping.

The diagnostic carries only prices from positive-quantity rows, with a maximum
age of three calendar days. That is a conservative screening assumption, not a
resolution of the inconsistency. It checks the raw three-price sum against
1 +/- 0.10 before normalization. Passing this screen never means model-ready.

## Source-checked pilot: 6 November 2001

The IEM FedPolicyB prospectus explicitly names FRdown1101, FRsame1101 and
FRup1101, the 6 November meeting, and the initial 3 October reference date.
The contracts distinguish a lower, unchanged or higher target rate, paying
USD 1 for the realized category. The Federal Reserve calendar independently
confirms the meeting date.

The pilot has 108 contract rows and 36 daily snapshots. Under the diagnostic
rules, 32 days pass, two fail coherence and two are meeting-day or later.
The 32 include calendar days: they are not 32 paired futures observations or
model rows. The complete announcement date is excluded because these data
contain no intraday trade timestamps.

The directional score is 100 times (p_up - p_down), measured in probability
points. It is not an expected basis-point move. No matching futures series is
supplied or estimated by this layer.

## What still needs checking

1. Resolve the source price/volume inconsistency and verify the daily time zone
   and close convention before synchronizing with futures.
2. Source-check the remaining family definitions and meeting assignments.
   FedPolicy and FedPolicyB differ in their intermeeting treatment.
   Names and last observed trading dates are not sufficient evidence.
3. Find the actual spin-off notices for 20:0300, 20:0500, 20:0501, 51:1201,
   51:1008 and 51:1208. The generic prospectus example is not the actual notice
   for any of these events. Record effective dates and exclusive payoff ranges
   before replacing a parent with its children. Do not double count or infer
   exact magnitudes from names such as 25 or 50.
4. Keep quarterly families separate. Calendar-month ambiguities also need
   inspection: the 2017 meetings on 31 January-1 February and
   31 October-1 November cross month boundaries.
5. Obtain matched futures data with contract month, observation date/time,
   time zone, price type, source and units. For the November pilot, inspect
   the December 2001 delivery contract as the next-month candidate, rather
   than a back-adjusted continuous series. Verify what that settlement
   average measures and any additional policy meetings inside its horizon.
6. Build the paired pre-announcement sample, count surviving independent
   meetings, and form lags only within valid contiguous blocks. Then reproduce
   the declared predictive models and uncertainty estimates.

One worked meeting explains construction. A lead-lag conclusion needs the
validated multi-meeting sample and inference that accounts for dependence.

## Files

- source_checks.json is the editable source-review record. Regeneration does
  not overwrite it. It records one checked family, not approval of the project.
- generated/contract_register.csv inventories all 353 contracts.
- generated/family_register.csv records horizon, split status and next checks.
- Its analysis_gate column keeps quarterly, split and definition-unreviewed
  families out of downstream estimation by construction.
- generated/zero_quantity_price_changes.csv identifies every flagged row and
  its source URL.
- generated/pilot_2001_11_06.csv contains the raw pilot series and explicitly
  labelled diagnostic screening outputs.
- generated/audit_summary.json records counts, the input/review hashes and
  outstanding requirements.
- build_worked_example.py renders a one-page PDF from these outputs. It needs
  matplotlib and reportlab, separately from the dependency-free audit.

Generated files are disposable; review edits belong in source_checks.json.
The input hash changes if acquisition bytes change. The gate remains closed
until the complete validation and matching procedure is implemented and checked.

## Primary sources

- [IEM FedPolicyB prospectus](https://iemweb.biz.uiowa.edu/iem_prospectus/federal-reserve-monetary-policy-market-b/)
- [October 2001 IEM price history](https://iemweb.biz.uiowa.edu/iem_pricehistory/pricehistory/?Market_ID=51&Month=October&Year=2001)
- [Federal Reserve 2001 calendar](https://www.federalreserve.gov/monetarypolicy/fomchistorical2001.htm)
- [Federal Reserve 2017 calendar](https://www.federalreserve.gov/monetarypolicy/fomchistorical2017.htm)
- [6 November 2001 statement](https://www.federalreserve.gov/boarddocs/press/general/2001/20011106/)
- [CME explanation of Fed funds futures](https://www.cmegroup.com/education/courses/understanding-stir-futures/introduction-to-fed-fund-futures)
