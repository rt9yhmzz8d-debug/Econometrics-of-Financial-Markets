from pathlib import Path
from collections import defaultdict
from datetime import date, timedelta
import csv
import math
import json
import argparse
import numpy as np

HERE = Path(__file__).resolve().parent
VALIDATION = HERE.parent / "validation"
BC = VALIDATION / "external" / "barchart"

# Validated source is read-only.
PANEL0 = BC / "processed" / "historical_panel_2002_gap_safe.csv"

# Output paths are initialised after experiment arguments are parsed.

parser = argparse.ArgumentParser()
parser.add_argument("--hac-lag", type=int, default=6)
parser.add_argument("--experiment-id", default="baseline")
parser.add_argument("--drop-meeting", default="")
parser.add_argument("--meeting-fe", choices=["on", "off"], default="on")
args = parser.parse_args()

if not 0 <= args.hac_lag <= 12:
    raise SystemExit("STOP: --hac-lag must be between 0 and 12")

HAC_LAG = args.hac_lag
EXPERIMENT_ID = args.experiment_id
DROP_MEETING = args.drop_meeting.strip()
MEETING_FE = args.meeting_fe == "on"

# AutoResearch writes only inside its own sandbox.
OUTPUT = HERE / "outputs" / EXPERIMENT_ID
OUTPUT.mkdir(parents=True, exist_ok=True)

RESULT = OUTPUT / "historical_var_baseline.csv"
LOMO = OUTPUT / "historical_var_baseline_lomo.csv"

# The final gap-safe panel has already encoded the conservative closure/gap
# decision. This script verifies that record and reproduces the final
# econometric estimates from it.

blocks = defaultdict(list)

with PANEL0.open(newline="") as f:
    rows = list(csv.DictReader(f))

for r in rows:
    blocks[r["family"]].append(r)

families = sorted(blocks)

assert len(rows) == 201, f"Expected 201 matched levels, got {len(rows)}"
assert len(families) == 8, f"Expected 8 meetings, got {len(families)}"

valid_revisions = sum(r["revision_valid"] == "True" for r in rows)
valid_var = sum(r["var_lag_valid"] == "True" for r in rows)

assert valid_revisions == 179, valid_revisions
assert valid_var == 160, valid_var

def build_system(keep):
    keep = sorted(keep)
    X, yi, yf, groups = [], [], [], []

    for fam in keep:
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

            # Meeting fixed effects: first retained meeting omitted.
            if MEETING_FE:
                for f in keep[1:]:
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

def block_hac(X, y, groups, L=6):
    n, k = X.shape
    inv = np.linalg.inv(X.T @ X)
    beta = inv @ X.T @ y
    resid = y - X @ beta

    S = np.zeros((k, k))

    # Lag zero.
    for t in range(n):
        xt = X[t][:, None]
        S += resid[t] ** 2 * (xt @ xt.T)

    # Bartlett/Newey-West terms. Never cross meeting boundaries.
    for ell in range(1, L + 1):
        weight = 1.0 - ell / (L + 1.0)

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

def estimate(keep):
    X, yi, yf, groups = build_system(keep)

    bi, sei, ti, pi = block_hac(X, yi, groups, HAC_LAG)
    bf, sef, tf, pf = block_hac(X, yf, groups, HAC_LAG)

    return {
        "n": len(X),
        "meetings": len(keep),
        "ff_iem_b": bi[2],
        "ff_iem_se": sei[2],
        "ff_iem_t": ti[2],
        "ff_iem_p": pi[2],
        "iem_ff_b": bf[1],
        "iem_ff_se": sef[1],
        "iem_ff_t": tf[1],
        "iem_ff_p": pf[1],
    }

if DROP_MEETING:
    if DROP_MEETING not in families:
        raise SystemExit(
            "STOP: --drop-meeting must be one of: " + ", ".join(families)
        )
    ACTIVE_FAMILIES = [f for f in families if f != DROP_MEETING]
else:
    ACTIVE_FAMILIES = families

full = estimate(ACTIVE_FAMILIES)

if not DROP_MEETING and MEETING_FE:
    assert full["n"] == 160

# Holm adjustment across the two historical directional tests.
tests = sorted([
    ("FF_to_IEM", full["ff_iem_p"]),
    ("IEM_to_FF", full["iem_ff_p"]),
], key=lambda x: x[1])

holm = {}
running = 0.0

for i, (name, p) in enumerate(tests):
    adjusted = min(1.0, (len(tests) - i) * p)
    running = max(running, adjusted)
    holm[name] = running

# Freeze expected numerical reproduction only for the declared baseline.
if HAC_LAG == 6 and not DROP_MEETING and MEETING_FE:
    assert abs(full["ff_iem_b"] - 0.7445355822620687) < 1e-10
    assert abs(full["ff_iem_p"] - 0.13964990608962932) < 1e-10
    assert abs(full["iem_ff_b"] - 0.02009629893361374) < 1e-10
    assert abs(full["iem_ff_p"] - 0.04066711360635779) < 1e-10
    assert abs(holm["IEM_to_FF"] - 0.08133422721271558) < 1e-10

with RESULT.open("w", newline="") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow([
        "direction", "beta", "block_hac6_se", "t_stat",
        "raw_p", "holm_p", "n", "meetings"
    ])
    w.writerow([
        "FF_to_IEM",
        full["ff_iem_b"], full["ff_iem_se"], full["ff_iem_t"],
        full["ff_iem_p"], holm["FF_to_IEM"], full["n"], full["meetings"]
    ])
    w.writerow([
        "IEM_to_FF",
        full["iem_ff_b"], full["iem_ff_se"], full["iem_ff_t"],
        full["iem_ff_p"], holm["IEM_to_FF"], full["n"], full["meetings"]
    ])

lomo = []

if not DROP_MEETING and MEETING_FE:
    for dropped in families:
        keep = [x for x in families if x != dropped]
        r = estimate(keep)
        r["dropped_family"] = dropped
        lomo.append(r)

with LOMO.open("w", newline="") as f:
    fields = [
        "dropped_family", "n", "meetings",
        "ff_iem_b", "ff_iem_se", "ff_iem_t", "ff_iem_p",
        "iem_ff_b", "iem_ff_se", "iem_ff_t", "iem_ff_p",
    ]
    w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    w.writerows(lomo)

print("=== FINAL HISTORICAL REPRODUCTION ===")
print("meetings:", len(ACTIVE_FAMILIES))
print("matched levels:", len(rows))
print("valid revisions:", valid_revisions)
print("usable VAR rows:", full["n"])
print()
print("FF -> IEM")
print(f"beta={full['ff_iem_b']:.6f}")
print(f"raw_p={full['ff_iem_p']:.6f}")
print(f"holm_p={holm['FF_to_IEM']:.6f}")
print()
print("IEM -> FF")
print(f"beta={full['iem_ff_b']:.6f}")
print(f"raw_p={full['iem_ff_p']:.6f}")
print(f"holm_p={holm['IEM_to_FF']:.6f}")
print()
if HAC_LAG == 6 and not DROP_MEETING and MEETING_FE:
    print("REPRODUCTION = PASS")
else:
    print("EXPERIMENT = PASS")


summary = {
    "experiment_id": EXPERIMENT_ID,
    "hac_lag": HAC_LAG,
    "drop_meeting": DROP_MEETING or None,
    "meeting_fixed_effects": MEETING_FE,
    "meetings": len(ACTIVE_FAMILIES),
    "matched_levels": len(rows),
    "valid_revisions": valid_revisions,
    "usable_var_rows": full["n"],
    "FF_to_IEM": {
        "beta": float(full["ff_iem_b"]),
        "se": float(full["ff_iem_se"]),
        "raw_p": float(full["ff_iem_p"]),
        "holm_p": float(holm["FF_to_IEM"])
    },
    "IEM_to_FF": {
        "beta": float(full["iem_ff_b"]),
        "se": float(full["iem_ff_se"]),
        "raw_p": float(full["iem_ff_p"]),
        "holm_p": float(holm["IEM_to_FF"])
    }
}

(OUTPUT / "result.json").write_text(
    json.dumps(summary, indent=2) + "\n",
    encoding="utf-8"
)

print("RESULT_JSON =", OUTPUT / "result.json")
