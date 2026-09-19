# Historical IEM–Fed Funds Futures Extension: 2002

## Status

Historical 2002 gap-safe econometric extension: COMPLETE FOR REVIEW

Full project econometrics ready: FALSE

This extension is kept separate from the primary modern high-frequency analysis.

## Sample

Eight 2002 FOMC meeting blocks were matched between Iowa Electronic Markets
FedPolicy contracts and explicit CBOT 30-Day Fed Funds futures contracts
obtained from Barchart.

Final gap-safe sample:

- FOMC meetings: 8
- matched market levels: 201
- valid revisions after gap screening: 179
- usable VAR(1) observations: 160
- VAR order: 1
- meeting fixed effects: included
- covariance estimator: meeting-block-aware HAC(6)
- lags across meeting boundaries: prohibited
- lags across unexplained observation gaps: prohibited
- announcement-day observations: excluded from pre-meeting estimation

## Directional tests

### Fed Funds futures -> IEM

beta = 0.744536
block-HAC(6) SE = 0.504054
t = 1.477
raw p = 0.139650
two-test historical Holm p = 0.139650

The directional null is not rejected at alpha = 0.05.

### IEM -> Fed Funds futures

beta = 0.020096
block-HAC(6) SE = 0.009818
t = 2.047
raw p = 0.040667
two-test historical Holm p = 0.081334

The coefficient is positive and the unadjusted test is below 0.05, but the
directional null is not rejected at alpha = 0.05 after the historical
two-test Holm adjustment.

This result must not be described as statistically significant under the
Holm-adjusted 5% criterion.

## Leave-one-meeting-out sensitivity

FF -> IEM coefficient range:
0.519161 to 0.841002

IEM -> FF coefficient range:
0.012359 to 0.033989

Both directional coefficients remain positive across all eight
leave-one-meeting-out specifications. Statistical significance varies with
the meeting excluded, so individual LOMO p-values are treated as sensitivity
diagnostics rather than alternative confirmatory specifications.

## Gap audit

The initial pooled panel contained 185 potential VAR observations.

A subsequent date-gap audit identified transitions containing unexplained
missing weekdays. These transitions were conservatively broken.

Final gap-safe VAR observations: 160.

Known market closures and standard weekend transitions were distinguished
from unexplained gaps. Unexplained gaps do not generate revisions or VAR
lags.

## November 2001 validation pilot

The preceding November 2001 source-checked pilot established the futures
acquisition procedure.

For ZQX01:

- 5 November implied rate: 2.165%
- 6 November implied rate: 2.085%
- raw change: -8.0 bp
- current-month scaling factor: 30/24 = 1.25
- scaled surprise: -10.0 bp

The independently obtained GSS monetary-policy surprise for 6 November 2001
is also -10.0 bp.

This provides an external cross-check on the historical futures acquisition
and transformation.

## Multiple-testing status

The values reported above use Holm adjustment across the two directional
tests within this historical 2002 extension.

The project's frozen primary design specifies Holm adjustment across four
directional tests. If the historical tests are ultimately included in that
same confirmatory family, the final project-wide Holm correction must be
recomputed jointly using all four raw p-values.

No significance threshold or testing family should be changed in response
to the observed historical results.

## Interpretation

The gap-safe 2002 historical extension does not reject either directional
Granger null at the 5% Holm-adjusted level.

The IEM -> Fed Funds coefficient is positive and provides suggestive
unadjusted evidence, but it does not survive the current Holm correction.

The results therefore do not establish that either market leads the other.
They provide a reproducible historical external-validity exercise across
eight independent FOMC meetings.

## Remaining limitations

- Daily historical observations are not directly comparable in frequency
  with the primary 15-minute modern design.
- Eight FOMC meetings remain a modest number of independent policy events.
- Some historical observation gaps remain unexplained and are therefore
  conservatively excluded.
- Historical Barchart open-interest values are not relied upon.
- Results depend on the audited IEM probability construction and
  positive-quantity carry convention.
