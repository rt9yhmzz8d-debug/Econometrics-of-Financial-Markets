# AutoResearch Agent

This directory contains the autonomous research orchestration layer.

## Research loop

1. Read frozen research state.
2. Propose a falsifiable experiment.
3. Validate the proposal against the research constitution.
4. Execute only approved experiment classes.
5. Preserve null and adverse results.
6. Evaluate evidence against the frozen baseline.
7. Write machine-readable evidence and a research note.
8. Update research state.
9. Commit the experiment to an isolated branch.
10. Continue to the next admissible experiment.

## Safety model

The runner does not optimise for statistical significance.

Validated source data are read-only.

A failed, null or contradictory experiment must be retained.

The initial runner cannot automatically push or merge changes.

## Commands

    python central-bank-price-discovery/autoresearch/agent/runner.py status

    python central-bank-price-discovery/autoresearch/agent/runner.py plan
