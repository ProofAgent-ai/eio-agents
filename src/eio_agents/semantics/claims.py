"""Claims (03 §7.6): the claim builder (id, assembly, provenance) and the structural checks (duplicate ids, MAP-13).

A producer decides a claim (predicate, turns, state, decider, cited refs, parameters); `make_claim` assembles the claim
object around that decision. The split plan §3.10 row 8 keeps the decision recipes with the producer (for ProofAgent
archives, the adapter's recipes) and the assembly here. The claim id keeps the rc1 source-key slot (`ids.claim_id_slot`).
"""
from eio_agents.base.errors import require
from eio_agents.semantics import SCORED, ids


def make_claim(eio, *, run_id, predicate, turn_indices, state, parameters, evidence, decided_by, resolver, plan_hash,
               model, seed):
    """The claim object. `resolver` is the MAP-20 natural resolver (`resolvers.natural_resolver`) or None; `model` is
    recorded for a semantic claim, `seed` when it is an integer."""
    pd = eio.pred.get(predicate)
    require(pd is not None, "UNKNOWN_PREDICATE", predicate)
    pv = pd["version"]
    c = {"id": ids.claim_id(run_id, predicate, pv, ids.claim_id_slot(parameters), turn_indices), "run_id": run_id,
         "turn_indices": turn_indices, "predicate": predicate, "predicate_version": pv, "state": state,
         "parameters": parameters, "evidence": list(dict.fromkeys(evidence)), "decided_by": decided_by}
    if resolver:
        c["resolver"] = resolver
    if pd.get("risk"):
        c["risk"] = pd["risk"]
    mod, mver = eio.mod_of_pred[predicate]
    prov = {"module": mod, "module_version": mver, "module_hash": eio.modules[mod], "plan_hash": plan_hash}
    if decided_by == "semantic":
        prov["model"] = model
    if isinstance(seed, int):
        prov["seed"] = seed
    c["provenance"] = prov
    return c


def check_claims(claims, refs):
    """Unique claim ids, and MAP-13: a scored claim cites evidence; an APPLICABLE_FAIL cites a ref that can prove agent
    behaviour."""
    require(len({c["id"] for c in claims}) == len(claims), "DUPLICATE_CLAIM_ID")
    for c in claims:
        if c["state"] in SCORED:
            require(c["evidence"], "INVARIANT", f"scored claim without evidence {c['id']}")
        if c["state"] == "APPLICABLE_FAIL":
            require(any(refs[r]["can_prove_agent_behaviour"] for r in c["evidence"]), "INVARIANT", f"FAIL without agent ref {c['id']}")
