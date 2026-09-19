# AutoResearch Experiment 004: Observation influence

## Question

Are the historical VAR(1) cross-market coefficients driven by one or a small number of individual observations?

## Design

Starting from the frozen 160-row historical VAR sample, remove each usable observation one at a time and re-estimate the system.

For each deletion, record the resulting FF-to-IEM and IEM-to-FF cross-lag coefficients and their change relative to the full-sample baseline.

## Results

Baseline FF-to-IEM coefficient: 0.744536.

The largest absolute leave-one-out change is 0.444310. No individual observation deletion reverses the sign of the coefficient.

Baseline IEM-to-FF coefficient: 0.020096.

The largest absolute leave-one-out change is 0.008775. No individual observation deletion reverses the sign of the coefficient.

Influence is concentrated disproportionately in observations associated with meeting family 51:1102, which contributes only nine usable VAR rows.

## Interpretation

The directional signs of both historical cross-lag coefficients are not artifacts of a single observation. However, coefficient magnitudes, particularly FF-to-IEM, are meaningfully sensitive to some individual observations.

This complements the permutation and circular-shift falsification experiments. The historical directional estimates are resistant to single-row deletion, but the broader evidence for temporal price discovery remains weak under placebo timing tests.

The eight-meeting historical exercise should therefore remain characterised as a robustness stress test rather than independent confirmation of the main study.
