"""Byte-pinned synthetic 0.6 bundles, separate from preserved 0.5 vectors."""

import hashlib
import json
from pathlib import Path

import pytest

from eio_agents import ConversionError, canonical_bytes, convert, validate, verify
from eio_agents.validation import validate_bundle
from full_native_score_case import source_complete_bundle


DATA = Path(__file__).parent / "data/native/v0_6"


def test_unscored_0_6_fixture_is_current_and_exact():
    bundle_bytes = (DATA / "native.bundle.json").read_bytes()
    assert hashlib.sha256(bundle_bytes).hexdigest() == "c3da7d54ed2f497d548cbae792f25f7b817061407aab4686fb909a03074719e0"
    assert validate_bundle(bundle_bytes) == []
    record = convert(bundle_bytes)
    assert record["header"]["eio"]["release"] == "0.6.0"
    assert record["header"]["per_version"] == "2.0.0-rc3-draft"
    assert record["scores"] is None
    assert canonical_bytes(record) == (DATA / "native.per.jcs").read_bytes()
    assert validate(record) == []
    assert verify(record, bundle_bytes)["valid"]


def test_scored_0_6_fixture_is_source_complete_and_exact():
    bundle_bytes = (DATA / "source-complete.bundle.json").read_bytes()
    assert hashlib.sha256(bundle_bytes).hexdigest() == "df27142216466fbe4d9baf4558148c6dd19ffb1cd4712597cfd3cc588df085dd"
    bundle = json.loads(bundle_bytes)
    assert bundle == source_complete_bundle()
    assert validate_bundle(bundle_bytes) == []
    record = convert(bundle_bytes)
    assert record["header"]["eio"]["release"] == "0.6.0"
    assert record["header"]["per_version"] == "2.0.0"
    assert record["scores"]["scoring_profile"]["version"] == "0.3.1-draft.1"
    assert canonical_bytes(record) == (DATA / "source-complete.per.jcs").read_bytes()
    assert validate(record) == []
    result = verify(record, bundle_bytes)
    assert result["valid"] and result["digest_match"]
    assert b"zqxjvw-full-score-private-marker" not in bundle_bytes + canonical_bytes(record)


def test_historical_rc5_golden_and_schema_remain_pinned():
    old = (DATA / "source-complete.rc5-policy-draft.per.jcs").read_bytes()
    assert hashlib.sha256(old).hexdigest() == "657927962bc18b65cb1d4a1269b35c1f49a4839c96ed2c2a92ac63ae68f650eb"
    assert json.loads(old)["header"]["per_version"] == "2.0.0-rc5-policy-draft"
    from eio_agents.schemas import per_schema
    assert per_schema("2.0.0-rc5-policy-draft")["$id"] == "urn:eio-agents:provisional:per:2.0.0-rc5-policy-draft"


def test_preserved_0_5_bundle_cannot_be_replayed_under_0_6():
    old = (DATA.parent / "native.bundle.json").read_bytes()
    assert hashlib.sha256(old).hexdigest() == "12a212d955be08e8371de00486b294f9ec776885e9e86a8915c1434bbf1ec305"
    with pytest.raises(ConversionError) as error:
        convert(old)
    assert error.value.code == "BUNDLE_RECOMPUTE"
