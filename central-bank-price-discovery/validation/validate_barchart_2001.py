from pathlib import Path
import csv
import hashlib
from datetime import datetime

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "external" / "barchart" / "raw"
OUT = ROOT / "external" / "barchart" / "processed"
OUT.mkdir(parents=True, exist_ok=True)

FILES = {
    "ZQX01": {
        "path": RAW / "ZQX01_2001_raw.csv",
        "sha256": "39a4436ec42639e3d53319042edc3125ecc34bd5127ad4a7b7e1ca23fe0ffc73",
        "contract": "November 2001",
    },
    "ZQZ01": {
        "path": RAW / "ZQZ01_2001_raw.csv",
        "sha256": "fa5d458fa74bae76f4dbaecfa9e88bc6b2d68e79e16d2a1e16e9324c78570f30",
        "contract": "December 2001",
    },
}

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()

def parse_number(value):
    value = value.strip().replace(",", "")
    if value in {"", "N/A", "NA", "-"}:
        return None
    return float(value)

def load(symbol, spec):
    path = spec["path"]

    assert path.exists(), f"{symbol}: missing raw file"
    actual_hash = sha256(path)
    assert actual_hash == spec["sha256"], (
        f"{symbol}: SHA mismatch\n"
        f"expected {spec['sha256']}\nactual   {actual_hash}"
    )

    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        print(f"{symbol} columns:", reader.fieldnames)
        raw = list(reader)

    assert raw, f"{symbol}: no rows"

    date_col = next(
        (x for x in ["Time", "Date", "Trading Day", "Trade Date"] if x in raw[0]),
        None
    )
    assert date_col, f"{symbol}: cannot identify date column"

    latest_col = next(
        (x for x in ["Last", "Latest", "Close", "Settle"] if x in raw[0]),
        None
    )
    assert latest_col, f"{symbol}: cannot identify close/latest column"

    rows = []
    seen = set()

    for r in raw:
        date_text = r[date_col].strip()

        # Barchart appends a provenance/footer row after the observations.
        # Keep it in the hashed raw file but exclude it from data parsing.
        if date_text.startswith("Downloaded from Barchart.com"):
            continue

        try:
            d = datetime.strptime(date_text, "%Y-%m-%d").date()
        except ValueError:
            d = datetime.strptime(date_text, "%m/%d/%Y").date()
        assert d not in seen, f"{symbol}: duplicate date {d}"
        seen.add(d)

        row = {
            "date": d,
            "open": parse_number(r.get("Open", "")),
            "high": parse_number(r.get("High", "")),
            "low": parse_number(r.get("Low", "")),
            "price": parse_number(r.get(latest_col, "")),
            "volume": parse_number(r.get("Volume", "")),
            "open_interest": parse_number(
                r.get("Open Int", r.get("Open Interest", ""))
            ),
        }

        vals = [row["open"], row["high"], row["low"], row["price"]]
        if all(v is not None for v in vals):
            assert row["high"] >= max(row["open"], row["low"], row["price"]), \
                f"{symbol}: bad high on {d}"
            assert row["low"] <= min(row["open"], row["high"], row["price"]), \
                f"{symbol}: bad low on {d}"

        if row["volume"] is not None:
            assert row["volume"] >= 0, f"{symbol}: negative volume on {d}"

        if row["price"] is not None:
            row["implied_rate_pct"] = 100.0 - row["price"]
        else:
            row["implied_rate_pct"] = None

        rows.append(row)

    rows.sort(key=lambda x: x["date"])
    return rows

data = {symbol: load(symbol, spec) for symbol, spec in FILES.items()}

def by_date(rows):
    return {r["date"].isoformat(): r for r in rows}

nov = by_date(data["ZQX01"])
dec = by_date(data["ZQZ01"])

for symbol, d in [("ZQX01", nov), ("ZQZ01", dec)]:
    for required in ["2001-11-05", "2001-11-06", "2001-11-07"]:
        assert required in d, f"{symbol}: missing {required}"

nov5 = nov["2001-11-05"]["implied_rate_pct"]
nov6 = nov["2001-11-06"]["implied_rate_pct"]

raw_change_bp = (nov6 - nov5) * 100.0

days_in_month = 30
meeting_day = 6
remaining_days = days_in_month - meeting_day
scale = days_in_month / remaining_days
scaled_surprise_bp = raw_change_bp * scale

assert abs(raw_change_bp - (-8.0)) < 1e-8, raw_change_bp
assert abs(scaled_surprise_bp - (-10.0)) < 1e-8, scaled_surprise_bp

gss_mpspr = -0.10
gss_bp = gss_mpspr * 100.0
assert abs(gss_bp - scaled_surprise_bp) < 1e-8

out = OUT / "barchart_2001_event_validation.csv"

with out.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "meeting_date",
        "contract",
        "pre_date",
        "pre_price",
        "meeting_date_price",
        "pre_implied_rate_pct",
        "meeting_implied_rate_pct",
        "raw_change_bp",
        "kuttner_scale",
        "scaled_surprise_bp",
        "gss_mpspr",
        "gss_surprise_bp",
        "announcement_day_for_estimation",
        "pilot_futures_provenance_ready",
    ])
    w.writerow([
        "2001-11-06",
        "ZQX01",
        "2001-11-05",
        nov["2001-11-05"]["price"],
        nov["2001-11-06"]["price"],
        nov5,
        nov6,
        raw_change_bp,
        scale,
        scaled_surprise_bp,
        gss_mpspr,
        gss_bp,
        "EXCLUDE",
        "TRUE",
    ])

print()
print("=== BARCHART 2001 VALIDATION ===")
print("ZQX01 hash: PASS")
print("ZQZ01 hash: PASS")
print("Unique dates: PASS")
print("OHLC consistency: PASS")
print("Nonnegative volume: PASS")
print(f"Nov 5 implied rate: {nov5:.3f}%")
print(f"Nov 6 implied rate: {nov6:.3f}%")
print(f"Raw change: {raw_change_bp:.1f} bp")
print(f"Kuttner scale: {scale:.4f}")
print(f"Scaled surprise: {scaled_surprise_bp:.1f} bp")
print(f"GSS surprise: {gss_bp:.1f} bp")
print("GSS cross-check: PASS")
print("Announcement day estimation rule: EXCLUDE")
print("PILOT FUTURES PROVENANCE READY = TRUE")
print("FULL ECONOMETRICS READY = FALSE")
print("Output:", out)
