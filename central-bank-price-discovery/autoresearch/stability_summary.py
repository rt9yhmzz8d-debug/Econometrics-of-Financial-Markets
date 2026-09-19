#!/usr/bin/env python3

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "grid_evidence.json"
OUT_JSON = HERE / "stability_summary.json"
OUT_MD = HERE / "stability_summary.md"

data = json.loads(EVIDENCE.read_text())

# Support either a top-level list or {"experiments": [...]}
if isinstance(data, list):
    experiments = data
elif "controlled_experiments" in data:
    experiments = data["controlled_experiments"]
elif "experiments" in data:
    experiments = data["experiments"]
else:
    raise KeyError(
        f"No experiment collection found. Available keys: {list(data.keys())}"
    )

def get(exp_id):
    return next(x for x in experiments if x["experiment_id"] == exp_id)

baseline = get("HAC_06")
hac = [get(x) for x in ["HAC_01", "HAC_03", "HAC_06", "HAC_09", "HAC_12"]]
lomo = [get(f"LOMO_{i:02d}") for i in range(1, 9)]
no_fe = get("NO_MEETING_FE")

directions = {
    "FF_to_IEM": "FF → IEM",
    "IEM_to_FF": "IEM → FF",
}

summary = {}

for key, label in directions.items():
    b = baseline[key]
    lomo_beta = [x[key]["beta"] for x in lomo]
    hac_raw = [x[key]["raw_p"] for x in hac]
    hac_holm = [x[key]["holm_p"] for x in hac]

    base_sign = 1 if b["beta"] > 0 else -1 if b["beta"] < 0 else 0
    retained = sum(
        (1 if x > 0 else -1 if x < 0 else 0) == base_sign
        for x in lomo_beta
    )

    summary[key] = {
        "label": label,
        "baseline_beta": b["beta"],
        "baseline_raw_p": b["raw_p"],
        "baseline_holm_p": b["holm_p"],
        "lomo_beta_min": min(lomo_beta),
        "lomo_beta_max": max(lomo_beta),
        "lomo_sign_retention": retained / len(lomo_beta),
        "hac_raw_p_min": min(hac_raw),
        "hac_raw_p_max": max(hac_raw),
        "hac_holm_p_min": min(hac_holm),
        "hac_holm_p_max": max(hac_holm),
        "no_fe_beta": no_fe[key]["beta"],
    }

OUT_JSON.write_text(json.dumps(summary, indent=2) + "\n")

lines = [
    "# ECMT3150 Historical Stability Summary",
    "",
    "Pre-specified robustness summary. No specification is selected according to statistical significance.",
    "",
]

for x in summary.values():
    lines += [
        f"## {x['label']}",
        "",
        f"- Baseline beta: {x['baseline_beta']:.4f}",
        f"- LOMO beta range: {x['lomo_beta_min']:.4f} to {x['lomo_beta_max']:.4f}",
        f"- LOMO sign retention: {100*x['lomo_sign_retention']:.0f}%",
        f"- HAC raw-p range: {x['hac_raw_p_min']:.4f} to {x['hac_raw_p_max']:.4f}",
        f"- HAC Holm-p range: {x['hac_holm_p_min']:.4f} to {x['hac_holm_p_max']:.4f}",
        f"- No-meeting-FE beta: {x['no_fe_beta']:.4f}",
        "",
    ]

lines += [
    "## Interpretation guardrail",
    "",
    "Coefficient signs are evaluated separately from inference stability. "
    "Crossing a significance threshold in an individual robustness specification "
    "does not make that specification preferred.",
    "",
]

OUT_MD.write_text("\n".join(lines))

print(OUT_MD.read_text())
print("JSON:", OUT_JSON)
print("MARKDOWN:", OUT_MD)
