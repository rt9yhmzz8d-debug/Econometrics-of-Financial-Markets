#!/usr/bin/env python3
"""Reproduce a Round 4 acquisition audit. No estimation or automatic approval."""

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
NUMERIC = ("quantity", "dollar_volume", "low_price", "high_price", "last_price")
ALIASES = {"up": "up", "down": "down", "dwn": "down", "same": "same", "sam": "same"}
SPLIT_DIRECTIONS = {
    "25up": "up", "50up": "up", "25dn": "down", "50dn": "down",
    "25d": "down", "50d": "down", "50+d": "down",
}


def parse_contract(code):
    """Identify a family without assigning a meeting or a magnitude payoff."""
    match = re.fullmatch(r"FR(.+?)(\d{4})(Q?)", code)
    if not match or not 1 <= int(match[2][:2]) <= 12:
        raise ValueError(f"Unrecognized contract: {code}")
    stem, suffix, quarter = match.groups()
    stem = stem.lower()
    if stem not in ALIASES and stem not in SPLIT_DIRECTIONS:
        raise ValueError(f"Unreviewed contract spelling: {code}")
    return {
        "suffix": suffix + quarter,
        "horizon": "quarterly" if quarter else "meeting_interval",
        "direction_label": ALIASES.get(stem, SPLIT_DIRECTIONS.get(stem)),
        "role": "directional" if stem in ALIASES else "split_child",
    }


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def clean_rows(path):
    rows = read_csv(path)
    seen = set()
    for row in rows:
        row["day"] = date.fromisoformat(row["observation_date"])
        key = (row["market_id"], row["contract"], row["day"])
        if key in seen:
            raise ValueError(f"Duplicate market/contract/date: {key}")
        seen.add(key)
        row.update(parse_contract(row["contract"]))
        row["family"] = row["market_id"] + ":" + row["suffix"]
        for field in NUMERIC:
            value = float(row[field])
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"Invalid {field}: {key}")
            if field.endswith("price") and value > 1:
                raise ValueError(f"Price outside [0,1]: {key}")
            row[field] = value
        if row["low_price"] > row["high_price"]:
            raise ValueError(f"Low exceeds high: {key}")
    return sorted(rows, key=lambda r: (r["market_id"], r["contract"], r["day"]))


def zero_quantity_changes(rows):
    previous = {}
    changes = []
    for row in rows:
        key = (row["market_id"], row["contract"])
        old = previous.get(key)
        if old and row["quantity"] == 0 and row["last_price"] != old["last_price"]:
            gap = (row["day"] - old["day"]).days
            legacy_quarterly_zero_reappearance = (
                row["horizon"] == "quarterly" and row["observation_date"] == "2016-06-01"
                and gap > 365 and all(row.get(field, 0) == 0 for field in
                                      ("quantity", "dollar_volume", "low_price", "high_price", "last_price"))
            )
            changes.append({
                "market_id": row["market_id"], "contract": row["contract"],
                "family": row["family"], "horizon": row["horizon"], "role": row["role"],
                "observation_date": row["observation_date"],
                "previous_observation_date": old["observation_date"],
                "gap_calendar_days": gap,
                "previous_last_price": old["last_price"],
                "last_price": row["last_price"], "quantity": 0,
                "dollar_volume": row.get("dollar_volume", ""),
                "low_price": row.get("low_price", ""), "high_price": row.get("high_price", ""),
                "daily_low_or_high_nonzero": bool(row.get("low_price", 0) or row.get("high_price", 0)),
                "legacy_quarterly_zero_reappearance": legacy_quarterly_zero_reappearance,
                "source_url": row["source_url"],
                "status": "source_price_volume_consistency_unresolved",
            })
        previous[key] = row
    return changes


def diagnostic_screen(history, current_day, meeting_day, max_age=3, tolerance=0.1):
    """Screen a three-way bundle before normalization; never fill from the future."""
    reasons = []
    if current_day >= meeting_day:
        reasons.append("meeting_day_or_later")
    if set(history) != {"down", "same", "up"}:
        reasons.append("missing_component_history")
    if any(trade_day > current_day for trade_day, _ in history.values()):
        reasons.append("future_price")
    if any((current_day - trade_day).days > max_age for trade_day, _ in history.values()):
        reasons.append("stale_component")
    prices = [value for _, value in history.values()]
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in prices):
        reasons.append("invalid_price")
    total = sum(prices) if len(history) == 3 else None
    if total is not None and (total <= 0 or abs(total - 1) > tolerance + 1e-12):
        reasons.append("incoherent_raw_sum")
    probabilities = {}
    if not reasons:
        probabilities = {direction: value / total for direction, (_, value) in history.items()}
    return reasons, total, probabilities


def pilot_rows(rows, checks):
    pilot = checks["pilot"]
    contracts = {code: direction for direction, code in pilot["contracts"].items()}
    selected = [row for row in rows if row["family"] == pilot["family"]]
    if {r["contract"] for r in selected} != set(contracts):
        raise ValueError("Pilot does not contain exactly the source-checked contracts")
    by_day = defaultdict(dict)
    for row in selected:
        by_day[row["day"]][contracts[row["contract"]]] = row
    history = {}
    output = []
    settings = checks["diagnostic_screen"]
    for day, observed in sorted(by_day.items()):
        record = {"date": day.isoformat()}
        for direction in ("down", "same", "up"):
            row = observed.get(direction)
            if row and row["quantity"] > 0:
                history[direction] = (day, row["last_price"])
            record["reported_last_" + direction] = row["last_price"] if row else ""
            record["reported_quantity_" + direction] = row["quantity"] if row else ""
            previous = history.get(direction)
            record["last_positive_quantity_date_" + direction] = previous[0].isoformat() if previous else ""
            record["age_calendar_days_" + direction] = (day - previous[0]).days if previous else ""
        reasons, total, probabilities = diagnostic_screen(
            history, day, date.fromisoformat(pilot["meeting_date"]),
            settings["max_age_calendar_days"], settings["raw_probability_sum_tolerance"],
        )
        record["raw_sum_from_positive_quantity_history"] = total if total is not None else ""
        record["diagnostic_screen_pass"] = not reasons
        record["diagnostic_exclusion_reasons"] = ";".join(reasons)
        for direction in ("down", "same", "up"):
            record["diagnostic_p_" + direction] = probabilities.get(direction, "")
        record["diagnostic_directional_score"] = (
            100 * (probabilities["up"] - probabilities["down"]) if probabilities else ""
        )
        record["econometrics_ready"] = False
        output.append(record)
    return output


def write_csv(path, rows):
    if not rows:
        raise ValueError(f"No records for {path.name}")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run(input_dir, output_dir, checks_path=HERE / "source_checks.json"):
    checks = json.loads(checks_path.read_text())
    clean_path = input_dir / "03_iem_fedpolicy_clean.csv"
    rows = clean_rows(clean_path)
    raw = read_csv(input_dir / "02_iem_fedpolicy_raw.csv")
    requests = read_csv(input_dir / "01_request_audit.csv")
    groups = defaultdict(list)
    contracts = defaultdict(list)
    for row in rows:
        groups[row["family"]].append(row)
        contracts[(row["market_id"], row["contract"])].append(row)
    anomalies = zero_quantity_changes(rows)
    affected = Counter((r["market_id"], r["contract"]) for r in anomalies)
    contract_register = []
    for (market_id, code), observations in sorted(contracts.items()):
        first = observations[0]
        positive = [r for r in observations if r["quantity"] > 0]
        contract_register.append({
            "market_id": market_id, "contract": code, "family": first["family"],
            "horizon": first["horizon"], "direction_label_only": first["direction_label"],
            "role": first["role"], "rows": len(observations),
            "first_date": observations[0]["observation_date"],
            "last_date": observations[-1]["observation_date"],
            "positive_quantity_rows": len(positive),
            "first_positive_quantity_date": positive[0]["observation_date"] if positive else "",
            "last_positive_quantity_date": positive[-1]["observation_date"] if positive else "",
            "zero_quantity_price_changes": affected[(market_id, code)],
            "definition_status": "source_checked" if first["family"] == checks["pilot"]["family"] else "unreviewed",
            "meeting_date": checks["pilot"]["meeting_date"] if first["family"] == checks["pilot"]["family"] else "",
            "payoff_magnitude_status": "unreviewed" if first["role"] == "split_child" else "direction_only",
            "source_url_example": first["source_url"],
        })
    family_register = []
    for family, observations in sorted(groups.items()):
        split = any(r["role"] == "split_child" for r in observations)
        quarter = observations[0]["horizon"] == "quarterly"
        checked = family == checks["pilot"]["family"]
        analysis_gate = (
            "excluded_quarterly_horizon" if quarter else
            "excluded_split_notice_missing" if split else
            "blocked_price_volume_and_futures" if checked else
            "excluded_definition_mapping_unreviewed"
        )
        family_register.append({
            "family": family, "market": observations[0]["market_code"],
            "horizon": observations[0]["horizon"], "rows": len(observations),
            "contracts": ";".join(sorted({r["contract"] for r in observations})),
            "has_split_children": split,
            "positive_quantity_rows": sum(r["quantity"] > 0 for r in observations),
            "mapping_status": "source_checked" if checked else "unreviewed",
            "meeting_date": checks["pilot"]["meeting_date"] if checked else "",
            "comparison_date": checks["pilot"]["comparison_date"] if checked else "",
            "analysis_gate": analysis_gate,
            "next_check": (
                "Resolve price-volume inconsistencies and align futures" if checked else
                "Separate quarterly horizon; verify both endpoint meetings" if quarter else
                "Retrieve actual spin-off bulletin, dates and payoff ranges" if split else
                "Verify market-specific definition and event mapping"
            ),
        })
    pilot = pilot_rows(rows, checks)
    ordinary_interval = [r for r in family_register
                         if r["horizon"] == "meeting_interval" and not r["has_split_children"]]
    clean_hash = hashlib.sha256(clean_path.read_bytes()).hexdigest()
    summary = {
        "baseline_commit": checks["baseline_commit"],
        "input_sha256": clean_hash,
        "input_matches_checked_baseline": clean_hash == checks["clean_csv_sha256"],
        "review_file_sha256": hashlib.sha256(checks_path.read_bytes()).hexdigest(),
        "requests": len(requests),
        "http_successes": sum(r["http_ok"] == "TRUE" for r in requests),
        "requests_with_rows": sum(int(r["parsed_rows"]) > 0 for r in requests),
        "raw_rows": len(raw), "clean_rows": len(rows),
        "contracts": len(contracts), "families_total": len(groups),
        "meeting_interval_families": sum(r["horizon"] == "meeting_interval" for r in family_register),
        "quarterly_families": sum(r["horizon"] == "quarterly" for r in family_register),
        "quarterly_rows": sum(r["horizon"] == "quarterly" for r in rows),
        "split_families": [r["family"] for r in family_register if r["has_split_children"]],
        "ordinary_meeting_interval_families": len(ordinary_interval),
        "ordinary_meeting_interval_rows": sum(r["rows"] for r in ordinary_interval),
        "ordinary_meeting_interval_contracts": sum(len(r["contracts"].split(";")) for r in ordinary_interval),
        "zero_quantity_rows": sum(r["quantity"] == 0 for r in rows),
        "zero_quantity_changed_last_price_rows": len(anomalies),
        "zero_quantity_changed_last_price_contracts": len(affected),
        "meeting_interval_zero_quantity_changed_last_price_rows": sum(
            r["horizon"] == "meeting_interval" for r in anomalies),
        "zero_quantity_changed_rows_with_nonzero_daily_low_or_high": sum(
            r["daily_low_or_high_nonzero"] for r in anomalies),
        "legacy_quarterly_zero_reappearances_2016_06_01": sum(
            r["legacy_quarterly_zero_reappearance"] for r in anomalies),
        "families_without_positive_quantity": [r["family"] for r in family_register if r["positive_quantity_rows"] == 0],
        "source_checked_families": [checks["pilot"]["family"]],
        "pilot": {
            "family": checks["pilot"]["family"],
            "meeting_date": checks["pilot"]["meeting_date"],
            "contract_rows": sum(r["family"] == checks["pilot"]["family"] for r in rows),
            "daily_snapshots": len(pilot),
            "diagnostic_pass_days": sum(r["diagnostic_screen_pass"] for r in pilot),
            "diagnostic_reasons": dict(Counter(reason for r in pilot for reason in r["diagnostic_exclusion_reasons"].split(";") if reason)),
        },
        "econometrics_ready": False,
        "blockers": [
            "Resolve changed last-trade prices on zero-quantity source rows; positive-quantity carry is only a diagnostic assumption.",
            "Review remaining contract definitions, original-market intermeeting treatment and calendar mappings.",
            "Obtain actual six-family spin-off bulletins; labels do not establish exact payoff magnitudes.",
            "Keep quarterly families out of a single-meeting study until their separate horizon is handled.",
            "Supply and validate matching futures contracts, timestamps, price fields, settlement horizon and daily close alignment.",
            "Reproduce the paired sample and gap-safe lags before fitting the frozen models.",
        ],
    }
    if not summary["input_matches_checked_baseline"]:
        summary["blockers"].insert(0, "Input bytes changed since source inspection; review the new acquisition.")
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "contract_register.csv", contract_register)
    write_csv(output_dir / "family_register.csv", family_register)
    write_csv(output_dir / "zero_quantity_price_changes.csv", anomalies)
    write_csv(output_dir / "pilot_2001_11_06.csv", pilot)
    (output_dir / "audit_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default = next((HERE.parent / "code").glob("Round 4*/ecmt3150_iem_v4_results"))
    parser.add_argument("--input-dir", type=Path, default=default)
    parser.add_argument("--output-dir", type=Path, default=HERE / "generated")
    parser.add_argument("--require-ready", action="store_true", help="Exit 2 while econometrics is blocked.")
    args = parser.parse_args()
    try:
        result = run(args.input_dir, args.output_dir)
    except (ValueError, KeyError) as error:
        parser.exit(2, f"Validation failed: {error}\n")
    print(json.dumps(result, indent=2))
    if args.require_ready and not result["econometrics_ready"]:
        parser.exit(2, "Econometrics blocked; see audit_summary.json.\n")


if __name__ == "__main__":
    main()
