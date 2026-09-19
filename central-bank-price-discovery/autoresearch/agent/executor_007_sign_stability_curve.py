#!/usr/bin/env python3

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import statsmodels.api as sm


HERE = Path(__file__).resolve().parent
AUTORESEARCH = HERE.parent
REPO = HERE.parents[2]

PANEL = (
    AUTORESEARCH.parent / "validation" / "external" / "barchart" /
    "processed" / "historical_panel_2002_gap_safe.csv"
)
INFLUENCE = AUTORESEARCH / "influence_rows_004.csv"

BASE_FF_IEM = 0.7445355822620644
BASE_IEM_FF = 0.02009629893361374


def load_run(path):
    d = json.loads(path.read_text())

    if d["status"] != "selected_not_executed":
        raise SystemExit(
            f"STOP: run must be selected_not_executed, got {d['status']}"
        )

    proposal = d["selected_experiment"]

    if proposal["experiment_id"] != "agent_007_sign_stability_curve":
        raise SystemExit("STOP: unsupported experiment")

    design = proposal["design"]

    assert design["trim_counts"] == list(range(0, 21))
    assert design["ranking_rule"] == (
        "frozen experiment-004 influence ordering"
    )
    assert design["hac_lag"] == 6
    assert design["meeting_fixed_effects"] is True
    assert design["report_all_depths"] is True

    return d


def build_baseline():
    with PANEL.open(newline="") as f:
        rows = list(csv.DictReader(f))

    blocks = defaultdict(list)
    for r in rows:
        blocks[r["family"]].append(r)

    families = sorted(blocks)
    obs = []

    for fam in families:
        b = blocks[fam]

        for i, cur in enumerate(b):
            if cur["var_lag_valid"] != "True":
                continue

            lag = b[i - 1]

            obs.append({
                "family": fam,
                "date": cur["date"],
                "lag_iem": float(lag["delta_iem"]),
                "lag_ff": float(lag["delta_ff_bp"]),
                "cur_iem": float(cur["delta_iem"]),
                "cur_ff": float(cur["delta_ff_bp"]),
            })

    assert len(obs) == 160
    return obs, families

def estimate(obs, families):
    family_index = {fam: i for i, fam in enumerate(families)}

    y_iem = np.array([r["iem_revision"] for r in obs], dtype=float)
    y_ff = np.array([r["ff_revision"] for r in obs], dtype=float)

    x_ff_iem = []
    x_iem_ff = []

    for r in obs:
        dummies = [
            1.0 if family_index[r["family"]] == j else 0.0
            for j in range(1, len(families))
        ]

        x_ff_iem.append([
            1.0,
            r["lag_iem_revision"],
            r["lag_ff_revision"],
            *dummies,
        ])

        x_iem_ff.append([
            1.0,
            r["lag_ff_revision"],
            r["lag_iem_revision"],
            *dummies,
        ])

    fit_ff_iem = sm.OLS(
        y_iem,
        np.asarray(x_ff_iem, dtype=float),
    ).fit(
        cov_type="HAC",
        cov_kwds={"maxlags": 6},
    )

    fit_iem_ff = sm.OLS(
        y_ff,
        np.asarray(x_iem_ff, dtype=float),
    ).fit(
        cov_type="HAC",
        cov_kwds={"maxlags": 6},
    )

    return (
        float(fit_ff_iem.params[2]),
        float(fit_iem_ff.params[2]),
    )


def key(r):
    return (r["family"], r["date"])


def rankings():
    with INFLUENCE.open(newline="") as f:
        rows = list(csv.DictReader(f))

    ff_rank = sorted(
        rows,
        key=lambda r: (
            -abs(float(r["ff_to_iem_change"])),
            r["family"],
            r["date"],
        ),
    )

    iem_rank = sorted(
        rows,
        key=lambda r: (
            -abs(float(r["iem_to_ff_change"])),
            r["family"],
            r["date"],
        ),
    )

    return ff_rank, iem_rank


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: executor_007_sign_stability_curve.py RUN_JSON"
        )

    run_path = Path(sys.argv[1]).resolve()
    record = load_run(run_path)

    obs, families = build_baseline()

    ff0, iem0 = estimate(obs, families)

    assert abs(ff0 - BASE_FF_IEM) < 1e-10
    assert abs(iem0 - BASE_IEM_FF) < 1e-10

    ff_rank, iem_rank = rankings()

    trim_counts = (
        record["selected_experiment"]["design"]["trim_counts"]
    )

    results = []

    for n in trim_counts:
        drop_ff = {key(r) for r in ff_rank[:n]}

        keep_ff = [
            r for r in obs
            if key(r) not in drop_ff
        ]

        ff_beta, _ = estimate(keep_ff, families)

        drop_iem = {key(r) for r in iem_rank[:n]}

        keep_iem = [
            r for r in obs
            if key(r) not in drop_iem
        ]

        _, iem_beta = estimate(keep_iem, families)

        results.append({
            "trim_count": n,
            "FF_to_IEM": {
                "n": len(keep_ff),
                "beta": ff_beta,
                "change_from_baseline": ff_beta - ff0,
                "sign_preserved": bool(
                    np.sign(ff_beta) == np.sign(ff0)
                ),
                "removed": sorted(
                    [
                        {"family": a, "date": b}
                        for a, b in drop_ff
                    ],
                    key=lambda x: (x["family"], x["date"]),
                ),
            },
            "IEM_to_FF": {
                "n": len(keep_iem),
                "beta": iem_beta,
                "change_from_baseline": iem_beta - iem0,
                "sign_preserved": bool(
                    np.sign(iem_beta) == np.sign(iem0)
                ),
                "removed": sorted(
                    [
                        {"family": a, "date": b}
                        for a, b in drop_iem
                    ],
                    key=lambda x: (x["family"], x["date"]),
                ),
            },
        })

    evidence = {
        "experiment": "agent_007_sign_stability_curve",
        "run_id": record["run_id"],
        "preregistered_run": run_path.name,
        "baseline": {
            "n": len(obs),
            "FF_to_IEM_beta": ff0,
            "IEM_to_FF_beta": iem0,
        },
        "design": record["selected_experiment"]["design"],
        "results": results,
        "interpretation_rule": (
            "Report every preregistered deletion depth from 0 through 20. "
            "Do not select a depth based on coefficient direction, magnitude "
            "or statistical attractiveness."
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
        "engine": "executor_007_sign_stability_curve.py",
        "evidence": str(evidence_path.relative_to(REPO)),
        "baseline_reproduced": True,
        "trim_counts_executed": trim_counts,
    }

    record["evaluation"] = {
        "FF_to_IEM_sign_preserved_all": all(
            r["FF_to_IEM"]["sign_preserved"]
            for r in results
        ),
        "IEM_to_FF_sign_preserved_all": all(
            r["IEM_to_FF"]["sign_preserved"]
            for r in results
        ),
        "result_selection_performed": False,
        "null_results_recorded": True,
    }

    run_path.write_text(
        json.dumps(record, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=== SIGN STABILITY CURVE COMPLETE ===")
    print("run:", record["run_id"])
    print("baseline reproduction: PASS")

    for r in results:
        print(
            f"trim={r['trim_count']:2d}",
            f"FF->IEM={r['FF_to_IEM']['beta']:.6f}",
            f"IEM->FF={r['IEM_to_FF']['beta']:.6f}",
        )

    print("evidence:", evidence_path)
    print("STATE = EXECUTED")
    print("All preregistered depths reported.")
    print("No result selected by significance.")


if __name__ == "__main__":
    main()
