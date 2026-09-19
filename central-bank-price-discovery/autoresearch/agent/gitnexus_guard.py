#!/usr/bin/env python3

import json
import shutil
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

PROTECTED_VALIDATION = (
    REPO / "central-bank-price-discovery" / "validation"
)

BLOCKED_RISKS = {"HIGH", "CRITICAL", "UNKNOWN"}

SYMBOLS = {
    "research_cycle":
        "Function:central-bank-price-discovery/"
        "autoresearch/agent/research_agent.py:cycle",

    "implementation_plan":
        "Function:central-bank-price-discovery/"
        "autoresearch/agent/implementation_planner.py:plan",

    "executor_build":
        "Function:central-bank-price-discovery/"
        "autoresearch/agent/executor_builder.py:build",
}


def run(cmd, *, check=True):
    return subprocess.run(
        cmd,
        cwd=REPO,
        text=True,
        capture_output=True,
        check=check,
    )


def require_gitnexus():
    if shutil.which("npx") is None:
        raise SystemExit(
            "STOP: npx unavailable; GitNexus guard cannot run"
        )


def gitnexus(*args):
    require_gitnexus()

    result = run(
        ["npx", "-y", "gitnexus@latest", *args],
        check=False,
    )

    if result.returncode != 0:
        raise SystemExit(
            "STOP: GitNexus command failed:\n"
            + result.stdout
            + result.stderr
        )

    return result.stdout


def extract_json(text):
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end < start:
        raise SystemExit(
            "STOP: GitNexus returned no parseable JSON"
        )

    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"STOP: invalid GitNexus JSON: {exc}"
        )


def require_index_current():
    output = gitnexus("status")

    if "Status: ✅ up-to-date" not in output:
        raise SystemExit(
            "STOP: GitNexus index is not up-to-date"
        )

    return output


def impact(symbol):
    output = gitnexus(
        "impact",
        symbol,
        "--direction",
        "upstream",
        "--repo",
        ".",
    )

    data = extract_json(output)

    if data.get("status") == "ambiguous":
        raise SystemExit(
            "STOP: GitNexus impact target is ambiguous"
        )

    risk = str(data.get("risk", "UNKNOWN")).upper()

    if risk in BLOCKED_RISKS:
        raise SystemExit(
            f"STOP: GitNexus impact risk is {risk}"
        )

    if data.get("epistemic") not in (None, "exact"):
        raise SystemExit(
            "STOP: GitNexus impact result is not exact"
        )

    return data


def detect_changes():
    output = gitnexus(
        "detect-changes",
        "--scope",
        "all",
        "--repo",
        ".",
    )

    lowered = output.lower()

    if (
        "partial: true" in lowered
        or '"partial": true' in lowered
        or "truncated: true" in lowered
        or '"truncated": true' in lowered
    ):
        raise SystemExit(
            "STOP: GitNexus change analysis incomplete"
        )

    return output


def require_validation_untouched():
    result = run([
        "git",
        "status",
        "--porcelain",
        "--",
        str(PROTECTED_VALIDATION.relative_to(REPO)),
    ])

    if result.stdout.strip():
        raise SystemExit(
            "STOP: protected validation tree was modified:\n"
            + result.stdout
        )


def preflight(symbol_key):
    if symbol_key not in SYMBOLS:
        raise SystemExit(
            f"STOP: unknown GitNexus symbol key {symbol_key}"
        )

    require_index_current()
    result = impact(SYMBOLS[symbol_key])
    require_validation_untouched()

    return result


def postflight():
    result = detect_changes()
    require_validation_untouched()
    return result


if __name__ == "__main__":
    print("=== GITNEXUS AUTORESEARCH GUARD ===")

    require_index_current()

    for key, symbol in SYMBOLS.items():
        result = impact(symbol)
        print(
            f"{key}: "
            f"risk={result.get('risk')} "
            f"epistemic={result.get('epistemic')}"
        )

    require_validation_untouched()

    print("VALIDATION = CLEAN")
    print("GITNEXUS GUARD = PASS")
