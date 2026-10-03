"""A hand-written report -> bundle converter over the library internals, kept as the reference `build_bundle` must
reproduce: it starts from the source-complete sample bundle and replaces every part of the run from the report
(`tests/data/report/travel_report.json`), as a developer did before `build_bundle` existed."""
import copy

from eio_agents.base.canon import H, jb
from eio_agents.evidence.refs import no_call_ref, receipt_ref, span_ref
from eio_agents.ontology import load
from eio_agents.per.bundle import stage_digest
from eio_agents.semantics.ids import claim_id

CHECK_TO_PREDICATE = {
    "mixed_task_completed": ("eio.predicate.permissible-task-completed", "exact"),
    "no_forbidden_tool": ("eio.predicate.prohibited-tool-invoked", "exact"),
    "invented_rule": ("eio.predicate.authority-or-deadline-invented", "exact"),
}
RATING_TO_CRITERION = {"role_clarity": "eio.context.role-clarity", "grounding": "eio.context.grounding-sufficiency"}
FRAMEWORKS = ("eio.framework.owasp-agentic-threats", "eio.framework.aiuc-1")
TELEMETRY_UNAVAILABLE = {"llm_calls": None, "tokens": None, "latency_ms": None, "error_rate": None, "cost_usd": None,
                         "cost_provenance": "UNAVAILABLE"}


def reference_bundle(report, template):
    eio = load()
    b = copy.deepcopy(template)
    run_id = report["run_id"]
    plan_hash, seed = b["header"]["plan_hash"], b["header"]["seed"]
    b["header"]["run_id"] = run_id
    prov = b["provenance"]
    prov["producer"].update(name=report["evaluator"]["name"], version=report["evaluator"]["version"])
    prov["record"]["producer"] = dict(report["evaluator"])
    prov["record"]["run"].update(run_id=run_id, started_at=report["started_at"], completed_at=report["completed_at"])
    n = len(report["conversation"])
    prov["record"]["run"]["turns"].update(executed=n, selected=n)
    prov["agent"] = {"agent_id": report["agent"]["id"], "version": report["agent"]["version"],
                     "model": report["agent"]["model"]}
    prov["telemetry"] = {"agent_under_test": dict(TELEMETRY_UNAVAILABLE, llm_calls=n), "wall_clock_seconds": None}
    turns = []
    for i, t in enumerate(report["conversation"]):
        calls = [{"name": c["name"], "arguments": c["args"],
                  "arguments_pointer": f"/sources/turns/{i}/tool_calls/{j}/arguments", "result": c["result"]}
                 for j, c in enumerate(t["tools"])]
        turns.append({"turn_index": i + 1, "question": t["user"], "answer": t["agent"], "tool_calls": calls,
                      "retrievals": []})
    src = b["sources"]
    src["turns"] = turns
    src["transcript_sha256"] = H(jb(turns))
    prompt = report["system_prompt"]
    artifact = {"artifact_kind": "eio.artifact.system-prompt", "name": "system-prompt.md", "sha256": H(prompt.encode()),
                "code_points": len(prompt), "embedded": True, "data_class": "eio.data.public"}
    src["context_artifacts"] = [artifact]
    src["context_texts"] = {artifact["name"]: prompt}
    prov["record"]["inputs"]["context_artifacts"] = [artifact]
    refs, claims = {}, []
    for chk in report["checks"]:
        predicate, fidelity = CHECK_TO_PREDICATE[chk["check"]]
        t = chk["turn"]
        turn = turns[t - 1]
        evidence = []
        if "quote" in chk:
            a = turn["answer"].index(chk["quote"])
            evidence.append(span_ref(eio, "AGENT_SPAN", "AGENT_ANSWER", t, turn["answer"], a, a + len(chk["quote"]),
                                     "exact", "turns"))
        for j, c in enumerate(turn["tool_calls"]):
            evidence.append(receipt_ref(eio, t, j, c["name"], c["arguments"], 1, True, c["result"],
                                        c["arguments_pointer"], "turns"))
        if not turn["tool_calls"] and predicate == "eio.predicate.prohibited-tool-invoked":
            evidence.append(no_call_ref(eio, t, [], source_ref="turns", calls_field="tool_calls"))
        if predicate == "eio.predicate.authority-or-deadline-invented":
            evidence.append(span_ref(eio, "USER_INPUT", "USER_INPUT", t, turn["question"], 0, len(turn["question"]),
                                     "exact", "turns"))
        for r in evidence:
            refs.setdefault(r["id"], r)
        module, module_version = eio.mod_of_pred[predicate]
        version = eio.pred[predicate]["version"]
        claim = {"id": claim_id(run_id, predicate, version, None, [t]), "run_id": run_id, "turn_indices": [t],
                 "predicate": predicate, "predicate_version": version,
                 "state": "APPLICABLE_PASS" if chk["passed"] else "APPLICABLE_FAIL",
                 "parameters": {"fidelity": fidelity, "votes": None},
                 "evidence": [r["id"] for r in evidence], "decided_by": "deterministic"}
        if eio.pred[predicate].get("risk"):
            claim["risk"] = eio.pred[predicate]["risk"]
        claim["provenance"] = {"module": module, "module_version": module_version,
                               "module_hash": eio.modules[module], "plan_hash": plan_hash, "seed": seed}
        claims.append((claim, evidence, chk))
    b["graph"] = {"refs": list(refs.values()), "episodes": [[t["turn_index"]] for t in turns]}
    b["claims"] = [c for c, _, _ in claims]
    b["ballots"] = {"pooled_claims": [], "ballots": []}
    ns = b["native_scoring"]
    ns["scenario_bindings"] = [{"binding_id": f"s{k}", "turn_indices": c["turn_indices"], "severity": "HIGH"}
                               for k, (c, _, _) in enumerate(claims)]
    ns["claim_bindings"] = [{"claim_id": c["id"], "binding_id": f"s{k}"} for k, (c, _, _) in enumerate(claims)]
    predicates = {c["predicate"] for c in b["claims"]}
    ns["applicable_controls"] = [{"framework": f, "control_id": cid} for f in FRAMEWORKS
                                 for cid in eio.frameworks[f]["controls"]
                                 if predicates & set(eio.controls[cid]["predicate_targets"])]
    b["scope"]["frameworks"]["candidates"] = [{"id": f, "basis": "declared by the evaluator"} for f in FRAMEWORKS]
    ns["context_ratings"] = [{"criterion_id": RATING_TO_CRITERION[k], "artifact_name": artifact["name"],
                              "artifact_sha256": artifact["sha256"], "assessor_id": "travel-evals", "rating": v}
                             for k, v in report["context_ratings"].items()]
    ns["proof_citations"] = [{"claim_id": c["id"], "ref_id": ev[0]["id"], "role": "proof", "citation_anchor": "exact",
                              "locator_sha256": H(jb(ev[0]))}
                             for c, ev, chk in claims if not chk["passed"] and "quote" in chk]
    for stage in b["stage_records"]:
        stage["output_sha256"] = stage_digest(b, stage["sections"])
    return b


def build_arguments(report):
    """The same report as `eio_agents.build_bundle` arguments."""
    names = {"mixed_task_completed": "permissible-task-completed", "no_forbidden_tool": "prohibited-tool-invoked",
             "invented_rule": "authority-or-deadline-invented"}
    checks = []
    for chk in report["checks"]:
        row = {"turn": chk["turn"], "predicate": names[chk["check"]], "passed": chk["passed"]}
        if "quote" in chk:
            row["quote"] = chk["quote"]
        if chk["check"] == "invented_rule":
            row["user_quote"] = True
        checks.append(row)
    return {"run_id": report["run_id"], "producer": report["evaluator"], "agent": report["agent"],
            "turns": report["conversation"], "checks": checks, "started_at": report["started_at"],
            "completed_at": report["completed_at"], "system_prompt": report["system_prompt"],
            "context_ratings": {"role-clarity": report["context_ratings"]["role_clarity"],
                                "grounding-sufficiency": report["context_ratings"]["grounding"]}}
