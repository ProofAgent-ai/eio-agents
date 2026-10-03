"""Native-bundle regression tests; old adapter golden cases are externally preserved."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

import eio_agents

NATIVE = Path(__file__).parent / "data" / "native" / "v0_6/native.bundle.json"


def _bundle():
    return NATIVE.read_bytes()


def test_native_projection_is_deterministic_across_hash_seeds():
    code = ("import sys,eio_agents,pathlib;r=eio_agents.convert(pathlib.Path(sys.argv[1]).read_bytes());"
            "sys.stdout.buffer.write(eio_agents.canonical_bytes(r))")
    outs = []
    for seed in ("0", "12345"):
        p = subprocess.run([sys.executable, "-c", code, str(NATIVE)], capture_output=True,
                           env={**os.environ, "PYTHONHASHSEED": seed}, check=True)
        outs.append(p.stdout)
    assert outs[0] == outs[1] == eio_agents.canonical_bytes(eio_agents.convert(_bundle()))


def test_native_record_validates_and_verifies():
    rec = eio_agents.convert(_bundle())
    assert eio_agents.validate(rec) == []
    result = eio_agents.verify(rec, _bundle())
    assert result["valid"] and result["digest_match"], result["failures"]


def test_native_record_tampering_is_detected():
    rec = eio_agents.convert(_bundle())
    rec["claims"][0]["state"] = "APPLICABLE_FAIL"
    result = eio_agents.verify(rec, _bundle())
    assert not result["valid"] and not result["digest_match"]


def test_conversion_fails_closed_on_garbage():
    with pytest.raises(eio_agents.ConversionError) as e:
        eio_agents.convert(b'{"not": "an evaluation bundle"}')
    assert e.value.code == "BUNDLE_INPUT"


def test_stored_reports_are_refused_with_a_typed_error():
    """The library takes schema-3 bundles; schema-1/2 records need a producer adapter."""
    for raw in ({"archive_schema": 1}, {"archive_schema": 2}):
        with pytest.raises(eio_agents.ConversionError) as e:
            eio_agents.convert(raw)
        assert e.value.code == "BUNDLE_INPUT"


def test_standards_versions():
    s = eio_agents.standards()
    assert s["per_version"] == "2.1.0" and s["ontology_digest"]      # the default record format (decision #46)
