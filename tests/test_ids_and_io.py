"""Neutral native identifier, canonical I/O and archive-digest tests."""
import json
from pathlib import Path

import pytest

import eio_agents
from eio_agents import per
from eio_agents.base import canon
from eio_agents.base.errors import ConversionError
from eio_agents.semantics import ids

DATA = Path(__file__).parent / "data"
NATIVE = DATA / "native/v0_6/native.bundle.json"


def _expected():
    rec = eio_agents.convert(NATIVE.read_bytes())
    return per.canonical_bytes(rec), rec


def test_ids_recompute_native_ids():
    _b, rec = _expected()
    run_id = rec["provenance"]["run"]["run_id"]
    for c in rec["claims"]:
        assert c["id"] == canon.sd({"run_id": run_id, "predicate": c["predicate"],
                                     "predicate_version": c["predicate_version"],
                                     "source_key": c["parameters"]["source_key"],
                                     "turn_indices": sorted(c["turn_indices"])})
    kinds = set()
    for f in rec["findings"]:
        kinds.add(f["kind"])
        if f["kind"] == "BEHAVIOURAL":
            major = int(f["predicate_version"].split(".")[0])
            assert f["fingerprint"] == ids.behavioural_fingerprint(f["predicate"], major,
                                                                   f["scenarios"][0] if f["scenarios"] else None)
            assert f["issue_signature"] == ids.issue_signature(f["predicate"], major)
        else:
            assert f["fingerprint"] == ids.context_gap_fingerprint(f["criterion"], f["control"])
            assert f["issue_signature"] == ids.context_gap_issue_signature(f["criterion"])
        assert f["finding_id"] == ids.finding_id(run_id, f["fingerprint"])
    assert "BEHAVIOURAL" in kinds
    assert rec["evidence"]["cited_refs_hash"] == ids.cited_refs_hash(r["id"] for r in rec["evidence"]["refs"])


def test_per_io_writes_native_bytes(tmp_path):
    body, rec = _expected()
    assert per.canonical_bytes(rec) == body
    digest = per.write(rec, tmp_path / "r.per.json", tmp_path / "r.per.jcs")
    assert digest == per.per_sha256(rec) == canon.H(body)
    assert (tmp_path / "r.per.jcs").read_bytes() == body
    text = (tmp_path / "r.per.json").read_text(encoding="utf-8")
    assert text == per.pretty(rec) + "\n" and json.loads(text) == rec


def test_archive_sha256_by_schema():
    A = json.loads(NATIVE.read_bytes())
    assert per.archive_sha256(A) == canon.H(canon.jb(A))
    with pytest.raises(ConversionError, match="ARCHIVE_SCHEMA"):
        per.archive_sha256({"archive_schema": 1})
    assert per.archive_sha256({"archive_schema": 3}) == canon.H(b'{"archive_schema":3}')


def test_canon_fails_closed_on_non_finite_numbers():
    with pytest.raises(ConversionError, match="NON_FINITE"):
        canon.jb({"x": float("nan")})
