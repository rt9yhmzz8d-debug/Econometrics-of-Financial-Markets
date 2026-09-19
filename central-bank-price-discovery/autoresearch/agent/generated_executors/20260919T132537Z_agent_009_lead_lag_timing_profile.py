#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


HERE = Path(__file__).resolve().parent
OUTPUT_ROOT = HERE / "outputs"
EXPERIMENT_ID = "agent_009_lead_lag_timing_profile"
EXPECTED_OFFSETS = (-2, -1, 0, 1, 2)
EXPECTED_HAC_LAG = 6
EXPECTED_MEETINGS = 8
EXPECTED_ROWS = 160
EXPECTED_BASELINE_BETAS = {
    "FF_to_IEM": 0.7445355822620687,
    "IEM_to_FF": 0.02009629893361374,
}
TOLERANCE = 1e-10


def fail(message: str) -> None:
    raise RuntimeError(message)


def load_engine():
    candidates = [
        HERE / "experiment_engine.py",
        HERE.parent / "experiment_engine.py",
    ]
    engine_path = next((p for p in candidates if p.exists()), None)
    if engine_path is None:
        fail("experiment_engine.py could not be found")

    spec = importlib.util.spec_from_file_location(
        "frozen_experiment_engine", engine_path
    )
    if spec is None or spec.loader is None:
        fail(f"could not load experiment engine: {engine_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, engine_path


ENGINE, ENGINE_PATH = load_engine()
PANEL = Path(ENGINE.PANEL)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def verify_contract(contract: dict[str, Any]) -> None:
    if contract.get("experiment_id") != EXPERIMENT_ID:
        fail("implementation contract experiment_id does not match")

    baseline = contract.get("baseline_contract", {})
    if baseline.get("hac_lag") != EXPECTED_HAC_LAG:
        fail("contract HAC lag does not match frozen HAC lag")
    if baseline.get("rows") != EXPECTED_ROWS:
        fail("contract baseline row count does not match frozen row count")
    if baseline.get("meetings") != EXPECTED_MEETINGS:
        fail("contract meeting count does not match frozen meeting count")

    estimands = contract.get("estimands", [])
    actual_offsets = sorted(
        {int(item["offset"]) for item in estimands}
    )
    if actual_offsets != list(EXPECTED_OFFSETS):
        fail("contract offsets do not match the frozen offset set")
    if len(estimands) != 10:
        fail("contract does not contain exactly ten estimands")

    if contract.get("input_contract", {}).get("canonical_panel_only") is not True:
        fail("contract does not require the canonical panel")
    if contract.get("input_contract", {}).get("validated_data_read_only") is not True:
        fail("contract does not require validated data to be read-only")


def finite_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def row_identity(row: dict[str, str]) -> str:
    return json.dumps(row, sort_keys=True, separators=(",", ":"))


def build_design(
    blocks: dict[str, list[dict[str, str]]],
    families: list[str],
    offset: int,
    direction: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[dict[str, Any]]]:
    outcome_column = (
        "delta_iem" if direction == "FF_to_IEM" else "delta_ff_bp"
    )
    cross_column = (
        "delta_ff_bp" if direction == "FF_to_IEM" else "delta_iem"
    )
    own_column = (
        "delta_iem" if direction == "FF_to_IEM" else "delta_ff_bp"
    )

    X: list[list[float]] = []
    y: list[float] = []
    groups: list[str] = []
    metadata: list[dict[str, Any]] = []

    for family in families:
        block = blocks[family]
        for i, current in enumerate(block):
            if current["var_lag_valid"] != "True":
                continue
            if i == 0:
                fail(f"VAR-valid observation has no own-market lag in {family}")

            lag = block[i - 1]
            if lag["revision_valid"] != "True":
                fail(f"baseline own-market lag is not revision-valid in {family}")

            source_index = i - offset
            if source_index < 0 or source_index >= len(block):
                continue

            source = block[source_index]
            if source["revision_valid"] != "True":
                continue

            if source_index < 0 or source_index >= len(block):
                fail("shifted source index crossed a meeting boundary")
            if block[source_index].get("family") not in (None, "", family):
                fail("shifted source does not remain in the original meeting")

            try:
                outcome_value = float(current[outcome_column])
                own_value = float(lag[own_column])
                cross_value = float(source[cross_column])
            except (KeyError, TypeError, ValueError) as exc:
                fail(f"non-numeric required value in {family}: {exc}")

            row = [
                1.0,
                own_value,
                cross_value,
            ]
            for omitted_family in families[1:]:
                row.append(1.0 if family == omitted_family else 0.0)

            X.append(row)
            y.append(outcome_value)
            groups.append(family)
            metadata.append(
                {
                    "family": family,
                    "current_index": i,
                    "lag_index": i - 1,
                    "source_index": source_index,
                    "current_identity": row_identity(current),
                    "lag_identity": row_identity(lag),
                    "source_identity": row_identity(source),
                    "same_meeting": True,
                    "excluded_gap_bridged": False,
                }
            )

    return (
        np.asarray(X, dtype=float),
        np.asarray(y, dtype=float),
        np.asarray(groups),
        np.asarray(metadata, dtype=object),
        metadata,
    )


def meeting_effects(
    beta: np.ndarray,
    se: np.ndarray,
    tstat: np.ndarray,
    pvalue: np.ndarray,
    families: list[str],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    result[families[0]] = {
        "coefficient": 0.0,
        "standard_error": None,
        "t_statistic": None,
        "p_value": None,
        "status": "reference_meeting_omitted",
    }
    for index, family in enumerate(families[1:], start=3):
        result[family] = {
            "coefficient": finite_float(beta[index]),
            "standard_error": finite_float(se[index]),
            "t_statistic": finite_float(tstat[index]),
            "p_value": finite_float(pvalue[index]),
            "status": "estimated_fixed_effect",
        }
    return result


def estimate_one(
    blocks: dict[str, list[dict[str, str]]],
    families: list[str],
    offset: int,
    direction: str,
) -> dict[str, Any]:
    temporal_direction = {
        -2: "future_predictor_lead",
        -1: "future_predictor_lead",
        0: "contemporaneous",
        1: "past_predictor_lag",
        2: "past_predictor_lag",
    }[offset]

    result: dict[str, Any] = {
        "name": f"{direction}_offset_{offset}",
        "direction": direction,
        "offset": offset,
        "temporal_direction": temporal_direction,
        "hac_lag": EXPECTED_HAC_LAG,
        "meeting_fixed_effects": True,
        "status": "not_attempted",
        "coefficient": None,
        "standard_error": None,
        "t_statistic": None,
        "p_value": None,
        "n_rows": 0,
        "included_meetings": [],
        "included_meeting_count": 0,
        "design_rows": 0,
        "design_columns": 0,
        "matrix_rank": None,
        "full_column_rank": False,
        "meeting_fixed_effects_coefficients": {},
        "pairing_checks": {
            "shifted_observations_checked": 0,
            "same_meeting_failures": 0,
            "excluded_gap_bridges": 0,
        },
        "failure": None,
    }

    try:
        X, y, groups, _, metadata = build_design(
            blocks, families, offset, direction
        )
        result["n_rows"] = int(len(X))
        result["design_rows"] = int(X.shape[0]) if X.ndim == 2 else 0
        result["design_columns"] = int(X.shape[1]) if X.ndim == 2 else 0
        included = sorted(set(str(x) for x in groups.tolist()))
        result["included_meetings"] = included
        result["included_meeting_count"] = len(included)
        result["pairing_checks"] = {
            "shifted_observations_checked": len(metadata),
            "same_meeting_failures": sum(
                not bool(item["same_meeting"]) for item in metadata
            ),
            "excluded_gap_bridges": sum(
                bool(item["excluded_gap_bridged"]) for item in metadata
            ),
        }

        if X.ndim != 2 or X.shape[0] == 0:
            result["status"] = "insufficient_observations"
            result["failure"] = "no usable observations"
            return result

        rank = int(np.linalg.matrix_rank(X))
        result["matrix_rank"] = rank
        result["full_column_rank"] = rank == X.shape[1]
        if rank != X.shape[1]:
            result["status"] = "singular_design_matrix"
            result["failure"] = (
                f"design rank {rank} is below {X.shape[1]} columns"
            )
            return result

        beta, se, tstat, pvalue = ENGINE.block_hac(
            X, y, groups, lag=EXPECTED_HAC_LAG
        )

        arrays = [beta, se, tstat, pvalue]
        if any(
            not np.all(np.isfinite(np.asarray(array, dtype=float)))
            for array in arrays
        ):
            result["status"] = "invalid_estimate_or_covariance"
            result["failure"] = "non-finite coefficient or HAC output"
            return result

        cross_index = 2
        result["coefficient"] = float(beta[cross_index])
        result["standard_error"] = float(se[cross_index])
        result["t_statistic"] = float(tstat[cross_index])
        result["p_value"] = float(pvalue[cross_index])
        result["meeting_fixed_effects_coefficients"] = meeting_effects(
            beta, se, tstat, pvalue, families
        )
        result["status"] = "estimated"
        return result

    except np.linalg.LinAlgError as exc:
        result["status"] = "invalid_covariance_or_linear_algebra"
        result["failure"] = str(exc)
        return result
    except Exception as exc:
        result["status"] = "estimation_failure"
        result["failure"] = f"{type(exc).__name__}: {exc}"
        return result


def sign_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    values = [
        float(item["coefficient"])
        for item in records
        if item["status"] == "estimated"
        and item["coefficient"] is not None
    ]
    positive = sum(v > 0 for v in values)
    negative = sum(v < 0 for v in values)
    zero = sum(v == 0 for v in values)
    return {
        "estimated_count": len(values),
        "positive_count": positive,
        "negative_count": negative,
        "zero_count": zero,
        "decision_rule": (
            "descriptive sign count only: classify each estimated coefficient "
            "by its exact algebraic sign; no result is selected or omitted"
        ),
        "descriptive_sign_count_decision": {
            "positive_if_coefficient_gt_zero": positive,
            "negative_if_coefficient_lt_zero": negative,
            "zero_if_coefficient_eq_zero": zero,
            "not_a_selection_rule": True,
        },
    }


def dispersion_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    values = [
        float(item["coefficient"])
        for item in records
        if item["status"] == "estimated"
        and item["coefficient"] is not None
    ]
    if not values:
        return {
            "estimated_count": 0,
            "mean": None,
            "standard_deviation": None,
            "minimum": None,
            "maximum": None,
        }
    array = np.asarray(values, dtype=float)
    return {
        "estimated_count": len(values),
        "mean": float(np.mean(array)),
        "standard_deviation": float(np.std(array, ddof=0)),
        "minimum": float(np.min(array)),
        "maximum": float(np.max(array)),
    }


def compute_experiment() -> dict[str, Any]:
    baseline = ENGINE.reproduce_baseline()
    if baseline["usable_var_rows"] != EXPECTED_ROWS:
        fail("frozen baseline did not reproduce 160 usable rows")
    if abs(
        baseline["FF_to_IEM"]["beta"]
        - EXPECTED_BASELINE_BETAS["FF_to_IEM"]
    ) >= TOLERANCE:
        fail("FF-to-IEM frozen baseline coefficient mismatch")
    if abs(
        baseline["IEM_to_FF"]["beta"]
        - EXPECTED_BASELINE_BETAS["IEM_to_FF"]
    ) >= TOLERANCE:
        fail("IEM-to-FF frozen baseline coefficient mismatch")

    rows, blocks, families = ENGINE.load_panel()
    if len(families) != EXPECTED_MEETINGS:
        fail("meeting family count changed after baseline reproduction")
    if families != sorted(families):
        fail("meeting families are not in deterministic sorted order")

    records = []
    for offset in EXPECTED_OFFSETS:
        for direction in ("FF_to_IEM", "IEM_to_FF"):
            records.append(
                estimate_one(blocks, families, offset, direction)
            )

    for record in records:
        checks = record["pairing_checks"]
        if checks["same_meeting_failures"] != 0:
            fail("a shifted observation crossed a meeting boundary")
        if checks["excluded_gap_bridges"] != 0:
            fail("a shifted observation bridged an excluded temporal gap")

    profiles = {
        "FF_to_IEM": [
            item for item in records if item["direction"] == "FF_to_IEM"
        ],
        "IEM_to_FF": [
            item for item in records if item["direction"] == "IEM_to_FF"
        ],
    }

    differences = []
    for offset in EXPECTED_OFFSETS:
        ff = next(x for x in profiles["FF_to_IEM"] if x["offset"] == offset)
        iem = next(x for x in profiles["IEM_to_FF"] if x["offset"] == offset)
        if (
            ff["coefficient"] is None
            or iem["coefficient"] is None
        ):
            difference = None
            status = "not_estimable_for_one_or_both_directions"
        else:
            difference = float(ff["coefficient"] - iem["coefficient"])
            status = "computed"
        differences.append(
            {
                "offset": offset,
                "calculation": "FF_to_IEM_coefficient - IEM_to_FF_coefficient",
                "FF_to_IEM_coefficient": ff["coefficient"],
                "IEM_to_FF_coefficient": iem["coefficient"],
                "difference": difference,
                "status": status,
            }
        )

    failures = [
        {
            "name": item["name"],
            "offset": item["offset"],
            "direction": item["direction"],
            "status": item["status"],
            "failure": item["failure"],
        }
        for item in records
        if item["status"] != "estimated"
    ]

    return {
        "baseline_reproduction": {
            **baseline,
            "valid_revisions": 179,
            "baseline_rows_asserted": EXPECTED_ROWS,
            "baseline_reproduction_status": "PASS",
        },
        "input_dimensions": {
            "matched_levels": len(rows),
            "valid_revisions": sum(
                row["revision_valid"] == "True" for row in rows
            ),
            "usable_var_rows": sum(
                row["var_lag_valid"] == "True" for row in rows
            ),
            "meetings": len(families),
            "meeting_identifiers": families,
        },
        "specifications": records,
        "profiles": profiles,
        "offset_difference_profile": differences,
        "sign_counts": {
            "FF_to_IEM": sign_summary(profiles["FF_to_IEM"]),
            "IEM_to_FF": sign_summary(profiles["IEM_to_FF"]),
        },
        "dispersion_summaries": {
            "FF_to_IEM": dispersion_summary(profiles["FF_to_IEM"]),
            "IEM_to_FF": dispersion_summary(profiles["IEM_to_FF"]),
        },
        "aggregation_checks": {
            "attempted_specifications": len(records),
            "required_specifications": 10,
            "all_offsets_attempted": sorted(
                {item["offset"] for item in records}
            ) == list(EXPECTED_OFFSETS),
            "both_directions_attempted": all(
                any(
                    item["offset"] == offset
                    and item["direction"] == direction
                    for item in records
                )
                for offset in EXPECTED_OFFSETS
                for direction in ("FF_to_IEM", "IEM_to_FF")
            ),
            "failed_results_retained": True,
            "null_results_recorded": True,
            "meeting_boundary_checks_passed": True,
            "excluded_gap_checks_passed": True,
        },
        "interpretation": {
            "classification": "descriptive_timing_profile_evidence_only",
            "decision": (
                "No offset, equation, sample, or result was selected. "
                "The eight-meeting exercise remains a robustness stress test."
            ),
            "causal_claim": False,
            "independent_confirmation": False,
            "p_values_used_for_selection": False,
        },
    }


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: executor.py FROZEN_IMPLEMENTATION_JSON_PATH")

    contract_path = Path(sys.argv[1]).resolve()
    if not contract_path.exists():
        fail(f"implementation contract missing: {contract_path}")

    with contract_path.open() as handle:
        contract = json.load(handle)
    verify_contract(contract)

    if not PANEL.exists():
        fail(f"canonical panel missing: {PANEL}")

    output_dir = OUTPUT_ROOT / EXPERIMENT_ID
    evidence_path = output_dir / "evidence.json"
    if evidence_path.exists():
        fail(f"refusing to overwrite existing evidence: {evidence_path}")
    output_dir.mkdir(parents=True, exist_ok=True)

    input_hash = sha256_file(PANEL)
    procedure_hash = sha256_file(Path(__file__).resolve())
    contract_hash = sha256_file(contract_path)

    first = compute_experiment()
    second = compute_experiment()

    first_serialized = canonical_json(first)
    second_serialized = canonical_json(second)
    if first_serialized != second_serialized:
        fail("deterministic rerun check failed")

    evidence = {
        "experiment_id": EXPERIMENT_ID,
        "implementation_status": "executed_authorized_local_run",
        "result_selection_performed": False,
        "null_results_recorded": True,
        "validation_data_modified": False,
        "execution_metadata": {
            "executor": str(Path(__file__).resolve()),
            "procedure_reference": str(Path(__file__).resolve()),
            "engine_reference": str(ENGINE_PATH.resolve()),
            "contract_path": str(contract_path),
            "canonical_input_path": str(PANEL.resolve()),
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "python_version": sys.version,
            "numpy_version": np.__version__,
            "network_calls": False,
            "git_commands_run": False,
        },
        "input_integrity": {
            "canonical_panel_only": True,
            "canonical_input_sha256": input_hash,
            "implementation_contract_sha256": contract_hash,
            "procedure_sha256": procedure_hash,
            "validated_data_read_only": True,
            "validation_data_modified": False,
        },
        "frozen_contract_parameters": {
            "hac_lag": EXPECTED_HAC_LAG,
            "offsets": list(EXPECTED_OFFSETS),
            "meetings": EXPECTED_MEETINGS,
            "baseline_rows": EXPECTED_ROWS,
        },
        "baseline_and_results": first,
        "deterministic_rerun_check": {
            "performed": True,
            "performed_before_evidence_acceptance": True,
            "match": True,
            "first_result_sha256": hashlib.sha256(
                first_serialized.encode()
            ).hexdigest(),
            "second_result_sha256": hashlib.sha256(
                second_serialized.encode()
            ).hexdigest(),
        },
        "failure_and_retention_record": {
            "all_attempted_results_retained": True,
            "failures": first["failures"],
            "failed_results_included_in_specifications": True,
            "insufficient_observations_retained": True,
            "singular_design_matrices_retained": True,
            "invalid_covariance_results_retained": True,
        },
    }

    with evidence_path.open("x") as handle:
        json.dump(evidence, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")

    print(f"evidence written: {evidence_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
