#!/usr/bin/env python3

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUDGET_FILE = HERE / "budget.json"


def load_budget():
    with BUDGET_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def check_budget(next_call_max_cost=0.0):
    b = load_budget()

    spent = float(b["estimated_spend"])
    soft = float(b["soft_limit"])
    hard = float(b["hard_limit"])
    projected = spent + float(next_call_max_cost)

    if projected > hard:
        print(
            f"HARD STOP: projected spend US${projected:.2f} "
            f"would exceed US${hard:.2f}."
        )
        return 2

    if spent >= soft:
        print(
            f"SOFT LIMIT: US${spent:.2f} spent. "
            "Checkpoint/review mode only."
        )
        return 1

    print(
        f"BUDGET OK: US${spent:.2f} spent | "
        f"soft US${soft:.2f} | hard US${hard:.2f} | "
        f"projected US${projected:.2f}"
    )
    return 0


if __name__ == "__main__":
    next_cost = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    sys.exit(check_budget(next_cost))
