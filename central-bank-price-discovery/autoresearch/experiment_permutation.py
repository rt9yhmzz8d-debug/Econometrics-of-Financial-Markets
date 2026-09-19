from pathlib import Path
from collections import defaultdict
import csv
import json
import numpy as np

HERE = Path(__file__).resolve().parent
PANEL = (
    HERE.parent
    / "validation"
    / "external"
    / "barchart"
    / "processed"
    / "historical_panel_2002_gap_safe.csv"
)

OUT_JSON = HERE / "permutation_evidence_002.json"
OUT_CSV = HERE / "permutation_draws_002.csv"

N_PERM = 1000
SEED = 3150

BASELINE_FF_IEM = 0.7445355822620687
BASELINE_IEM_FF = 0.02009629893361374

rng = np.random.default_rng(SEED)

with PANEL.open(newline="") as f:
    rows = list(csv.DictReader(f))

blocks = defaultdict(list)
for r in rows:
    blocks[r["family"]].append(r)

families = sorted(blocks)

assert len(rows) == 201
assert len(families) == 8

# ---------------------------------------------------------------------
# Reproduce the exact frozen baseline design first.
# ---------------------------------------------------------------------

def baseline_system():
    X, yi, yf = [], [], []

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

    return (
        np.asarray(X, dtype=float),
        np.asarray(yi, dtype=float),
        np.asarray(yf, dtype=float),
    )


def ols_coefficients(X, yi, yf):
    # Same point estimator as frozen adapter.
    inv = np.linalg.inv(X.T @ X)

    bi = inv @ X.T @ yi
    bf = inv @ X.T @ yf

    # FF -> IEM is lagged FF coefficient in IEM equation.
    # IEM -> FF is lagged IEM coefficient in FF equation.
    return float(bi[2]), float(bf[1])


X0, yi0, yf0 = baseline_system()
base_ff_iem, base_iem_ff = ols_coefficients(X0, yi0, yf0)

assert len(X0) == 160
assert abs(base_ff_iem - BASELINE_FF_IEM) < 1e-10
assert abs(base_iem_ff - BASELINE_IEM_FF) < 1e-10

print("=== BASELINE REPRODUCTION ===")
print("usable VAR rows:", len(X0))
print("FF -> IEM:", f"{base_ff_iem:.12f}")
print("IEM -> FF:", f"{base_iem_ff:.12f}")
print("BASELINE REPRODUCTION = PASS")
print()

# ---------------------------------------------------------------------
# Extract the exact revision observations that participate in the
# baseline VAR rows.
#
# Each retained item is the contemporaneous pair
# (delta_iem_t, delta_ff_t).  We permute these PAIRS jointly within
# meetings. This preserves each meeting's contemporaneous joint
# distribution while destroying chronological lead-lag ordering.
# ---------------------------------------------------------------------

meeting_revisions = {}

for fam in families:
    b = blocks[fam]

    # Identify all revisions needed to reproduce every valid VAR pair:
    # both current observations and their corresponding lag observations.
    used_indices = set()

    for i, cur in enumerate(b):
        if cur["var_lag_valid"] != "True":
            continue

        assert i > 0
        assert b[i - 1]["revision_valid"] == "True"
        assert cur["revision_valid"] == "True"

        used_indices.add(i - 1)
        used_indices.add(i)

    idx = sorted(used_indices)

    revisions = np.asarray([
        [
            float(b[i]["delta_iem"]),
            float(b[i]["delta_ff_bp"]),
        ]
        for i in idx
    ], dtype=float)

    meeting_revisions[fam] = revisions


# ---------------------------------------------------------------------
# Permutation estimator.
#
# After shuffling each meeting's paired revisions, adjacent positions
# define placebo lag/current relationships. We preserve the number of
# baseline VAR observations contributed by each meeting.
# ---------------------------------------------------------------------

baseline_n_by_family = {}

for fam in families:
    baseline_n_by_family[fam] = sum(
        r["var_lag_valid"] == "True"
        for r in blocks[fam]
    )


def permuted_system():
    X, yi, yf = [], [], []

    for fam in families:
        z = meeting_revisions[fam].copy()
        z = z[rng.permutation(len(z))]

        n_needed = baseline_n_by_family[fam]

        # Adjacent shuffled pairs generate placebo lag relationships.
        # Use exactly the baseline number of rows for this meeting.
        if len(z) - 1 < n_needed:
            raise RuntimeError(
                f"{fam}: insufficient revisions for {n_needed} VAR rows"
            )

        for i in range(1, n_needed + 1):
            lag = z[i - 1]
            cur = z[i]

            x = [
                1.0,
                float(lag[0]),
                float(lag[1]),
            ]

            for f in families[1:]:
                x.append(1.0 if fam == f else 0.0)

            X.append(x)
            yi.append(float(cur[0]))
            yf.append(float(cur[1]))

    return (
        np.asarray(X, dtype=float),
        np.asarray(yi, dtype=float),
        np.asarray(yf, dtype=float),
    )


draws = []

print(f"Running {N_PERM:,} within-meeting temporal permutations...")
print("Seed:", SEED)

for j in range(N_PERM):
    X, yi, yf = permuted_system()

    assert len(X) == 160

    ff_iem, iem_ff = ols_coefficients(X, yi, yf)

    draws.append({
        "permutation": j + 1,
        "ff_to_iem_beta": ff_iem,
        "iem_to_ff_beta": iem_ff,
    })

    if (j + 1) % 100 == 0:
        print(f"completed {j + 1}/{N_PERM}")


ff_draws = np.asarray(
    [x["ff_to_iem_beta"] for x in draws],
    dtype=float
)

iem_draws = np.asarray(
    [x["iem_to_ff_beta"] for x in draws],
    dtype=float
)

# Requested one-sided empirical exceedance probabilities.
ff_exceed = int(np.sum(ff_draws >= BASELINE_FF_IEM))
iem_exceed = int(np.sum(iem_draws >= BASELINE_IEM_FF))

ff_empirical_p = ff_exceed / N_PERM
iem_empirical_p = iem_exceed / N_PERM

# Finite-simulation correction, useful if zero permutations exceed baseline.
ff_empirical_p_plus1 = (ff_exceed + 1) / (N_PERM + 1)
iem_empirical_p_plus1 = (iem_exceed + 1) / (N_PERM + 1)


def quantiles(x):
    q = np.quantile(x, [0.01, 0.025, 0.05, 0.5, 0.95, 0.975, 0.99])
    return {
        "q01": float(q[0]),
        "q025": float(q[1]),
        "q05": float(q[2]),
        "median": float(q[3]),
        "q95": float(q[4]),
        "q975": float(q[5]),
        "q99": float(q[6]),
    }


evidence = {
    "experiment": "temporal_permutation_002",
    "frozen_parent_checkpoint": "ec15070",
    "seed": SEED,
    "permutations": N_PERM,
    "meetings": len(families),
    "usable_var_rows_per_draw": 160,
    "null_design": (
        "Jointly permute paired IEM and Fed Funds revisions within each "
        "meeting, preserving contemporaneous joint distributions and "
        "meeting identity while destroying chronological lead-lag ordering."
    ),
    "baseline": {
        "FF_to_IEM_beta": BASELINE_FF_IEM,
        "IEM_to_FF_beta": BASELINE_IEM_FF,
    },
    "FF_to_IEM": {
        "baseline_beta": BASELINE_FF_IEM,
        "placebo_mean": float(np.mean(ff_draws)),
        "placebo_sd": float(np.std(ff_draws, ddof=1)),
        "exceedances": ff_exceed,
        "empirical_p": ff_empirical_p,
        "empirical_p_plus1": ff_empirical_p_plus1,
        "quantiles": quantiles(ff_draws),
    },
    "IEM_to_FF": {
        "baseline_beta": BASELINE_IEM_FF,
        "placebo_mean": float(np.mean(iem_draws)),
        "placebo_sd": float(np.std(iem_draws, ddof=1)),
        "exceedances": iem_exceed,
        "empirical_p": iem_empirical_p,
        "empirical_p_plus1": iem_empirical_p_plus1,
        "quantiles": quantiles(iem_draws),
    },
}

with OUT_CSV.open("w", newline="") as f:
    w = csv.DictWriter(
        f,
        fieldnames=[
            "permutation",
            "ff_to_iem_beta",
            "iem_to_ff_beta",
        ],
        lineterminator="\n",
    )
    w.writeheader()
    w.writerows(draws)

OUT_JSON.write_text(
    json.dumps(evidence, indent=2) + "\n",
    encoding="utf-8",
)

print()
print("=== TEMPORAL PERMUTATION RESULTS ===")
print()
print("FF -> IEM")
print("baseline beta:", f"{BASELINE_FF_IEM:.6f}")
print("placebo mean:", f"{np.mean(ff_draws):.6f}")
print("placebo sd:", f"{np.std(ff_draws, ddof=1):.6f}")
print("exceedances:", f"{ff_exceed}/{N_PERM}")
print("empirical p:", f"{ff_empirical_p:.6f}")
print("plus-one p:", f"{ff_empirical_p_plus1:.6f}")

print()
print("IEM -> FF")
print("baseline beta:", f"{BASELINE_IEM_FF:.6f}")
print("placebo mean:", f"{np.mean(iem_draws):.6f}")
print("placebo sd:", f"{np.std(iem_draws, ddof=1):.6f}")
print("exceedances:", f"{iem_exceed}/{N_PERM}")
print("empirical p:", f"{iem_empirical_p:.6f}")
print("plus-one p:", f"{iem_empirical_p_plus1:.6f}")

print()
print("JSON:", OUT_JSON)
print("CSV:", OUT_CSV)
print("PERMUTATION TEST = PASS")
