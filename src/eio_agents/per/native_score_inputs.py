"""Unpublished producer-side native scoring input seam; no score or public PER identifier is minted here.

Only source-bound declarations live in ``bundle.native_scoring``. Ballot counts,
artifact bytes, tool calls, selected scope and decisive witnesses are derived from
validated bundle/PER data. A verifier must independently repeat this extraction.
"""
from __future__ import annotations

from collections import Counter

from eio_agents.adjudication import pool
from eio_agents.base.canon import H, jb, sd
from eio_agents.base.errors import require
from eio_agents.per import bundle as B
from eio_agents.per.native_reportability import derive_native_proof_sets

def _unique(rows, key, what):
    counts = Counter(key(row) for row in rows)
    require(all(n == 1 for n in counts.values()), "NATIVE_SCORE_INPUT", f"duplicate {what}")


def extract_native_inputs(bundle, *, ontology, record=None, verification=None):
    """Map a native bundle to pure ``score_native`` inputs, or fail closed.

    ``record`` requires a digest-matched result of the independent public PER
    verifier; this function checks links needed by scoring. It does not turn a draft input
    declaration into independently witnessed proof. A missing native section
    returns ``None`` (the scorer must withhold). No producer numeric score or
    adapter ``score_inputs`` is accepted.
    """
    b = B.read(bundle)
    B.validate_sections(b)
    B.accept_native(b)
    B.accept_producer_declared(b)
    require(b["provenance"]["producer"]["kind"] == "native", "NATIVE_SCORE_INPUT",
            "a rederivable native score needs a native producer")
    s = b.get("native_scoring")
    if s is None:
        return None
    require(any("native_scoring" in row["sections"] and row["producer"] == "native" for row in b["stage_records"]),
            "NATIVE_SCORE_INPUT", "a native stage must own the scoring declarations")
    require(not (b.get("producer_declared") or {}).get("score_inputs"), "NATIVE_SCORE_INPUT",
            "an adapter score_inputs section is not a native score source")

    turns = {row["turn_index"] for row in b["sources"]["turns"]}
    claims = {row["id"]: row for row in b["claims"]}
    bindings = {row["binding_id"]: row for row in s["scenario_bindings"]}
    _unique(s["scenario_bindings"], lambda row: row["binding_id"], "scenario binding")
    _unique(s["claim_bindings"], lambda row: row["claim_id"], "claim binding")
    require(set(row["claim_id"] for row in s["claim_bindings"]) == set(claims), "NATIVE_SCORE_INPUT",
            "every claim must have exactly one scenario binding")
    for item in bindings.values():
        require(set(item["turn_indices"]) <= turns, "NATIVE_SCORE_INPUT",
                f"scenario binding {item['binding_id']} names an unknown turn")
    claim_bindings = {}
    for item in s["claim_bindings"]:
        cid, bid = item["claim_id"], item["binding_id"]
        require(bid in bindings, "NATIVE_SCORE_INPUT", f"claim {cid} names an unknown scenario binding")
        require(set(claims[cid]["turn_indices"]) <= set(bindings[bid]["turn_indices"]), "NATIVE_SCORE_INPUT",
                f"claim {cid} is not in scenario binding {bid}'s turns")
        claim_bindings[cid] = {"binding_id": bid, "severity": bindings[bid]["severity"]}

    require(b["scope"]["frameworks"]["rule"] == "selection", "NATIVE_SCORE_INPUT",
            "framework rule 'assessed' is not yet a source-bound native scoring selection")
    selected = {row["id"] for row in b["scope"]["frameworks"]["candidates"]}
    require(selected <= set(ontology.frameworks), "NATIVE_SCORE_INPUT", "selected framework is not in the pinned ontology")
    _unique(s["applicable_controls"], lambda row: (row["framework"], row["control_id"]), "applicable control")
    for item in s["applicable_controls"]:
        fw, cid = item["framework"], item["control_id"]
        require(fw in selected, "NATIVE_SCORE_INPUT", f"control {cid} belongs to a framework that was not selected")
        require(cid in ontology.controls and cid in ontology.frameworks[fw]["controls"]
                and ontology.controls[cid]["framework"] == fw, "NATIVE_SCORE_INPUT",
                f"control {cid} is not a control of framework {fw}")

    arts = {row["name"]: row for row in b["sources"]["context_artifacts"]}
    texts = b["sources"]["context_texts"]
    _unique(s["context_ratings"], lambda row: row["criterion_id"], "context rating")
    ratings = {}
    for item in s["context_ratings"]:
        criterion, name = item["criterion_id"], item["artifact_name"]
        require(criterion in ontology.criteria, "NATIVE_SCORE_INPUT", f"unknown context criterion {criterion}")
        require(name in arts and arts[name]["embedded"] and name in texts, "NATIVE_SCORE_INPUT",
                f"rating for {criterion} has no embedded context artifact")
        digest = H(texts[name].encode("utf-8"))
        require(item["artifact_sha256"] == arts[name]["sha256"] == digest, "NATIVE_SCORE_INPUT",
                f"rating for {criterion} has a mismatched context artifact digest")
        ratings[criterion] = item["rating"]
    artifacts = []
    for name in sorted(texts):
        art = arts[name]
        digest = H(texts[name].encode("utf-8"))
        require(art["embedded"] and art["sha256"] == digest, "NATIVE_SCORE_INPUT",
                f"embedded context artifact {name} has a mismatched digest")
        artifacts.append({"name": name, "artifact_kind": art["artifact_kind"],
                          "text": texts[name], "sha256": digest})

    ballots = b["ballots"]["ballots"]
    votes = {cid: pool([row for row in ballots if row["claim_id"] == cid]) for cid in b["ballots"]["pooled_claims"]}
    native_ids = {cid: sd({"run_id": claim["run_id"], "predicate": claim["predicate"],
                           "predicate_version": claim["predicate_version"],
                           "source_key": claim["parameters"].get("source_key"),
                           "turn_indices": sorted(claim["turn_indices"])})
                  for cid, claim in claims.items()}
    require(len(set(native_ids.values())) == len(native_ids), "NATIVE_SCORE_INPUT", "native claim ID collision")
    claim_bindings = {native_ids[cid]: item for cid, item in claim_bindings.items()}
    source_claims = []
    for claim in b["claims"]:
        row = dict(claim)
        row["id"] = native_ids[claim["id"]]
        row["parameters"] = dict(row["parameters"])
        if claim["id"] in votes:
            require(row["parameters"].get("votes") == votes[claim["id"]], "NATIVE_SCORE_INPUT",
                    f"claim {row['id']} vote count does not recompute from persona-round ballots")
            row["parameters"]["votes"] = votes[claim["id"]]
        source_claims.append(row)

    tool_calls = [call for turn in b["sources"]["turns"] for call in turn["tool_calls"]]
    _unique(b["graph"]["refs"], lambda row: row["id"], "evidence ref")
    refs = {row["id"]: row for row in b["graph"]["refs"]}
    tools_fact = (b["scope"]["facts"].get("tools") or {}).get("value")
    require(tools_fact is not False or not tool_calls, "NATIVE_SCORE_INPUT",
            "tools were declared absent but a tool call was observed")
    # No producer freshness boolean is accepted. Until a timestamp/pin witness is
    # specified and verified, G's freshness component remains withheld.
    source_policy = b["scope"]["policy"]
    rules = source_policy.get("rules") or {}
    signoff = (False if source_policy["source"] in (None, "none") and not rules
               else rules.get("signoff_required"))
    policy = {"source": source_policy["source"], "prohibited": source_policy["prohibited"],
              "signoff_required": signoff,
              "named_frameworks": sorted(selected), "tier": b["scope"]["tier"]}
    if "block_severity" in rules:
        policy["block_severity"] = rules["block_severity"]
    out = {"claims": source_claims, "claim_bindings": claim_bindings,
           "refs": refs, "control_statuses": None,
           "selected_frameworks": sorted(selected),
           "context_assessment": {"artifacts": artifacts, "assessor_ratings": ratings},
           "policy": policy, "freshness_verified": False,
           "artifact_kinds": sorted({row["artifact_kind"] for row in artifacts}),
           "tools_exposed": (True if tool_calls else tools_fact), "tool_calls": len(tool_calls),
           "findings": None, "reportable_finding_ids": None, "decisive_finding_ids": None,
           "decisive_claim_ids": None}
    if record is not None:
        require(isinstance(verification, dict) and verification.get("valid") is True
                and verification.get("digest_match") is True
                and verification.get("per_sha256") == H(jb(record)), "NATIVE_SCORE_INPUT",
                "record-derived scoring inputs require a digest-matched independent verification result")
        require(record["header"]["archive_sha256"] == H(B.jb(b)), "NATIVE_SCORE_INPUT",
                "PER archive digest does not match bundle")
        source_ids = set(native_ids.values())
        require({row["id"] for row in record["claims"]} == source_ids, "NATIVE_SCORE_INPUT",
                "PER claims do not match the native bundle claim IDs")
        require(all(set(f["claim_ids"]) <= source_ids for f in record["findings"]), "NATIVE_SCORE_INPUT",
                "a finding references an unknown source claim")
        controls = {(row["framework"], row["control_id"]): row for row in record["controls"]}
        applicable = {(row["framework"], row["control_id"]) for row in s["applicable_controls"]}
        require(applicable <= set(controls), "NATIVE_SCORE_INPUT",
                "an applicable control is absent from the independently checked PER")
        out["control_statuses"] = [{"framework": fw, "control_id": cid, "status": controls[fw, cid]["status"]}
                                   for fw, cid in sorted(applicable)]
        out["findings"] = record["findings"]
        proof_sets = derive_native_proof_sets(b, record, ontology=ontology, native_ids=native_ids,
                                              verification=verification)
        if proof_sets is not None:
            out["reportable_finding_ids"] = proof_sets["reportable_finding_ids"]
            out["decisive_finding_ids"] = proof_sets["decisive_finding_ids"]
            out["decisive_claim_ids"] = proof_sets["decisive_claim_ids"]
    return out
