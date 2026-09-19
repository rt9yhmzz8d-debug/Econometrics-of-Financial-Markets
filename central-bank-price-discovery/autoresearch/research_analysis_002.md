# AutoResearch Experiment 002: Within-Meeting Temporal Permutation Test

## Purpose

This experiment tests whether the baseline VAR(1) lead-lag coefficients are unusually large relative to a placebo distribution in which temporal ordering is destroyed within each FOMC meeting.

The test is deliberately adversarial. It preserves the meeting structure and empirical distribution of the observations while removing the chronological ordering required for genuine lead-lag price discovery.

## Baseline

The frozen baseline contains 160 usable VAR observations across eight meetings.

- FF -> IEM beta: 0.744536
- IEM -> FF beta: 0.020096

The experiment successfully reproduced both baseline coefficients before performing any permutations.

## Permutation design

1,000 independent temporal permutations were generated using seed 3150.

Observations were permuted strictly within meeting blocks. The resulting placebo samples therefore destroy the observed temporal ordering without pooling observations across different FOMC meetings.

The baseline VAR(1) structure and meeting fixed effects were then re-estimated on each placebo sample.

## Results

### FF -> IEM

- Baseline beta: 0.744536
- Placebo mean: -0.040673
- Placebo standard deviation: 0.888266
- Placebo coefficients >= baseline: 198 / 1000
- Empirical p-value: 0.198000
- Plus-one corrected p-value: 0.198801

### IEM -> FF

- Baseline beta: 0.020096
- Placebo mean: -0.001252
- Placebo standard deviation: 0.017714
- Placebo coefficients >= baseline: 117 / 1000
- Empirical p-value: 0.117000
- Plus-one corrected p-value: 0.117882

## Interpretation

Neither directional coefficient is unusually large relative to the corresponding within-meeting temporal placebo distribution at conventional significance levels.

The FF -> IEM coefficient is exceeded by approximately 19.8% of placebo estimates. The IEM -> FF coefficient is exceeded by approximately 11.7%.

This materially weakens a temporal price-discovery interpretation of the historical eight-meeting sample. In particular, the IEM -> FF coefficient previously appeared comparatively precise under some asymptotic HAC specifications, but the permutation test shows that a coefficient at least as large as the observed estimate occurs with non-negligible frequency after the within-meeting temporal ordering is destroyed.

Accordingly, the historical validation sample does not provide robust evidence that either market systematically leads the other.

This result should not be hidden or replaced by a more favourable specification. It is a substantive falsification result and should be reported alongside the HAC and leave-one-meeting-out robustness analysis.

## Scaling caveat

The raw coefficients 0.7445 and 0.0201 should not be directly interpreted as evidence that one directional economic effect is approximately 37 times larger than the other.

The two VAR equations use dependent variables measured on different scales. Raw cross-equation coefficient magnitudes therefore combine the underlying relationship with the units and variance of the variables.

A direct comparison of economic magnitudes would require standardisation or transformation to a common scale.

## Conclusion

Experiment 002 does not support a robust temporal lead-lag relationship in the eight-meeting historical validation sample.

The coefficient signs observed in the original data may be stable across several conventional specifications, but stability of sign is insufficient evidence of temporal price discovery when coefficients of comparable magnitude can arise with non-negligible probability after chronological ordering is destroyed.

This result strengthens the case for describing the eight-meeting analysis as a stress test rather than independent confirmation of the main study.
