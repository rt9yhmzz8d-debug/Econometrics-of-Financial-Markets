#!/usr/bin/env python3

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys

from openai import OpenAI

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

EXPERIMENTS = HERE / "experiments"
IMPLEMENTATIONS = HERE / "implementations"
BUDGET = HERE / "state" / "api_budget.json"
CONSTITUTION = HERE / "RESEARCH_CONSTITUTION.md"
ENGINE = HERE / "experiment_engine.py"

IMPLEMENTATIONS.mkdir(parents=True, exist_ok=True)

MODEL = "gpt-5.6-luna"
MAX_OUTPUT = 3500

# Conservative local accounting assumptions.
INPUT_USD_PER_M = 0.25
OUTPUT_USD_PER_M = 2.00


def git(*args):
    p = subprocess.run(
        ["git", *args],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=True,
    )
    return p.stdout.strip()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, obj):
    path.write_text(
        json.dumps(obj, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def require_environment():
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key.startswith("sk-"):
        raise SystemExit("STOP: OPENAI_API_KEY unavailable")

    if git("branch", "--show-current") != "autoresearch-agent-006":
        raise SystemExit("STOP: wrong Git branch")

    dirty_validation = git(
        "status",
        "--porcelain",
        "--",
        "central-bank-price-discovery/validation",
    )

    if dirty_validation:
        raise SystemExit(
            "STOP: protected validation directory is dirty"
        )

    if not ENGINE.exists():
        raise SystemExit("STOP: generic engine missing")


def latest_proposal():
    files = sorted(EXPERIMENTS.glob("*_ai_proposal.json"))
    if not files:
        raise SystemExit("STOP: no AI proposal exists")
    return files[-1]


def evidence_exists(experiment_id):
    for p in (HERE / "outputs").glob("**/evidence.json"):
        try:
            d = load(p)
        except Exception:
            continue

        if (
            d.get("experiment_id") == experiment_id
            or d.get("experiment") == experiment_id
        ):
            return True

    return False


def budget():
    b = load(BUDGET)

    remaining = (
        float(b["budget_usd"])
        - float(b["estimated_spend_usd"])
    )

    if remaining < 0.05:
        raise SystemExit("STOP: API budget reserve reached")

    return b, remaining


def record_usage(response):
    b = load(BUDGET)

    inp = int(response.usage.input_tokens)
    out = int(response.usage.output_tokens)

    cost = (
        inp / 1_000_000 * INPUT_USD_PER_M
        + out / 1_000_000 * OUTPUT_USD_PER_M
    )

    projected = float(b["estimated_spend_usd"]) + cost

    if projected > float(b["budget_usd"]):
        raise SystemExit(
            "STOP: response would exceed local API budget"
        )

    b["estimated_spend_usd"] = projected
    b["api_calls"] = int(b.get("api_calls", 0)) + 1
    b["input_tokens"] = int(b.get("input_tokens", 0)) + inp
    b["output_tokens"] = int(b.get("output_tokens", 0)) + out
    b["last_call_estimated_cost_usd"] = cost
    b["updated_at_utc"] = datetime.now(
        timezone.utc
    ).isoformat()

    write(BUDGET, b)

    return cost


def make_prompt(proposal):
    constitution = CONSTITUTION.read_text(encoding="utf-8")

    engine = ENGINE.read_text(encoding="utf-8")

    return f"""
You are the implementation-planning component of a constrained
econometric autoresearch system.

You are NOT executing an experiment.
You are NOT choosing results.
You are NOT modifying data.
You are translating one already-frozen research proposal into a
strict machine-readable implementation contract.

RESEARCH CONSTITUTION:

{constitution}

FROZEN GENERIC ENGINE:

{engine}

FROZEN PROPOSAL:

{json.dumps(proposal, indent=2)}

Return ONLY valid JSON.

Required top-level structure:

{{
  "experiment_id": "...",
  "implementation_status": "planned_not_executed",
  "analysis_type": "...",
  "required_engine_capabilities": ["..."],
  "input_contract": {{
    "canonical_panel_only": true,
    "validated_data_read_only": true,
    "required_columns": ["..."]
  }},
  "baseline_contract": {{
    "rows": 160,
    "meetings": 8,
    "hac_lag": 6,
    "reproduction_required": true
  }},
  "estimands": [
    {{
      "name": "...",
      "outcome": "...",
      "predictors": ["..."],
      "offset": 1,
      "temporal_direction": "lag_or_lead",
      "meeting_fixed_effects": true,
      "hac_lag": 6
    }}
  ],
  "pairing_rules": [
    "..."
  ],
  "pre_execution_assertions": [
    "..."
  ],
  "required_outputs": [
    "..."
  ],
  "interpretation_rules": [
    "..."
  ],
  "forbidden_actions": [
    "..."
  ]
}}

Rules:

1. Preserve the frozen proposal exactly in substance.
2. Never add an offset, specification or test merely because it may
   produce statistical significance.
3. Never permit modification of validation/.
4. Never bridge excluded temporal gaps.
5. Never cross FOMC meeting boundaries.
6. Require baseline reproduction before experiment execution.
7. Require all preregistered results to be reported.
8. Null, reversed and adverse results must be retained.
9. Do not generate Python code.
10. Do not execute anything.
11. Do not change the research question.
12. Do not use p-values as an optimisation criterion.
""".strip()


def validate_plan(plan, proposal):
    if plan.get("experiment_id") != proposal.get("experiment_id"):
        raise SystemExit("STOP: experiment ID changed")

    if plan.get("implementation_status") != "planned_not_executed":
        raise SystemExit("STOP: invalid implementation state")

    inp = plan.get("input_contract", {})

    if inp.get("canonical_panel_only") is not True:
        raise SystemExit("STOP: canonical-panel guard failed")

    if inp.get("validated_data_read_only") is not True:
        raise SystemExit("STOP: validation read-only guard failed")

    base = plan.get("baseline_contract", {})

    if base.get("rows") != 160:
        raise SystemExit("STOP: baseline row invariant changed")

    if base.get("meetings") != 8:
        raise SystemExit("STOP: meeting invariant changed")

    if base.get("hac_lag") != 6:
        raise SystemExit("STOP: HAC invariant changed")

    if base.get("reproduction_required") is not True:
        raise SystemExit("STOP: reproduction guard missing")

    forbidden = " ".join(
        plan.get("forbidden_actions", [])
    ).lower()

    required_phrases = [
        "significance",
        "validation",
    ]

    for phrase in required_phrases:
        if phrase not in forbidden:
            raise SystemExit(
                f"STOP: forbidden-action guard missing {phrase}"
            )


def plan():
    require_environment()

    proposal_path = latest_proposal()
    proposal = load(proposal_path)

    experiment_id = proposal["experiment_id"]

    if evidence_exists(experiment_id):
        raise SystemExit(
            f"STOP: {experiment_id} already has evidence; "
            "do not plan it again"
        )

    _, remaining = budget()

    print("=== IMPLEMENTATION PLANNER ===")
    print("proposal:", proposal_path.relative_to(REPO))
    print("experiment:", experiment_id)
    print(f"budget remaining before call: ${remaining:.4f}")
    print("API CALL: implementation planning only")

    client = OpenAI()

    response = client.responses.create(
        model=MODEL,
        input=make_prompt(proposal),
        max_output_tokens=MAX_OUTPUT,
    )

    cost = record_usage(response)

    raw = response.output_text.strip()

    try:
        implementation = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"STOP: invalid implementation JSON: {exc}"
        )

    validate_plan(implementation, proposal)

    stamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    out = IMPLEMENTATIONS / (
        f"{stamp}_{experiment_id}_implementation.json"
    )

    write(out, implementation)

    print()
    print("IMPLEMENTATION CONTRACT = VALID")
    print("file:", out.relative_to(REPO))
    print(f"estimated API cost: ${cost:.6f}")
    print()
    print("STATE = PLANNED_NOT_EXECUTED")
    print("NO ECONOMETRIC RESULT OBSERVED")
    print("NO VALIDATION DATA MODIFIED")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    sub.add_parser("plan")

    args = parser.parse_args()

    if args.command == "plan":
        plan()


if __name__ == "__main__":
    main()
