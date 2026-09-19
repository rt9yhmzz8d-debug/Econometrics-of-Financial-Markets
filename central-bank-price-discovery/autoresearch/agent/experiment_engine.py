#!/usr/bin/env python3

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import csv
import math
import numpy as np

HERE = Path(__file__).resolve().parent
AUTORESEARCH = HERE.parent
PROJECT = AUTORESEARCH.parent

PANEL = (
    PROJECT
    / "validation"
    / "external"
    / "barchart"
    / "processed"
    / "historical_panel_2002_gap_safe.csv"
)

BASELINE = {
    "rows": 160,
    "meetings": 8,
    "FF_to_IEM_beta": 0.7445355822620687,
    "IEM_to_FF_beta": 0.02009629893361374,
}


def load_panel():
    if not PANEL.exists():
        raise RuntimeError(f"canonical panel missing: {PANEL}")

    with PANEL.open(newline="") as f:
        rows = list(csv.DictReader(f))

    blocks = defaultdict(list)

    for row in rows:
        blocks[row["family"]].append(row)

    families = sorted(blocks)

    if len(rows) != 201:
        raise RuntimeError(
            f"expected 201 matched levels, found {len(rows)}"
        )

    if len(families) != 8:
        raise RuntimeError(
            f"expected 8 meetings, found {len(families)}"
        )

    valid_revisions = sum(
        r["revision_valid"] == "True"
        for r in rows
    )

    valid_var = sum(
        r["var_lag_valid"] == "True"
        for r in rows
    )

    if valid_revisions != 179:
        raise RuntimeError(
            f"expected 179 valid revisions, found {valid_revisions}"
        )

    if valid_var != 160:
        raise RuntimeError(
            f"expected 160 VAR rows, found {valid_var}"
        )

    return rows, blocks, families


def baseline_system(blocks, families):
    X = []
    yi = []
    yf = []
    groups = []

    for fam in families:
        block = blocks[fam]

        for i, cur in enumerate(block):
            if cur["var_lag_valid"] != "True":
                continue

            if i == 0:
                raise RuntimeError(
                    "VAR-valid observation has no lag"
                )

            lag = block[i - 1]

            if lag["revision_valid"] != "True":
                raise RuntimeError(
                    "baseline lag is not revision-valid"
                )

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

    return (
        np.asarray(X, dtype=float),
        np.asarray(yi, dtype=float),
        np.asarray(yf, dtype=float),
        np.asarray(groups),
    )


def block_hac(X, y, groups, lag=6):
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

            term = (
                resid[t]
                * resid[t - ell]
                * (xt @ xl.T)
            )

            S += weight * (term + term.T)

    V = inv @ S @ inv

    se = np.sqrt(
        np.maximum(np.diag(V), 0.0)
    )

    tstat = beta / se

    p = np.asarray([
        math.erfc(abs(x) / math.sqrt(2.0))
        for x in tstat
    ])

    return beta, se, tstat, p


def reproduce_baseline():
    rows, blocks, families = load_panel()

    X, yi, yf, groups = baseline_system(
        blocks,
        families,
    )

    if len(X) != BASELINE["rows"]:
        raise RuntimeError(
            f"baseline rows changed: {len(X)}"
        )

    bi, sei, ti, pi = block_hac(
        X,
        yi,
        groups,
        lag=6,
    )

    bf, sef, tf, pf = block_hac(
        X,
        yf,
        groups,
        lag=6,
    )

    ff_iem = float(bi[2])
    iem_ff = float(bf[1])

    if abs(
        ff_iem - BASELINE["FF_to_IEM_beta"]
    ) >= 1e-10:
        raise RuntimeError(
            "FF -> IEM baseline reproduction failed"
        )

    if abs(
        iem_ff - BASELINE["IEM_to_FF_beta"]
    ) >= 1e-10:
        raise RuntimeError(
            "IEM -> FF baseline reproduction failed"
        )

    return {
        "matched_levels": len(rows),
        "usable_var_rows": len(X),
        "meetings": len(families),
        "FF_to_IEM": {
            "beta": ff_iem,
            "se": float(sei[2]),
            "t": float(ti[2]),
            "p": float(pi[2]),
        },
        "IEM_to_FF": {
            "beta": iem_ff,
            "se": float(sef[1]),
            "t": float(tf[1]),
            "p": float(pf[1]),
        },
    }


def main():
    result = reproduce_baseline()

    print("=== GENERIC EXPERIMENT ENGINE ===")
    print("canonical panel:", PANEL)
    print("matched levels:", result["matched_levels"])
    print("usable VAR rows:", result["usable_var_rows"])
    print("meetings:", result["meetings"])

    print(
        "FF -> IEM:",
        f'{result["FF_to_IEM"]["beta"]:.12f}',
    )

    print(
        "IEM -> FF:",
        f'{result["IEM_to_FF"]["beta"]:.12f}',
    )

    print("BASELINE REPRODUCTION = PASS")
    print("EXPERIMENT 008 = NOT EXECUTED")


if __name__ == "__main__":
    main()
