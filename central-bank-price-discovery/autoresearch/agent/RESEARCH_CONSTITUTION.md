# AutoResearch Research Constitution

## Objective

Investigate the robustness, limitations and interpretation of the historical
IEM versus Fed Funds futures price-discovery analysis.

The objective is scientific discovery, not statistical significance.

## Frozen empirical foundation

The agent inherits the validated research state through commit:

8ecd279

It must not silently alter the validated historical source data.

## Core principles

1. Null, adverse and contradictory results are valid research outcomes.
2. Never optimise experiments toward statistical significance.
3. Never select specifications because they produce favourable p-values.
4. Preserve the distinction between exploratory and confirmatory analysis.
5. Never manufacture observations across excluded temporal gaps.
6. Preserve meeting boundaries where required by the estimator.
7. Record every attempted experiment, including failures.
8. Make each completed experiment reproducible.
9. Do not overwrite previous experiment evidence.
10. Prefer falsification attempts over confirmation attempts.

## Protected paths

The agent must treat validated source data as read-only, including:

central-bank-price-discovery/validation/

The agent may write only to:

central-bank-price-discovery/autoresearch/

unless explicitly authorised otherwise.

## Baseline invariants

Historical matched levels: 201
Valid revisions: 179
Baseline usable VAR rows: 160
Meetings: 8

Baseline HAC(6), meeting-FE estimates:

FF -> IEM beta:
0.7445355822620687

IEM -> FF beta:
0.02009629893361374

The agent must reproduce the baseline before trusting a new experiment.

## Existing evidence

Experiment 002:
within-meeting temporal permutation falsification.

Experiment 003:
relative circular-shift placebo.

Experiment 004:
leave-one-observation-out influence analysis.

Experiment 005:
HAC bandwidth x meeting fixed-effect specification multiverse.

Existing null or adverse evidence must not be discarded merely because a new
experiment produces a more favourable result.

## Interpretation constraint

The eight-meeting historical exercise is currently treated as a robustness
stress test rather than independent confirmation of temporal price discovery.

Changing this interpretation requires materially stronger evidence, not merely
a nominal p-value below 0.05.
