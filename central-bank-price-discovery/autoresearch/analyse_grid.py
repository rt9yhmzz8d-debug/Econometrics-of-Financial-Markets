from pathlib import Path
import json
import sys

AR = Path(__file__).resolve().parent
OUT = AR / "outputs"

sys.path.insert(0, str(AR))
from model_adapter import call_agent

BASELINE_ID = "HAC_06"

# Only analyse the controlled grid, not earlier manual test runs.
GRID_IDS = [
    "HAC_01",
    "HAC_03",
    "HAC_06",
    "HAC_09",
    "HAC_12",
    "NO_MEETING_FE",
    "LOMO_01",
    "LOMO_02",
    "LOMO_03",
    "LOMO_04",
    "LOMO_05",
    "LOMO_06",
    "LOMO_07",
    "LOMO_08",
]

records = []

for experiment_id in GRID_IDS:
    p = OUT / experiment_id / "result.json"

    if not p.exists():
        raise SystemExit(f"STOP: missing {p}")

    x = json.loads(p.read_text(encoding="utf-8"))
    records.append(x)

baseline = next(
    x for x in records
    if x.get("experiment_id") == BASELINE_ID
)

# Compact machine-readable evidence package.
evidence = {
    "research_question": "Who prices the Fed first?",
    "interpretation_rule": (
        "Treat the 8-meeting historical sample as an independent "
        "robustness/stress-test sample. Do not search for significance."
    ),
    "baseline": baseline,
    "controlled_experiments": records,
}

evidence_path = AR / "grid_evidence.json"
evidence_path.write_text(
    json.dumps(evidence, indent=2) + "\n",
    encoding="utf-8",
)

system_prompt = """
You are the adversarial econometric research agent for an ECMT3150 project.

Research question:
Who prices the Fed first? Specifically, assess lead-lag price discovery
between Iowa Electronic Markets policy probabilities and Fed Funds futures.

Your job is NOT to find statistical significance.

Your job is to:
- stress-test the result,
- identify fragility,
- identify null or contradictory evidence,
- distinguish coefficient stability from inference stability,
- avoid p-hacking,
- avoid treating a specification as preferred because p < 0.05,
- treat HAC bandwidth variants as sensitivity checks,
- treat leave-one-meeting-out results as influence diagnostics,
- be especially cautious because this historical validation sample has
  only eight meetings,
- never claim causality from these regressions,
- never promote a finding into the final report automatically.

The frozen baseline is HAC(6), meeting fixed effects ON, all eight meetings.

Return concise research analysis only.
"""

user_prompt = f"""
Analyse this complete deterministic robustness grid.

{json.dumps(evidence, indent=2)}

Return exactly these headings:

1. BASELINE
2. COEFFICIENT STABILITY
3. INFERENCE FRAGILITY
4. LEAVE-ONE-MEETING-OUT
5. CONTRADICTORY_OR_NULL_FINDINGS
6. WHAT_NOT_TO_CLAIM
7. NEXT_EXPERIMENT

For NEXT_EXPERIMENT:
Choose exactly ONE next experiment that is methodologically motivated by
the evidence rather than by which specification gives the smallest p-value.

The permitted next-experiment families are:
- additional HAC sensitivity justified by dependence structure,
- meeting influence diagnostics,
- coefficient/inference stability summaries,
- tests using the already validated gap-safe historical panel.

Do not request new data.
Do not modify validated source files.
Do not choose an experiment merely because it may produce significance.

State:
HYPOTHESIS:
SPECIFICATION:
WHY:
FALSIFICATION_VALUE:
"""

print("Evidence file:", evidence_path)
print("Experiments supplied:", len(records))
print("Baseline:", BASELINE_ID)
print()
print("Calling adversarial research agent...")

r = call_agent(system_prompt, user_prompt)

analysis_path = AR / "research_analysis_001.md"
analysis_path.write_text(
    r["text"].rstrip() + "\n",
    encoding="utf-8",
)

print()
print("=== AGENT ANALYSIS ===")
print(r["text"])
print()
print("=== METER ===")
print("MODEL:", r["model"])
print("INPUT TOKENS:", r["input_tokens"])
print("OUTPUT TOKENS:", r["output_tokens"])
print("CALL COST USD:", f'{r["cost_usd"]:.6f}')
print("CUMULATIVE USD:", f'{r["cumulative_cost_usd"]:.6f}')
print("SAVED:", analysis_path)
