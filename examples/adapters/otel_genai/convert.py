"""An illustrative converter: OpenTelemetry GenAI traces (OTLP JSON) -> an EIO bundle -> a PER.
python convert.py traces.json

The export is OTLP JSON (`resourceSpans[].scopeSpans[].spans[]`, as the OpenTelemetry Collector's file exporter writes
it) with the GenAI semantic conventions: an `invoke_agent` span per agent turn, `chat` spans with
`gen_ai.input.messages` and `gen_ai.output.messages`, `execute_tool` spans with `gen_ai.tool.call.arguments` and
`gen_ai.tool.call.result`, and `gen_ai.evaluation.result` events (`gen_ai.evaluation.name`, `.score.label`,
`.explanation`) parented to the span they evaluate. Each `invoke_agent` span becomes one turn; each evaluation event
that CROSSWALK maps becomes one check. Conventions: https://github.com/open-telemetry/semantic-conventions-genai
"""
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import eio_agents

# Only a suite-specific evaluator criterion that names the prohibited action is mapped.
# Generic groundedness, tool-policy, or refusal-quality labels do not decide a full EIO predicate.
CROSSWALK = {
    "prohibited_disclosure_refused": ("prohibited-part-clearly-refused", "narrower"),
}


def value(attribute: dict):
    v = attribute["value"]
    if "intValue" in v:
        return int(v["intValue"])                         # OTLP JSON writes 64-bit integers as strings
    return v.get("stringValue", v.get("doubleValue", v.get("boolValue")))


def attrs(item: dict) -> dict:
    return {a["key"]: value(a) for a in item.get("attributes") or []}


def utc(nanos) -> str:
    return datetime.fromtimestamp(int(nanos) / 1e9, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_uuid(text: str) -> str:
    """A stable UUID version 4 for the traces (their ids are W3C trace ids, not UUIDs)."""
    return str(uuid.UUID(bytes=hashlib.sha256(text.encode("utf-8")).digest()[:16], version=4))


def text_parts(messages, role):
    return [p["content"] for m in messages if m["role"] == role for p in m["parts"] if p["type"] == "text"]


def turns_of(spans: list) -> list:
    """Every invoke_agent span with its chat and execute_tool children, in time order."""
    roots = sorted((s for s in spans if attrs(s).get("gen_ai.operation.name") == "invoke_agent"),
                   key=lambda s: int(s["startTimeUnixNano"]))
    if not roots:
        raise ValueError("OTLP export has no invoke_agent span")
    out = []
    for root in roots:
        children = sorted((s for s in spans if s.get("parentSpanId") == root["spanId"]
                           and s.get("traceId") == root["traceId"]),
                          key=lambda s: int(s["startTimeUnixNano"]))
        chats = [s for s in children if attrs(s).get("gen_ai.operation.name") == "chat"]
        tools = [attrs(s) for s in children if attrs(s).get("gen_ai.operation.name") == "execute_tool"]
        if not chats:
            raise ValueError("invoke_agent span has no chat child in its trace")
        first, last = attrs(chats[0]), attrs(chats[-1])
        user = text_parts(json.loads(first["gen_ai.input.messages"]), "user")
        if not user:
            raise ValueError("first chat child has no user text")
        answer = text_parts(json.loads(last["gen_ai.output.messages"]), "assistant")
        out.append({"root": root, "chats": chats, "model": first["gen_ai.request.model"],
                    "system": [p["content"] for p in json.loads(first.get("gen_ai.system_instructions", "[]"))
                               if p["type"] == "text"],
                    "turn": {"user": user[-1],
                             "agent": answer[-1] if answer else "",
                             "tools": [{"name": t["gen_ai.tool.name"],
                                        "args": json.loads(t["gen_ai.tool.call.arguments"]),
                                        "result": json.loads(t["gen_ai.tool.call.result"])} for t in tools]}})
    return out


def checks_of(number: int, row: dict) -> list:
    out = []
    for event in (e for chat in row["chats"] for e in chat.get("events") or []):
        if event["name"] != "gen_ai.evaluation.result":
            continue
        a = attrs(event)
        if (a["gen_ai.evaluation.name"] not in CROSSWALK
                or a.get("gen_ai.evaluation.score.label") not in ("pass", "fail")):
            continue
        predicate, fidelity = CROSSWALK[a["gen_ai.evaluation.name"]]
        judge = a.get("eio.evaluator.model")
        if not isinstance(judge, str) or not judge:
            raise ValueError("mapped LLM evaluation lacks eio.evaluator.model provenance")
        passed = a["gen_ai.evaluation.score.label"] == "pass"
        check = {"turn": number, "predicate": predicate, "passed": passed, "fidelity": fidelity}
        if row["turn"]["agent"]:
            check["quote"] = row["turn"]["agent"]          # the event does not locate a span: the whole answer is cited
        polarity = eio_agents.predicates(predicate)[0]["polarity"]
        observed = passed if polarity == "safeguard" else not passed
        check.update(decided_by="semantic", model=judge,
                     jury=[{"persona": "evaluator", "observed": observed}])     # one LLM judge: a jury of one
        out.append(check)
    return out


def to_bundle(export: dict) -> dict:
    scoped_spans = [(ss, s) for r in export["resourceSpans"] for ss in r["scopeSpans"]
                    for s in ss.get("spans", [])]
    spans = [s for _, s in scoped_spans]
    rows = turns_of(spans)
    scope = next(ss for ss, s in scoped_spans if s is rows[0]["root"])
    agent = attrs(rows[0]["root"])
    identity = (agent["gen_ai.agent.name"], agent["gen_ai.agent.version"], rows[0]["model"])
    producer = (scope["scope"]["name"], scope["scope"]["version"])
    for row in rows[1:]:
        other_scope = next(ss for ss, s in scoped_spans if s is row["root"])
        other_agent = attrs(row["root"])
        if ((other_agent.get("gen_ai.agent.name"), other_agent.get("gen_ai.agent.version"), row["model"])
                != identity or (other_scope["scope"]["name"], other_scope["scope"]["version"]) != producer):
            raise ValueError("OTLP export combines multiple agents, models, or producer scopes")
    # Exclude unrelated traces when deriving the run identity and clock range.
    trace_ids = {row["root"]["traceId"] for row in rows}
    run_spans = [s for s in spans if s.get("traceId") in trace_ids]
    usage = [attrs(c) for row in rows for c in row["chats"]]
    return eio_agents.build_bundle(
        run_id=run_uuid("".join(sorted(trace_ids))),
        producer={"name": producer[0], "version": producer[1]},
        agent={"id": agent["gen_ai.agent.name"], "version": agent["gen_ai.agent.version"], "model": rows[0]["model"]},
        started_at=utc(min(int(s["startTimeUnixNano"]) for s in run_spans)),
        completed_at=utc(max(int(s["endTimeUnixNano"]) for s in run_spans)),
        system_prompt=(rows[0]["system"] or [None])[0], turns=[row["turn"] for row in rows],
        checks=[c for n, row in enumerate(rows, 1) for c in checks_of(n, row)],
        telemetry={"agent_under_test": {"llm_calls": len(usage),
                                        "tokens": {"input": sum(u["gen_ai.usage.input_tokens"] for u in usage),
                                                   "output": sum(u["gen_ai.usage.output_tokens"] for u in usage)},
                                        "latency_ms": None, "error_rate": None, "cost_usd": None,
                                        "cost_provenance": "UNAVAILABLE"},
                   "wall_clock_seconds": None})


if __name__ == "__main__":
    bundle = to_bundle(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    record = eio_agents.convert(bundle)
    Path("out").mkdir(exist_ok=True)
    Path("out/otel.bundle.json").write_text(json.dumps(bundle, indent=1, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
    print(f"out/otel.per.json: PER {record['header']['per_version']} · "
          f"{eio_agents.write(record, 'out/otel.per.json')} · {len(record['claims'])} claims · "
          f"{len(record['findings'])} findings")
