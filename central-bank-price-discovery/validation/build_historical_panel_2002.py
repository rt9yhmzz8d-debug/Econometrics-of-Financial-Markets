from pathlib import Path
import csv
from collections import defaultdict
from datetime import date

HERE = Path(__file__).resolve().parent
RAW = HERE.parent / "raw"
MAP = HERE.parent / "meeting_map_2002.csv"

IEM_CONTRACTS = HERE.parents[1] / "generated" / "contract_register.csv"
IEM_FAMILIES  = HERE.parents[1] / "generated" / "family_register.csv"

OUT = HERE / "historical_panel_2002.csv"
SUMMARY = HERE / "historical_panel_2002_summary.csv"

def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None

# Load meeting map
meetings = []
with MAP.open(newline="") as f:
    meetings = list(csv.DictReader(f))

# Find the original IEM acquisition file through the audit code/register.
# We use audit_round4's existing pilot machinery rather than inventing
# a second probability construction.
import sys
sys.path.insert(0, str(HERE.parents[1]))
from audit_round4 import parse_contract, diagnostic_screen

# Locate candidate source CSVs already used by Round 4
validation_root = HERE.parents[1]
repo_root = validation_root.parents[1]

candidate_csvs = []
for p in repo_root.rglob("*.csv"):
    if "validation/external" in str(p):
        continue
    candidate_csvs.append(p)

# Build a contract->rows lookup from any source CSV containing
# Date/Contract/Last/Quantity-like fields.
raw_contract_rows = defaultdict(list)

for p in candidate_csvs:
    try:
        with p.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames or []
            lower = {x.lower(): x for x in fields}

            ccol = next((lower[x] for x in
                         ["contract", "contract_name", "symbol"]
                         if x in lower), None)
            dcol = next((lower[x] for x in
                         ["date", "trade_date", "observation_date"]
                         if x in lower), None)
            lcol = next((lower[x] for x in
                         ["last", "price", "last_price"]
                         if x in lower), None)
            qcol = next((lower[x] for x in
                         ["quantity", "qty", "volume"]
                         if x in lower), None)

            if not all([ccol, dcol, lcol]):
                continue

            for r in reader:
                c = r.get(ccol, "")
                if c.startswith("FR"):
                    raw_contract_rows[c].append({
                        "date": r[dcol],
                        "last": fnum(r[lcol]),
                        "quantity": fnum(r[qcol]) if qcol else None,
                    })
    except Exception:
        pass

# If raw acquisition isn't discoverable, use the generated registers to
# fail explicitly rather than silently fabricate probabilities.
if not raw_contract_rows:
    raise SystemExit(
        "RAW_IEM_SOURCE_NOT_DISCOVERED: use audit_round4.py's actual "
        "acquisition path before building the pooled panel."
    )

def load_futures(symbol):
    p = RAW / f"{symbol}_raw.csv"
    assert p.exists(), f"Missing {p}"

    out = {}
    with p.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            d = r["Time"].strip()
            if d.startswith("Downloaded from Barchart.com"):
                continue
            px = fnum(r["Latest"])
            if px is None:
                continue
            out[d] = {
                "price": px,
                "rate": 100.0 - px,
                "volume": fnum(r.get("Volume")),
            }
    return out

# Contract membership from generated register
family_contracts = defaultdict(dict)
with IEM_CONTRACTS.open(newline="") as f:
    for r in csv.DictReader(f):
        if r["role"] != "ordinary":
            continue
        family_contracts[r["family"]][r["direction_label_only"]] = r["contract"]

all_rows = []
summaries = []

for m in meetings:
    fam = m["family"]
    meeting = m["meeting_date"]
    symbol = m["zq_contract"]

    cmap = family_contracts.get(fam, {})
    needed = {"down", "same", "up"}

    if not needed.issubset(cmap):
        print(f"SKIP {fam}: incomplete IEM direction mapping {cmap}")
        continue

    # Reconstruct daily IEM values using positive-quantity carry only,
    # mirroring the diagnostic nature of the existing Round 4 pilot.
    daily = defaultdict(dict)

    for direction in ["down", "same", "up"]:
        contract = cmap[direction]
        rows = sorted(raw_contract_rows.get(contract, []),
                      key=lambda x: x["date"])

        last_positive = None

        for r in rows:
            if r["date"] >= meeting:
                continue

            q = r["quantity"]
            if q is None or q > 0:
                if r["last"] is not None:
                    last_positive = r["last"]

            if last_positive is not None:
                daily[r["date"]][direction] = last_positive

    iem = {}
    for d, vals in daily.items():
        if not needed.issubset(vals):
            continue
        total = vals["down"] + vals["same"] + vals["up"]
        if total <= 0:
            continue

        pdown = vals["down"] / total
        psame = vals["same"] / total
        pup = vals["up"] / total

        iem[d] = {
            "p_down": pdown,
            "p_same": psame,
            "p_up": pup,
            "score": 100.0 * (pup - pdown),
        }

    ff = load_futures(symbol)

    dates = sorted(
        d for d in (set(iem) & set(ff))
        if d < meeting
    )

    block = []

    for d in dates:
        block.append({
            "family": fam,
            "meeting_date": meeting,
            "contract": symbol,
            "date": d,
            "iem_score": iem[d]["score"],
            "ff_rate_pct": ff[d]["rate"],
            "ff_price": ff[d]["price"],
            "ff_volume": ff[d]["volume"],
        })

    # Revisions between consecutive matched TRADING observations
    for i, r in enumerate(block):
        r["delta_iem"] = ""
        r["delta_ff_bp"] = ""
        r["revision_valid"] = False
        r["var_lag_valid"] = False

        if i >= 1:
            prev = block[i-1]
            r["delta_iem"] = r["iem_score"] - prev["iem_score"]
            r["delta_ff_bp"] = (
                r["ff_rate_pct"] - prev["ff_rate_pct"]
            ) * 100.0
            r["revision_valid"] = True

        # VAR(1) needs current revision and immediately preceding
        # revision within the SAME meeting block.
        if i >= 2 and r["revision_valid"] and block[i-1]["revision_valid"]:
            r["var_lag_valid"] = True

    all_rows.extend(block)

    summaries.append({
        "family": fam,
        "meeting_date": meeting,
        "contract": symbol,
        "matched_levels": len(block),
        "valid_revisions": sum(x["revision_valid"] for x in block),
        "usable_var_rows": sum(x["var_lag_valid"] for x in block),
    })

OUT.parent.mkdir(parents=True, exist_ok=True)

fields = [
    "family","meeting_date","contract","date",
    "iem_score","ff_rate_pct","ff_price","ff_volume",
    "delta_iem","delta_ff_bp","revision_valid","var_lag_valid"
]

with OUT.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(all_rows)

with SUMMARY.open("w", newline="") as f:
    fields2 = [
        "family","meeting_date","contract",
        "matched_levels","valid_revisions","usable_var_rows"
    ]
    w = csv.DictWriter(f, fieldnames=fields2)
    w.writeheader()
    w.writerows(summaries)

print("=== 2002 MULTI-MEETING PANEL ===")
for x in summaries:
    print(
        x["family"], x["meeting_date"], x["contract"],
        "levels=", x["matched_levels"],
        "revisions=", x["valid_revisions"],
        "VAR rows=", x["usable_var_rows"]
    )

print()
print("Meetings retained:", len(summaries))
print("Matched levels:", sum(x["matched_levels"] for x in summaries))
print("Valid revisions:", sum(x["valid_revisions"] for x in summaries))
print("Usable VAR rows:", sum(x["usable_var_rows"] for x in summaries))
print("Panel:", OUT)
print("Summary:", SUMMARY)
