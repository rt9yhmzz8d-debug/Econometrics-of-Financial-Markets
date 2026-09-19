# ECMT3150 validation ledger

Updated: 19 September 2026 (Sydney)

## Current source state

- The original Round 4 acquisition remains fixed at
  `e5928a751856e59816342085dd76f33a8ac5ee79` for byte-level comparison.
- The validation layer was squash-merged to GitHub main as `ae6c0e7`.
- The shared Google Doc now states that IEM is a historical feasibility and
  external-validity extension, not evidence for the headline intraday result.
- The report's 86-meeting, 1,019-row historical model remains a reported result,
  not a result reproduced from the public Round 4 acquisition commit.

## Verified

- Round 4 contains 31,667 clean rows, 353 contracts and 113 parsed families.
- The family universe is 107 meeting-interval plus 6 quarterly families.
- Removing the quarterly and six split families leaves 101 ordinary
  meeting-interval candidates, containing 24,977 rows and 303 contracts.
- The FedPolicyB prospectus defines cumulative target changes between scheduled
  meetings and specifies the midpoint when the target is an interval.
- Family `51:1101` is source-checked: 6 November 2001 decision, 3 October 2001
  comparison date, and lower/unchanged/higher USD 1 contracts.
- The estimation gate is closed and tested. No model is fitted by this layer.
- Six downloaded external files have been classified. The GSS and SF Fed files
  independently agree on the direction of the 6 November 2001 surprise, and the
  Federal Reserve confirms a 50-basis-point cut to 2 percent.
- The two SF Fed filenames are byte-identical. They are one source, not two
  independent checks.
- LSEG identifies `02FFZ1^0` as the December 2001 candidate, but the supplied
  retrieval contains zero dated price observations.
- Pilot sensitivity yields 33 valid pre-meeting days when zero-quantity reported
  last prices are accepted, 29 with same-day positive quantity for every leg,
  and 32 under positive-quantity carry rules of one, three or seven days.

## Excluded or unresolved

- All 15 Market 20 FedPolicy families: the FedPolicyB prospectus says the older
  market used different inter-meeting treatment, but does not state that rule.
- Six split families: actual contemporaneous spin-off notices and exclusive
  payoff intervals have not been found.
- Six quarterly families: their three-month horizon is not a single-meeting
  outcome. Sixteen old quarterly contracts also reappear as all-zero rows on
  1 June 2016 after gaps of 566 to 1,357 days.
- Historical price freshness: 247 meeting-interval rows change Last Price while
  Units and Dollar Volume are zero. In 208 of all 263 flagged rows, Low or High
  is nevertheless nonzero. The source fields cannot yet support a mechanical
  zero-volume carry rule.
- Futures matching: no verified December 2001 delivery series, time zone, close
  convention or settlement-horizon adjustment is present in the repository.
- The SF Fed and GSS event surprises cannot substitute for the missing futures
  panel: they are announcement-window or derived research measures, not daily
  pre-announcement prices for the identified contract.

## Next bounded action

Obtain the raw daily `02FFZ1^0` series, or a demonstrably equivalent exact
December 2001 contract, for 3 October through 5 November 2001. Require dates,
timestamps, time zone, close or settlement field, volume and source metadata.
Verify how the contract's monthly-average payoff incorporates both the 6
November and 11 December policy meetings. Only then construct the paired pilot
table. Do not fit a lead-lag model until the IEM price-field ambiguity and the
broader family mapping gate are also resolved.
