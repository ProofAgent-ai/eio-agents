"""Neutral reliability, compliance and evidence views over a native record."""
import copy
import random
from collections import defaultdict
from pathlib import Path

from eio_agents import compliance, per, reliability

DATA = Path(__file__).parent / "data"
NATIVE = DATA / "native/v0_6/native.bundle.json"


def _native():
    import eio_agents
    return eio_agents.convert(NATIVE.read_bytes())


def test_band_of_rule():
    nr = {"band": "NOT_RETESTED", "retests": 0, "reproduced_in": 0, "trial_kind": None, "ledger_key": None}
    def trial(r):
        return {"claim_id": "c", "ledger_key": "k", "trial_kind": "eio.trial.repeat", "reproduced_in": r, "passes": 3,
                "may_auto_block": False}
    assert reliability.band_of(None, 3) == nr and reliability.band_of(trial(1), 0) == nr
    assert reliability.band_of(dict(trial(1), trial_kind="eio.trial.probe"), 3)["trial_kind"] == "eio.trial.probe"   # carry note 3
    bands = [reliability.band_of(trial(r), 3)["band"] for r in (0, 1, 3)]
    assert bands == ["UNCONFIRMED", "INTERMITTENT", "CONFIRMED"]
    assert sorted(reliability.BR, key=reliability.BR.get) == ["NOT_RETESTED", "UNCONFIRMED", "INTERMITTENT", "CONFIRMED"]


def test_order_refs_and_cited_ref_ids():
    rec = _native()
    refs = rec["evidence"]["refs"]
    shuffled = refs[:]
    random.Random(7).shuffle(shuffled)
    claims = copy.deepcopy(rec["claims"])
    for c in claims:
        c["evidence"].reverse()
    ref_list, order = per.order_refs({r["id"]: r for r in shuffled}, claims)
    assert ref_list == refs and order == {r["id"]: i for i, r in enumerate(refs)}
    assert claims == rec["claims"]
    assert per.cited_ref_ids({k: v for k, v in rec.items() if k != "evidence"}) == {r["id"] for r in refs}


def test_controls_step_recomputes_the_native_controls(eio):
    rec = _native()
    fidelity = {c["id"]: c["parameters"]["fidelity"] for c in rec["claims"]}
    causes = {o["predicate"]: o["cause_if_unmet"] for o in rec["coverage"]["obligations"] if o["cause_if_unmet"]}
    causes.update({d["predicate"]: d["cause_if_silent"] for d in rec["coverage"]["dispatch"] if d["cause_if_silent"]})
    byp = defaultdict(list)
    for c in rec["claims"]:
        byp[c["predicate"]].append(c)
    refs = {r["id"]: r for r in rec["evidence"]["refs"]}
    findings = [dict(f, control_ids=None) for f in rec["findings"]]
    rows = compliance.controls_step(eio, rec["scope"]["frameworks"], byp, {c["id"]: i for i, c in enumerate(rec["claims"])},
                                    refs, {r: i for i, r in enumerate(refs)}, findings,
                                    lambda p, cl: causes.get(p, "NEVER_SELECTED"),
                                    lambda c: fidelity[c["id"]])
    assert rows == rec["controls"]
    assert [f["control_ids"] for f in findings] == [f["control_ids"] for f in rec["findings"]]


def test_native_without_scoring_profile_withholds_axes():
    rec = _native()
    assert rec["scores"] is None
    assert "per.lim.scoring_profile.none" in {row["limitation_id"] for row in rec["limitations"]}
