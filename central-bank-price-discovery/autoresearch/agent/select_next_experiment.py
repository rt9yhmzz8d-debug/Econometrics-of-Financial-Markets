#!/usr/bin/env python3

import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUTORESEARCH = HERE.parent
REPO = HERE.parents[2]
RUNS = HERE / "runs"

STATE = HERE / "state" / "research_state.json"
CONSTITUTION = HERE / "RESEARCH_CONSTITUTION.md"

MULTIVERSE = AUTORESEARCH / "multiverse_evidence_005.json"
INFLUENCE = AUTORESEARCH / "influence_evidence_004.json"
INFLUENCE_ROWS = AUTORESEARCH / "influence_rows_004.csv"

RUN_006 = HERE / "runs" / "20260919T115018Z.json"
EVIDENCE_006 = (
    HERE / "outputs" / "20260919T115018Z" / "evidence.json"
)


def git(*args):
    p = subprocess.run(
        ["git", *args],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=True,
    )
    return p.stdout.strip()


def require_clean():
    dirty = git("status", "--porcelain")
    if dirty:
        raise SystemExit(
            "STOP: working tree must be clean before autonomous selection:\n"
            + dirty
        )


def load(path):
    if not path.exists():
        raise SystemExit(f"STOP: required evidence missing: {path}")
    return json.loads(path.read_text())


def candidate_score(candidate):
    # Scores are methodological-priority scores only.
    # They never use p-values or statistical significance as rewards.
    return (
        candidate["independence"]
        + candidate["addresses_known_fragility"]
        + candidate["uses_frozen_data"]
        + candidate["interpretability"]
        + candidate["reproducibility"]
    )


def main():
    require_clean()

    state = load(STATE)
    multiverse = load(MULTIVERSE)
    influence = load(INFLUENCE)
    run006 = load(RUN_006)
    evidence006 = load(EVIDENCE_006)

    if state["optimise_for_significance"] is not False:
        raise SystemExit("STOP: significance optimisation protection failed")

    if run006["status"] != "executed":
        raise SystemExit("STOP: Experiment 006 is not frozen as executed")

    results006 = evidence006["results"]

    trim10 = next(
        x for x in results006
        if x["trim_count"] == 10
    )

    known_findings = {
        "baseline_rows": state["baseline"]["usable_var_rows"],
        "multiverse_specifications": multiverse["specifications"],
        "FF_to_IEM_sign_preserved_under_trim10":
            trim10["FF_to_IEM"]["sign_preserved"],
        "IEM_to_FF_sign_preserved_under_trim10":
            trim10["IEM_to_FF"]["sign_preserved"],
        "IEM_to_FF_trim10_beta":
            trim10["IEM_to_FF"]["beta"],
        "FF_to_IEM_trim10_beta":
            trim10["FF_to_IEM"]["beta"],
    }

    candidates = [
        {
            "experiment_id": "agent_007_joint_symmetric_trim",
            "title": "Symmetric joint-influence trimming",
            "research_question":
                "Does the directional pattern survive when the same "
                "pre-specified observations are removed from both equations?",
            "motivation":
                "Experiment 006 ranked influential observations separately "
                "for each equation. A common deletion set tests whether that "
                "asymmetry itself drives the robustness result.",
            "design": {
                "ranking_rule":
                    "maximum normalised absolute leave-one-out coefficient "
                    "change across the two directions",
                "trim_counts": [1, 3, 5, 10],
                "same_rows_removed_from_both_equations": True,
                "hac_lag": 6,
                "meeting_fixed_effects": True,
                "source": "influence_rows_004.csv",
            },
            "independence": 3,
            "addresses_known_fragility": 5,
            "uses_frozen_data": 5,
            "interpretability": 5,
            "reproducibility": 5,
        },
        {
            "experiment_id": "agent_007_meeting_concentration",
            "title": "Influence concentration by FOMC meeting",
            "research_question":
                "Are the influential observations disproportionately "
                "concentrated in particular meetings?",
            "motivation":
                "Several influential rows appear in the November 2002 "
                "meeting. Quantifying concentration can distinguish "
                "observation fragility from meeting-level dependence.",
            "design": {
                "analysis":
                    "rank concentration of top influence observations "
                    "by meeting family",
                "top_k": [5, 10, 20],
                "source": "influence_rows_004.csv",
                "no_refitting_for_significance": True,
            },
            "independence": 4,
            "addresses_known_fragility": 4,
            "uses_frozen_data": 5,
            "interpretability": 5,
            "reproducibility": 5,
        },
        {
            "experiment_id": "agent_007_sign_stability_curve",
            "title": "Full influence-trim stability curve",
            "research_question":
                "At what deletion depth do the directional coefficients "
                "change sign or materially depart from baseline?",
            "motivation":
                "Experiment 006 used four preregistered deletion depths. "
                "A complete deterministic stability curve can reveal whether "
                "the trim-10 reversal is abrupt or gradual.",
            "design": {
                "trim_counts": list(range(0, 21)),
                "ranking_rule":
                    "frozen experiment-004 influence ordering",
                "hac_lag": 6,
                "meeting_fixed_effects": True,
                "report_all_depths": True,
            },
            "independence": 3,
            "addresses_known_fragility": 5,
            "uses_frozen_data": 5,
            "interpretability": 4,
            "reproducibility": 5,
        },
    ]

    for c in candidates:
        c["methodological_priority_score"] = candidate_score(c)

    # Never select an experiment that has already been preregistered or run.
    # A dry-run preregistration also counts as consumed: once a decision has
    # been frozen, the selector moves on rather than silently repeating it.
    consumed_experiment_ids = set()

    for prior_path in RUNS.glob("*.json"):
        try:
            prior = json.loads(prior_path.read_text())
        except Exception:
            continue

        prior_exp = (
            prior.get("selected_experiment")
            or prior.get("proposal")
            or {}
        )

        experiment_id = prior_exp.get("experiment_id")
        if experiment_id:
            consumed_experiment_ids.add(experiment_id)

    eligible_candidates = [
        c for c in candidates
        if c["experiment_id"] not in consumed_experiment_ids
    ]

    if not eligible_candidates:
        raise SystemExit(
            "STOP: no unused candidate experiments remain. "
            "Add new scientifically motivated candidates before continuing."
        )

    eligible_candidates.sort(
        key=lambda x: (
            -x["methodological_priority_score"],
            x["experiment_id"],
        )
    )

    selected = eligible_candidates[0]

    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")

    record = {
        "run_id": run_id,
        "created_at_utc": now.isoformat(),
        "status": "selected_not_executed",
        "branch": git("branch", "--show-current"),
        "starting_commit": git("rev-parse", "HEAD"),
        "parent_checkpoint": "6ae93a3",
        "selection_policy": {
            "optimise_for_significance": False,
            "p_values_used_as_selection_reward": False,
            "null_results_admissible": True,
            "validated_data_read_only": True,
            "selection_basis":
                "methodological information gain and robustness value",
        },
        "known_findings": known_findings,
        "candidate_experiments": candidates,
        "selected_experiment": selected,
        "execution": None,
        "evaluation": None,
    }

    RUNS.mkdir(parents=True, exist_ok=True)
    path = RUNS / f"{run_id}_experiment007.json"
    path.write_text(json.dumps(record, indent=2) + "\n")

    print("=== AUTONOMOUS EXPERIMENT 007 SELECTED ===")
    print("run:", run_id)
    print("experiment:", selected["experiment_id"])
    print("title:", selected["title"])
    print(
        "methodological priority:",
        selected["methodological_priority_score"],
    )
    print("record:", path)
    print()
    print("STATE = SELECTED_NOT_EXECUTED")
    print("No experiment has been executed.")
    print("No result has been observed.")
    print("No result has been selected by significance.")


if __name__ == "__main__":
    main()
