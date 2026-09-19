#!/usr/bin/env python3

import json
import os
from pathlib import Path
from openai import OpenAI

HERE = Path(__file__).resolve().parent
BUDGET_FILE = HERE / "budget.json"

MODEL = "gpt-5.6-luna"

# Standard short-context rates, USD per 1M tokens.
INPUT_PER_M = 0.20
OUTPUT_PER_M = 1.20

# Fail closed using a deliberately conservative reservation.
MAX_OUTPUT_TOKENS = 3000
RESERVED_INPUT_TOKENS = 30000


def load_budget():
    return json.loads(BUDGET_FILE.read_text(encoding="utf-8"))


def save_budget(b):
    tmp = BUDGET_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(b, indent=2) + "\n", encoding="utf-8")
    tmp.replace(BUDGET_FILE)


def estimated_max_call_cost():
    return (
        RESERVED_INPUT_TOKENS / 1_000_000 * INPUT_PER_M
        + MAX_OUTPUT_TOKENS / 1_000_000 * OUTPUT_PER_M
    )


def budget_gate():
    b = load_budget()

    spent = float(b["estimated_spend"])
    soft = float(b["soft_limit"])
    hard = float(b["hard_limit"])
    reserve = estimated_max_call_cost()

    if spent >= soft:
        raise RuntimeError(
            f"SOFT STOP: US${spent:.4f} spent. Human review required."
        )

    if spent + reserve > hard:
        raise RuntimeError(
            f"HARD STOP: US${spent:.4f} + reserved US${reserve:.4f} "
            f"would exceed US${hard:.2f}."
        )

    return b


def call_agent(instructions, prompt):
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set")

    b = budget_gate()
    client = OpenAI()

    response = client.responses.create(
        model=MODEL,
        reasoning={"effort": "medium"},
        instructions=instructions,
        input=prompt,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    usage = response.usage

    input_tokens = int(usage.input_tokens or 0)
    output_tokens = int(usage.output_tokens or 0)

    cost = (
        input_tokens / 1_000_000 * INPUT_PER_M
        + output_tokens / 1_000_000 * OUTPUT_PER_M
    )

    b["estimated_spend"] = round(
        float(b["estimated_spend"]) + cost, 8
    )
    b["model_calls"] = int(b["model_calls"]) + 1

    save_budget(b)

    return {
        "text": response.output_text,
        "model": MODEL,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost,
        "cumulative_cost_usd": b["estimated_spend"],
    }


if __name__ == "__main__":
    print("MODEL =", MODEL)
    print("MAX RESERVED CALL COST = US$", f"{estimated_max_call_cost():.4f}")
    print("No API call made.")
