"""Native context disclosure; historical FIN context vectors live in the adapter corpus."""
from pathlib import Path

import eio_agents

NATIVE = Path(__file__).parent / "data/native/v0_6/native.bundle.json"


def test_native_without_context_discloses_not_supplied_and_verifies():
    bundle = NATIVE.read_bytes()
    record = eio_agents.convert(bundle)
    assert record["evidence"]["completeness"]["context_artifacts"] == "NOT_SUPPLIED"
    assert all(ref["kind"] != "POLICY_SPAN" for ref in record["evidence"]["refs"])
    assert all(not finding["explanation"]["context_refs"] for finding in record["findings"])
    assert "per.lim.context.not_supplied" in {row["limitation_id"] for row in record["limitations"]}
    assert eio_agents.validate(record) == []
    result = eio_agents.verify(record, bundle)
    assert result["valid"] and result["digest_match"], result["failures"]


def test_native_without_component_digests_discloses_limitation():
    record = eio_agents.convert(NATIVE.read_bytes())
    assert record["subject"]["ai_bom"]["content_hash"] is None
    assert "per.lim.ai_bom.no_digests" in {row["limitation_id"] for row in record["limitations"]}
