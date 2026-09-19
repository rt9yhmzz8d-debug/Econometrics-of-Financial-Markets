#!/usr/bin/env python3

from pathlib import Path
from collections import defaultdict
import csv
import json
import math
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
AR = HERE.parent
REPO = HERE.parents[2]

PROPOSAL = (
    HERE / "experiments" /
    "20260919T123700Z_ai_proposal.json"
)

PANEL = (
    AR.parent / "validation" / "external" / "barchart" /
    "processed" / "historical_panel_2002_gap_safe.csv"
)

BASE_FF_IEM = 0.7445355822620687
BASE_IEM_FF = 0.02009629893361374
OFFSETS = [1, 2, 3]
HAC_LAG = 6


def load_proposal():
    d = json.loads(PROPOSAL.read_text())

    assert d["experiment_id"] == "agent_008_lead_lag_symmetry"
    assert d["method"]["parameters"]["offsets"] == OFFSETS

    return d


def load_panel():
    with PANEL.open(newline="") as f:
        rows = list(csv.DictReader(f))

    blocks = defaultdict(list)

    for r in rows:
        blocks[r["family"]].append(r)

    families = sorted(blocks)

    assert len(rows) == 201
    assert len(families) == 8
    assert sum(r["revision_valid"] == "True" for r in rows) == 179
    assert sum(r["var_lag_valid"] == "True" for r in rows) == 160

    return rows, blocks, families


def block_hac(X, y, groups, lag=6):
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    groups = np.asarray(groups)

    n, k = X.shape

    inv = np.linalg.inv(X.T @ X)
    beta = inv @ X.T @ y
    resid = y - X @ beta

    S = np.zeros((k, k))

    for t in range(n):
        xt = X[t][:, None]
        S += resid[t] ** 2 * (xt @ xt.T)

    for ell in range(1, lag + 1):
        weight = 1.0 - ell / (lag + 1.0)

        for t in range(ell, n):
            if groups[t] != groups[t - ell]:
                continue

            xt = X[t][:, None]
            xl = X[t - ell][:, None]

            term = resid[t] * resid[t - ell] * (xt @ xl.T)
            S += weight * (term + term.T)

    V = inv @ S @ inv
    se = np.sqrt(np.maximum(np.diag(V), 0.0))
    tstat = beta / se

    p = np.asarray([
        math.erfc(abs(x) / math.sqrt(2.0))
        for x in tstat
    ])

    return beta, se, tstat, p


def baseline(blocks, families):
    X = []
    yi = []
    yf = []
    groups = []

    for fam in families:
        b = blocks[fam]

        for i, cur in enumerate(b):
            if cur["var_lag_valid"] != "True":
                continue

            assert i > 0
            lag = b[i - 1]
            assert lag["revision_valid"] == "True"

            x = [
                1.0,
                float(lag["delta_iem"]),
                float(lag["delta_ff_bp"]),
            ]

            for f in families[1:]:
                x.append(1.0 if fam == f else 0.0)

            X.append(x)
            yi.append(float(cur["delta_iem"]))
            yf.append(float(cur["delta_ff_bp"]))
            groups.append(fam)

    bi, sei, ti, pi = block_hac(X, yi, groups, HAC_LAG)
    bf, sef, tf, pf = block_hac(X, yf, groups, HAC_LAG)

    assert len(X) == 160
    assert abs(float(bi[2]) - BASE_FF_IEM) < 1e-10
    assert abs(float(bf[1]) - BASE_IEM_FF) < 1e-10

    return {
        "n": len(X),
        "meetings": len(families),
        "FF_to_IEM": {
            "beta": float(bi[2]),
            "se": float(sei[2]),
            "t": float(ti[2]),
            "p": float(pi[2]),
        },
        "IEM_to_FF": {
            "beta": float(bf[1]),
            "se": float(sef[1]),
            "t": float(tf[1]),
            "p": float(pf[1]),
        },
    }


def revision_rows(block):
    return [
        (i, r)
        for i, r in enumerate(block)
        if r["revision_valid"] == "True"
    ]


def valid_path(block, a, b):
    lo = min(a, b)
    hi = max(a, b)

    if lo == hi:
        return True

    for j in range(lo + 1, hi + 1):
        if block[j]["revision_valid"] != "True":
            return False

    return True


def estimate_temporal(blocks, families, offset, direction, temporal):
    X = []
    y = []
    groups = []

    for fam in families:
        block = blocks[fam]
        valid = revision_rows(block)

        for pos, (idx, cur) in enumerate(valid):
            other_pos = (
                pos - offset
                if temporal == "lag"
                else pos + offset
            )

            if other_pos < 0 or other_pos >= len(valid):
                continue

            other_idx, other = valid[other_pos]

            if not valid_path(block, idx, other_idx):
                continue

            if direction == "FF_to_IEM":
                dep = float(cur["delta_iem"])
                pred = float(other["delta_ff_bp"])
            else:
                dep = float(cur["delta_ff_bp"])
                pred = float(other["delta_iem"])

            x = [1.0, pred]

            for f in families[1:]:
                x.append(1.0 if fam == f else 0.0)

            X.append(x)
            y.append(dep)
            groups.append(fam)

    if not X:
        raise RuntimeError(
            f"no observations for {direction} {temporal} k={offset}"
        )

    beta, se, tstat, p = block_hac(
        X,
        y,
        groups,
        HAC_LAG,
    )

    return {
        "n": len(X),
        "meetings": len(set(groups)),
        "beta": float(beta[1]),
        "se": float(se[1]),
        "t": float(tstat[1]),
        "p": float(p[1]),
        "sign": (
            "positive"
            if beta[1] > 0
            else "negative"
            if beta[1] < 0
            else "zero"
        ),
    }


def main():
    load_proposal()
    rows, blocks, families = load_panel()

    base = baseline(blocks, families)

    results = []

    for k in OFFSETS:
        for direction in ("FF_to_IEM", "IEM_to_FF"):
            lag = estimate_temporal(
                blocks,
                families,
                k,
                direction,
                "lag",
            )

            lead = estimate_temporal(
                blocks,
                families,
                k,
                direction,
                "lead",
            )

            results.append({
                "offset": k,
                "direction": direction,
                "lag": lag,
                "lead": lead,
                "lag_minus_lead_beta":
                    lag["beta"] - lead["beta"],
            })

    evidence = {
        "experiment_id": "agent_008_lead_lag_symmetry",
        "status": "executed",
        "proposal": str(PROPOSAL.relative_to(REPO)),
        "source_panel": str(PANEL.relative_to(REPO)),
        "protected_validation_data_modified": False,
        "baseline_reproduced": True,
        "baseline": base,
        "offsets_executed": OFFSETS,
        "hac_lag": HAC_LAG,
        "meeting_fixed_effects": True,
        "all_prespecified_offsets_reported": True,
        "result_selection_performed": False,
        "null_results_recorded": True,
        "results": results,
    }

    out_dir = HERE / "outputs" / "experiment_008"
    out_dir.mkdir(parents=True, exist_ok=True)

    out = out_dir / "evidence.json"

    out.write_text(
        json.dumps(evidence, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=== EXPERIMENT 008 COMPLETE ===")
    print("baseline reproduction: PASS")

    for r in results:
        print(
            f'k={r["offset"]} '
            f'{r["direction"]} '
            f'lag={r["lag"]["beta"]:.6f} '
            f'lead={r["lead"]["beta"]:.6f} '
            f'diff={r["lag_minus_lead_beta"]:.6f} '
            f'n_lag={r["lag"]["n"]} '
            f'n_lead={r["lead"]["n"]}'
        )

    print("evidence:", out)
    print("ALL PRE-SPECIFIED OFFSETS REPORTED")
    print("NO RESULT SELECTED BY SIGNIFICANCE")


if __name__ == "__main__":
    main()
