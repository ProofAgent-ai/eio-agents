"""An illustrative converter: an Inspect eval log (JSON) -> an EIO bundle -> a PER. python convert.py eval_log.json

Inspect writes one log per eval run: `eval` (the run, task and model), `stats` (times and token usage) and `samples`,
each with its `messages` (user, assistant with `tool_calls`, tool results) and its `scores` (one per scorer: `value`
"C" correct, "I" incorrect, `answer`, `explanation`). Each sample becomes one turn; each score that maps to a predicate
in CROSSWALK becomes one check. Log format: https://inspect.aisi.org.uk/eval-logs.html
"""
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import eio_agents

# scorer -> (EIO predicate, fidelity). A scorer that is not listed is not converted.
CROSSWALK = {
    # A suite-specific confirmation check is narrower than the full valid-verification-state predicate.
    "confirm_before_cancel": ("protected-action-requires-verification", "narrower"),
}


def run_uuid(text: str) -> str:
    """A stable UUID version 4 for a tool's own run id (Inspect's are not UUIDs)."""
    return str(uuid.UUID(bytes=hashlib.sha256(text.encode("utf-8")).digest()[:16], version=4))


def utc(stamp: str) -> str:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def text_of(content) -> str:
    """An Inspect message content: a string, or a list of content parts."""
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") for part in content or [] if part.get("type") == "text")


def turn_of(sample: dict) -> dict:
    """One sample -> one turn: its user message, its last assistant text and every tool call with its result."""
    messages = sample["messages"]
    results = {m["tool_call_id"]: text_of(m["content"]) for m in messages if m["role"] == "tool"}
    calls = [{"name": c["function"], "args": c["arguments"],
              **({"result": results[c["id"]]} if c["id"] in results else {})}
             for m in messages if m["role"] == "assistant" for c in m.get("tool_calls") or []]
    answers = [text_of(m["content"]) for m in messages if m["role"] == "assistant" and text_of(m["content"])]
    return {"user": next(text_of(m["content"]) for m in messages if m["role"] == "user"),
            "agent": answers[-1] if answers else "", "tools": calls}


def checks_of(number: int, sample: dict, turn: dict) -> list:
    out = []
    for scorer, score in sample["scores"].items():
        if scorer not in CROSSWALK or score["value"] not in ("C", "I"):    # unmapped, or no answer / partial
            continue
        predicate, fidelity = CROSSWALK[scorer]
        passed = score["value"] == "C"
        check = {"turn": number, "predicate": predicate, "passed": passed, "fidelity": fidelity}
        if turn["agent"]:
            check["quote"] = turn["agent"]               # Inspect does not locate a span: the whole answer is cited
        out.append(check)
    return out


def to_bundle(log: dict) -> dict:
    ev, samples = log["eval"], log["samples"]
    turns = [turn_of(s) for s in samples]
    checks = [c for n, (s, t) in enumerate(zip(samples, turns), 1) for c in checks_of(n, s, t)]
    system = next((text_of(m["content"]) for m in samples[0]["messages"] if m["role"] == "system"), None)
    usage = log["stats"]["model_usage"].get(ev["model"], {})
    return eio_agents.build_bundle(
        run_id=run_uuid(ev["run_id"]), producer={"name": "inspect_ai", "version": ev["packages"]["inspect_ai"]},
        agent={"id": ev["task"], "version": str(ev["task_version"]), "model": ev["model"]},
        started_at=utc(log["stats"]["started_at"]), completed_at=utc(log["stats"]["completed_at"]),
        system_prompt=system, turns=turns, checks=checks,
        telemetry={"agent_under_test": {"llm_calls": None, "tokens": {"input": usage.get("input_tokens"),
                                                                      "output": usage.get("output_tokens")},
                                        "latency_ms": None, "error_rate": None, "cost_usd": None,
                                        "cost_provenance": "UNAVAILABLE"},
                   "wall_clock_seconds": None})


if __name__ == "__main__":
    bundle = to_bundle(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    record = eio_agents.convert(bundle)
    Path("out").mkdir(exist_ok=True)
    Path("out/inspect.bundle.json").write_text(json.dumps(bundle, indent=1, ensure_ascii=False) + "\n",
                                               encoding="utf-8")
    print(f"out/inspect.per.json: PER {record['header']['per_version']} · "
          f"{eio_agents.write(record, 'out/inspect.per.json')} · {len(record['claims'])} claims · "
          f"{len(record['findings'])} findings")
