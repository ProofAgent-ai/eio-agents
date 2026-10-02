"""Scoring (03 §7.10): metric views, axis objects, readiness, caps, cap reasons and drivers, over the bundle's declared
score-input section (split plan §3.10 row 15; §4.3), and the scoring machinery of L4: the readiness-index engine
(`engine`, no numeric defaults), the profile registry and the attested-profile mechanism (`profiles`), and the draft
signature of the EIO-Agents reference scoring (`reference`).

The score-input section lives in the adapter-only producer-declared section (`producer_declared.score_inputs`, §4.4). It
is generic (carry note 4): axes are keyed by EIO axis id, each `{axis, value, components [{id, value}]}`, and metrics by
EIO metric id. The scoring profile is declared with its document (`profile`): an attested document (today `harness-2.x`)
travels in the section and its sha256 is recomputed (`profiles.resolve_profile`); a rederivable one is loaded from the
registry. Every profile number comes from the document: the engine combines the declared axis values with its epsilon,
axis weights and readiness ceiling into the raw and capped readiness and the completeness rule; the band ramp, the
method, the stated axis weights and the published metric set are the document's. The margin and interval are declared
inputs of the attested profile. This module also applies the cap rules (W1, "blocked only with a cap reason"), the
evidence-fraction and measurement-status rules, and builds the drivers and explanations from the claims.

    score_inputs = {
      "profile": {"id", "version", "verifiability", "sha256", "document"}, "attribution": bool,
      "metrics": [{"id", "legacy_metric", "label", "value", "confidence", "members": [claim id], "pre_cap", "via_cap",
                   "contributions": [[claim id, points]] | null, "not_evaluated_reason"}],
      "axes": [{"axis", "value", "components": [{"id", "value"}], "explanation": {"template_id", "params"},
                "context_criteria": [criterion id]}],
      "readiness": {"blocked", "margin", "interval", "cap_claims": [claim id], "triggers": [str]}}

**The published metric set** (split plan §3.11) is declared by the scoring profile (`published_metrics` of its
document), never derived from a legacy key. The producer declares metric inputs for members of that set, in its order; a
metric outside the set fails closed; a metric of the set the producer does not declare is omitted by rule (the harness-2.x
rule for a metric with no value and no member claim); a declared metric with no member claims and no value is
NOT_EVALUATED. The attested `harness-2.x` profile publishes the six metrics that carry a harness metric key (its document
is assembled by the adapter); the draft reference profile publishes every `eio.metric.*` of the loaded release. Nothing
here filters on `legacy_key`. **The G component ids** are the document's `g_component_ids` (rc2-draft, L4).

`P` below is the projection context of `eio_agents.per.project` (the loaded release, the claims and refs of the bundle,
findings, and the explanation builders).
"""
from collections import defaultdict

from eio_agents.base.canon import q4
from eio_agents.base.errors import ConversionError, require
from eio_agents.semantics import SEVR
from eio_agents.semantics.why import AXIS_SYMBOLS

from .engine import band_of, normalized_weights, readiness_index
from .profiles import record_profile, resolve_profile


def _severity_key(P, cid):
    return -SEVR.get((P.FID.get(P.CLAIM2F.get(cid)) or {}).get("severity"), 0), P.CIDX[cid]


def cap_claims(P):
    """The deterministic APPLICABLE_FAIL claims on a cap predicate (the cap candidates of eio.cap.proven-critical-breach)."""
    eio = P.eio
    return [c for c in P.claims if c["predicate"] in eio.cap_preds and c["state"] == "APPLICABLE_FAIL" and c["decided_by"] == "deterministic"]


def published_metric_set(eio, inputs, profile):
    """The published metrics of a record: the declared metric inputs, each a member of the scoring profile's published
    metric set (an `eio.metric.*` of the loaded release), declared once and in the profile's order; fails closed otherwise
    (`BUNDLE_SCORE_INPUTS`)."""
    known = {x["id"] for x in eio.metrics}
    ids = [m["id"] for m in inputs["metrics"]]
    pub = list(profile["published_metrics"])
    for mid in ids:
        require(mid in known, "BUNDLE_SCORE_INPUTS", f"unknown metric {mid}")
        require(mid in pub, "BUNDLE_SCORE_INPUTS", f"metric {mid} is outside the published metric set of {profile['id']}")
    require(len(set(ids)) == len(ids), "BUNDLE_SCORE_INPUTS", "a metric is declared twice in the published metric set")
    require(ids == sorted(ids, key=pub.index), "BUNDLE_SCORE_INPUTS", "the metric inputs are not in the profile's order")
    return ids


NO_VALUE_REASON = "no value was declared and no member claim was decided"   # the NOT_EVALUATED reason of an empty metric


class ScoreView:
    """The score view of one projection over the declared score inputs `inputs`."""

    def __init__(self, P, inputs):
        self.P, self.inputs = P, inputs
        require(isinstance(inputs.get("metrics"), list) and isinstance(inputs.get("axes"), list)
                and isinstance(inputs.get("readiness"), dict), "BUNDLE_SCORE_INPUTS", "metrics, axes and readiness are required")
        # the scoring profile document: attested (digest recomputed, adapter producers only) or from the registry
        self.profile = resolve_profile(inputs.get("profile"), producer_kind=P.bundle["provenance"]["producer"]["kind"], ontology=P.eio)
        self.params = self.profile["parameters"]

    # ---------------------------------------------------------------- metric views
    def metrics_step(self):
        P, eio, SI = self.P, self.P.eio, self.inputs
        self.has_attribution = bool(SI["attribution"])
        self.CAPC_ALL = cap_claims(P)
        capset = {c["id"] for c in self.CAPC_ALL}
        metrics, self.metric_points, self.metric_members = [], defaultdict(float), {}
        self.published = published_metric_set(eio, SI, self.profile)
        declared = {m["id"]: m for m in SI["metrics"]}
        for mid in self.published:
            m = declared[mid]
            val = m["value"]
            for cid in m["members"]:
                require(cid in P.C, "BUNDLE_SCORE_INPUTS", f"{mid}: unknown member claim {cid}")
            cl = [c for c in P.claims if c["id"] in set(m["members"])]
            self.metric_members[mid] = cl
            b = P.basis(cl)
            ret = b["pass"] + b["fail"] + b["not_applicable"]
            ef = q4(ret / b["claims"]) if b["claims"] else None
            if val is None:
                status = "NOT_EVALUATED"
            elif not cl:
                status = "NOT_APPLICABLE"
            elif ef < eio.release_evidence_floor:
                status = "DIAGNOSTIC_ONLY"
            else:
                status = "MEASURED"
            lab = m["label"]                              # the declared label, or null: the gate reasons then name the id
            capd = pre = capclaim = None
            drivers = []
            if self.has_attribution:
                contrib = defaultdict(float)
                for cid, pts in m["contributions"] or []:
                    require(cid in P.C, "BUNDLE_SCORE_INPUTS", f"{mid}: unknown contribution claim {cid}")
                    contrib[cid] += pts
                if m["pre_cap"] is not None:
                    capc = [c for c in cl if c["id"] in capset]
                    require(capc, "METRIC_CAP", f"{mid} capped without a cap claim")
                    capclaim = capc[0]
                    pre = m["pre_cap"]
                    capd = {"cap": eio.cap["id"], "scope": "metric", "ceiling": q4(eio.cap["ceiling"] * 10), "claim_id": capclaim["id"]}
                    drivers.append({"rank": 1, "claim_id": capclaim["id"], "role": "cap",
                                    "contribution": {"points": q4(contrib.get(capclaim["id"], 0.0)), "via_cap": m["via_cap"],
                                                     "unit": "points_0_100"}})
                for cid in sorted(contrib, key=lambda cid: (-abs(contrib[cid]), P.CIDX[cid])):
                    if capclaim and cid == capclaim["id"]:
                        continue
                    drivers.append({"rank": len(drivers) + 1, "claim_id": cid, "role": "deduction",
                                    "contribution": {"points": q4(contrib[cid]), "via_cap": 0, "unit": "points_0_100"}})
                for d in drivers:
                    self.metric_points[d["claim_id"]] += abs(d["contribution"]["points"]) + abs(d["contribution"]["via_cap"])
            else:
                fails = [c for c in cl if c["state"] == "APPLICABLE_FAIL"]
                fails.sort(key=lambda c: _severity_key(P, c["id"]))
                drivers = [{"rank": i + 1, "claim_id": c["id"], "role": "deduction", "contribution": None} for i, c in enumerate(fails)]
            if not drivers:                                                                     # E-7: every number cites claims
                drivers = [{"rank": i + 1, "claim_id": c["id"], "role": "satisfaction", "contribution": None}
                           for i, c in enumerate(c for c in cl if c["state"] == "APPLICABLE_PASS")]
            drc = [P.C[d["claim_id"]] for d in drivers]
            refs = P.cited_first([r for c in drc for r in c["evidence"]], drc)
            ctx = P.ctx_refs_of_claim(capclaim) if capclaim else []
            if capd:
                params = {"metric": lab or mid, "value": val, "pre_cap": pre, "cap": eio.cap["id"], "claim_id": capclaim["id"],
                          "predicate": capclaim["predicate"], "turn": capclaim["turn_indices"][0], "fail": b["fail"],
                          "applicable": b["applicable"], "not_applicable": b["not_applicable"], "evaluator_fault": b["evaluator_fault"]}
                tid = "eio.why.metric.capped@1"
            elif status == "NOT_EVALUATED":
                params = {"metric": lab or mid, "reason": m["not_evaluated_reason"] or (NO_VALUE_REASON if not cl else None)}
                tid = "eio.why.metric.not_evaluated@1"
            elif status == "DIAGNOSTIC_ONLY":
                params = {"metric": lab or mid, "value": val, "returned": ret, "expected": b["claims"], "fraction": ef,
                          "floor": eio.release_evidence_floor, "evaluator_fault": b["evaluator_fault"]}
                tid = "eio.why.metric.diagnostic_only@1"
            else:
                params = {"metric": lab or mid, "value": val, "fail": b["fail"], "applicable": b["applicable"],
                          "not_applicable": b["not_applicable"], "evaluator_fault": b["evaluator_fault"]}
                tid = "eio.why.metric@1"
            metrics.append({"metric": mid, "legacy_metric": m.get("legacy_metric"), "value": val, "measurement_status": status,
                            "evidence_fraction": ef, "pre_cap": pre, "cap": capd, "confidence": m["confidence"],
                            "explanation": P.explanation(tid, params, b, drivers, refs, ctx), "_returned": ret, "_drivers": drivers,
                            "_label": lab})
        self.metrics = metrics
        self.M_BY = {m["metric"]: m for m in metrics}

    # ---------------------------------------------------------------- axes
    def axes_step(self):
        P, SI = self.P, self.inputs
        sym_of = {a["id"]: a["symbol"] for a in P.eio.axes}
        weights = normalized_weights(self.params)                    # the weight a record states: the profile's, normalized
        gids = self.profile["g_component_ids"]
        axes, self.axis_values = [], {}
        for a in SI["axes"]:
            aid = a["axis"]
            require(aid in sym_of, "BUNDLE_SCORE_INPUTS", f"unknown axis {aid}")
            require(aid in weights, "BUNDLE_SCORE_INPUTS", f"axis {aid} is not an axis of the scoring profile {self.profile['id']}")
            sym, val = sym_of[aid], a["value"]
            if sym == "G":                                           # the G component ids are declared by the profile (L4)
                bad = [x["id"] for x in a["components"] if gids is None or x["id"] not in gids]
                require(not bad, "BUNDLE_SCORE_INPUTS", f"G component id(s) {bad[:2]} not declared by the scoring profile {self.profile['id']}")
            self.axis_values[sym] = val
            ctx = []
            bad = [c for c in a.get("context_criteria") or [] if c not in P.eio.criteria]
            require(not bad, "BUNDLE_SCORE_INPUTS", f"{aid}: unknown context criterion {bad[:1]!r:.80} (L3 fix round 2)")
            if a.get("context_criteria") and P.ctx_embedded:
                ctx = [x for crit in a["context_criteria"] for x in P.ctx_refs_for_criterion(crit)]
            axes.append({"axis": aid, "symbol": sym, "value": val, "weight": q4(weights[aid]),
                         "measurement_status": "MEASURED" if val is not None else "NOT_EVALUATED",
                         "components": [dict(x) for x in a["components"]], "_tid": a["explanation"]["template_id"],
                         "_params": a["explanation"]["params"], "_ctx": ctx})
        self.axes = axes

    # ---------------------------------------------------------------- readiness value, cap reasons, drivers (E-6, 04 §5.7)
    def readiness_step(self):
        P, eio, R = self.P, self.P.eio, self.inputs["readiness"]
        # the engine combines the declared axis values with the profile document (epsilon, weights, completeness)
        vals = {a["axis"]: a["value"] for a in self.inputs["axes"]}
        has = any(v is not None for v in vals.values())
        idx = readiness_index(vals, self.params, blocked=False)
        self.readiness_raw = q4(idx.raw) if has else None
        self.readiness_complete, self.readiness_missing = idx.complete, list(idx.missing_axes)
        cap_ids = set(R["cap_claims"])
        require(cap_ids <= {c["id"] for c in self.CAPC_ALL}, "BUNDLE_SCORE_INPUTS", "a declared cap claim is not a cap candidate")
        blocked, ceiling = bool(R["blocked"]), q4(self.params["readiness_ceiling"])
        self.cap_reasons = []
        for c in self.CAPC_ALL:
            if c["id"] in cap_ids:
                w = [r for r in c["evidence"] if P.witnessing_anchored(r)]
                if not w:                                                               # W1: an unwitnessed claim is never a cap
                    P.lim("per.lim.cap.unwitnessed_claim", claim_id=c["id"])
                    continue
                self.cap_reasons.append({"cap": eio.cap["id"], "scope": "readiness", "ceiling": ceiling, "claim_id": c["id"],
                                         "turn": c["turn_indices"][0], "ref": w[0]})
        for trig in R["triggers"]:
            self.cap_reasons.append({"trigger": trig, "scope": "readiness", "ceiling": ceiling})
            P.lim("per.lim.cap.no_claim", trigger=trig)
        self.readiness_caps = [P.C[x["claim_id"]] for x in self.cap_reasons if "claim_id" in x]
        # W1: a producer score can block on a verdict EIO does not accept as proof; with no cap claim and no claimless
        # trigger there is no cap, and readiness is reported uncapped (value = raw). The ceiling is the profile's.
        self.readiness_blocked = blocked and bool(self.cap_reasons)
        self.readiness_value = (q4(readiness_index(vals, self.params, blocked=self.readiness_blocked).value) if has else None)
        capd_ids = [c["id"] for c in self.readiness_caps]
        if self.has_attribution:
            rest = sorted([cid for cid in self.metric_points if cid not in capd_ids], key=lambda cid: (-self.metric_points[cid], P.CIDX[cid]))
        else:
            fails = {d["claim_id"] for m in self.metrics for d in m["_drivers"] if d["role"] == "deduction"} - set(capd_ids)
            rest = sorted(fails, key=lambda cid: _severity_key(P, cid))
        self.readiness_role = "deduction"
        if not capd_ids and not rest:        # E-7: no claim deducts -> the metrics' satisfaction drivers (metric order, de-duplicated)
            rest = list(dict.fromkeys(d["claim_id"] for m in self.metrics for d in m["_drivers"] if d["role"] == "satisfaction"))
            self.readiness_role = "satisfaction"
        self.readiness_driver_ids = capd_ids + rest

    # ---------------------------------------------------------------- after the release state (I-3)
    def band(self, state):
        val = self.readiness_value
        if val is None:
            return None
        if state == "BLOCK":
            return "F"
        return band_of(val, self.params["band_ramp"])

    def finish(self, state):
        P, R = self.P, self.inputs["readiness"]
        val = self.readiness_value
        band = self.band(state)
        axes_list = {sym: self.axis_values.get(sym) for sym in AXIS_SYMBOLS}
        rdrv = []
        for i, c in enumerate(self.readiness_caps):                 # the ceiling is applied once: the first cap claim carries it
            rdrv.append({"rank": len(rdrv) + 1, "claim_id": c["id"], "role": "cap",
                         "contribution": {"points": None, "via_cap": q4(val - self.readiness_raw) if i == 0 else 0, "unit": "points_0_100"}})
        for cid in self.readiness_driver_ids[len(self.readiness_caps):]:
            rdrv.append({"rank": len(rdrv) + 1, "claim_id": cid, "role": self.readiness_role, "contribution": None})
        rdc = [P.C[d["claim_id"]] for d in rdrv]
        refs = P.cited_first([r for c in rdc for r in c["evidence"]], rdc)
        ctx = P.ctx_refs_of_claim(self.readiness_caps[0]) if self.readiness_caps else []
        if self.readiness_caps:
            c0 = self.readiness_caps[0]
            tid = "eio.why.readiness.capped@1"
            params = {"value": val, "band": band, "raw": self.readiness_raw, "cap": P.eio.cap["id"], "claim_id": c0["id"],
                      "predicate": c0["predicate"], "turn": c0["turn_indices"][0], "axes_list": axes_list}
        elif self.readiness_blocked:
            raise ConversionError("NO_TEMPLATE: eio.template.why has no template for a readiness block without a cap claim "
                                  "(claimless trigger); fail closed", code="NO_TEMPLATE")
        elif not self.readiness_complete:
            tid, params = "eio.why.readiness.partial@1", {"value": val, "band": band, "axes_list": axes_list}
        else:
            tid, params = "eio.why.readiness@1", {"value": val, "band": band, "axes_list": axes_list}
        self.readiness = {"value": val, "raw": self.readiness_raw, "band": band, "blocked": bool(self.readiness_blocked),
                          "complete": bool(self.readiness_complete), "missing_axes": list(self.readiness_missing),
                          "cap_reasons": self.cap_reasons,
                          "margin": R["margin"], "interval": list(R["interval"]) if R["interval"] else None,
                          "method": self.params["method"],
                          "explanation": P.explanation(tid, params, P.basis(P.claims), rdrv, refs, ctx)}
        # axes: E carries the readiness drivers with E contributions; the other axes are not claim-based under this profile
        n_m = len([m for m in self.metrics if m["value"] is not None]) or 1
        out = []
        for a in self.axes:
            tid, params, actx = a.pop("_tid"), a.pop("_params"), a.pop("_ctx", [])
            if a["symbol"] == "E" and a["value"] is not None:
                edr = []
                for d in rdrv:
                    pts = vc = 0.0
                    has = False
                    for m in self.metrics:
                        for md in m["_drivers"]:
                            if md["claim_id"] == d["claim_id"] and md["contribution"]:
                                pts += md["contribution"]["points"] or 0
                                vc += md["contribution"]["via_cap"]
                                has = True
                    edr.append({"rank": d["rank"], "claim_id": d["claim_id"], "role": d["role"],
                                "contribution": {"points": q4(pts / n_m), "via_cap": q4(vc / n_m), "unit": "points_0_100"} if has else None})
                a["explanation"] = P.explanation(tid, params, P.basis(P.claims), edr, refs, ctx)
            else:
                a["explanation"] = P.explanation(tid, params, dict(P.ZB), [], [], actx if a["symbol"] == "Q" else [])
            out.append(a)
        self.axes = out

    def block(self):
        """The PER `scores` block."""
        return {"scoring_profile": record_profile(self.profile), "readiness": self.readiness, "axes": self.axes,
                "metrics": [{k: v for k, v in mm.items() if not k.startswith("_")} for mm in self.metrics]}
