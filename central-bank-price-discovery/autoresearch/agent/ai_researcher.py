#!/usr/bin/env python3

"""
AI research-design layer for ECMT3150 AutoResearch.

IMPORTANT:
- This module proposes experiments.
- It does NOT execute econometric experiments.
- It does NOT modify validated source data.
- It does NOT select results by significance.
- The deterministic orchestrator remains responsible for execution.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI


HERE = Path(__file__).resolve().parent
AR = HERE.parent

CONSTITUTION = HERE / "RESEARCH_CONSTITUTION.md"
STATE = HERE / "state" / "research_state.json"
RUNS = HERE / "runs"
OUTPUTS = HERE / "outputs"

BUDGET_STATE = HERE / "state" / "api_budget.json"

MODEL = "gpt-5.6-luna"

# Current configured accounting rates.
# USD per 1,000,000 tokens.
INPUT_USD_PER_M = 0.20
OUTPUT_USD_PER_M = 1.20

DEFAULT_BUDGET_USD = 15.00

MAX_PROPOSAL_OUTPUT_TOKENS = 6000


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def initialise_budget():
    if BUDGET_STATE.exists():
        return load_json(BUDGET_STATE)

    state = {
        "budget_usd": DEFAULT_BUDGET_USD,
        "estimated_spend_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "api_calls": 0,
        "model": MODEL,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "accounting_note": (
            "Local token-based safety accounting. "
            "Actual provider billing remains authoritative."
        ),
    }

    write_json(BUDGET_STATE, state)
    return state


def estimated_cost(input_tokens: int, output_tokens: int):
    return (
        input_tokens / 1_000_000 * INPUT_USD_PER_M
        + output_tokens / 1_000_000 * OUTPUT_USD_PER_M
    )


def budget_status():
    b = initialise_budget()
    remaining = b["budget_usd"] - b["estimated_spend_usd"]

    print("=== AUTORESEARCH API BUDGET ===")
    print(f"budget:           ${b['budget_usd']:.4f}")
    print(f"estimated spend:  ${b['estimated_spend_usd']:.4f}")
    print(f"remaining:        ${remaining:.4f}")
    print(f"API calls:        {b['api_calls']}")
    print(f"input tokens:     {b['input_tokens']}")
    print(f"output tokens:    {b['output_tokens']}")
    print(f"model:            {b['model']}")


def assert_budget_available():
    b = initialise_budget()

    if b["estimated_spend_usd"] >= b["budget_usd"]:
        raise SystemExit("STOP: AUTORESEARCH API BUDGET EXHAUSTED")

    return b


def record_usage(response):
    b = initialise_budget()

    inp = int(response.usage.input_tokens)
    out = int(response.usage.output_tokens)

    cost = estimated_cost(inp, out)

    b["input_tokens"] += inp
    b["output_tokens"] += out
    b["api_calls"] += 1
    b["estimated_spend_usd"] += cost
    b["last_call_estimated_cost_usd"] = cost
    b["updated_at_utc"] = datetime.now(timezone.utc).isoformat()

    write_json(BUDGET_STATE, b)

    if b["estimated_spend_usd"] > b["budget_usd"]:
        raise SystemExit(
            "STOP: local API budget exceeded after final accounted call"
        )

    return cost


def completed_experiments():
    completed = []

    for path in sorted(RUNS.glob("*.json")):
        try:
            d = load_json(path)
        except Exception:
            continue

        exp = (
            d.get("selected_experiment")
            or d.get("proposal")
            or {}
        )

        if not exp:
            continue

        completed.append({
            "run_file": path.name,
            "experiment_id": exp.get("experiment_id"),
            "title": exp.get("title"),
            "status": d.get("status"),
            "evaluation": d.get("evaluation"),
        })

    return completed


def evidence_index():
    evidence = []

    for path in sorted(OUTPUTS.glob("*/evidence.json")):
        try:
            d = load_json(path)
        except Exception:
            continue

        evidence.append({
            "path": str(path.relative_to(AR)),
            "experiment": d.get("experiment"),
            "baseline": d.get("baseline"),
            "evaluation": d.get("evaluation"),
        })

    return evidence


def build_prompt():
    constitution = CONSTITUTION.read_text(encoding="utf-8")
    state = load_json(STATE)

    context = {
        "research_state": state,
        "completed_experiments": completed_experiments(),
        "evidence_index": evidence_index(),
    }

    return f"""
You are the research-design component of an autonomous econometrics
research system.

Your task is to propose ONE new scientifically useful experiment for the
historical IEM versus Fed Funds futures price-discovery project.

RESEARCH CONSTITUTION:

{constitution}

CURRENT MACHINE-READABLE RESEARCH CONTEXT:

{json.dumps(context, indent=2)}

MANDATORY RULES:

1. Do not optimise for statistical significance.
2. Do not use p-values as the reward or experiment-selection objective.
3. Prefer falsification, robustness, identification and sensitivity tests.
4. Valid null and adverse findings are scientific successes.
5. Do not modify validated historical source data.
6. Preserve temporal gaps and meeting boundaries.
7. The baseline contains 160 usable VAR observations across 8 meetings.
8. The proposed experiment must be deterministic after preregistration.
9. Do not repeat an experiment already present in the run history.
10. Do not propose arbitrary data deletion to improve results.
11. Do not reinterpret this eight-meeting exercise as independent
    confirmation without materially stronger evidence.
12. Keep the experiment small enough to run locally on a MacBook.
13. Use only information supplied here. Do not invent additional data.
14. Return JSON only.

Return exactly one JSON object with this structure:

{{
  "experiment_id": "agent_008_descriptive_name",
  "title": "...",
  "research_question": "...",
  "falsifiable_hypothesis": "...",
  "motivation": "...",
  "method": {{
    "analysis_type": "...",
    "inputs": ["..."],
    "steps": ["..."],
    "parameters": {{}}
  }},
  "protected_invariants": [
    "160-row baseline reproduced before analysis",
    "validated data read only",
    "meeting boundaries preserved",
    "null results retained",
    "no significance optimisation"
  ],
  "expected_information_gain": "...",
  "interpretation_if_supported": "...",
  "interpretation_if_not_supported": "...",
  "limitations": ["..."],
  "execution_requirements": ["..."]
}}

Do not include markdown fences.
""".strip()


def propose():
    if not os.environ.get("OPENAI_API_KEY", "").startswith("sk-"):
        raise SystemExit("STOP: OPENAI_API_KEY is unavailable")

    b = assert_budget_available()

    remaining = b["budget_usd"] - b["estimated_spend_usd"]

    # Reserve a buffer so one unusually large response cannot intentionally
    # consume the final cents of the research budget.
    if remaining < 0.05:
        raise SystemExit("STOP: less than $0.05 local budget remains")

    client = OpenAI()

    response = client.responses.create(
        model=MODEL,
        input=build_prompt(),
        max_output_tokens=MAX_PROPOSAL_OUTPUT_TOKENS,
        text={
            "format": {
                "type": "json_schema",
                "name": "research_proposal",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "experiment_id": {"type": "string"},
                        "title": {"type": "string"},
                        "research_question": {"type": "string"},
                        "falsifiable_hypothesis": {"type": "string"},
                        "motivation": {"type": "string"},
                        "method": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "analysis_type": {"type": "string"},
                                "inputs": {
                                    "type": "array",
                                    "items": {"type": "string"}
                                },
                                "steps": {
                                    "type": "array",
                                    "items": {"type": "string"}
                                },
                                "parameters": {"type": "object"}
                            },
                            "required": [
                                "analysis_type",
                                "inputs",
                                "steps",
                                "parameters"
                            ],
                            "additionalProperties": True
                        },
                        "protected_invariants": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "expected_information_gain": {"type": "string"},
                        "interpretation_if_supported": {"type": "string"},
                        "interpretation_if_not_supported": {"type": "string"},
                        "limitations": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "execution_requirements": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    },
                    "required": [
                        "experiment_id",
                        "title",
                        "research_question",
                        "falsifiable_hypothesis",
                        "motivation",
                        "method",
                        "protected_invariants",
                        "expected_information_gain",
                        "interpretation_if_supported",
                        "interpretation_if_not_supported",
                        "limitations",
                        "execution_requirements"
                    ],
                    "additionalProperties": False
                }
            }
        },
    )

    cost = record_usage(response)

    raw = response.output_text.strip()

    try:
        proposal = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"STOP: researcher returned invalid JSON: {exc}"
        )

    required = {
        "experiment_id",
        "title",
        "research_question",
        "falsifiable_hypothesis",
        "motivation",
        "method",
        "protected_invariants",
        "expected_information_gain",
        "interpretation_if_supported",
        "interpretation_if_not_supported",
        "limitations",
        "execution_requirements",
    }

    missing = sorted(required - set(proposal))

    if missing:
        raise SystemExit(
            "STOP: AI proposal missing required fields: "
            + ", ".join(missing)
        )

    if not proposal["experiment_id"].startswith("agent_"):
        raise SystemExit("STOP: invalid experiment ID")

    completed_ids = {
        x["experiment_id"]
        for x in completed_experiments()
        if x.get("experiment_id")
    }

    if proposal["experiment_id"] in completed_ids:
        raise SystemExit("STOP: AI proposed an already-consumed experiment")

    out = HERE / "experiments" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "_ai_proposal.json"
    )

    write_json(out, proposal)

    print("=== AI RESEARCH PROPOSAL CREATED ===")
    print("model:", MODEL)
    print("experiment:", proposal["experiment_id"])
    print("title:", proposal["title"])
    print("proposal:", out.relative_to(HERE.parents[2]))
    print(f"estimated API cost: ${cost:.6f}")
    print()
    print("STATE = PROPOSAL_ONLY")
    print("NO ECONOMETRIC EXPERIMENT EXECUTED")
    print("NO RESULT OBSERVED")
    print("NO SOURCE DATA MODIFIED")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("budget")
    sub.add_parser("propose")

    args = parser.parse_args()

    if args.command == "budget":
        budget_status()
    elif args.command == "propose":
        propose()
