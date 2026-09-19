# AutoResearch Experiment 003: Relative Circular-Shift Placebo

## Question

Can the historical VAR(1) coefficients survive a placebo that preserves each
market's within-meeting revision sequence while disrupting the temporal
alignment between IEM and Fed Funds futures?

## Design

Within each of the eight meetings, IEM revisions remain in their original
order. The Fed Funds revision sequence is circularly shifted relative to IEM.

The procedure preserves each market's marginal distribution and circular
serial ordering, meeting identity, meeting fixed effects, and exactly the 160
baseline VAR rows. It changes the relative temporal alignment between markets.

1,000 placebo draws were generated with seed 3151.

## Results

### FF -> IEM

Baseline beta: 0.744536

Placebo mean: -0.038579

Placebo standard deviation: 0.875340

Placebo estimates at least as large as baseline: 204 / 1,000

Empirical one-sided p-value: 0.204

Plus-one corrected p-value: 0.204795

### IEM -> FF

Baseline beta: 0.020096

Placebo mean: -0.000799

Placebo standard deviation: 0.019681

Placebo estimates at least as large as baseline: 158 / 1,000

Empirical one-sided p-value: 0.158

Plus-one corrected p-value: 0.158841

## Interpretation

Neither directional coefficient is unusual under this circular-shift placebo.

The result therefore does not provide strong evidence that the observed
cross-market VAR(1) coefficients identify genuine temporal price discovery in
this eight-meeting historical sample.

This conclusion agrees with Experiment 002. The unrestricted within-meeting
permutation produced empirical p-values of 0.198 for FF -> IEM and 0.117 for
IEM -> FF. The more structure-preserving circular-shift placebo produces
0.204 and 0.158 respectively.

The convergence of these falsification exercises is important. The positive
baseline coefficients are real features of the observed sample, but similarly
large coefficients occur with non-negligible frequency after the relevant
cross-market timing relationship is disrupted.

The historical eight-meeting analysis should therefore be presented as a
stress test, not as independent confirmation that either market systematically
prices the Fed first.

## Scaling guardrail

The raw coefficients 0.7445 and 0.0201 are not directly comparable measures
of economic importance because the IEM and Fed Funds revision variables use
different units and scales. Their numerical magnitude alone cannot establish
which market has the larger economic effect.

## Falsification verdict

The eight-meeting historical VAR(1) lead-lag signal does not survive the
temporal placebo evidence strongly enough to support a standalone price
discovery claim.
