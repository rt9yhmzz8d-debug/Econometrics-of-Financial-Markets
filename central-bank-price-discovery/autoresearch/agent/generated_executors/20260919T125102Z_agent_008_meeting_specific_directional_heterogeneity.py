#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
AGENT = HERE.parent
AUTORESEARCH = AGENT.parent
OUTPUT_ROOT = AGENT / "outputs"
EXPECTED_EXPERIMENT_ID = "agent_008_meeting_specific_directional_heterogeneity"

if str(AGENT) not in sys.path:
    sys.path.insert(0, str(AGENT))

import experiment_engine as engine


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finite_or_none(value):
    value = float(value)
    return value if math.isfinite(value) else None


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return finite_or_none(value)
    return value


def paired_system(blocks, families):
    rows = []
    yi = []
    yf = []
    groups = []

    for family in families:
        block = blocks[family]
        for index, current in enumerate(block):
            if current["var_lag_valid"] != "True":
                continue
            if index == 0:
                raise RuntimeError(
                    f"VAR-valid observation has no within-meeting lag: {family}"
                )

            lagged = block[index - 1]
            if lagged["revision_valid"] != "True":
                raise RuntimeError(
                    f"paired lag is not revision-valid: {family}"
                )

            rows.append((family, current, lagged))
            yi.append(float(current["delta_iem"]))
            yf.append(float(current["delta_ff_bp"]))
            groups.append(family)

    return (
        rows,
        np.asarray(yi, dtype=float),
        np.asarray(yf, dtype=float),
        np.asarray(groups),
    )


def meeting_specific_design(groups, lag_iem, lag_ff, families, direction):
    x = []
    for family, iem_lag, ff_lag in zip(groups, lag_iem, lag_ff):
        directional_lag = ff_lag if direction == "FF_to_IEM" else iem_lag
        own_lag = iem_lag if direction == "FF_to_IEM" else ff_lag

        row = [1.0, own_lag]
        row.extend(
            directional_lag if family == meeting else 0.0
            for meeting in families
        )
        row.extend(
            1.0 if family == meeting else 0.0
            for meeting in families[1:]
        )
        x.append(row)

    return np.asarray(x, dtype=float)


def design_dimensions(x, families):
    rank = int(np.linalg.matrix_rank(x))
    return {
        "total_observations": int(x.shape[0]),
        "number_of_regressors": int(x.shape[1]),
        "number_of_meeting_interactions": int(len(families)),
        "number_of_fixed_effect_indicators": int(len(families) - 1),
        "rank": rank,
        "full_rank": bool(rank == x.shape[1]),
    }


def estimate_direction(x, y, groups, families, direction):
    dimensions = design_dimensions(x, families)
    records = []

    if not dimensions["full_rank"]:
        for meeting in families:
            records.append(
                {
                    "meeting": meeting,
                    "direction": direction,
                    "coefficient": None,
                    "sign": None,
                    "usable_observation_count": int(
                        np.sum(groups == meeting)
                    ),
                    "standard_error": None,
                    "hac_lag": 6,
                    "t_statistic": None,
                    "p_value": None,
                    "estimation_status": "rank_deficient",
                    "rank": dimensions["rank"],
                }
            )
        return dimensions, records, None

    try:
        beta, se, tstat, pvalue = engine.block_hac(
            x,
            y,
            groups,
            lag=6,
        )
    except np.linalg.LinAlgError as exc:
        status = f"singular_hac:{type(exc).__name__}"
        for meeting in families:
            records.append(
                {
                    "meeting": meeting,
                    "direction": direction,
                    "coefficient": None,
                    "sign": None,
                    "usable_observation_count": int(
                        np.sum(groups == meeting)
                    ),
                    "standard_error": None,
                    "hac_lag": 6,
                    "t_statistic": None,
                    "p_value": None,
                    "estimation_status": status,
                    "rank": dimensions["rank"],
                }
            )
        return dimensions, records, None

    coefficient_values = []
    for meeting_index, meeting in enumerate(families):
        coefficient = float(beta[2 + meeting_index])
        standard_error = float(se[2 + meeting_index])
        t_value = float(tstat[2 + meeting_index])
        p_value = float(pvalue[2 + meeting_index])

        if not math.isfinite(coefficient):
            status = "nonfinite_coefficient"
            sign = None
            coefficient_values.append(None)
        else:
            status = "estimated"
            sign = (
                "positive"
                if coefficient > 0
                else "negative"
                if coefficient < 0
                else "zero"
            )
            coefficient_values.append(coefficient)

        records.append(
            {
                "meeting": meeting,
                "direction": direction,
                "coefficient": finite_or_none(coefficient),
                "sign": sign,
                "usable_observation_count": int(
                    np.sum(groups == meeting)
                ),
                "standard_error": finite_or_none(standard_error),
                "hac_lag": 6,
                "t_statistic": finite_or_none(t_value),
                "p_value": finite_or_none(p_value),
                "estimation_status": status,
                "rank": dimensions["rank"],
            }
        )

    return dimensions, records, coefficient_values


def dispersion(records):
    values = [
        float(record["coefficient"])
        for record in records
        if record["estimation_status"] == "estimated"
        and record["coefficient"] is not None
    ]
    if not values:
        return {
            "available_coefficient_count": 0,
            "minimum": None,
            "maximum": None,
            "median": None,
            "first_quartile": None,
            "third_quartile": None,
            "interquartile_range": None,
        }

    array = np.asarray(values, dtype=float)
    q1, median, q3 = np.percentile(array, [25, 50, 75])
    return {
        "available_coefficient_count": len(values),
        "minimum": float(np.min(array)),
        "maximum": float(np.max(array)),
        "median": float(median),
        "first_quartile": float(q1),
        "third_quartile": float(q3),
        "interquartile_range": float(q3 - q1),
    }


def aggregation(records, pooled_beta):
    contributions = []
    numerator = 0.0
    denominator = 0

    for record in records:
        coefficient = record["coefficient"]
        count = record["usable_observation_count"]
        if (
            record["estimation_status"] == "estimated"
            and coefficient is not None
        ):
            contribution = float(coefficient) * int(count)
            numerator += contribution
            denominator += int(count)
        else:
            contribution = None

        contributions.append(
            {
                "meeting": record["meeting"],
                "direction": record["direction"],
                "coefficient": coefficient,
                "usable_observation_count": count,
                "weighted_contribution": contribution,
            }
        )

    weighted_average = (
        numerator / denominator if denominator else None
    )
    difference = (
        weighted_average - float(pooled_beta)
        if weighted_average is not None
        else None
    )

    return {
        "meeting_contributions": contributions,
        "total_usable_observations_used": denominator,
        "observation_weighted_average": weighted_average,
        "reproduced_pooled_baseline_coefficient": float(pooled_beta),
        "algebraic_difference_from_pooled_baseline": difference,
    }


def sign_summary(records):
    positive = sum(
        record["coefficient"] is not None
        and record["coefficient"] > 0
        for record in records
    )
    total = len(records)
    return {
        "positive_count": int(positive),
        "meeting_count": int(total),
        "positive_proportion": float(positive / total) if total else None,
    }


def compute_experiment():
    baseline = engine.reproduce_baseline()
    rows, blocks, families = engine.load_panel()
    paired_rows, yi, yf, groups = paired_system(blocks, families)

    lag_iem = np.asarray(
        [float(item[2]["delta_iem"]) for item in paired_rows],
        dtype=float,
    )
    lag_ff = np.asarray(
        [float(item[2]["delta_ff_bp"]) for item in paired_rows],
        dtype=float,
    )

    x_ff_iem = meeting_specific_design(
        groups, lag_iem, lag_ff, families, "FF_to_IEM"
    )
    x_iem_ff = meeting_specific_design(
        groups, lag_iem, lag_ff, families, "IEM_to_FF"
    )

    dims_ff_iem, records_ff_iem, values_ff_iem = estimate_direction(
        x_ff_iem, yi, groups, families, "FF_to_IEM"
    )
    dims_iem_ff, records_iem_ff, values_iem_ff = estimate_direction(
        x_iem_ff, yf, groups, families, "IEM_to_FF"
    )

    aggregation_ff_iem = aggregation(
        records_ff_iem,
        baseline["FF_to_IEM"]["beta"],
    )
    aggregation_iem_ff = aggregation(
        records_iem_ff,
        baseline["IEM_to_FF"]["beta"],
    )

    ff_signs = sign_summary(records_ff_iem)
    iem_signs = sign_summary(records_iem_ff)

    stability_supported = (
        ff_signs["positive_count"] >= 6
        and iem_signs["positive_count"] < 6
    )

    if stability_supported:
        stability_text = (
            "descriptive directional stability pattern supported"
        )
    elif (
        ff_signs["positive_count"] < 6
        or iem_signs["positive_count"] >= 6
    ):
        stability_text = (
            "pooled directional result is heterogeneous and potentially "
            "episode-specific"
        )
    else:
        stability_text = "descriptive stability decision indeterminate"

    return {
        "baseline_reproduction": baseline,
        "families": list(families),
        "meeting_specific_coefficients": (
            records_ff_iem + records_iem_ff
        ),
        "design_dimensions": {
            "FF_to_IEM": dims_ff_iem,
            "IEM_to_FF": dims_iem_ff,
        },
        "aggregation_checks": {
            "FF_to_IEM": aggregation_ff_iem,
            "IEM_to_FF": aggregation_iem_ff,
        },
        "sign_counts": {
            "FF_to_IEM": ff_signs,
            "IEM_to_FF": iem_signs,
        },
        "dispersion": {
            "FF_to_IEM": dispersion(records_ff_iem),
            "IEM_to_FF": dispersion(records_iem_ff),
        },
        "stability_decision": {
            "rule": (
                "FF_to_IEM positive in at least 6 of 8 meetings and "
                "IEM_to_FF positive in fewer than 6 of 8 meetings"
            ),
            "supported": bool(stability_supported),
            "descriptive_statement": stability_text,
            "not_a_significance_test": True,
        },
        "failure_records": [
            record
            for record in records_ff_iem + records_iem_ff
            if record["estimation_status"] != "estimated"
        ],
    }


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: executor.py IMPLEMENTATION_CONTRACT.json"
        )

    contract_path = Path(sys.argv[1]).resolve()
    if not contract_path.is_file():
        raise RuntimeError(f"implementation contract missing: {contract_path}")

    with contract_path.open() as handle:
        contract = json.load(handle)

    if contract.get("experiment_id") != EXPECTED_EXPERIMENT_ID:
        raise RuntimeError(
            "implementation contract experiment_id does not match "
            f"{EXPECTED_EXPERIMENT_ID}"
        )

    output_dir = OUTPUT_ROOT / EXPECTED_EXPERIMENT_ID
    evidence_path = output_dir / "evidence.json"

    if evidence_path.exists():
        raise RuntimeError(
            f"refusing to overwrite existing evidence file: {evidence_path}"
        )
    if output_dir.exists():
        raise RuntimeError(
            f"refusing to reuse existing experiment output directory: "
            f"{output_dir}"
        )

    canonical_panel = Path(engine.PANEL).resolve()
    if not canonical_panel.is_file():
        raise RuntimeError(f"canonical panel missing: {canonical_panel}")

    first = json_safe(compute_experiment())
    second = json_safe(compute_experiment())

    first_fingerprint = hashlib.sha256(
        json.dumps(
            first,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    second_fingerprint = hashlib.sha256(
        json.dumps(
            second,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()

    rerun_identical = (
        first == second
        and first_fingerprint == second_fingerprint
    )
    if not rerun_identical:
        raise RuntimeError(
            "deterministic rerun verification failed"
        )

    output_dir.mkdir(parents=True, exist_ok=False)

    metadata = {
        "experiment_id": EXPECTED_EXPERIMENT_ID,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "software_or_engine_version": "python-numpy-experiment-engine",
        "python_version": sys.version,
        "canonical_input_path": str(canonical_panel),
        "canonical_input_sha256": sha256_file(canonical_panel),
        "procedure_path": str(Path(__file__).resolve()),
        "procedure_sha256": sha256_file(Path(__file__).resolve()),
        "implementation_contract_path": str(contract_path),
        "output_path": str(output_dir),
        "result_selection_performed": False,
        "null_results_recorded": True,
        "validation_data_modified": False,
        "planned_and_executed_without_modifying_validated_source_data": True,
    }

    evidence = {
        "metadata": metadata,
        "experiment_status": "executed_after_baseline_reproduction",
        "baseline_reproduction_passed": True,
        "results": first,
        "deterministic_rerun": {
            "performed_before_final_evidence_acceptance": True,
            "second_computation_performed": True,
            "identical_results": True,
            "first_computation_fingerprint": first_fingerprint,
            "second_computation_fingerprint": second_fingerprint,
        },
    }

    with evidence_path.open("x") as handle:
        json.dump(
            evidence,
            handle,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        handle.write("\n")

    print(str(evidence_path))


if __name__ == "__main__":
    main()
