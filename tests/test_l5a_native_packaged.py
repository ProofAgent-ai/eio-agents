"""Public API smoke for the isolated native S1b rc3 bridge (not a release gate)."""
import copy
import json
import os
from pathlib import Path

import pytest

from eio_agents.api import convert, standards, validate, verify
from eio_agents.base.errors import ConversionError
from eio_agents.ontology import load
from eio_agents.schemas import current_native_per_schema, per_schema
from eio_agents.validation.reader import EIO


FROZEN = Path(os.environ.get("L5A_FROZEN_EIO_DATA", str(Path(__file__).resolve().parents[1] / "src/eio_agents/ontology/data")))
BUNDLE = Path(__file__).parent / "data/native/v0_6/native.bundle.json"


@pytest.fixture(scope="module")
def source():
    if not FROZEN.exists():
        pytest.skip("a verified frozen EIO release is required until the coordinated L5a digest reissue")
    return json.loads(BUNDLE.read_text()), load(FROZEN)


def test_packaged_native_convert_validate_verify(source):
    bundle, ontology = source
    record = convert(bundle, ontology=ontology)
    assert record["header"]["schema_uri"] == "https://w3id.org/eio-agents/per/2.0.0-rc3-draft/per.schema.json"
    assert len(record["claims"]) == 4
    assert len(record["evidence"]["refs"]) == 6
    assert record["scores"] is None
    assert any(row["limitation_id"] == "per.lim.scoring_profile.none" for row in record["limitations"])
    assert validate(record, eio=EIO(ontology.root)) == []
    result = verify(record, bundle, ontology=ontology)
    assert result["valid"] is True and result["digest_match"] is True
    assert result["per_sha256"] == result["rederived_sha256"]
    assert result["failures"] == []


def test_packaged_native_verifier_rejects_tampering(source):
    bundle, ontology = source
    record = convert(bundle, ontology=ontology)
    tampered = copy.deepcopy(record)
    tampered["claims"][0]["state"] = "APPLICABLE_FAIL"
    result = verify(tampered, bundle, ontology=ontology)
    assert result["valid"] is False
    assert result["digest_match"] is False
    assert result["failures"]


def test_packaged_native_dispatch_fails_closed_on_bad_provenance(source):
    bundle, ontology = source
    malformed = copy.deepcopy(bundle)
    malformed["provenance"] = []
    with pytest.raises(ConversionError):
        convert(malformed, ontology=ontology)


def test_standards_identifies_only_the_standalone_projector():
    stated = standards()
    assert stated["per_schema_id"] == "https://www.proofagent.ai/eio-agents/schema/per/2.1.0/per.schema.json"
    assert stated["per_version"] == "2.1.0" and stated["release_semantics"] == "2.2"
    assert stated["native_full_per_version"] == "2.1.0"
    assert stated["native_full_per_schema_id"] == (
        "https://www.proofagent.ai/eio-agents/schema/per/2.1.0/per.schema.json"
    )
    assert stated["current_native_per_version"] == stated["native_full_per_version"]
    assert current_native_per_schema()["$id"] == stated["current_native_per_schema_id"]
    assert per_schema()["$id"] == stated["per_schema_id"]  # PER 2.1.0 is the default (owner decision #46)
    assert stated["native_full_scoring_profile_id"] == "eio-agents.reference-scoring"
    assert stated["native_full_scoring_profile_version"] == "0.3.1"
    assert stated["projector"].startswith("eio_agents.convert ")
    assert stated["converter"] == stated["projector"]
    assert "adapter_projector" not in stated
