"""Neutral `semantics` and resolver rules against a native producer record."""
from pathlib import Path

import pytest

from eio_agents.base.errors import ConversionError
from eio_agents.per import privacy
from eio_agents.resolvers import RESOLVER_READS
from eio_agents.semantics import coverage, release, scope, why
from eio_agents.validation.checker import READS

DATA = Path(__file__).parent / "data"
NATIVE = DATA / "native/v0_6/native.bundle.json"


def _native():
    import eio_agents
    return eio_agents.convert(NATIVE.read_bytes())


def _explanations(node):
    if isinstance(node, dict):
        if isinstance(node.get("explanation"), dict):
            yield node["explanation"]
        for v in node.values():
            yield from _explanations(v)
    elif isinstance(node, list):
        for v in node:
            yield from _explanations(v)


def _refs(rec):
    R = rec["evidence"]["refs"]
    return {r["id"]: r for r in R}, {r["id"]: i for i, r in enumerate(R)}


def test_every_native_summary_renders_from_its_template(eio):
    rec = _native()
    ex = list(_explanations(rec))
    assert len(ex) > 10
    for e in ex:
        # a stored summary renders its params with the display rule (a fingerprint as its 19-character form; decision #31)
        assert why.render(eio, e["template_id"], privacy.display(e["params"])) == e["summary"], e["template_id"]


def test_render_fails_closed(eio):
    with pytest.raises(ConversionError, match="UNKNOWN_TEMPLATE"):
        why.render(eio, "eio.why.none@1", {})
    with pytest.raises(ConversionError, match="TEMPLATE_PARAMS"):
        why.render(eio, "eio.why.reliability.not_retested@1", {})
    assert why.fmt_score(82.25) == "82.3" and why.fmt_decimal(0.5) == "0.5" and why.fmt_decimal(1) == "1.0"
    assert why.fmt_turn_list([1, 2, 3, 4, 5, 6, 7]) == "turns 1, 2, 3, 4, 5 and 2 more"


def test_coverage_recomputes_the_native_coverage_block(eio):
    """The native producer's recorded capability causes are injected."""
    rec = _native()
    R, order = _refs(rec)
    cov = rec["coverage"]
    causes = {o["predicate"]: o["cause_if_unmet"] for o in cov["obligations"] if o["cause_if_unmet"]}
    causes.update({d["predicate"]: d["cause_if_silent"] for d in cov["dispatch"] if d["cause_if_silent"]})
    sc = rec["scope"]
    tier = (sc["tier"] or {}).get("id")
    facts = {k: v["value"] for k, v in sc["facts"].items()}

    def claim_driven(tid, params, cl, role):
        return why.claim_driven(eio, R, order, tid, params, cl, role)
    byp, obls, block = coverage.coverage_step(eio, rec["claims"], [o["id"] for o in cov["obligations"]], facts,
                                              sc["escalations"], tier, lambda p, cl: causes[p], claim_driven)
    assert block == cov and obls == cov["obligations"]
    assert sum(len(v) for v in byp.values()) == len(rec["claims"])
    assert any(o["met"] is False for o in obls) and any("explanation" in o for o in obls)
    for o in obls:
        assert coverage.eff_impact(eio, o["release_impact_declared"], o["required"], sc["escalations"], tier) == o["release_impact"]


def test_eff_impact_floor_and_escalation(eio):
    esc = [{"when": {}, "promote": {"WARN": "CONTRIBUTING_BLOCK"}}]
    assert coverage.eff_impact(eio, "WARN", True, esc, None) == "CONTRIBUTING_BLOCK"
    assert coverage.eff_impact(eio, "WARN", False, esc, None) == "WARN"          # not required: never raised
    high = eio.tiers["eio.tier.high"]["obligation_floor"]
    assert coverage.eff_impact(eio, "NONE", None, [], "eio.tier.high") == high


def test_basis_cited_first_and_owning(eio):
    rec = _native()
    R, order = _refs(rec)
    C = {c["id"]: c for c in rec["claims"]}
    rr = rec["release_recommendation"]
    assert rr["explanation"]["basis"] == why.basis(rec["claims"])
    assert why.basis([]) == why.ZB
    drivers = [C[d["claim_id"]] for d in rr["explanation"]["drivers"]]
    assert rr["explanation"]["evidence_refs"] == why.cited_first(eio, R, order, [r for c in drivers for r in c["evidence"]], drivers)[:12]
    claim_finding = {x: f["finding_id"] for f in rec["findings"] for x in f["claim_ids"]}
    finding_order = {f["finding_id"]: i for i, f in enumerate(rec["findings"])}
    for e in rr["contributing"] + rr["decisive"]:
        if e["kind"] in ("gate", "cap", "metric_floor"):
            assert e["finding_ids"] == release.owning(claim_finding, finding_order, e["claim_ids"])


def test_oversight_gate_vectors(eio):
    g = [g for g in eio.gates if g["id"] == "eio.gate.human-oversight-declared"][0]
    vecs = [v for v in g["test_vectors"] if "record" not in v]
    assert len(vecs) >= 5
    for v in vecs:
        f = v["facts"]
        assert release.oversight_gate(f["tier"], f["consequential_actions"], f["human_oversight"])[0] == v["met"], v


def test_domains_declared():
    doms = [{"id": "eio.domain.a", "source": "profile"}, {"id": "eio.domain.b", "source": "alias"},
            {"id": "eio.domain.c", "source": "import"}, {"id": "eio.domain.generic-agent", "source": "default"}]
    assert scope.domains_declared(doms) == ["eio.domain.a", "eio.domain.b"]


def test_resolver_reads(eio):
    assert set(RESOLVER_READS) <= set(eio.resolver_kind)
    assert all(kinds <= set(eio.kind) for kinds in RESOLVER_READS.values())
    assert RESOLVER_READS == READS                      # the verifier's independent copy agrees
