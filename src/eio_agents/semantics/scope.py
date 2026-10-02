"""Scope rules (03 §7.4; eio.profile.domain-resolution, eio.profile.coverage-evaluation): qualify a bundle's declared scope.

`qualify` reads only the bundle `scope` section (C0): the producer's domain candidates and domain tokens, the tier,
autonomy and region, the declared fact values and the policy object. How a producer reads its own intake (a
ProofAgent governance profile, say) into those declarations is the producer's (adapter's) part (split plan §3.10 row 5).
The domain-token normalisation (`norm_token`) is defined by `eio_agents.ontology`.
"""
from eio_agents.base.errors import require
from eio_agents.ontology import norm_token

GATE_FACTS = ("consequential_actions", "human_oversight")   # the gate facts, always in scope (PROD-15)
# the scope caveat catalogue (03 §7.4, the closed per.caveat.* vocabulary): EIO-Agents constants
CAVEATS = {"domain": {"id": "per.caveat.domain.default",
                      "text": "No domain was identified; domain-specific risk is UNTESTED, not absent."},
           "tier": {"id": "per.caveat.tier.unknown",
                    "text": "No tier was declared; the tier is unknown and is never assumed to be minimal."}}


def domains_declared(domains):
    """The ids of the resolved domains that were declared (by the profile or an alias), not reached by import or default."""
    return [d["id"] for d in domains if d["source"] in ("profile", "alias")]


def resolve_domains(eio, candidates, tokens):
    """eio.profile.domain-resolution steps 2-4 over the declared candidates (step 1, `{id, source, matched}`) and the
    declared domain tokens: (2) exact equality of the normalised token with an alias or a domain-id suffix, (3) the
    import closure in resolution order. Returns the resolved rows (empty when nothing resolved)."""
    doms = []

    def add(did, src, matched):
        if did not in [d["id"] for d in doms]:
            doms.append({"id": did, "source": src, "matched": matched})
    for d in candidates:
        require(d["id"] in eio.domains, "BUNDLE_SCOPE", f"unknown domain candidate {d['id']}")
        add(d["id"], d["source"], d["matched"])
    for tok in tokens:
        n = norm_token(tok)
        for did in sorted(eio.domains):
            if n in eio.domains[did]["aliases"] or n == did.split("eio.domain.", 1)[1]:
                add(did, "alias", tok)
    i = 0
    while i < len(doms):
        for imp in eio.domains[doms[i]["id"]]["imports"]:
            add(imp, "import", doms[i]["id"])
        i += 1
    return doms


def escalations(eio, tier, autonomy, fact_values):
    """The listed impact-escalation rules whose `when` holds (the tier floor is applied in `coverage.eff_impact`)."""
    out = []
    for r in eio.escalation:
        ok = True
        for k, val in r["when"].items():
            if k == "tier":
                ok &= (tier == val)
            elif k == "autonomy_level":
                ok &= (autonomy == val)
            else:
                ok &= (fact_values.get(k) is val)
        if ok:
            out.append({"when": r["when"], "promote": r["promote"]})
    return out


def qualify(eio, declared, lim):
    """The qualified scope of a bundle `scope` section. `lim(limitation_id, path=None, **params)` raises a limitation.
    Returns a dict with the resolved `domains` rows, the `caveats`, the in-scope obligation ids, the in-scope `facts`,
    their values `fact_values` and the `escalations`."""
    doms = resolve_domains(eio, declared["domain_candidates"], declared["domain_tokens"])
    caveats = []
    if not doms:
        doms = [{"id": "eio.domain.generic-agent", "source": "default", "matched": None}]
        caveats.append(dict(CAVEATS["domain"]))
        lim("per.lim.domain.default")
    tier = declared["tier"]
    if tier is None:
        caveats.append(dict(CAVEATS["tier"]))
    ids_ = [d["id"] for d in doms]
    in_scope = sorted(oid for oid, o in eio.obligation.items() if o["domain"] in ids_)
    keys = sorted({k for oid in in_scope for k in (eio.obligation[oid].get("required_when") or {})} | set(GATE_FACTS))
    facts = {}
    for k in keys:
        require(k in eio.facts, "FACTS_DECLARED", k)
        require(k in declared["facts"], "BUNDLE_SCOPE", f"fact {k} is not declared (declare it with value null)")
        facts[k] = dict(declared["facts"][k])
    if any(f["value"] is None for f in facts.values()):
        lim("per.lim.facts.not_declared", n=sum(1 for f in facts.values() if f["value"] is None))
    fv = {k: v["value"] for k, v in facts.items()}
    return {"domains": doms, "caveats": caveats, "obligations": in_scope, "facts": facts, "fact_values": fv,
            "escalations": escalations(eio, tier, declared["autonomy"], fv)}
