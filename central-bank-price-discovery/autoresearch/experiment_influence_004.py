from pathlib import Path
from collections import defaultdict
import csv
import json
import numpy as np

HERE = Path(__file__).resolve().parent
PANEL = (
    HERE.parent / "validation" / "external" / "barchart" /
    "processed" / "historical_panel_2002_gap_safe.csv"
)

OUT_JSON = HERE / "influence_evidence_004.json"
OUT_CSV = HERE / "influence_rows_004.csv"

BASE_FF_IEM = 0.7445355822620687
BASE_IEM_FF = 0.02009629893361374

with PANEL.open(newline="") as f:
    rows = list(csv.DictReader(f))

blocks = defaultdict(list)
for r in rows:
    blocks[r["family"]].append(r)

families = sorted(blocks)
assert len(families) == 8

def build_system(drop=None):
    X, yi, yf, labels = [], [], [], []

    for fam in families:
        b = blocks[fam]

        for i, cur in enumerate(b):
            if cur["var_lag_valid"] != "True":
                continue

            key = (fam, cur["date"])
            if drop is not None and key == drop:
                continue

            lag = b[i - 1]

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
            labels.append(key)

    return np.asarray(X), np.asarray(yi), np.asarray(yf), labels

def estimate(drop=None):
    X, yi, yf, labels = build_system(drop)

    bi = np.linalg.lstsq(X, yi, rcond=None)[0]
    bf = np.linalg.lstsq(X, yf, rcond=None)[0]

    return float(bi[2]), float(bf[1]), labels

base_ff, base_iem, labels = estimate()

assert abs(base_ff - BASE_FF_IEM) < 1e-10
assert abs(base_iem - BASE_IEM_FF) < 1e-10
assert len(labels) == 160

results = []

for fam, date in labels:
    ff, iem, _ = estimate((fam, date))

    results.append({
        "family": fam,
        "date": date,
        "ff_to_iem_beta": ff,
        "iem_to_ff_beta": iem,
        "ff_to_iem_change": ff - BASE_FF_IEM,
        "iem_to_ff_change": iem - BASE_IEM_FF,
        "ff_to_iem_pct_change":
            100 * (ff - BASE_FF_IEM) / abs(BASE_FF_IEM),
        "iem_to_ff_pct_change":
            100 * (iem - BASE_IEM_FF) / abs(BASE_IEM_FF),
    })

with OUT_CSV.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=results[0].keys())
    w.writeheader()
    w.writerows(results)

worst_ff = sorted(
    results,
    key=lambda x: abs(x["ff_to_iem_change"]),
    reverse=True
)[:10]

worst_iem = sorted(
    results,
    key=lambda x: abs(x["iem_to_ff_change"]),
    reverse=True
)[:10]

evidence = {
    "experiment": "leave_one_observation_out_influence_004",
    "parent_checkpoint": "7f3cf19",
    "baseline_n": 160,
    "baseline": {
        "FF_to_IEM": BASE_FF_IEM,
        "IEM_to_FF": BASE_IEM_FF,
    },
    "maximum_absolute_change": {
        "FF_to_IEM": max(abs(x["ff_to_iem_change"]) for x in results),
        "IEM_to_FF": max(abs(x["iem_to_ff_change"]) for x in results),
    },
    "sign_flips": {
        "FF_to_IEM": sum(
            np.sign(x["ff_to_iem_beta"]) != np.sign(BASE_FF_IEM)
            for x in results
        ),
        "IEM_to_FF": sum(
            np.sign(x["iem_to_ff_beta"]) != np.sign(BASE_IEM_FF)
            for x in results
        ),
    },
    "top_10_FF_to_IEM_influence": worst_ff,
    "top_10_IEM_to_FF_influence": worst_iem,
}

OUT_JSON.write_text(
    json.dumps(
        evidence,
        indent=2,
        default=lambda x: x.item() if hasattr(x, "item") else x
    ) + "\n"
)

print("=== EXPERIMENT 004: LEAVE-ONE-OBSERVATION-OUT ===")
print("baseline rows:", len(labels))
print()

print("FF -> IEM")
print("baseline:", BASE_FF_IEM)
print("max absolute beta change:",
      evidence["maximum_absolute_change"]["FF_to_IEM"])
print("sign flips:", evidence["sign_flips"]["FF_to_IEM"])

print()
print("IEM -> FF")
print("baseline:", BASE_IEM_FF)
print("max absolute beta change:",
      evidence["maximum_absolute_change"]["IEM_to_FF"])
print("sign flips:", evidence["sign_flips"]["IEM_to_FF"])

print("\n=== MOST INFLUENTIAL FF -> IEM ===")
for x in worst_ff:
    print(
        x["family"], x["date"],
        "beta =", round(x["ff_to_iem_beta"], 6),
        "change =", round(x["ff_to_iem_change"], 6)
    )

print("\n=== MOST INFLUENTIAL IEM -> FF ===")
for x in worst_iem:
    print(
        x["family"], x["date"],
        "beta =", round(x["iem_to_ff_beta"], 6),
        "change =", round(x["iem_to_ff_change"], 6)
    )

print("\nJSON:", OUT_JSON)
print("CSV:", OUT_CSV)
print("EXPERIMENT 004 = PASS")
