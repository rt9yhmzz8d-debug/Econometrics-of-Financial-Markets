from pathlib import Path
from datetime import date
import csv

HERE = Path(__file__).resolve().parent

IEM = HERE / "generated" / "pilot_2001_11_06.csv"
FF = HERE / "external" / "barchart" / "raw" / "ZQX01_2001_raw.csv"
OUT = HERE / "external" / "barchart" / "processed" / "paired_pilot_2001_11_06.csv"

def number(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None

iem = {}

with IEM.open(newline="") as f:
    for r in csv.DictReader(f):
        if r["diagnostic_screen_pass"] != "True":
            continue
        if r["date"] >= "2001-11-06":
            continue

        score = number(r["diagnostic_directional_score"])

        if score is not None:
            iem[r["date"]] = score

ff = {}

with FF.open(newline="", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        d = r["Time"].strip()

        if d.startswith("Downloaded from Barchart.com"):
            continue
        if d >= "2001-11-06":
            continue

        price = number(r["Latest"])
        volume = number(r["Volume"])

        if price is not None:
            ff[d] = {
                "price": price,
                "rate": 100.0 - price,
                "volume": volume,
            }

dates = sorted(set(iem) & set(ff))
rows = []

for i, d in enumerate(dates):
    row = {
        "date": d,
        "iem_directional_score": iem[d],
        "zqx01_price": ff[d]["price"],
        "ff_implied_rate_pct": ff[d]["rate"],
        "volume": ff[d]["volume"],
        "delta_iem": "",
        "delta_ff_bp": "",
        "revision_valid": False,
        "break_reason": "first_observation",
    }

    if i > 0:
        previous = dates[i - 1]
        gap = (
            date.fromisoformat(d)
            - date.fromisoformat(previous)
        ).days

        if gap == 1:
            row["delta_iem"] = iem[d] - iem[previous]
            row["delta_ff_bp"] = (
                ff[d]["rate"] - ff[previous]["rate"]
            ) * 100.0
            row["revision_valid"] = True
            row["break_reason"] = ""
        else:
            row["break_reason"] = f"calendar_gap_{gap}_days"

    rows.append(row)

OUT.parent.mkdir(parents=True, exist_ok=True)

fields = [
    "date",
    "iem_directional_score",
    "zqx01_price",
    "ff_implied_rate_pct",
    "volume",
    "delta_iem",
    "delta_ff_bp",
    "revision_valid",
    "break_reason",
]

with OUT.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)

valid = [r for r in rows if r["revision_valid"]]

print("=== PAIRED 2001 PILOT ===")
print("Matched pre-meeting levels:", len(rows))
print()

for r in rows:
    print(
        r["date"],
        f"IEM={r['iem_directional_score']:.4f}",
        f"FF={r['ff_implied_rate_pct']:.3f}%",
        f"dIEM={r['delta_iem']}",
        f"dFFbp={r['delta_ff_bp']}",
        f"valid={r['revision_valid']}",
        r["break_reason"],
    )

print()
print("Valid revisions:", len(valid))

# A bivariate VAR(1) with intercept has 3 parameters per equation.
# A tiny handful of observations is not treated as an estimable
# lead-lag system.
if len(valid) < 10:
    print("VAR_GRANGER_READY = FALSE")
    print("Reason: insufficient admissible pre-meeting daily revisions.")
else:
    print("VAR_GRANGER_READY = TRUE")

print("Output:", OUT)
