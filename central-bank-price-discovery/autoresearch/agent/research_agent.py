#!/usr/bin/env python3

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RUNS = HERE / "runs"
OUTPUTS = HERE / "outputs"

SELECTOR = HERE / "select_next_experiment.py"
AI_RESEARCHER = HERE / "ai_researcher.py"
EXPERIMENTS = HERE / "experiments"

EXPECTED_BRANCH = "autoresearch-agent-006"


def run(cmd, *, capture=False, check=True):
    result = subprocess.run(
        cmd,
        cwd=REPO,
        text=True,
        capture_output=capture,
        check=check,
    )
    return result.stdout.strip() if capture else result


def git(*args):
    return run(["git", *args], capture=True)


def require_clean_tree():
    dirty = git("status", "--porcelain")
    if dirty:
        raise SystemExit(
            "STOP: working tree is dirty before autonomous cycle:\n" + dirty
        )


def require_branch():
    branch = git("branch", "--show-current")
    if branch != EXPECTED_BRANCH:
        raise SystemExit(
            f"STOP: expected branch {EXPECTED_BRANCH}, got {branch}"
        )


def latest_007_plus():
    files = sorted(
        RUNS.glob("*_experiment*.json"),
        key=lambda x: x.stat().st_mtime,
    )
    return files[-1] if files else None


def load(path):
    return json.loads(path.read_text())


def freeze(path, message):
    run(["git", "add", str(path.relative_to(REPO))])
    run(["git", "commit", "-m", message])


def preserve_evidence(path):
    run(["git", "add", "-f", str(path.relative_to(REPO))])


def pending_preregistered_run():
    """Return newest genuinely pending preregistration, if one exists."""
    records = []

    for path in RUNS.glob("*.json"):
        try:
            record = load(path)
        except Exception:
            continue

        exp = (
            record.get("selected_experiment")
            or record.get("proposal")
            or {}
        ).get("experiment_id")

        if exp:
            records.append((path, record, exp))

    executed_ids = {
        exp
        for _, record, exp in records
        if record.get("status") == "executed"
    }

    pending = [
        (path, record)
        for path, record, exp in records
        if record.get("status") == "selected_not_executed"
        and exp not in executed_ids
    ]

    if not pending:
        return None

    pending.sort(
        key=lambda item: item[1].get("created_at_utc", "")
    )

    return pending[-1][0]


def latest_ai_proposal():
    files = sorted(
        EXPERIMENTS.glob("*_ai_proposal.json"),
        key=lambda x: x.stat().st_mtime,
    )
    return files[-1] if files else None


def proposal_has_evidence(experiment_id):
    for path in OUTPUTS.rglob("evidence.json"):
        try:
            evidence = load(path)
        except Exception:
            continue

        evidence_id = (
            evidence.get("experiment_id")
            or (evidence.get("metadata") or {}).get("experiment_id")
        )

        if evidence_id == experiment_id:
            return True

    return False


def generate_ai_proposal():
    """Generate exactly one new methodological proposal.

    This stage may call the research model, but it must not execute an
    econometric experiment or modify validated source data.
    """
    before = set(EXPERIMENTS.glob("*_ai_proposal.json"))

    run([
        sys.executable,
        str(AI_RESEARCHER),
        "propose",
    ])

    after = set(EXPERIMENTS.glob("*_ai_proposal.json"))
    created = sorted(after - before)

    if len(created) != 1:
        raise SystemExit(
            "STOP: AI researcher did not create exactly one proposal"
        )

    proposal_path = created[0]
    proposal = load(proposal_path)

    experiment_id = proposal.get("experiment_id")

    if not experiment_id:
        raise SystemExit(
            "STOP: AI proposal missing experiment_id"
        )

    if proposal_has_evidence(experiment_id):
        raise SystemExit(
            "STOP: AI proposed an experiment that already has evidence: "
            + experiment_id
        )

    return proposal_path, proposal


def freeze_ai_proposal(path, experiment_id):
    freeze(
        path,
        f"Preregister AI-proposed {experiment_id}",
    )


def select_next():
    before = set(RUNS.glob("*.json"))

    result = subprocess.run(
        [sys.executable, str(SELECTOR)],
        cwd=REPO,
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        combined = (
            (result.stdout or "")
            + "\n"
            + (result.stderr or "")
        )

        if "no unused candidate experiments remain" in combined.lower():
            raise subprocess.CalledProcessError(
                result.returncode,
                result.args,
                output=result.stdout,
                stderr=result.stderr,
            )

        raise SystemExit(
            "STOP: selector failed unexpectedly:\n" + combined
        )

    after = set(RUNS.glob("*.json"))
    created = sorted(after - before)

    if len(created) != 1:
        raise SystemExit(
            f"STOP: selector created {len(created)} run records"
        )

    return created[0]


def validate_selected_record(path):
    d = load(path)

    if d.get("status") != "selected_not_executed":
        raise SystemExit(
            "STOP: selected experiment is not in "
            "selected_not_executed state"
        )

    policy = d.get("selection_policy", {})

    if policy.get("optimise_for_significance") is not False:
        raise SystemExit("STOP: significance optimisation guard failed")

    if policy.get("p_values_used_as_selection_reward") is not False:
        raise SystemExit("STOP: p-value reward guard failed")

    if policy.get("null_results_admissible") is not True:
        raise SystemExit("STOP: null-result guard failed")

    return d


def executor_for(record):
    exp = record["selected_experiment"]["experiment_id"]

    # Explicit routing prevents one experiment from accidentally being
    # executed by another experiment's frozen implementation.
    executor_map = {
        "agent_007_joint_symmetric_trim":
            HERE / "executor_007.py",
        "agent_007_meeting_concentration":
            HERE / "executor_007_meeting_concentration.py",
        "agent_007_sign_stability_curve":
            HERE / "executor_007_sign_stability_curve.py",
    }

    candidate = executor_map.get(exp)

    if candidate is not None and candidate.exists():
        return candidate

    raise SystemExit(
        "STOP: no frozen executor exists for selected experiment "
        f"{exp}. Selection has been preserved but execution was not attempted."
    )


def execute(path, executor):
    run([sys.executable, str(executor), str(path)])

    d = load(path)

    if d.get("status") != "executed":
        raise SystemExit("STOP: executor did not mark run executed")

    execution = d.get("execution") or {}

    if execution.get("baseline_reproduced") is not True:
        raise SystemExit("STOP: baseline reproduction failed")

    evaluation = d.get("evaluation") or {}

    if evaluation.get("result_selection_performed") is not False:
        raise SystemExit("STOP: result-selection guard failed")

    if evaluation.get("null_results_recorded") is not True:
        raise SystemExit("STOP: null-result recording guard failed")

    evidence_rel = execution.get("evidence")
    if not evidence_rel:
        raise SystemExit("STOP: evidence path missing")

    evidence = REPO / evidence_rel

    if not evidence.exists():
        raise SystemExit("STOP: evidence file missing")

    return evidence


def cycle(dry_run=False):
    require_branch()
    require_clean_tree()

    start = git("rev-parse", "HEAD")

    print("=== AUTONOMOUS CYCLE ===")
    print("starting commit:", start[:12])

    selected = pending_preregistered_run()

    if selected is not None:
        print("pending preregistration detected:", selected.relative_to(REPO))
        print("action: RESUME EXISTING FROZEN DECISION")
        record = validate_selected_record(selected)
        newly_selected = False
    else:
        try:
            selected = select_next()
            record = validate_selected_record(selected)
            newly_selected = True
        except subprocess.CalledProcessError as exc:
            # Fail closed on selector bugs. Only candidate exhaustion may
            # hand control to the AI proposal stage.
            combined = (
                (exc.stdout or "")
                + "\n"
                + (exc.stderr or "")
            )

            exhaustion_message = (
                "no unused candidate experiments remain"
            )

            if exhaustion_message not in combined.lower():
                raise

            print(
                "finite candidate selector exhausted; "
                "requesting new AI research proposal"
            )

            proposal_path, proposal = generate_ai_proposal()
            exp = proposal["experiment_id"]

            print("AI proposal:", exp)
            print("proposal:", proposal_path.relative_to(REPO))

            # Freeze the scientific question before implementation or
            # econometric results are generated.
            freeze_ai_proposal(
                proposal_path,
                exp,
            )

            print("AI proposal preregistration: FROZEN")
            print(
                "STOP: proposal frozen. Implementation planning and "
                "execution require a subsequent stage."
            )
            return

    exp = record["selected_experiment"]["experiment_id"]

    print("selected:", exp)
    print("record:", selected.relative_to(REPO))

    if newly_selected:
        # Freeze the machine's decision before any result exists.
        freeze(
            selected,
            f"Preregister autonomously selected {exp}",
        )
        print("preregistration: FROZEN")
    else:
        print("preregistration: ALREADY FROZEN")

    if dry_run:
        print("DRY RUN: stopping before execution")
        return

    # Important safety boundary:
    # only an already-existing frozen executor may be used.
    executor = executor_for(record)

    # Executor must already be tracked in Git.
    tracked = git("ls-files", str(executor.relative_to(REPO)))
    if not tracked:
        raise SystemExit(
            "STOP: executor exists but is not frozen in Git"
        )

    require_clean_tree()

    evidence = execute(selected, executor)

    run(["git", "add", str(selected.relative_to(REPO))])
    preserve_evidence(evidence)

    run([
        "git",
        "commit",
        "-m",
        f"Record preregistered {exp} results",
    ])

    print("execution: COMPLETE")
    print("evidence:", evidence.relative_to(REPO))
    print("checkpoint:", git("rev-parse", "--short", "HEAD"))
    print("push: NOT PERFORMED")
    print("merge: NOT PERFORMED")


def status():
    require_branch()

    print("=== AUTORESEARCH ORCHESTRATOR STATUS ===")
    print("branch:", git("branch", "--show-current"))
    print("HEAD:", git("rev-parse", "--short", "HEAD"))
    print("tree clean:", not bool(git("status", "--porcelain")))

    latest = latest_007_plus()
    if latest:
        d = load(latest)
        print("latest run:", latest.name)
        print("latest state:", d.get("status"))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")

    run_parser = sub.add_parser("run")
    run_parser.add_argument(
        "--max-experiments",
        type=int,
        default=1,
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    args = parser.parse_args()

    if args.command == "status":
        status()
        return

    if args.max_experiments < 1 or args.max_experiments > 20:
        raise SystemExit(
            "STOP: --max-experiments must be between 1 and 20"
        )

    for i in range(args.max_experiments):
        print()
        print(
            f"===== CYCLE {i + 1}/{args.max_experiments} ====="
        )
        cycle(dry_run=args.dry_run)

        if args.dry_run:
            break


if __name__ == "__main__":
    main()
