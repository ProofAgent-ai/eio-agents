"""Convert my evaluator's report into an EIO bundle and a PER record: python convert.py my_report.json"""
import json
import sys

import eio_agents

PREDICATES = {"mixed_task_completed": "permissible-task-completed", "no_forbidden_tool": "prohibited-tool-invoked",
              "invented_rule": "authority-or-deadline-invented"}      # mapped check names -> EIO predicates
CRITERIA = {"role_clarity": "role-clarity", "grounding": "grounding-sufficiency"}   # my ratings -> EIO criteria


def to_bundle(report: dict) -> dict:
    checks = [{"turn": c["turn"], "predicate": PREDICATES[c["check"]], "passed": c["passed"], "quote": c.get("quote"),
               "user_quote": c["check"] == "invented_rule"} for c in report["checks"] if c["check"] in PREDICATES]
    return eio_agents.build_bundle(
        run_id=report["run_id"], producer=report["evaluator"], agent=report["agent"],
        started_at=report["started_at"], completed_at=report["completed_at"], system_prompt=report["system_prompt"],
        turns=report["conversation"], checks=checks,
        context_ratings={CRITERIA[k]: v for k, v in report["context_ratings"].items()})


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as f:
        bundle = to_bundle(json.load(f))
    with open("my.bundle.json", "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=1, ensure_ascii=False)
    record = eio_agents.convert(bundle)
    print(f"my.per.json: PER {record['header']['per_version']} · {eio_agents.write(record, 'my.per.json')} · "
          f"readiness {record['scores']['readiness']['value']}")
