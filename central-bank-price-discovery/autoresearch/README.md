# ECMT3150 AutoResearch

Autonomous adversarial robustness research for **Who Prices the Fed First?**

## Safety architecture

- Runs only on the `autoresearch-ecmt3150` branch.
- Files outside this directory are treated as read-only.
- Experiment history is append-only.
- Null and contradictory findings are retained.
- Statistical significance is not an optimisation objective.
- US$12 soft budget threshold.
- US$15 absolute agent-side budget ceiling.
- No automatic budget extension.
- One agent at a time.
- Live model calls remain disabled until the model and econometric adapters pass preflight tests.

`budget.json` records agent-side estimated spend. It is not a provider billing cap.

## Current status

Scaffold installed. Live autonomous execution intentionally disabled.
