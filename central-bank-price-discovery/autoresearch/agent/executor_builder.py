#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

IMPLEMENTATIONS = HERE / "implementations"
GENERATED = HERE / "generated_executors"
BUDGET = HERE / "state" / "api_budget.json"

ENGINE = HERE / "experiment_engine.py"

MODEL = "gpt-5.6-luna"
MAX_OUTPUT_TOKENS = 7000

GENERATED.mkdir(parents=True, exist_ok=True)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, text):
    path.write_text(text, encoding="utf-8")


def latest_contract():
    files = sorted(
        IMPLEMENTATIONS.glob("*_implementation.json"),
        key=lambda p: p.stat().st_mtime,
    )

    if not files:
        raise SystemExit("STOP: no implementation contract exists")

    return files[-1]


def require_key():
    key = os.environ.get("OPENAI_API_KEY", "")

    if not key.startswith("sk-"):
        raise SystemExit("STOP: OPENAI_API_KEY unavailable")


def require_contract(contract):
    if contract.get("implementation_status") != "planned_not_executed":
        raise SystemExit(
            "STOP: implementation contract is not planned_not_executed"
        )

    baseline = contract.get("baseline_contract", {})

    if baseline.get("rows") != 160:
        raise SystemExit("STOP: baseline row contract changed")

    if baseline.get("meetings") != 8:
        raise SystemExit("STOP: meeting contract changed")

    if baseline.get("hac_lag") != 6:
        raise SystemExit("STOP: HAC contract changed")

    inp = contract.get("input_contract", {})

    if inp.get("canonical_panel_only") is not True:
        raise SystemExit("STOP: canonical-panel guard failed")

    if inp.get("validated_data_read_only") is not True:
        raise SystemExit("STOP: validation read-only guard failed")


def budget_available():
    b = load(BUDGET)

    remaining = (
        float(b["budget_usd"])
        - float(b["estimated_spend_usd"])
    )

    # Large reserve relative to one executor-generation request.
    if remaining < 0.10:
        raise SystemExit("STOP: API budget reserve reached")

    return b, remaining


def estimate_cost(input_tokens, output_tokens):
    # Preserve the same conservative local accounting convention already
    # used by the research system. This is an estimate, not provider billing.
    #
    # These constants deliberately err on the conservative side for the
    # local kill-switch and can be updated independently of the experiment.
    input_per_million = 0.25
    output_per_million = 2.00

    return (
        input_tokens / 1_000_000 * input_per_million
        + output_tokens / 1_000_000 * output_per_million
    )


def record_usage(response):
    b = load(BUDGET)

    inp = int(response.usage.input_tokens)
    out = int(response.usage.output_tokens)

    cost = estimate_cost(inp, out)

    projected = float(b["estimated_spend_usd"]) + cost

    if projected > float(b["budget_usd"]):
        raise SystemExit(
            "STOP: generated response would exceed local API budget"
        )

    b["estimated_spend_usd"] = projected
    b["api_calls"] = int(b.get("api_calls", 0)) + 1
    b["input_tokens"] = int(b.get("input_tokens", 0)) + inp
    b["output_tokens"] = int(b.get("output_tokens", 0)) + out
    b["last_call_estimated_cost_usd"] = cost
    b["model"] = MODEL

    BUDGET.write_text(
        json.dumps(b, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return cost


def make_prompt(contract):
    engine = ENGINE.read_text(encoding="utf-8")

    return f"""
You are the code-generation component of a constrained econometric
autoresearch system.

Your task is ONLY to generate a Python executor for an already-frozen
implementation contract.

You are NOT selecting a research question.
You are NOT changing the specification.
You are NOT executing the experiment.
You are NOT optimising for statistical significance.

FROZEN IMPLEMENTATION CONTRACT:

{json.dumps(contract, indent=2)}

EXISTING GENERIC ENGINE:

{engine}

REQUIREMENTS:

1. Return ONLY executable Python source code. No markdown fences.

2. The generated program must import and reuse experiment_engine.py where
   possible rather than reimplementing the frozen baseline differently.

3. It must reproduce the frozen 160-row baseline before estimating the
   new experiment.

4. It must read validated data only through the canonical panel path
   represented by experiment_engine.py.

5. It must NEVER write to validation/.

6. All outputs must be under:
   central-bank-price-discovery/autoresearch/agent/outputs/

7. Preserve all eight meeting families.

8. Never construct lags across meeting boundaries or excluded gaps.

9. Implement exactly the frozen estimands and pairing rules. Do not add
   alternative models, offsets, bandwidths, samples, transformations,
   significance searches, or exploratory variants.

10. Report ALL meeting-specific coefficients, including negative, null,
    unstable or failed estimates.

11. Explicitly test matrix rank before accepting an estimate.

12. HAC lag must remain exactly 6 where estimable.

13. P-values may be reported because the frozen contract requests them,
    but MUST NOT be used for selection or interpretation.

14. Implement the frozen descriptive sign-count decision exactly.

15. Record baseline reproduction, design dimensions, coefficients,
    uncertainty, sign counts, dispersion summaries, aggregation checks,
    failures and execution metadata in evidence.json.

16. Compute SHA-256 fingerprints for the canonical input and the procedure.

17. Include a deterministic rerun check. The second computation must be
    performed before final evidence is accepted, and numerical/statistical
    results from the two computations must match.

18. The evidence must explicitly contain:
    "result_selection_performed": false
    "null_results_recorded": true
    "validation_data_modified": false

19. Refuse to overwrite an existing evidence file for this experiment.

20. The executor must accept the frozen implementation JSON path as its
    sole positional argument and verify that its experiment_id matches.

21. Do not call OpenAI or any external network service from the generated
    executor.

22. Do not run git commands from the generated executor.

23. Do not modify the implementation contract.

Generate the executor now.
""".strip()


def validate_source(source, experiment_id):
    forbidden = [
        "OPENAI_API_KEY",
        "OpenAI(",
        "responses.create",
        "git push",
        "git commit",
    ]

    for item in forbidden:
        if item in source:
            raise SystemExit(
                f"STOP: generated executor contains forbidden token: {item}"
            )

    required = [
        experiment_id,
        "evidence.json",
        "result_selection_performed",
        "null_results_recorded",
        "validation_data_modified",
    ]

    for item in required:
        if item not in source:
            raise SystemExit(
                f"STOP: generated executor missing required token: {item}"
            )

    if "validation/" in source and "experiment_engine" not in source:
        raise SystemExit(
            "STOP: generated executor appears to bypass generic engine"
        )


def build():
    require_key()

    contract_path = latest_contract()
    contract = load(contract_path)

    require_contract(contract)

    experiment_id = contract["experiment_id"]

    existing = list(
        GENERATED.glob(f"*_{experiment_id}.py")
    )

    if existing:
        raise SystemExit(
            "STOP: generated executor already exists for this experiment"
        )

    _, remaining = budget_available()

    print("=== EXECUTOR BUILDER ===")
    print("contract:", contract_path.relative_to(REPO))
    print("experiment:", experiment_id)
    print(f"budget remaining before call: ${remaining:.4f}")
    print("API CALL: code generation only")
    print("NO ECONOMETRIC EXECUTION")

    client = OpenAI()

    response = client.responses.create(
        model=MODEL,
        input=make_prompt(contract),
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    cost = record_usage(response)

    source = response.output_text.strip()

    if source.startswith("```"):
        raise SystemExit(
            "STOP: model returned markdown instead of raw Python"
        )

    validate_source(source, experiment_id)

    stamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    out = GENERATED / f"{stamp}_{experiment_id}.py"

    write(out, source + "\n")

    fingerprint = hashlib.sha256(
        source.encode("utf-8")
    ).hexdigest()

    print()
    print("EXECUTOR SOURCE = GENERATED_NOT_EXECUTED")
    print("file:", out.relative_to(REPO))
    print("sha256:", fingerprint)
    print(f"estimated API cost: ${cost:.6f}")
    print()
    print("NO ECONOMETRIC RESULT OBSERVED")
    print("NO VALIDATION DATA MODIFIED")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    sub.add_parser("build")

    args = parser.parse_args()

    if args.command == "build":
        build()


if __name__ == "__main__":
    main()
