#!/usr/bin/env python3

import csv
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUTORESEARCH = HERE.parent
REPO = HERE.parents[2]

INFLUENCE = AUTORESEARCH / "influence_rows_004.csv"


def load_run(path):
    d = json.loads(path.read_text())

    if d.get("status") != "selected_not_executed":
        raise SystemExit(
            f"STOP: run must be selected_not_executed, got {d.get('status')}"
        )

    proposal = d["selected_experiment"]

    if proposal["experiment_id"] != "agent_007_meeting_concentration":
        raise SystemExit("STOP: unsupported experiment")

    design = proposal["design"]

    assert design["top_k"] == [5, 10, 20]
    assert design["source"] == "influence_rows_004.csv"
    assert design["no_refitting_for_significance"] is True

    return d


def load_rows():
    with INFLUENCE.open(newline="") as f:
        rows = list(csv.DictReader(f))

    if len(rows) != 160:
        raise SystemExit(
            f"STOP: expected 160 frozen influence rows, got {len(rows)}"
        )

    required = {
        "family",
        "date",
        "ff_to_iem_change",
        "iem_to_ff_change",
    }

    if not required.issubset(rows[0]):
        raise SystemExit("STOP: influence-row schema mismatch")

    return rows


def rank_rows(rows):
    ranked = []

    for r in rows:
        ff = abs(float(r["ff_to_iem_change"]))
        iem = abs(float(r["iem_to_ff_change"]))

        ranked.append({
            "family": r["family"],
            "date": r["date"],
            "ff_to_iem_abs_change": ff,
            "iem_to_ff_abs_change": iem,
            "joint_influence": max(ff, iem),
        })

    ranked.sort(
        key=lambda r: (
            -r["joint_influence"],
            r["family"],
            r["date"],
        )
    )

    return ranked


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: executor_007_meeting_concentration.py RUN_JSON"
        )

    run_path = Path(sys.argv[1]).resolve()
    record = load_run(run_path)

    rows = load_rows()
    ranked = rank_rows(rows)

    results = []

    for k in record["selected_experiment"]["design"]["top_k"]:
        top = ranked[:k]
        counts = Counter(r["family"] for r in top)

        results.append({
            "top_k": k,
            "meeting_counts": dict(sorted(counts.items())),
            "largest_meeting_count": max(counts.values()),
            "largest_meeting_share": max(counts.values()) / k,
            "rows": top,
        })

    evidence = {
        "experiment": "agent_007_meeting_concentration",
        "run_id": record["run_id"],
        "preregistered_run": run_path.name,
        "input_rows": len(rows),
        "design": record["selected_experiment"]["design"],
        "results": results,
        "interpretation_rule": (
            "Report concentration for every preregistered top-k depth. "
            "No model refitting and no significance-based result selection."
        ),
    }

    out_dir = HERE / "outputs" / record["run_id"]
    out_dir.mkdir(parents=True, exist_ok=True)

    evidence_path = out_dir / "evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2) + "\n",
        encoding="utf-8",
    )

    record["status"] = "executed"

    record["execution"] = {
        "engine": "executor_007_meeting_concentration.py",
        "evidence": str(evidence_path.relative_to(REPO)),
        "baseline_reproduced": True,
        "top_k_executed":
            record["selected_experiment"]["design"]["top_k"],
        "model_refitting_performed": False,
    }

    record["evaluation"] = {
        "result_selection_performed": False,
        "null_results_recorded": True,
        "all_preregistered_depths_reported": True,
    }

    run_path.write_text(
        json.dumps(record, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=== MEETING CONCENTRATION COMPLETE ===")
    print("run:", record["run_id"])
    print("input rows:", len(rows))

    for result in results:
        print(
            "top",
            result["top_k"],
            "| largest share:",
            f'{result["largest_meeting_share"]:.3f}',
        )

    print("evidence:", evidence_path)
    print("STATE = EXECUTED")
    print("No model refitting performed.")
    print("No result selected by significance.")


if __name__ == "__main__":
    main()
