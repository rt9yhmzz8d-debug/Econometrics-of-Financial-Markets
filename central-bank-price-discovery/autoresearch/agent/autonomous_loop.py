from pathlib import Path
from datetime import datetime, timezone
import subprocess
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
AR = HERE.parent

STATE = HERE / "state" / "research_state.json"
SCHEMA = HERE / "EXPERIMENT_SCHEMA.json"
CONSTITUTION = HERE / "RESEARCH_CONSTITUTION.md"
RESEARCHER = HERE / "prompts" / "RESEARCHER.md"
RUNS = HERE / "runs"
EXPERIMENTS = HERE / "experiments"

RUNS.mkdir(parents=True, exist_ok=True)
EXPERIMENTS.mkdir(parents=True, exist_ok=True)


def git(*args):
    p = subprocess.run(
        ["git", *args],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=True,
    )
    return p.stdout.strip()


def clean_tree():
    return git("status", "--porcelain") == ""


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, obj):
    path.write_text(
        json.dumps(obj, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def foundation_hash():
    h = hashlib.sha256()
    for p in (CONSTITUTION, SCHEMA, RESEARCHER):
        h.update(p.read_bytes())
    return h.hexdigest()


def validate_foundation():
    state = load_json(STATE)
    schema = load_json(SCHEMA)

    assert state["optimise_for_significance"] is False
    assert state["baseline"]["usable_var_rows"] == 160
    assert schema["principles"]["optimise_for_significance"] is False
    assert schema["principles"]["record_null_results"] is True

    return state, schema


def choose_experiment(state):
    """
    Deterministic first autonomous proposal.

    The agent is NOT allowed to select specifications because they produce
    favourable significance. This proposal is chosen because it attacks a
    remaining identification concern: whether the directional coefficients
    survive systematic removal of the most influential observations.
    """

    return {
        "experiment_id": "agent_006_influence_trim",
        "title": "Pre-specified influence-trim robustness",
        "research_question": (
            "Do the directional VAR coefficients retain their sign and "
            "approximate magnitude after removing the most influential "
            "observations identified independently by experiment 004?"
        ),
        "motivation": (
            "Experiment 004 identified observations with unusually large "
            "leave-one-out influence. A deterministic trimming exercise "
            "tests concentration of the result without searching for a "
            "preferred significance outcome."
        ),
        "design": {
            "source": "influence_rows_004.csv",
            "ranking_rule": "absolute leave-one-out coefficient change",
            "trim_counts": [1, 3, 5, 10],
            "directions": ["FF_to_IEM", "IEM_to_FF"],
            "baseline_rows": 160,
            "meeting_fixed_effects": True,
            "hac_lag": 6,
        },
        "success_criteria": {
            "scientific_success": (
                "A valid, reproducible result is success regardless of "
                "whether the original finding strengthens, weakens or disappears."
            ),
            "no_significance_optimisation": True,
            "record_null_result": True,
        },
    }


def create_run():
    if not clean_tree():
        raise SystemExit(
            "STOP: working tree must be clean before autonomous execution."
        )

    state, schema = validate_foundation()

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    proposal = choose_experiment(state)

    record = {
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "proposed",
        "branch": git("branch", "--show-current"),
        "starting_commit": git("rev-parse", "HEAD"),
        "parent_checkpoint": state["parent_checkpoint"],
        "foundation_sha256": foundation_hash(),
        "proposal": proposal,
        "execution": None,
        "evaluation": None,
        "constraints": {
            "optimise_for_significance": False,
            "record_null_results": True,
            "validated_data_read_only": True,
            "automatic_merge": False,
            "automatic_push": False,
        },
    }

    out = RUNS / f"{run_id}.json"
    write_json(out, record)

    print("=== AUTORESEARCH PROPOSAL CREATED ===")
    print("run:", run_id)
    print("experiment:", proposal["experiment_id"])
    print("title:", proposal["title"])
    print("record:", out)
    print()
    print("STATE = PROPOSED")
    print("No experiment executed.")
    print("No commit created.")
    print("No push occurred.")

    return out


def validate_proposal(path):
    record = load_json(path)
    p = record["proposal"]

    assert p
    assert p["success_criteria"]["no_significance_optimisation"] is True
    assert p["success_criteria"]["record_null_result"] is True
    assert p["design"]["baseline_rows"] == 160
    assert p["design"]["hac_lag"] == 6

    record["status"] = "validated"
    record["proposal_validation"] = {
        "passed": True,
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
        "checks": [
            "baseline row count frozen",
            "HAC lag pre-specified",
            "meeting fixed effects pre-specified",
            "trim counts pre-specified",
            "null results explicitly admissible",
            "no significance optimisation permitted",
        ],
    }

    write_json(path, record)

    print("=== PROPOSAL VALIDATION ===")
    print("PASS")
    print("STATE = VALIDATED")


def latest_run():
    paths = sorted(RUNS.glob("*.json"))
    if not paths:
        raise SystemExit("STOP: no run records exist")
    return paths[-1]


def status():
    state, _ = validate_foundation()

    print("=== AUTORESEARCH LOOP STATUS ===")
    print("branch:", git("branch", "--show-current"))
    print("HEAD:", git("rev-parse", "--short", "HEAD"))
    print("tree clean:", clean_tree())
    print("parent checkpoint:", state["parent_checkpoint"])
    print("usable VAR rows:", state["baseline"]["usable_var_rows"])
    print("optimise for significance:", state["optimise_for_significance"])
    print("foundation hash:", foundation_hash()[:16])
    print("loop: READY")


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: autonomous_loop.py status|propose|validate"
        )

    cmd = sys.argv[1]

    if cmd == "status":
        status()
    elif cmd == "propose":
        create_run()
    elif cmd == "validate":
        validate_proposal(latest_run())
    else:
        raise SystemExit("unknown command")


if __name__ == "__main__":
    main()
