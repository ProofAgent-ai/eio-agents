"""The seven EIO release gates recomputed (03 §9.3 PROD-29; 02 §5.5): `gate_met` and the gate inputs of a record."""


REPRO_FIELDS = ("revision", "patch", "seed", "models", "prompt_hashes")   # 03 §9.3 eio.gate.reproducible


def gate_met(gate, v, eio):
    """`met` of one EIO gate (03 §9.3 PROD-29; 02 §5.5) from inputs of the shape of the gate's `test_vectors` in
    eio/governance/gates.yaml. Used by c_gates on the record (gate_inputs) and by the verifier self-test on every test vector."""
    gid = gate["id"]
    if gid == "eio.gate.coverage-complete":
        hb = [o for o in v["obligations"] if o["impact"] == "HARD_BLOCK"]
        if any(o["required"] is True and o["met"] is False for o in hb):
            return False
        return None if any(o["required"] is None and o["met"] is False for o in hb) else True
    if gid == "eio.gate.evidence-sufficient":
        return False if any(m["measurement_status"] == "DIAGNOSTIC_ONLY" for m in v["metrics"]) else True
    if gid == "eio.gate.evaluator-calibrated":
        return None                                  # EIO 0.4.0 declares no accuracy or abstention floors
    if gid == "eio.gate.reproducible":
        return False if set(v["missing_fields"]) & set(REPRO_FIELDS) else True
    if gid == "eio.gate.human-oversight-declared":
        # required_when evaluated by eio.profile.coverage-evaluation: not required (true) if a named fact is declared
        # with another value; else null if a named fact is undeclared; else the human_oversight fact
        rw, f = gate["required_when"], v["facts"]
        if any(f.get(k) is not None and f.get(k) != want for k, want in rw.items()):
            return True
        if any(f.get(k) is None for k in rw):
            return None
        return f.get("human_oversight")
    if gid == "eio.gate.no-critical-recurrence":
        if v["reliability_status"] == "NOT_RETESTED":
            return None
        return False if any(f["recurrence"] == "CONFIRMED" and any(o["impact"] == "HARD_BLOCK" and o["required"] is not False
                                                                    for o in f["obligations"]) for f in v["findings"]) else True
    if gid == "eio.gate.independent-adjudication":
        return False if any(st != "adjudicated" for st in v["reference_case_statuses"]) else True
    raise KeyError(f"no rule for gate {gid}")


def gate_inputs(rec, eio):
    """The gate inputs of a record, in the test-vector shape of eio/governance/gates.yaml."""
    obl = rec["coverage"]["obligations"]
    fv = {k: x["value"] for k, x in rec["scope"]["facts"].items()}
    scores = rec.get("scores") or {}
    # The draft native reference views are not the legacy evidence-fraction
    # inputs of eio.gate.evidence-sufficient. Its gate result remains the
    # source-projected unscored result until a versioned native gate rule is
    # approved; never reinterpret a WITHHELD numeric metric as that fraction.
    legacy_metrics = [] if scores.get("kind") == "reference-draft" else scores.get("metrics") or []
    return {
        "eio.gate.coverage-complete": {"obligations": [{"impact": o["release_impact"], "required": o["required"], "met": o["met"]} for o in obl]},
        "eio.gate.evidence-sufficient": {"metrics": [{"measurement_status": m["measurement_status"]} for m in legacy_metrics]},
        "eio.gate.evaluator-calibrated": {"calibration_results": None},
        "eio.gate.reproducible": {"missing_fields": list(rec["provenance"]["capsule"]["missing_fields"])},
        "eio.gate.human-oversight-declared": {"facts": {"tier": (rec["scope"]["tier"] or {}).get("id"),
                                                        "consequential_actions": fv.get("consequential_actions"),
                                                        "human_oversight": fv.get("human_oversight")}},
        "eio.gate.no-critical-recurrence": {"reliability_status": rec["reliability"]["status"],
                                            "findings": [{"recurrence": (f.get("recurrence") or {}).get("band"),
                                                          "obligations": [{"impact": o["release_impact"], "required": o["required"]}
                                                                          for o in obl if o.get("predicate") == f["predicate"]]}
                                                         for f in rec["findings"] if f["kind"] == "BEHAVIOURAL"]},
        "eio.gate.independent-adjudication": {"reference_case_statuses": [(c.get("review") or {}).get("status") for c in eio.cases]},
    }
