"""Byte-pinned synthetic 0.6 bundles, separate from preserved 0.5 vectors."""

import hashlib
import json
from pathlib import Path

import pytest

from eio_agents import ConversionError, canonical_bytes, convert, validate, verify
from eio_agents.validation import validate_bundle
from full_native_score_case import source_complete_bundle


DATA = Path(__file__).parent / "data/native/v0_8"
HISTORICAL = Path(__file__).parent / "data/native/v0_6"
PER_2_1 = Path(__file__).parent / "data/native/per_2_1"


def test_unscored_0_8_fixture_is_current_and_exact():
    bundle_bytes = (DATA / "native.bundle.json").read_bytes()
    assert hashlib.sha256(bundle_bytes).hexdigest() == "bf425c5a4eb63fdd458aed5240e4bd0fdc38138a7df55632d9ecb0e13b791f9c"
    assert json.loads(bundle_bytes)["bundle_version"] == "3.0.0"
    assert validate_bundle(bundle_bytes) == []
    record = convert(bundle_bytes)
    assert record["header"]["eio"]["release"] == "0.6.0"
    assert record["header"]["per_version"] == "2.1.0"
    assert record["header"]["release_semantics"] == "2.2"
    assert record["scores"] is None                                   # no native scoring inputs: no score is guessed
    assert record["release_recommendation"]["state"] == "REVIEW"      # no policy: readiness withheld (decision #46)
    assert canonical_bytes(record) == (DATA / "native.per.jcs").read_bytes()
    assert validate(record) == []
    assert verify(record, bundle_bytes)["valid"]


def test_scored_0_8_fixture_is_source_complete_and_exact():
    bundle_bytes = (DATA / "source-complete.bundle.json").read_bytes()
    assert hashlib.sha256(bundle_bytes).hexdigest() == "9df95b00e5dcf536aede3c4c8f37c6d2a196f574237e36d4f7f1c8a5e15cded7"
    bundle = json.loads(bundle_bytes)
    assert bundle == source_complete_bundle()
    assert validate_bundle(bundle_bytes) == []
    record = convert(bundle_bytes)
    assert record["header"]["eio"]["release"] == "0.6.0"
    assert record["header"]["per_version"] == "2.1.0"
    assert record["scores"]["scoring_profile"]["version"] == "0.3.1"
    assert record["header"]["release_semantics"] == "2.2"
    assert record["release_recommendation"]["state"] == "REVIEW"      # no policy: default floor 85 (decision #46)
    assert canonical_bytes(record) == (DATA / "source-complete.per.jcs").read_bytes()
    assert validate(record) == []
    result = verify(record, bundle_bytes)
    assert result["valid"] and result["digest_match"]
    assert b"zqxjvw-full-score-private-marker" not in bundle_bytes + canonical_bytes(record)


def test_published_per_2_0_golden_is_immutable_and_still_validates():
    historical = (HISTORICAL / "source-complete.per.jcs").read_bytes()
    assert hashlib.sha256(historical).hexdigest() == "9ea9b9f30cad6d6f827914480e0d0ee1f15c8ecb71828829bbcd7bcbb29b9ecc"
    record = json.loads(historical)
    assert record["header"]["per_version"] == "2.0.0"
    assert validate(record) == []


def test_historical_0_6_bundle_reprojects_to_versioned_per_2_1():
    bundle = (HISTORICAL / "source-complete.bundle.json").read_bytes()
    assert hashlib.sha256(bundle).hexdigest() == "0660c2a2fb554a0ed7a312109b998384b0aa98960bdd861d2e7263035cdbd6f3"
    assert canonical_bytes(convert(bundle)) == (PER_2_1 / "source-complete.per.jcs").read_bytes()


def test_historical_rc5_golden_and_schema_remain_pinned():
    old = (HISTORICAL / "source-complete.rc5-policy-draft.per.jcs").read_bytes()
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
