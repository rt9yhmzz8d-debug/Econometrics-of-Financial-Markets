from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import subprocess
import sys

HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "state" / "research_state.json"
SCHEMA_FILE = HERE / "EXPERIMENT_SCHEMA.json"
CONSTITUTION_FILE = HERE / "RESEARCH_CONSTITUTION.md"
PROMPT_FILE = HERE / "prompts" / "RESEARCHER.md"
RUNS = HERE / "runs"
LOGS = HERE / "logs"

REPO = HERE.parents[2]

REQUIRED = [
    STATE_FILE,
    SCHEMA_FILE,
    CONSTITUTION_FILE,
    PROMPT_FILE,
]

def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def write_json(path: Path, obj):
    path.write_text(
        json.dumps(obj, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

def git(*args: str) -> str:
    p = subprocess.run(
        ["git", *args],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=True,
    )
    return p.stdout.strip()

def validate_foundation():
    for p in REQUIRED:
        if not p.exists():
            raise SystemExit(f"STOP: missing foundation file: {p}")

    state = load_json(STATE_FILE)
    schema = load_json(SCHEMA_FILE)

    if state.get("optimise_for_significance") is not False:
        raise SystemExit("STOP: state permits optimisation for significance")

    principles = schema.get("principles", {})

    if principles.get("optimise_for_significance") is not False:
        raise SystemExit("STOP: schema permits optimisation for significance")

    if principles.get("record_null_results") is not True:
        raise SystemExit("STOP: schema does not require null-result retention")

    return state, schema

def foundation_hash() -> str:
    h = hashlib.sha256()
    for p in REQUIRED:
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()

def make_run_record():
    state, schema = validate_foundation()

    branch = git("branch", "--show-current")
    head = git("rev-parse", "HEAD")
    dirty = git("status", "--porcelain")

    if branch != "autoresearch-agent-006":
        raise SystemExit(
            f"STOP: wrong branch {branch!r}; expected autoresearch-agent-006"
        )

    if dirty:
        raise SystemExit(
            "STOP: working tree is dirty before autonomous run:\n" + dirty
        )

    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")

    record = {
        "run_id": run_id,
        "created_at_utc": now.isoformat(),
        "status": "planned",
        "branch": branch,
        "starting_commit": head,
        "foundation_sha256": foundation_hash(),
        "parent_checkpoint": state.get("parent_checkpoint"),
        "baseline": state.get("baseline"),
        "constraints": {
            "optimise_for_significance": False,
            "record_null_results": True,
            "validated_data_read_only": True,
            "no_automatic_merge": True,
            "no_automatic_push": True,
        },
        "proposal": None,
        "execution": None,
        "evaluation": None,
    }

    path = RUNS / f"{run_id}.json"
    write_json(path, record)

    return path, record

def status():
    state, _ = validate_foundation()

    print("=== AUTORESEARCH STATUS ===")
    print("branch:", git("branch", "--show-current"))
    print("HEAD:", git("rev-parse", "--short", "HEAD"))
    print("parent checkpoint:", state.get("parent_checkpoint"))
    print("usable VAR rows:", state.get("baseline", {}).get("usable_var_rows"))
    print("optimise for significance:", state.get("optimise_for_significance"))
    print("foundation hash:", foundation_hash()[:16])
    print("runner: READY")

def plan():
    path, record = make_run_record()

    print("=== AUTORESEARCH RUN CREATED ===")
    print("run:", record["run_id"])
    print("starting commit:", record["starting_commit"][:12])
    print("record:", path)
    print()
    print("STATE = PLANNED")
    print("No experiment has been executed.")
    print("No commit has been created.")
    print("No push has occurred.")

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("plan")

    args = parser.parse_args()

    if args.command == "status":
        status()
    elif args.command == "plan":
        plan()

if __name__ == "__main__":
    main()
