#!/usr/bin/env python3
"""Audit external event checks and IEM pilot sensitivity without fitting a model."""

import argparse
import csv
from datetime import date
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIRECTIONS = ("down", "same", "up")


def coherent_probabilities(prices, tolerance=0.1):
    if set(prices) != set(DIRECTIONS):
        return None
    total = sum(prices.values())
    if total <= 0 or abs(total - 1) > tolerance + 1e-12:
        return None
    return {key: value / total for key, value in prices.items()}


def directional_score(probabilities):
    return 100 * (probabilities["up"] - probabilities["down"])


def build_pilot_sensitivity(pilot_rows, meeting_day, tolerance=0.1):
    policies = {
        "reported_last_regardless_of_quantity": None,
        "same_day_positive_quantity_only": 0,
        "positive_quantity_carry_1_calendar_day": 1,
        "positive_quantity_carry_3_calendar_days": 3,
        "positive_quantity_carry_7_calendar_days": 7,
    }
    history = {}
    daily = []
    for row in pilot_rows:
        day = date.fromisoformat(row["date"])
        if day >= meeting_day:
            continue
        for direction in DIRECTIONS:
            quantity = float(row["reported_quantity_" + direction])
            price = float(row["reported_last_" + direction])
            if quantity > 0:
                history[direction] = (day, price)
        for policy, max_age in policies.items():
            if max_age is None:
                prices = {d: float(row["reported_last_" + d]) for d in DIRECTIONS}
            else:
                prices = {
                    d: value for d, (trade_day, value) in history.items()
                    if (day - trade_day).days <= max_age
                }
            probabilities = coherent_probabilities(prices, tolerance)
            daily.append({
                "date": day.isoformat(),
                "policy": policy,
                "valid": bool(probabilities),
                "directional_score": directional_score(probabilities) if probabilities else "",
            })
    summary = []
    for policy in policies:
        valid = [r for r in daily if r["policy"] == policy and r["valid"]]
        values = [float(r["directional_score"]) for r in valid]
        summary.append({
            "policy": policy,
            "valid_pre_meeting_days": len(valid),
            "first_valid_date": valid[0]["date"] if valid else "",
            "last_valid_date": valid[-1]["date"] if valid else "",
            "first_directional_score": values[0] if values else "",
            "last_directional_score": values[-1] if values else "",
            "minimum_directional_score": min(values) if values else "",
            "maximum_directional_score": max(values) if values else "",
        })
    return daily, summary


def validate_external_checks(checks):
    files = {item["name"]: item for item in checks["files"]}
    required = {
        "gss_data_aer_final.dta", "gss_program_aer_final.do",
        "monetary-policy-surprises-data.xlsx", "sf_fed_monetary_policy_surprises.xlsx",
        "lseg_fed_funds_contract_search.csv", "fed_funds_december_2001_priceclose.csv",
    }
    if set(files) != required:
        raise ValueError("External evidence register does not contain the expected files")
    if files["monetary-policy-surprises-data.xlsx"]["sha256"] != files["sf_fed_monetary_policy_surprises.xlsx"]["sha256"]:
        raise ValueError("The two SF Fed downloads are recorded as duplicates but their hashes differ")
    if files["monetary-policy-surprises-data.xlsx"]["event_observation"]["FF1"] is not None:
        raise ValueError("FF1 is expected to be missing for the pilot event")
    if files["fed_funds_december_2001_priceclose.csv"]["dated_price_observations"] != 0:
        raise ValueError("The LSEG price file is no longer an empty retrieval; review it before reuse")
    if any(item["usable_for_pairing"] for item in files.values()):
        raise ValueError("A source was marked pairable without an implemented daily contract series")
    negative_checks = [
        files["gss_data_aer_final.dta"]["event_observation"]["mpspr_basis_points_after_published_code_scaling"],
        files["monetary-policy-surprises-data.xlsx"]["event_observation"]["MPS_as_stored"],
        checks["event"]["actual_target_change_basis_points"],
    ]
    if not all(math.isfinite(value) and value < 0 for value in negative_checks):
        raise ValueError("External event-direction checks are not consistently negative")
    return {
        "external_files_reviewed": len(files),
        "duplicate_downloads": 1,
        "candidate_futures_instrument": files["lseg_fed_funds_contract_search.csv"]["instrument"],
        "candidate_futures_dated_price_observations": 0,
        "event_direction_checks": "negative_easing_surprise_and_realized_cut",
        "external_direction_check": "passes",
        "paired_daily_futures_leg": "missing",
        "econometrics_ready": False,
    }


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run(checks_path, pilot_path, output_dir):
    checks = json.loads(checks_path.read_text())
    external = validate_external_checks(checks)
    with pilot_path.open(newline="", encoding="utf-8") as stream:
        pilot = list(csv.DictReader(stream))
    daily, sensitivity = build_pilot_sensitivity(
        pilot, date.fromisoformat(checks["event"]["meeting_date"])
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "pilot_sensitivity_daily.csv", daily)
    write_csv(output_dir / "pilot_sensitivity_summary.csv", sensitivity)
    result = {
        **external,
        "pilot_sensitivity": sensitivity,
        "interpretation": checks["decision"]["report_role"],
        "blockers": [
            "Obtain dated daily prices, volume, field definition and time-zone metadata for an exact Fed funds futures contract.",
            "Resolve how the selected monthly-average settlement horizon loads on the 6 November and 11 December 2001 meetings.",
            "Resolve IEM changed-price observations with zero reported quantity before treating daily revisions as trade-timed information.",
            "Complete source-checked mappings before extending beyond the single pilot family.",
        ],
    }
    (output_dir / "external_validation_summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checks", type=Path, default=HERE / "external_source_checks.json")
    parser.add_argument("--pilot", type=Path, default=HERE / "generated/pilot_2001_11_06.csv")
    parser.add_argument("--output-dir", type=Path, default=HERE / "generated")
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    try:
        result = run(args.checks, args.pilot, args.output_dir)
    except (ValueError, KeyError) as error:
        parser.exit(2, f"External validation failed: {error}\n")
    print(json.dumps(result, indent=2))
    if args.require_ready and not result["econometrics_ready"]:
        parser.exit(2, "Econometrics blocked; see external_validation_summary.json.\n")


if __name__ == "__main__":
    main()
