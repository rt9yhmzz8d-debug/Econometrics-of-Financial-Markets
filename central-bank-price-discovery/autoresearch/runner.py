#!/usr/bin/env python3
import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUDGET = HERE / "budget.json"
REGISTRY = HERE / "experiment_registry.csv"
JOURNAL = HERE / "research_journal.md"

def load_budget():
    return json.loads(BUDGET.read_text(encoding="utf-8"))

def save_budget(b):
    tmp = BUDGET.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(b, indent=2) + "\n", encoding="utf-8")
    tmp.replace(BUDGET)

def git_clean_outside_sandbox():
    p = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT, capture_output=True, text=True, check=True
    )
    bad = []
    prefix = "central-bank-price-discovery/autoresearch/"
    for line in p.stdout.splitlines():
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if not path.startswith(prefix):
            bad.append(line)
    return bad

def budget_gate(projected_cost):
    b = load_budget()
    spent = float(b["estimated_spend"])
    soft = float(b["soft_limit"])
    hard = float(b["hard_limit"])

    if projected_cost < 0:
        raise SystemExit("STOP: projected cost cannot be negative")

    if spent + projected_cost > hard:
        raise SystemExit(
            f"HARD STOP: US${spent:.2f} + US${projected_cost:.2f} "
            f"would exceed US${hard:.2f}"
        )

    if spent >= soft:
        raise SystemExit(
            f"SOFT STOP: US${spent:.2f} already spent. "
            "Human review required before exploratory work continues."
        )
    return b

def next_id():
    rows = list(csv.DictReader(REGISTRY.open(encoding="utf-8")))
    return f"EXP_{len(rows)+1:04d}"

def append_registry(row):
    with REGISTRY.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=[
            "experiment_id","timestamp","status","hypothesis","specification",
            "sample_n","meetings_n","result_summary","cost_usd",
            "cumulative_cost_usd"
        ]).writerow(row)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--projected-cost", type=float, default=0.0)
    ap.add_argument("--hypothesis", default="DRY RUN")
    args = ap.parse_args()

    bad = git_clean_outside_sandbox()
    if bad:
        print("STOP: changes exist outside the AutoResearch sandbox:")
        print("\n".join(bad))
        return 3

    b = budget_gate(args.projected_cost)

    if args.dry_run:
        print("AUTORESEARCH PREFLIGHT PASS")
        print(f"branch={subprocess.check_output(['git','branch','--show-current'], cwd=ROOT, text=True).strip()}")
        print(f"spent=US${float(b['estimated_spend']):.2f}")
        print(f"soft=US${float(b['soft_limit']):.2f}")
        print(f"hard=US${float(b['hard_limit']):.2f}")
        print(f"projected_next_call=US${args.projected_cost:.2f}")
        print("No model call made.")
        return 0

    # Deliberately fail closed until a model adapter and econometric adapter
    # have both been installed and tested.
    print("STOP: live agent adapter is not enabled yet.")
    print("No model call made.")
    return 4

if __name__ == "__main__":
    sys.exit(main())
