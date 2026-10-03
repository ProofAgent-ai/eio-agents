"""An illustrative converter: a promptfoo results.json -> an EIO bundle -> a PER. python convert.py results.json

`promptfoo eval -o results.json` writes the eval (`results.version` 3): each entry of `results.results` is one test
case run against one prompt and provider, with the model's `response.output` and a `gradingResult` whose
`componentResults` hold one result per assertion (`assertion.type`, `assertion.metric`, `pass`, `reason`). Each test
case becomes one turn; each assertion that CROSSWALK maps becomes one check.
Output format: https://www.promptfoo.dev/docs/configuration/outputs/
"""
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import eio_agents

# Only this suite's calibrated RBAC assertion is mapped. Generic contains, rubric and JavaScript
# results do not decide the full meaning of an EIO predicate and must not become claims.
CROSSWALK = {
    ("promptfoo:redteam:rbac", "RbacEnforcement"): ("unverified-authority-accepted", "narrower"),
}
# assertion types that a program decides; every other type (llm-rubric, factuality, promptfoo:redteam:*) is graded
DETERMINISTIC = {"contains", "icontains", "not-contains", "equals", "regex", "starts-with", "is-json", "javascript",
                 "python", "contains-any", "contains-all"}
AGENT_ID = "bank-assistant"                      # results.json does not name the application under test
SYSTEM_SPLIT = "\n\nCustomer: "                  # the prompt template puts the system text before the customer turn


def run_uuid(text: str) -> str:
    """A stable UUID version 4 for promptfoo's eval id."""
    return str(uuid.UUID(bytes=hashlib.sha256(text.encode("utf-8")).digest()[:16], version=4))


def utc(stamp: str) -> str:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def turn_of(result: dict) -> dict:
    """A test case -> a turn. An OpenAI-style provider returns its tool calls as the output (promptfoo runs no tool,
    so the calls have no result)."""
    output = result["response"]["output"]
    if isinstance(output, list):
        tools = [{"name": c["function"]["name"], "args": json.loads(c["function"]["arguments"])} for c in output]
        return {"user": result["vars"]["query"], "agent": "", "tools": tools}
    return {"user": result["vars"]["query"], "agent": output, "tools": []}


def checks_of(number: int, result: dict, turn: dict, grader: str) -> list:
    out = []
    for component in result["gradingResult"]["componentResults"]:
        assertion = component["assertion"]
        key = (assertion.get("type"), assertion.get("metric"))
        if key not in CROSSWALK:
            continue
        predicate, fidelity = CROSSWALK[key]
        check = {"turn": number, "predicate": predicate, "passed": component["pass"], "fidelity": fidelity}
        if turn["agent"]:
            check["quote"] = turn["agent"]               # promptfoo does not locate a span: the whole output is cited
        if assertion["type"] not in DETERMINISTIC:
            polarity = eio_agents.predicates(predicate)[0]["polarity"]
            observed = component["pass"] if polarity == "safeguard" else not component["pass"]
            # the grading provider is an LLM judge: a jury of one
            check.update(decided_by="semantic", model=grader, jury=[{"persona": "grader", "observed": observed}])
        out.append(check)
    return out


def to_bundle(export: dict) -> dict:
    results = export["results"]["results"]
    turns = [turn_of(r) for r in results]
    grader = export["config"]["defaultTest"]["options"]["provider"]         # the grading provider
    checks = [c for n, (r, t) in enumerate(zip(results, turns), 1) for c in checks_of(n, r, t, grader)]
    template = export["results"]["prompts"][0]["raw"]
    stamp = utc(export["results"]["timestamp"])
    tokens = export["results"]["stats"]["tokenUsage"]
    # results.json records its format version, not the promptfoo version: the format version names the producer
    return eio_agents.build_bundle(
        run_id=run_uuid(export["evalId"]), producer={"name": "promptfoo", "version": str(export["results"]["version"])},
        agent={"id": AGENT_ID, "version": "1.0.0", "model": results[0]["provider"]["id"]},
        started_at=stamp, completed_at=stamp, system_prompt=template.split(SYSTEM_SPLIT)[0], turns=turns,
        checks=checks,
        telemetry={"agent_under_test": {"llm_calls": len(results), "tokens": {"input": tokens["prompt"],
                                                                             "output": tokens["completion"]},
                                        "latency_ms": None, "error_rate": None, "cost_usd": None,
                                        "cost_provenance": "UNAVAILABLE"},
                   "wall_clock_seconds": sum(r["latencyMs"] for r in results) / 1000})


if __name__ == "__main__":
    bundle = to_bundle(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    record = eio_agents.convert(bundle)
    Path("out").mkdir(exist_ok=True)
    Path("out/promptfoo.bundle.json").write_text(json.dumps(bundle, indent=1, ensure_ascii=False) + "\n",
                                                encoding="utf-8")
    print(f"out/promptfoo.per.json: PER {record['header']['per_version']} · "
          f"{eio_agents.write(record, 'out/promptfoo.per.json')} · {len(record['claims'])} claims · "
          f"{len(record['findings'])} findings")
