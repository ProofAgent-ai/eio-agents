"""An illustrative converter: a DeepEval test run (JSON) -> an EIO bundle -> a PER. python convert.py test_run.json

DeepEval's test run is its `TestRun` model serialized with camelCase aliases: `testCases`, each with `input`,
`actualOutput`, `toolsCalled` (`name`, `inputParameters`, `output`), `expectedTools` and `metricsData` (`name`,
`score`, `threshold`, `success`, `reason`, `evaluationModel`). Each test case becomes one turn; each metric that
CROSSWALK maps becomes one check. Docs: https://deepeval.com/docs/evaluation-test-cases and
https://deepeval.com/docs/metrics-introduction
"""
import hashlib
import json
import sys
import uuid
from pathlib import Path

import eio_agents

# Only this suite's specifically worded criterion is mapped. Tool Correctness is not task
# completion, and generic Hallucination does not necessarily decide expressed certainty.
CROSSWALK = {
    "Policy Adherence [GEval]": ("authority-or-deadline-invented", "narrower"),  # a G-Eval criterion: no invented terms
}
# A metric with an evaluationModel is graded by that model; one without (Tool Correctness compares tool names) is
# decided by a program.
STARTED_AT, COMPLETED_AT = "2026-09-30T16:00:00Z", "2026-09-30T16:00:10Z"   # a test run records durations only
AGENT_ID = "claims-assistant"


def run_uuid(text: str) -> str:
    """A stable UUID version 4 for a test run (DeepEval's file has no run id: the file's own digest names it)."""
    return str(uuid.UUID(bytes=hashlib.sha256(text.encode("utf-8")).digest()[:16], version=4))


def turn_of(case: dict) -> dict:
    tools = [{"name": t["name"], "args": t.get("inputParameters") or {},
              **({"result": t["output"]} if "output" in t else {})}
             for t in case.get("toolsCalled") or []]
    return {"user": case["input"], "agent": case["actualOutput"], "tools": tools}


def checks_of(number: int, case: dict, turn: dict) -> list:
    out = []
    for metric in case["metricsData"]:
        if metric["name"] not in CROSSWALK or metric.get("error") or metric.get("success") is None:
            continue
        predicate, fidelity = CROSSWALK[metric["name"]]
        check = {"turn": number, "predicate": predicate, "passed": metric["success"], "fidelity": fidelity,
                 "quote": turn["agent"]}                 # DeepEval does not locate a span: the whole output is cited
        if metric.get("evaluationModel"):
            polarity = eio_agents.predicates(predicate)[0]["polarity"]
            observed = metric["success"] if polarity == "safeguard" else not metric["success"]
            check.update(decided_by="semantic", model=metric["evaluationModel"],
                         jury=[{"persona": "evaluator", "observed": observed}])     # one LLM judge: a jury of one
        out.append(check)
    return out


def to_bundle(run: dict, digest: str) -> dict:
    cases = sorted(run["testCases"], key=lambda c: c["order"])
    turns = [turn_of(c) for c in cases]
    checks = [x for n, (c, t) in enumerate(zip(cases, turns), 1) for x in checks_of(n, c, t)]
    hyper = run.get("hyperparameters") or {}
    return eio_agents.build_bundle(
        run_id=run_uuid(digest), producer={"name": "deepeval", "version": "unrecorded"},
        agent={"id": AGENT_ID, "version": "1.0.0", "model": hyper["model"]},
        started_at=STARTED_AT, completed_at=COMPLETED_AT, system_prompt=hyper.get("system_prompt"),
        turns=turns, checks=checks,
        telemetry={"agent_under_test": {"llm_calls": len(cases), "tokens": None, "latency_ms": None,
                                        "error_rate": None, "cost_usd": None, "cost_provenance": "UNAVAILABLE"},
                   "wall_clock_seconds": run.get("runDuration")})


def load(path: str):
    raw = Path(path).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


if __name__ == "__main__":
    bundle = to_bundle(*load(sys.argv[1]))
    record = eio_agents.convert(bundle)
    Path("out").mkdir(exist_ok=True)
    Path("out/deepeval.bundle.json").write_text(json.dumps(bundle, indent=1, ensure_ascii=False) + "\n",
                                                encoding="utf-8")
    print(f"out/deepeval.per.json: PER {record['header']['per_version']} · "
          f"{eio_agents.write(record, 'out/deepeval.per.json')} · {len(record['claims'])} claims · "
          f"{len(record['findings'])} findings")
