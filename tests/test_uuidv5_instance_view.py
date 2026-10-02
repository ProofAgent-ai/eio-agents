"""Exact LS3 candidate mapping, independent of the PER report bytes."""
import copy
import json
import uuid
from pathlib import Path

import pytest

from eio_agents.per.instance_iri import PROPOSED_NAMESPACE, jsonld_instance_view


GOLDEN = Path(__file__).parent / "data/native/v0_6/native.per.jcs"


def test_proposed_uuidv5_view_preserves_compact_per_bytes():
    report_bytes = GOLDEN.read_bytes()
    record = json.loads(report_bytes)
    before = copy.deepcopy(record)
    view = jsonld_instance_view(record)
    assert record == before and GOLDEN.read_bytes() == report_bytes
    namespace = uuid.uuid5(uuid.NAMESPACE_URL, "https://www.proofagent.ai/eio-agents/instances")
    assert str(namespace) == "7e08e973-ec7e-5a32-a8c7-c9a628e2866e"
    assert PROPOSED_NAMESPACE == namespace
    rows = (("claim", record["claims"], "id"),
            ("ref", record["evidence"]["refs"], "id"),
            ("finding", record["findings"], "finding_id"))
    expected = [(kind, row[key], f"urn:uuid:{uuid.uuid5(namespace, f'eio-agents:{kind}:{row[key]}')}")
                for kind, items, key in rows for row in items]
    assert [(node["@type"].split(".")[-1], node["per:compact_id"], node["@id"])
            for node in view["@graph"]] == [({"claim": "evaluation-claim", "ref": "evidence-ref", "finding": "finding"}[kind], cid, iri)
                                       for kind, cid, iri in expected]
    assert len({node["@id"] for node in view["@graph"]}) == len(view["@graph"])


def test_duplicate_or_invalid_compact_id_fails_closed():
    record = json.loads(GOLDEN.read_bytes())
    record["claims"].append(copy.deepcopy(record["claims"][0]))
    with pytest.raises(ValueError, match="duplicate claim"):
        jsonld_instance_view(record)
    record["claims"].pop()
    record["claims"][0]["id"] = "not-a-compact-id"
    with pytest.raises(ValueError, match="compact_id"):
        jsonld_instance_view(record)
