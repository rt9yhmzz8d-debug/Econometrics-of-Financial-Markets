## 1. BASELINE

- With HAC(6), meeting fixed effects, and all eight meetings:
  - **FF → IEM:** β = 0.745, SE = 0.504.
  - **IEM → FF:** β = 0.0201, SE = 0.0098.
- The estimated coefficients are positive in both directions, but the evidence is not symmetric in precision. The IEM → FF coefficient is estimated much more precisely than the FF → IEM coefficient.
- The baseline does not establish that either market systematically prices first. It provides directional evidence that is more consistent with IEM information entering Fed Funds futures than with the reverse, but this interpretation remains conditional on the specification and the small eight-meeting sample.

## 2. COEFFICIENT STABILITY

- Coefficients are mechanically identical across HAC bandwidths because HAC changes inference, not OLS point estimates.
- The full-sample coefficients are also stable to removing meeting fixed effects:
  - FF → IEM changes from 0.745 to 0.743.
  - IEM → FF changes from 0.0201 to 0.0186.
- Leave-one-meeting-out estimates remain positive in every case.
- FF → IEM varies from 0.519 to 0.841 across leave-one-out samples. This is a meaningful range, although the coefficient remains positive.
- IEM → FF varies from 0.0124 to 0.0340. It is generally close to 0.02, but the estimate falls materially when 51:0802 is removed and rises when 51:0102 is removed.
- Thus, the **sign pattern is stable**, while the **magnitude—especially for FF → IEM—is not tightly pinned down**.

## 3. INFERENCE FRAGILITY

- Inference is sensitive to the HAC bandwidth:
  - For FF → IEM, the baseline two-sided p-value ranges from 0.057 at HAC(12) to 0.154 at HAC(3), with no comparable baseline result below 0.05.
  - For IEM → FF, the raw p-value ranges from 0.020 at HAC(12) to 0.122 at HAC(1).
- The IEM → FF result is therefore not inference-stable across reasonable HAC choices. Its Holm-adjusted p-value ranges from 0.040 to 0.245.
- The HAC(6) baseline is neither the most favorable nor the least favorable specification for IEM → FF, so the result should not be selected based on its p-value.
- Removing meeting fixed effects reduces the apparent precision in both directions, particularly for IEM → FF.
- Coefficient stability should not be confused with inference stability: the IEM → FF coefficient remains positive, but the associated uncertainty changes substantially across dependence assumptions.

## 4. LEAVE-ONE-MEETING-OUT

- The leave-one-meeting-out results indicate nontrivial meeting influence.
- Dropping 51:0102 produces a large change in inference for FF → IEM: β = 0.817 with a much smaller SE of 0.292. This suggests that this meeting is influential for the FF → IEM uncertainty, not that the relationship is generally established.
- Dropping 51:0802 weakens both estimated relationships, especially FF → IEM, whose SE rises to 0.783 and whose coefficient becomes least precisely estimated.
- Dropping 51:1102 produces the most favorable inference for IEM → FF, while dropping 51:0802 produces one of the weakest results. This indicates that the apparent precision of the IEM → FF relationship depends partly on particular meetings.
- The coefficients remain positive in all leave-one-out samples, but the small number of meetings means these diagnostics are themselves noisy. They should be treated as influence diagnostics, not as alternative preferred estimates.

## 5. CONTRADICTORY_OR_NULL_FINDINGS

- The FF → IEM direction is not robustly distinguishable from zero under the baseline HAC specifications, despite its consistently positive coefficient.
- The IEM → FF direction is positive throughout, but its inferential support disappears or weakens materially under HAC(1), HAC(3), no meeting fixed effects, and several leave-one-out samples.
- The 51:0802 deletion produces a relatively weak result in both directions, providing a useful null-style stress test against an overly favorable interpretation.
- The fact that dropping 51:0102 makes FF → IEM appear much more precise, while dropping 51:0802 makes it much less precise, is contradictory evidence against treating the full-sample result as uniformly representative.
- The data therefore support a stable positive sign pattern more strongly than they support a stable conclusion about statistical or economic dominance.

## 6. WHAT_NOT_TO_CLAIM

- Do not claim that IEM causes Fed Funds futures to move.
- Do not claim that IEM definitively prices the Fed first.
- Do not describe the IEM → FF result as robustly statistically significant.
- Do not use HAC(12), or any other bandwidth, because it produces the smallest p-value.
- Do not treat the 51:0102 leave-one-out result as the preferred result.
- Do not interpret positive coefficients in both directions as proof of a one-way information flow.
- Do not generalize strongly from eight meetings. The sample is a historical validation and stress-test sample, not a large-sample confirmation.
- Do not infer robustness from coefficient signs alone when inference varies materially across HAC and meeting-deletion specifications.

## 7. NEXT_EXPERIMENT

**HYPOTHESIS:**  
The directional coefficient pattern is more stable than the associated inference: both coefficients remain positive, but uncertainty is materially affected by dependence assumptions and influential meetings.

**SPECIFICATION:**  
Construct a pre-specified stability summary using the already reported grid: coefficient ranges, minimum and maximum estimates, sign retention, full-sample HAC-adjusted SE and p-value ranges, no-fixed-effects changes, and leave-one-meeting-out ranges. Report separate summaries for FF → IEM and IEM → FF without selecting a preferred specification.

**WHY:**  
The main unresolved issue is not whether one specification crosses a significance threshold, but whether the apparent ordering survives reasonable changes in inference and sample composition. A formal stability summary directly addresses that issue without adding data or searching over models.

**FALSIFICATION_VALUE:**  
The directional interpretation should be weakened or rejected if the coefficient signs change, if one direction’s magnitude is highly unstable relative to the other, or if the apparent IEM → FF advantage is driven by only one or two meetings rather than persisting across the pre-specified diagnostics.
