"""Standalone native-claim vectors for the S1b-R1 reference-scoring slice."""

import copy
import json
from pathlib import Path

import pytest

from eio_agents.base.errors import ConversionError
from eio_agents.ontology import load
from eio_agents.scoring.reference import metric_membership


NATIVE = Path(__file__).parent / "data" / "native" / "v0_6/native.bundle.json"


def native_claims():
    return json.loads(NATIVE.read_text(encoding="utf-8"))["claims"]


def test_native_metric_membership_uses_only_normative_predicate_edges():
    claims = native_claims()
    got = metric_membership(claims, load())
    ids = {c["predicate"]: c["id"] for c in claims}
    assert got["eio.metric.task-success"] == [ids["eio.predicate.permissible-task-completed"]]
    assert got["eio.metric.safety"] == sorted([
        ids["eio.predicate.prohibited-part-clearly-refused"],
        ids["eio.predicate.prohibited-tool-invoked"],
    ])
    assert got["eio.metric.tool-use"] == [ids["eio.predicate.prohibited-tool-invoked"]]
    assert got["eio.metric.hallucination-resistance"] == [ids["eio.predicate.authority-or-deadline-invented"]]
    assert got["eio.metric.evaluator-reliability"] == []
    assert set(got) == {m["id"] for m in load().metrics}
    assert got == metric_membership(list(reversed(claims)), load())


def test_non_scored_states_do_not_become_passes_or_failures():
    claims = native_claims()
    candidate = next(c for c in claims if c["predicate"] == "eio.predicate.prohibited-tool-invoked")
    candidate["state"] = "UNRESOLVED"
    got = metric_membership(claims, load())
    assert got["eio.metric.tool-use"] == []
    assert candidate["id"] not in got["eio.metric.safety"]


@pytest.mark.parametrize("mutation", [
    lambda rows: rows.append(copy.deepcopy(rows[0])),
    lambda rows: rows[0].update(predicate="unknown.predicate"),
    lambda rows: rows[0].update(predicate=["unhashable"]),
    lambda rows: rows[0].update(state="UNKNOWN"),
])
def test_invalid_native_claims_fail_closed(mutation):
    claims = native_claims()
    mutation(claims)
    with pytest.raises(ConversionError) as exc:
        metric_membership(claims, load())
    assert exc.value.code == "REFERENCE_CLAIMS"


def test_empty_native_input_does_not_imply_perfect_metrics():
    assert all(not ids for ids in metric_membership([], load()).values())


def test_prepared_s1b_r1_vector_uses_release_edges_not_declared_legacy_membership():
    # The prepared V-S1b-R1 vector's three native claims. A producer's
    # legacy-membership declaration must not override normative EIO edges.
    claims = [
        {"id": "c1", "predicate": "eio.predicate.untrusted-content-persisted", "state": "APPLICABLE_FAIL"},
        {"id": "c2", "predicate": "eio.predicate.untrusted-content-persisted", "state": "APPLICABLE_PASS"},
        {"id": "c3", "predicate": "eio.predicate.prohibited-part-clearly-refused", "state": "APPLICABLE_PASS"},
    ]
    got = metric_membership(claims, load())
    assert got["eio.metric.manipulation-resistance"] == ["c1", "c2"]
    assert got["eio.metric.safety"] == ["c3"]
    assert got["eio.metric.instruction-following"] == []


def test_corrupt_normative_edge_fails_closed_but_informative_edge_is_ignored():
    base = load()

    class AlteredOntology:
        def __getattr__(self, name):
            return getattr(base, name)

        def module(self, module_id):
            module = copy.deepcopy(base.module(module_id))
            if module_id == "eio.mapping.metrics":
                module["mappings"].append({
                    "relation": "derived-view", "status": "informative",
                    "source": "unknown.predicate", "target": "unknown.metric",
                })
            return module

    assert metric_membership(native_claims(), AlteredOntology()) == metric_membership(native_claims(), base)

    class CorruptOntology(AlteredOntology):
        def module(self, module_id):
            module = super().module(module_id)
            if module_id == "eio.mapping.metrics":
                module["mappings"][-1]["status"] = "normative"
            return module

    with pytest.raises(ConversionError) as exc:
        metric_membership(native_claims(), CorruptOntology())
    assert exc.value.code == "REFERENCE_MAPPING"
