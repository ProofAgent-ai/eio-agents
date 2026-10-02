"""Native EIO stress checks; historical producer archives belong to its adapter corpus."""
import copy
import json
from pathlib import Path

import pytest

import eio_agents
from eio_agents.base.errors import ConversionError
from eio_agents.ontology import load
from eio_agents.validation.reader import EIO

DATA = Path(__file__).parent / "data"
NATIVE = DATA / "native" / "v0_6/native.bundle.json"


def _summaries(node):
    if isinstance(node, dict):
        e = node.get("explanation")
        if isinstance(e, dict) and "summary" in e:
            yield e["template_id"], e["summary"]
        for v in node.values():
            yield from _summaries(v)
    elif isinstance(node, list):
        for v in node:
            yield from _summaries(v)


@pytest.fixture(scope="module")
def source():
    return json.loads(NATIVE.read_text(encoding="utf-8")), load()


def test_native_bundle_converts_validates_and_verifies_with_bounded_explanations(source):
    b, ontology = source
    rec = eio_agents.convert(b, ontology=ontology)
    assert eio_agents.validate(rec, eio=EIO(ontology.root)) == []
    r = eio_agents.verify(rec, b, ontology=ontology)
    assert r["valid"] and r["digest_match"], r["failures"]
    assert all(len(s) <= 600 for _, s in _summaries(rec))


def test_native_reliability_does_not_invent_a_rate(source):
    b, ontology = source
    rec = eio_agents.convert(b, ontology=ontology)
    assert rec["reliability"]["status"] == "NOT_RETESTED"
    assert rec["reliability"]["rate"] is None


def test_native_malformed_provenance_fails_closed(source):
    b, ontology = source
    bad = copy.deepcopy(b)
    bad["provenance"] = []
    with pytest.raises(ConversionError):
        eio_agents.convert(bad, ontology=ontology)


def test_native_projection_is_deterministic(source):
    b, ontology = source
    first = eio_agents.convert(b, ontology=ontology)
    second = eio_agents.convert(copy.deepcopy(b), ontology=ontology)
    assert eio_agents.canonical_bytes(first) == eio_agents.canonical_bytes(second)
