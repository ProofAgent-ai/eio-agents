"""`project(bundle)`: the PER projection of an evaluation bundle (contract §6.2), exported as `eio_agents.convert`.

In order: read the bundle; validate its sections (step 1), including the names its sources are resolved by (each turn
index, artifact name and context text names one item); apply the producer-declared acceptance rule (split plan §4.4) and
the native-producer rule (a native bundle is its own archive); check the stage-record digests (step 4); recompute ids,
refs, computed statements, episodes and pooled votes from the bundle's own sources (step 2: a ref that no recipe rebuilds
is accepted only as a non-witnessing ref that locates no text); evaluate the views from the bundle's claims, trials, scope
and declared inputs (step 3): scope qualification, context refs and gaps, coverage, findings, controls, scores, gates,
release and reliability; project the record, normalise it and check it is canonicalisable (steps 6-7). The context refs
the projector derives go into a strict store: a declared ref with the id of a derived ref must be that ref.

Everything here reads bundle objects only. The rc1 parameters of a claim (`legacy_check`, `mapping_relation`, `trap`,
`legacy_decided_by`, `state_source`) travel into the PER untouched as opaque parameters (rc1 requires them; renamed at
L5a); the bundle-only `parameters.fidelity` is read here and not written to an rc1 record. Two reads of rc1 parameters
remain, both on the split plan §6.2 L2 exit allowlist or its review addition: the rc1 claim sort key (`rc1_claim_key`
below) and the check that an adapter claim's `mapping_relation` equals its declared fidelity. The claim-id slot is read in
`semantics.ids`. The proof rule reads only the declared fidelity (`semantics.proof`).

Step 7 (contract §6.2): the record is validated before it is returned (`per.conformance.check_record`, `PER_INVALID`).

A bundle without a score-input section projects `scores` as null (rc1-invalid until the rc2-draft relaxation, L5a).
"""
import copy
from collections import Counter

import eio_agents.compliance as compliance
import eio_agents.reliability as reliability
from eio_agents.base.canon import H, jb, normalize
from eio_agents.base.errors import require
from eio_agents.evidence import context_refs as ev_context
from eio_agents.evidence import contract as ev_contract
from eio_agents.evidence.refs import RefStore
from eio_agents.ontology import load
from eio_agents.per import bundle as B
from eio_agents.per import privacy
from eio_agents.per.capsule import CAPSULE_FIELDS
from eio_agents.per.conformance import check_record
from eio_agents.per.context import embedded
from eio_agents.per.evidence import KIND_ORDER, cited_ref_ids, order_refs, ref_key
from eio_agents.per.header import archive_identity, header
from eio_agents.per.limitations import limitation, limitation_row, load_catalogue
from eio_agents.resolvers import natural_resolver
from eio_agents.scoring import ScoreView
from eio_agents.semantics import SCORED
from eio_agents.semantics import coverage as sem_coverage
from eio_agents.semantics import findings as sem_findings
from eio_agents.semantics import ids
from eio_agents.semantics import proof as sem_proof
from eio_agents.semantics import release as sem_release
from eio_agents.semantics import scope as sem_scope
from eio_agents.semantics import why as sem_why
from eio_agents.semantics.claims import check_claims

from eio_agents.per import PER_VERSION  # noqa: E402  (defined before the package imports this module)
CONVERTER_SUPPLIED = ("evidence_graph_schema", "predicate_versions")   # capsule fields the projector itself supplies
COMPLETENESS_LIMITATIONS = (("tool_outputs", "per.lim.tool_output.not_captured"),
                            ("retrieval_text", "per.lim.retrieval_text.not_captured"),
                            ("sentinel_locations", "per.lim.sentinel_locations.not_captured"),
                            ("code_check_offsets", "per.lim.code_check_offsets.not_captured"),
                            ("reliability_pass_transcripts", "per.lim.reliability_pass_transcripts.not_captured"))


def rc1_claim_key(c):
    """The rc1 claim order: (first turn, predicate, rc1 source key, id); `(turn_indices, predicate, id)` from L5a. A native
    claim has no source key (it sorts as the empty key, as the verifier's twin does)."""
    return (min(c["turn_indices"]), c["predicate"], c["parameters"].get("legacy_check") or "", c["id"])


class ProjectionRefStore(RefStore):
    """The refs of one projection: the bundle's refs, then the context refs the projector derives. A derived ref whose id
    is stored already must be that same ref, so a producer-declared ref never shadows a derived one (review H-1:
    `BUNDLE_RECOMPUTE`). The shared `evidence.refs.RefStore` keeps its first-stored rule: the adapter's A-8 anchor merge
    (`StrongestAnchorRefStore`) relies on it."""

    def __init__(self, refs=None):
        seen = {}
        for r in refs or []:                        # the one collision EIO-Agents does not resolve yet (`_no_collision`)
            _no_collision(seen.setdefault(r["id"], r), r)
        super().__init__(refs)

    def put(self, r):
        rid = r["id"]
        o = self.refs.get(rid)
        if o is not None:
            _no_collision(o, r)
            require(o == r, "BUNDLE_RECOMPUTE", f"ref {rid}: the bundle declares a ref with the id of a derived ref and other content")
        return super().put(r)


def _no_collision(a, b):
    """Two POLICY_SPAN refs with one id and different artifacts hold the same text at the same offsets in two artifacts.
    03 §6 gives every colliding ref the id over x = source_ref|text; EIO-Agents does not implement that rule yet (L3
    deviation, until S5), so the case fails closed with its name (L2 exit D-35, F-9)."""
    require(a is b or not (a["kind"] == b["kind"] == "POLICY_SPAN" and a["source_ref"] != b["source_ref"]), "BUNDLE_RECOMPUTE",
            f"ref {a['id']}: identical policy text in two artifacts ({a['source_ref']!r} and {b['source_ref']!r}, the same "
            "offsets): 03 §6 gives every colliding POLICY_SPAN the id over x = source_ref|text, which EIO-Agents does not "
            "implement yet (L2 exit D-35, F-9; until S5)")


def capsule_block(declared):
    """The PER capsule (eio.profile.required-capsule-fields) from the producer's declared capsule fields."""
    present = set(declared["present"]) | set(CONVERTER_SUPPLIED)
    missing = [f for f in CAPSULE_FIELDS if f not in present]
    cap = {"reproducible": not missing, "reproducible_declared": declared["reproducible_declared"], "missing_fields": missing,
           "caveats": list(declared["caveats"])}
    if declared["lock_digest"]:
        cap["lock_digest"] = declared["lock_digest"]
    return cap


def require_metric_floor_for_scoring(eio, score_inputs):
    """A neutral unscored run needs no producer floor; a scored run cannot invent one."""
    require(score_inputs is None or eio.critical_metric_floor is not None, "SCORING_PROFILE",
            "scored projection requires a declared, validated critical-metric floor; the neutral core has none")


def strict_native_proof_required(eio, producer_kind):
    """Select the pinned proof rule independently of PER schema/version."""
    return (producer_kind == "native" and
            not eio.profiles["eio.profile.proof-status"]["native_claim_proves"])


class Projection:
    """The state of one projection: the loaded release, the bundle's objects and the views derived from them."""

    ZB = sem_why.ZB
    BR = reliability.BR
    KIND_ORDER = KIND_ORDER

    def __init__(self, eio, bundle, catalogue, guard=None, *, strict_native_proof=False):
        self.eio, self.bundle, self.catalogue = eio, bundle, catalogue
        self.strict_native_proof = strict_native_proof
        self.native_proof_citations = {}
        self.identity = archive_identity(bundle)                  # before any step changes the bundle objects
        # the withheld content (L3 fix round 2: the record-wide rule)
        self.guard = guard if guard is not None else B.Withheld(bundle["sources"], eio)
        self.lims = []
        h = bundle["header"]
        self.run_id, self.plan_hash = h["run_id"], h["plan_hash"]
        self.decl = bundle.get("producer_declared") or {}
        src = bundle["sources"]
        self.context_artifacts = src["context_artifacts"]
        self.ctx_embedded = embedded(self.context_artifacts)
        self.ctx_text = src["context_texts"]
        for a in self.ctx_embedded:
            require(a["name"] in self.ctx_text and H(self.ctx_text[a["name"]].encode("utf-8")) == a["sha256"], "BUNDLE_RECOMPUTE",
                    f"context artifact {a['name']}: embedded text missing or its digest does not recompute")
        # the embedded artifacts as PROD-43 reads them for the context refs derived here: the most restrictive declaration of
        # their content, the same bytes or the same normalized text (L2 exit D-32; L3 fix round 1, issue 3); the record lists
        # them as declared
        conf = ev_context.confidential_digests(self.context_artifacts, self.ctx_text)
        self.ctx_searched = [ev_context.effective(a, conf, self.ctx_text[a["name"]]) for a in self.ctx_embedded]
        self.store = ProjectionRefStore(bundle["graph"]["refs"])
        self.refs = self.store.refs
        episodes = [set(e) for e in bundle["graph"]["episodes"]]
        self.episode_turns = lambda turns: set().union(*[e for e in episodes if e & set(turns)]) if episodes else set()
        # claims: the declared fidelity is bundle-only (rc1 records carry the mapping relation instead)
        self.claims = bundle["claims"]
        self._fidelity = {}
        for c in self.claims:
            fid = c["parameters"].pop("fidelity")
            # an rc1 adapter claim carries its fidelity twice (the rc1 `mapping_relation`, renamed `fidelity` at L5a):
            # the two must agree, or proof status and the findings' fidelity would rest on different values (review H3)
            rc1 = c["parameters"].get("mapping_relation")
            require(rc1 is None or rc1 == fid, "BUNDLE_RECOMPUTE",
                    f"claim {c['id']}: parameters.fidelity {fid} != the rc1 mapping_relation {rc1}")
            self._fidelity[c["id"]] = fid
        sc = self.decl.get("scenarios")
        self._scenario = {t["turn_index"]: t["label"] for t in sc["turns"]} if sc else {}
        self._scenario_severity = dict(sc["severity"]) if sc else {}
        cl = self.decl.get("context_links")
        self._ctx_key = dict(cl["claims"]) if cl else {}
        self._ctx_rows = cl["rows"] if cl else {}
        self._ctx_cache = {}
        cap = self.decl.get("capabilities")
        self.capabilities = ({"reachable_predicates": set(cap["reachable_predicates"]),
                              "not_implemented_predicates": set(cap["not_implemented_predicates"])} if cap else None)
        self.trials = bundle["trials"]
        self._trial = reliability.trial_index(self.trials)
        self.trial_passes = int(self.trials["passes"]) if self.trials else 0

    # ---------------------------------------------------------------- helpers read by the views
    def lim(self, lid, path=None, **params):
        # the parameters sealed before the catalogue renders them (the closed field table, decision #31)
        self.lims.append(limitation(self.catalogue, lid, path, **privacy.seal_params(self.eio, params)))

    def label_value(self, label):
        return privacy.label_value(self.eio, label)

    def fidelity(self, c):
        return self._fidelity[c["id"]]

    def scenario_of(self, c):
        return self._scenario.get(c["turn_indices"][0])

    def scenario_severity(self, label):
        return self._scenario_severity.get(label)

    def witnessing_anchored(self, rid):
        return self.eio.witnessing_anchored(self.refs[rid])

    def band_of(self, c):
        return reliability.band_of(self._trial.get(c["id"]), self.trial_passes)

    def claim_proven(self, c):
        if self.strict_native_proof:
            return sem_proof.native_claim_proven(c, self.band_of(c)["band"], self.fidelity(c),
                                                 self.native_proof_citations.get(c["id"], []))
        return sem_proof.claim_proven(self.eio, c, self.refs, self.band_of(c)["band"], self.fidelity(c))

    def basis(self, cl):
        return sem_why.basis(cl)

    def cited_first(self, refs, drivers_claims):
        return sem_why.cited_first(self.eio, self.refs, self.REF_ORDER, refs, drivers_claims)

    def explanation(self, tid, params, bas, drivers, refs, ctx=None):
        return sem_why.explanation(self.eio, tid, params, bas, drivers, refs, ctx)

    def claim_driven(self, tid, params, cl, role, ctx=None, bas=None):
        return sem_why.claim_driven(self.eio, self.refs, self.REF_ORDER, tid, params, cl, role, ctx, bas)

    def census(self, pred, cl):
        return sem_coverage.census(self.capabilities, pred, cl)

    # ---------------------------------------------------------------- context refs over declared link rows (§3.10 row 10)
    def ctx_key_of(self, c):
        return self._ctx_key.get(c["id"]) if c["state"] == "APPLICABLE_FAIL" else None

    def ctx_refs_of_key(self, key):
        """The context refs of one declared link key: related_rule for a lexical hit, absent_control for an absence. A row
        marked `strength: incidental` is never cited (04 §4.6 MAP-28 rule 1)."""
        if key in self._ctx_cache:
            return self._ctx_cache[key]
        out = []
        if self.ctx_embedded:
            for row in self._ctx_rows.get(key) or []:
                if row["strength"] == "incidental":
                    continue
                crit, ctl = row["criterion"], row["control"]
                r = ev_context.context_line_ref(self.eio, crit, ctl, self.ctx_searched, self.ctx_text)
                rid = self.store.put(r) if r is not None else None
                rel = "related_rule"
                if rid is None:
                    files = [a["name"] for a in self.ctx_embedded if a["artifact_kind"] in (self.eio.criteria[crit].get("evaluates") or [])]
                    if not files:
                        continue
                    terms = [x for x in self.eio.criteria[crit]["controls"] if x["id"] == ctl][0]["requires_any"]
                    rid = self.store.put(ev_context.ctx_absence_ref(self.eio, files, sum(len(self.ctx_text[f]) for f in files), terms))
                    rel = "absent_control"
                if rid not in [x["ref_id"] for x in out]:
                    out.append({"ref_id": rid, "relation": rel, "via": row["via"]})
        self._ctx_cache[key] = out
        return out

    def ctx_refs_of_claim(self, c):
        k = self.ctx_key_of(c)
        return self.ctx_refs_of_key(k) if k is not None else []

    def ctx_refs_for_criterion(self, criterion):
        return ev_context.context_refs_for_criterion(self.store, self.eio, criterion, self.ctx_searched, self.ctx_text)

    # ---------------------------------------------------------------- steps
    def claims_step(self):
        eio = self.eio
        for c in self.claims:
            require(c["predicate"] in eio.pred, "UNKNOWN_PREDICATE", c["predicate"])
            pd = eio.pred[c["predicate"]]
            mod, mver = eio.mod_of_pred[c["predicate"]]
            require(c["predicate_version"] == pd["version"], "BUNDLE_RECOMPUTE", f"claim {c['id']}: predicate_version")
            p = c["provenance"]
            require((p.get("module"), p.get("module_version"), p.get("module_hash"), p.get("plan_hash"))
                    == (mod, mver, eio.modules[mod], self.plan_hash), "BUNDLE_RECOMPUTE", f"claim {c['id']}: provenance")
            require(c.get("risk") == (pd.get("risk") or None), "BUNDLE_RECOMPUTE", f"claim {c['id']}: risk")
            if "resolver" in c:                                                     # MAP-20
                kinds = [self.refs[r]["kind"] for r in c["evidence"]]
                require(natural_resolver(eio, c["resolver"], c["predicate"], c["decided_by"], kinds) == c["resolver"],
                        "BUNDLE_RECOMPUTE", f"claim {c['id']}: resolver {c['resolver']} is not the claim's natural resolver")
            require(len(set(c["evidence"])) == len(c["evidence"]), "BUNDLE_RECOMPUTE", f"claim {c['id']}: duplicate evidence")
        self.claims.sort(key=rc1_claim_key)
        check_claims(self.claims, self.refs)
        self.C = {c["id"]: c for c in self.claims}
        self.CIDX = {c["id"]: i for i, c in enumerate(self.claims)}
        for c in self.claims:
            if c["state"] in SCORED:
                c["parameters"]["contract_check"] = ev_contract.contract_check(self.eio, c, self.refs, self.episode_turns)
        if self.strict_native_proof:
            rows = (self.bundle.get("native_scoring") or {}).get("proof_citations") or []
            self.native_proof_citations = sem_proof.checked_native_citations(
                self.eio, self.claims, self.refs, rows,
                lambda ref, scope, claim: ev_contract.in_scope(ref, scope, claim, self.episode_turns))

    def scope_step(self):
        d = self.bundle["scope"]
        q = sem_scope.qualify(self.eio, d, self.lim)
        self.tier, self.fact_values, self.escalations, self.in_scope_obligations = d["tier"], q["fact_values"], q["escalations"], q["obligations"]
        self.policy = d["policy"]
        frameworks = compliance.select_frameworks(self.eio, d["frameworks"], d["region"], sem_scope.domains_declared(q["domains"]))
        self.frameworks = frameworks
        self.scope = {"domains": q["domains"], "tier": ({"id": d["tier"], "source": d["tier_source"]} if d["tier"] else None),
                      "autonomy": d["autonomy"], "region": d["region"], "facts": q["facts"], "escalations": q["escalations"],
                      "frameworks": frameworks, "caveats": q["caveats"]}

    def context_gap_step(self):
        """CONTEXT_GAP inputs from the context assessment (C-ctx), and the context refs of failing claims (created before
        the refs are ordered)."""
        self.gaps = []
        ca = self.bundle["context_assessment"]
        names = {a["name"] for a in self.ctx_embedded}
        rules = B.SearchRules(self.eio, self.bundle, self.guard) if (ca or {}).get("gaps") else None
        for g in (ca or {}).get("gaps") or []:
            require(g["criterion"] in self.eio.criteria, "BUNDLE_SCHEMA", f"unknown context criterion {g['criterion']!r:.80}")
            controls = {x["id"]: x for x in self.eio.criteria[g["criterion"]].get("controls") or []}
            require(g["control"] in controls, "BUNDLE_SCHEMA", f"unknown control {g['control']!r:.80} of {g['criterion']}")
            files = g["files_searched"]
            # the embedded files searched recompute (review H-1, R-4): no term occurs in any of them, and the characters
            # searched are theirs (all embedded), or at least theirs (the rest is not embedded); the terms and names are the
            # release's (the control's checklist terms) or the bundle's (L3 fix round 1, issue 1)
            B.check_context_search(f"context gap {g['criterion']}/{g['control']}", files, g["chars_searched"], g["terms"],
                                   self.ctx_text, names, rules, controls[g["control"]]["requires_any"])
            rid = self.store.put(ev_context.ctx_absence_ref(self.eio, files, g["chars_searched"], g["terms"]))
            self.gaps.append({"criterion": g["criterion"], "control": g["control"], "ref": rid, "files": sorted(g["files_searched"]),
                              "chars": g["chars_searched"], "terms": g["terms"]})
        for c in self.claims:
            self.ctx_refs_of_claim(c)

    def views(self):
        eio = self.eio
        self.ref_list, self.REF_ORDER = order_refs(self.refs, self.claims)
        self.BYP, self.obligations, self.coverage = sem_coverage.coverage_step(
            eio, self.claims, self.in_scope_obligations, self.fact_values, self.escalations, self.tier, self.census, self.claim_driven)
        self.findings = sem_findings.findings(self, self.band_of, self.claim_proven, self.gaps)
        self.FID = {f["finding_id"]: f for f in self.findings}
        self.CLAIM2F = {cid: f["finding_id"] for f in self.findings for cid in f["claim_ids"]}
        self.FORDER = {f["finding_id"]: i for i, f in enumerate(self.findings)}
        self.controls = compliance.controls_step(eio, self.frameworks, self.BYP, self.CIDX, self.refs, self.REF_ORDER,
                                                 self.findings, self.census, self.fidelity)
        si = self.decl.get("score_inputs")
        require_metric_floor_for_scoring(eio, si)
        self.S = ScoreView(self, si) if si is not None else None
        if self.S:
            self.S.metrics_step()
            self.S.axes_step()
            self.S.readiness_step()
        self.capsule = capsule_block(self.bundle["provenance"]["capsule"])
        self.capsule_missing = self.capsule["missing_fields"]
        metrics = self.S.metrics if self.S else []
        members = self.S.metric_members if self.S else {}
        # a gate reason names a metric by its label's record value (decision #31; the record rebuilds it from the metric row)
        gate_views = [dict(m, _label=privacy.metric_label_value(self.eio, m["_label"] or m["metric"])) for m in metrics]
        self.gate_results = sem_release.gates(self, gate_views, members)
        self.release = sem_release.release(self, self.gate_results, self.S.M_BY if self.S else {}, members,
                                           self.S.readiness_value if self.S else None, self.S.readiness_driver_ids if self.S else [])
        self.state = self.release["state"]
        if self.S:
            self.S.finish(self.state)
        self.reliability = reliability.reliability_block(eio, self.trials, self.claims, self.findings, self.CLAIM2F,
                                                         self.claim_driven, self.basis)

    def completeness(self):
        """The evidence completeness block. `sentinel_locations` and `code_check_offsets` are rc1 evidence classes of the
        first adapter (neutral names at L5a, §5.3): written when the producer declares them."""
        c = self.bundle["sources"]["completeness"]
        out = {"tool_outputs": c["tool_outputs"], "retrieval_text": c["retrieval_text"]}
        for k in ("sentinel_locations", "code_check_offsets"):
            if k in c:
                out[k] = c[k]
        out.update({"context_artifacts": "CAPTURED" if self.ctx_embedded else "NOT_SUPPLIED",
                    "reliability_pass_transcripts": c["reliability_pass_transcripts"]})
        return out

    def subject(self):
        """The subject: the declared agent, and the AI-BOM over the context artifacts and the agent model."""
        agent = dict(self.bundle["provenance"]["agent"])
        kindmap = {"eio.artifact.system-prompt": "file", "eio.artifact.policy": "file", "eio.artifact.tool-schema": "file",
                   "eio.artifact.agent-manifest": "file", "eio.artifact.knowledge-source": "data"}
        comps = [{"kind": kindmap.get(a["artifact_kind"], "file"), "name": a["name"], "sha256": a["sha256"]} for a in self.context_artifacts]
        if agent["model"]:
            comps.append({"kind": "machine-learning-model", "name": agent["model"], "sha256": None})
        comps.sort(key=lambda c: (c["kind"], c["name"]))
        ch = H(jb(comps)) if any(c["sha256"] for c in comps) else None
        return {"agent": agent, "ai_bom": {"content_hash": ch, "components": comps}}

    def evidence_block(self, ref_ids, completeness):
        """The evidence block: the cited refs in 03 §5.6 rule 1 order. The order is the rule's key, not a position fixed
        when the views started: the scores step derives the context lines of an axis's criteria later (04 §4.6 rule 6),
        and a line that no earlier step derived is placed by the same rule (review R-3)."""
        src = self.bundle["sources"]
        # a citation key inside a producer-declared field (a git `ref` in telemetry, for example) names no ref of the bundle:
        # the rc1 schema allows no such field there, so the record fails its step-7 check with the same code (L2 exit D-30)
        unknown = sorted(x for x in ref_ids if x not in self.refs)
        require(not unknown, "PER_INVALID", f"the record cites {unknown[:3]} under a citation key ('evidence', 'evidence_refs', "
                "'counterevidence', 'ref' or 'ref_id'), and no evidence ref of the bundle has that id")
        rl = sorted((self.refs[x] for x in ref_ids), key=ref_key)
        pointer = dict(src["archive_pointer"])
        pointer["archive_sha256"] = self.archive_sha256          # the record's archive digest (a native bundle's own)
        return {"cited_refs_hash": ids.cited_refs_hash(r["id"] for r in rl), "transcript_sha256": src["transcript_sha256"],
                "archive_pointer": pointer,
                "refs": rl,
                "turns": [{"turn_index": t["turn_index"], "trap": self._scenario.get(t["turn_index"]),
                           "question_sha256": H(t["question"]), "answer_sha256": H(t["answer"]),
                           "tool_calls": [{"name": c["name"], "arguments_sha256": H(jb(c["arguments"]))} for c in t["tool_calls"]],
                           "retrievals": [{"source": x["source"]} for x in t["retrievals"]]}
                          for t in sorted(src["turns"], key=lambda t: t["turn_index"])],
                "counts": {"refs": len(rl), "by_kind": dict(sorted(Counter(r["kind"] for r in rl).items())),
                           "agent_refs": sum(1 for r in rl if r["can_prove_agent_behaviour"]),
                           "witnessing_anchored": sum(1 for r in rl if self.witnessing_anchored(r["id"]))},
                "completeness": completeness}

    def limitations_step(self, provenance, subject, completeness):
        """The core limitation raises of the projection (04 §5.13); the producer's disclosures come with the bundle."""
        L = self.lim
        for fld in ("started_at", "completed_at"):
            if provenance["run"][fld] is None:
                L("per.lim.timestamps.not_captured", f"/provenance/run/{fld}")
        if not self.ctx_embedded:
            L("per.lim.context.artifacts_not_embedded" if self.bundle["context_assessment"] is not None else "per.lim.context.not_supplied")
        for fld in ("agent_id", "version"):
            if subject["agent"][fld] is None:
                L("per.lim.agent.not_captured", f"/subject/agent/{fld}")
        if subject["ai_bom"]["content_hash"] is None:
            L("per.lim.ai_bom.no_digests")
        if self.policy["source"] == "none":
            L("per.lim.policy.none")
        for k, lid in COMPLETENESS_LIMITATIONS:
            if completeness.get(k) == "NOT_CAPTURED":
                L(lid, f"/evidence/completeness/{k}")
        pe = self.bundle["header"]["producer_eio"]
        if pe and pe["ontology_digest"] != self.eio.ontology_digest:
            L("per.lim.ontology.producer_differs", producer_release=pe["release"], producer_digest=pe["ontology_digest"])
        for r in self.refs.values():
            if r["anchor"] == "turn" and r["kind"] == "USER_INPUT":
                L("per.lim.anchor.sentinel_location", ref=r["id"])
        for x in self.bundle["limitations"]:                     # the producer's parameters as a dict (L3 fix round 2)
            self.lims.append(limitation_row(self.catalogue, x["id"], x["path"], privacy.seal_params(self.eio, x["params"])))

    def project(self, *, bridge_native_rc2=False):
        self.claims_step()
        self.scope_step()
        self.context_gap_step()
        self.views()
        completeness = self.completeness()
        provenance = dict(copy.deepcopy(self.bundle["provenance"]["record"]))
        provenance["capsule"] = self.capsule
        subject = self.subject()
        self.limitations_step(provenance, subject, completeness)
        hdr = header(self.eio, self.bundle, PER_VERSION, self.identity)
        self.archive_sha256 = hdr["archive_sha256"]
        rec = {"header": hdr, "provenance": provenance, "subject": subject, "scope": self.scope,
               "evidence": None, "claims": self.claims, "coverage": self.coverage, "findings": self.findings, "controls": self.controls,
               "scores": self.S.block() if self.S else None, "reliability": self.reliability,
               "release_recommendation": self.release, "limitations": None, "telemetry": self.bundle["provenance"]["telemetry"]}
        rec["evidence"] = self.evidence_block(cited_ref_ids({k: v for k, v in rec.items() if k != "evidence"}), completeness)
        carried = {r["id"] for r in rec["evidence"]["refs"]}
        lims = [x for x in self.lims if not (x["field_path"].startswith("/evidence/refs/") and x["field_path"].split("/")[-1] not in carried)]
        lims = list({(x["field_path"], x["limitation_id"]): x for x in lims}.values())
        rec["limitations"] = sorted(lims, key=lambda x: (x["field_path"], x["limitation_id"]))
        rec = normalize(copy.deepcopy(rec))
        # the closed field table (decision #31): producer text as fingerprints, the per-value decisions, the rendered texts
        # that carry a sealed value re-rendered; an unlisted field fails closed
        privacy.seal(self.eio, rec)
        jb(rec)                                                                  # canonicalisable (PROD-9, lone surrogates)
        if not bridge_native_rc2:
            check_record(self.eio, rec, self.bundle["provenance"]["producer"]["kind"] == "native")   # step 7 (review H2)
        # L3 fix round 2, the record-wide rule: no string of the record carries withheld content, outside the exempt fields
        at = B.record_content_problems(rec, self.guard)
        require(not at, "WITHHELD_CONTENT", f"{len(at)} string(s) of the record carry withheld content (a withheld context "
                f"artifact's text, or a tool-call or state value naming a subject); first: {at[0]}" if at else "")
        return rec


def project(bundle, *, ontology=None, bridge_native_rc2=False):
    """Bundle (bytes, JSON text or dict) -> PER dict. `ontology` is the EIO release to project under (default: the
    bundled release, loaded and verified for this call). Fails closed with a typed `ConversionError`."""
    eio = ontology if ontology is not None else load()
    b = B.read(bundle)
    B.validate_sections(b)
    B.check_names(b)
    B.accept_producer_declared(b)
    B.accept_native(b)
    B.check_vocabulary(eio, b)
    B.check_stage_digests(eio, b)
    guard = B.Withheld(b["sources"], eio)
    # the bundle's side of the record-wide rule, read before any step changes the bundle objects; raised after the
    # projection, so that a name or search input fails with its own code first (L3 fix round 2)
    leaks = B.bundle_content_problems(b, guard)
    shapes = B.shape_problems(b, eio)              # L3 fix round 4: the identifying-shape backstop, raised likewise
    producer = privacy.producer_texts(b, eio)        # decision #31: read before any step changes the bundle objects
    require(not bridge_native_rc2 or b["provenance"]["producer"]["kind"] in ("native", "adapter"), "BUNDLE_INPUT",
            "the neutral bridge takes a native or adapter producer")
    # Historical 0.4 records retain their pinned rule. The reviewed new S1b
    # release flips this profile flag in its coordinated ontology reissue. The
    # rule is independent of the PER schema version (rc2, rc3, or later).
    strict_native_proof = strict_native_proof_required(eio, b["provenance"]["producer"]["kind"])
    P = Projection(eio, b, load_catalogue(), guard, strict_native_proof=strict_native_proof)
    B.recompute(eio, b, P.claims, P.refs, guard)
    rec = P.project(bridge_native_rc2=bridge_native_rc2)
    require(not leaks, "WITHHELD_CONTENT", f"{len(leaks)} string(s) of the bundle that a record carries in clear carry withheld "
            "content (a withheld context artifact's text, or a tool-call or state value naming a subject); first: "
            f"{leaks[0] if leaks else ''} (L3 fix round 2)")
    require(not shapes, "WITHHELD_CONTENT", f"{len(shapes)} string(s) of the bundle that a record carries in clear hold an "
            "identifying-shaped token (a producer's own text never states an identifying value: a number of four digits "
            "or more, digit groups, a word of letters and digits, a long hex or base64 token, an e-mail address, a URL "
            f"with credentials, a secret key); first: {shapes[0] if shapes else ''} (L3 fix round 4)")
    # decision #31, last: every string of the record in the closed field table and of its class, and no producer text of
    # the bundle in clear (after the schema and the round 2-4 rules, which keep their codes)
    if not bridge_native_rc2:
        privacy.check(eio, rec, producer)
    return rec
