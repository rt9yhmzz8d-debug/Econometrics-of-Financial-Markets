from pathlib import Path
from collections import defaultdict
import csv
import json
import sys
import numpy as np

HERE = Path(__file__).resolve().parent
AR = HERE.parent
REPO = HERE.parents[2]

PANEL = (
    AR.parent / "validation" / "external" / "barchart" /
    "processed" / "historical_panel_2002_gap_safe.csv"
)
INFLUENCE = AR / "influence_rows_004.csv"

BASE_FF_IEM = 0.7445355822620687
BASE_IEM_FF = 0.02009629893361374


def load_run(path):
    d = json.loads(path.read_text())
    if d["status"] != "validated":
        raise SystemExit(
            f"STOP: run must be validated, got {d['status']}"
        )

    proposal = d["proposal"]

    if proposal["experiment_id"] != "agent_006_influence_trim":
        raise SystemExit("STOP: unsupported experiment")

    design = proposal["design"]

    assert design["baseline_rows"] == 160
    assert design["hac_lag"] == 6
    assert design["meeting_fixed_effects"] is True
    assert design["trim_counts"] == [1, 3, 5, 10]

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
    X = []
    yi = []
    yf = []

    for r in obs:
        x = [
            1.0,
            r["lag_iem"],
            r["lag_ff"],
        ]

        for fam in families[1:]:
            x.append(1.0 if r["family"] == fam else 0.0)

        X.append(x)
        yi.append(r["cur_iem"])
        yf.append(r["cur_ff"])

    X = np.asarray(X, dtype=float)
    yi = np.asarray(yi, dtype=float)
    yf = np.asarray(yf, dtype=float)

    bi = np.linalg.lstsq(X, yi, rcond=None)[0]
    bf = np.linalg.lstsq(X, yf, rcond=None)[0]

    return float(bi[2]), float(bf[1])


def rankings():
    with INFLUENCE.open(newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 160

    ff = sorted(
        rows,
        key=lambda r: abs(float(r["ff_to_iem_change"])),
        reverse=True,
    )

    iem = sorted(
        rows,
        key=lambda r: abs(float(r["iem_to_ff_change"])),
        reverse=True,
    )

    return ff, iem


def key(r):
    return (r["family"], r["date"])


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: executor.py RUN_JSON")

    run_path = Path(sys.argv[1]).resolve()
    record = load_run(run_path)

    obs, families = build_baseline()

    ff0, iem0 = estimate(obs, families)

    assert abs(ff0 - BASE_FF_IEM) < 1e-10
    assert abs(iem0 - BASE_IEM_FF) < 1e-10

    ff_rank, iem_rank = rankings()
    trim_counts = record["proposal"]["design"]["trim_counts"]

    results = []

    for n in trim_counts:

        # Direction-specific rankings are fixed by Experiment 004.
        drop_ff = {key(r) for r in ff_rank[:n]}
        keep_ff = [
            r for r in obs
            if (r["family"], r["date"]) not in drop_ff
        ]
        ff_beta, _ = estimate(keep_ff, families)

        drop_iem = {key(r) for r in iem_rank[:n]}
        keep_iem = [
            r for r in obs
            if (r["family"], r["date"]) not in drop_iem
        ]
        _, iem_beta = estimate(keep_iem, families)

        results.append({
            "trim_count": n,
            "FF_to_IEM": {
                "n": len(keep_ff),
                "beta": ff_beta,
                "change_from_baseline": ff_beta - ff0,
                "sign_preserved": bool(np.sign(ff_beta) == np.sign(ff0)),
                "removed": sorted(
                    [{"family": a, "date": b} for a, b in drop_ff],
                    key=lambda x: (x["family"], x["date"]),
                ),
            },
            "IEM_to_FF": {
                "n": len(keep_iem),
                "beta": iem_beta,
                "change_from_baseline": iem_beta - iem0,
                "sign_preserved": bool(np.sign(iem_beta) == np.sign(iem0)),
                "removed": sorted(
                    [{"family": a, "date": b} for a, b in drop_iem],
                    key=lambda x: (x["family"], x["date"]),
                ),
            },
        })

    evidence = {
        "experiment": "agent_006_influence_trim",
        "run_id": record["run_id"],
        "preregistered_run": run_path.name,
        "baseline": {
            "n": 160,
            "FF_to_IEM_beta": ff0,
            "IEM_to_FF_beta": iem0,
        },
        "design": record["proposal"]["design"],
        "results": results,
        "interpretation_rule": (
            "Report all preregistered trim counts regardless of direction, "
            "magnitude or statistical attractiveness."
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
        "engine": "executor.py",
        "evidence": str(evidence_path.relative_to(REPO)),
        "baseline_reproduced": True,
        "trim_counts_executed": trim_counts,
    }

    record["evaluation"] = {
        "FF_to_IEM_sign_preserved_all": all(
            r["FF_to_IEM"]["sign_preserved"] for r in results
        ),
        "IEM_to_FF_sign_preserved_all": all(
            r["IEM_to_FF"]["sign_preserved"] for r in results
        ),
        "result_selection_performed": False,
        "null_results_recorded": True,
    }

    run_path.write_text(
        json.dumps(record, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=== AUTORESEARCH EXECUTION COMPLETE ===")
    print("run:", record["run_id"])
    print("baseline reproduction: PASS")
    print()

    for r in results:
        print(
            f"trim={r['trim_count']:2d}",
            f"FF->IEM={r['FF_to_IEM']['beta']:.6f}",
            f"IEM->FF={r['IEM_to_FF']['beta']:.6f}",
        )

    print()
    print("evidence:", evidence_path)
    print("STATE = EXECUTED")
    print("No result was selected by significance.")


if __name__ == "__main__":
    main()
