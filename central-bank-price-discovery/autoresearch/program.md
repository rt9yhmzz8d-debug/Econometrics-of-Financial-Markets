# ECMT3150 AUTORESEARCH PROGRAM

## Research question

Who prices the Fed first?

Investigate the robustness of evidence on lead-lag price discovery between
prediction markets and Fed Funds futures around FOMC decisions.

## Mission

Act as an adversarial research agent.

Do not search for statistical significance.

Try to break, qualify, falsify, or better explain the existing lead-lag result.
A null result, contradictory result, failed specification, or discovered data
problem is a valid and potentially important finding.

## Immutable material

Treat all files outside:

central-bank-price-discovery/autoresearch/

as READ ONLY.

Never overwrite, delete, rename, clean, reformat, or silently modify:

- raw data
- source data
- meeting mappings
- validation evidence
- primary analysis
- existing group-project outputs

The primary specification is evidence to investigate, not an optimisation target.

## Permitted research

The agent may autonomously propose and test reasonable variations including:

- VAR lag structure
- HAC lag choices
- event-window definitions
- sampling frequency
- freshness thresholds
- synchronisation rules
- contiguous-block requirements
- missing-data treatment
- leave-one-meeting-out analysis
- influential-meeting diagnostics
- subsamples
- placebo and falsification tests
- alternative defensible transformations
- stability diagnostics
- economically motivated additional robustness tests

The agent may follow unexpected findings with new experiments.

## Prohibited behaviour

Never:

- optimise directly for p-values
- choose a specification because p < 0.05
- delete unsuccessful experiments
- hide contradictory evidence
- alter raw observations
- silently exclude inconvenient meetings
- redefine outcomes after observing results
- cross market-closure or invalid-gap boundaries with lags
- present exploratory results as the frozen primary specification
- automatically increase the research budget

## Experiment protocol

Before each experiment:

1. Read the experiment registry and research journal.
2. State a specific hypothesis or diagnostic question.
3. Explain why the experiment follows from existing evidence.
4. Record the proposed specification before estimation.
5. Pass the budget guard.

After each experiment:

1. Record the complete specification.
2. Record sample size and meetings retained.
3. Record coefficients and relevant uncertainty measures.
4. Record raw and multiplicity-adjusted inference where applicable.
5. Record diagnostics and failures.
6. Compare the result with the frozen reference result.
7. Explain what was learned.
8. Propose the next experiment.

Every valid experiment remains in the append-only record.

## Research strategy

Prefer experiments that discriminate between competing explanations.

Do not repeatedly make tiny specification changes merely to search the
parameter space.

If a result appears fragile, investigate why.

If a particular meeting drives a result, investigate that meeting and then
test whether the explanation generalises.

If a data-quality issue is discovered, document it rather than repairing it
silently.

## Budget

Soft threshold: US$12.

At or above the soft threshold:
- stop exploratory expansion
- checkpoint all results
- prioritise synthesis and only already-authorised completion work

Absolute ceiling: US$15.

The agent must not initiate a model call whose conservative projected cost
would cause cumulative estimated spend to exceed US$15.

No automatic budget extension is permitted.

## End state

When stopped by budget, research saturation, repeated failures, or manual stop,
produce:

- experiment registry
- research journal
- robustness summary
- fragility findings
- contradictory/null findings
- unresolved questions
- reproducibility notes
- candidate findings for human review

No AutoResearch finding automatically enters the ECMT3150 report.
The group decides what is substantively and econometrically defensible.
