"""Public PER validation and independent source rederivation for a native producer.

Historical producer-specific variants remain in the external adapter corpus.
"""

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

import eio_agents
from eio_agents.base.errors import ConversionError
from eio_agents.per import bundle as B
from eio_agents.validation import validate_bundle
from eio_agents.validation.verify import c_sources


BUNDLE = Path(__file__).parent / "data" / "native" / "v0_6/native.bundle.json"


@pytest.fixture(scope="module")
def native_pair():
    bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
    return bundle, eio_agents.convert(copy.deepcopy(bundle))


def _restamp(bundle):
    for stage in bundle["stage_records"]:
        stage["output_sha256"] = B.stage_digest(bundle, stage["sections"])
    return bundle


def test_verify_runs_in_process(native_pair, monkeypatch):
    import tempfile

    def forbidden(*_args, **_kwargs):
        raise AssertionError("verify spawned a process or wrote a temporary file")

    for module, name in ((subprocess, "run"), (subprocess, "Popen"),
                         (tempfile, "TemporaryDirectory"), (tempfile, "NamedTemporaryFile")):
        monkeypatch.setattr(module, name, forbidden)
    bundle, record = native_pair
    result = eio_agents.verify(record, bundle)
    assert result["valid"] and result["digest_match"]
    assert result["per_sha256"] == result["rederived_sha256"]
    assert eio_agents.validate(record) == []


def test_ver5_recomputes_native_sources(native_pair):
    bundle, record = native_pair
    problems, info = c_sources(record, bundle)
    assert problems == []
    assert "4 spans, 1 receipts and 1 absences recomputed" in info


@pytest.mark.parametrize("mutate", [
    lambda bundle: bundle["sources"]["turns"][2].__setitem__("answer", "Tampered answer"),
    lambda bundle: bundle["sources"]["turns"][0]["tool_calls"][0].__setitem__("arguments", {"order_id": "A-9999"}),
    lambda bundle: bundle["sources"]["archive_pointer"].__setitem__("turns", "/elsewhere"),
])
def test_verify_detects_a_tampered_native_source(native_pair, mutate):
    original, record = native_pair
    changed = copy.deepcopy(original)
    mutate(changed)
    result = eio_agents.verify(record, _restamp(changed))
    assert not result["valid"] and not result["digest_match"]
    assert c_sources(record, changed)[0]


def test_verifier_checks_native_episode_union():
    from types import SimpleNamespace

    from eio_agents.validation.checker import Checker

    record = {"evidence": {"turns": [
        {"turn_index": 1, "trap": "a"}, {"turn_index": 2, "trap": "a"},
        {"turn_index": 3, "trap": None}, {"turn_index": 4, "trap": None},
        {"turn_index": 5, "trap": "b"},
    ]}}
    checker = SimpleNamespace(rec=record)
    assert Checker.episode_turns(checker, {"turn_indices": [1, 3]}) == {1, 2, 3}
    assert Checker.episode_turns(checker, {"turn_indices": [3, 4]}) == {3, 4}


def test_verify_detects_a_tampered_record(native_pair):
    bundle, original = native_pair
    record = copy.deepcopy(original)
    record["claims"][0]["state"] = "NOT_APPLICABLE"
    result = eio_agents.verify(record, bundle)
    assert not result["valid"] and not result["digest_match"]
    assert result["failures"]


def test_verify_reports_an_unprojectable_native_bundle(native_pair):
    original, record = native_pair
    bundle = copy.deepcopy(original)
    bundle["claims"][0]["state"] = "MAYBE"
    result = eio_agents.verify(record, _restamp(bundle))
    assert not result["valid"] and not result["digest_match"]
    assert result["rederived_sha256"] is None
    assert any(row["check"].startswith("D3") for row in result["failures"])


def test_verify_requires_a_bundle_not_a_stored_report(native_pair):
    _bundle, record = native_pair
    with pytest.raises(ConversionError) as error:
        eio_agents.verify(record, {"archive_schema": 2})
    assert error.value.code == "BUNDLE_INPUT"


def test_convert_input_errors_are_typed():
    for source in (b"{not json", b"[]"):
        with pytest.raises(ConversionError) as error:
            eio_agents.convert(source)
        assert error.value.code == "BUNDLE_INPUT"
    for source in (str(BUNDLE), BUNDLE, "does-not-exist.json", 3):
        with pytest.raises(TypeError, match="bytes or a dict"):
            eio_agents.convert(source)
    with pytest.raises(FileNotFoundError):
        eio_agents.convert_file(BUNDLE.with_name("missing.json"), BUNDLE.with_name("never-written.json"))


def test_validate_bundle_and_convert_fail_closed_on_invalid_native_states(native_pair):
    original, _record = native_pair
    bundle = copy.deepcopy(original)
    bundle["claims"][0]["state"] = "MAYBE"
    assert any(row["check"].startswith("B3") for row in validate_bundle(bundle))
    with pytest.raises(ConversionError):
        eio_agents.convert(_restamp(bundle))
    assert validate_bundle({"archive_schema": 2})[0]["check"].startswith("B0")


def test_explain_returns_only_registered_native_renderings(native_pair):
    _bundle, record = native_pair
    finding = record["findings"][0]
    assert eio_agents.explain(record, finding["finding_id"]) == finding["explanation"]["summary"]
    assert eio_agents.explain(record, "release_recommendation") == record["release_recommendation"]["explanation"]["summary"]
    with pytest.raises(LookupError):
        eio_agents.explain(record, "eio.metric.no-such-metric")


def test_native_convert_loads_no_legacy_or_harness_module():
    code = f"""
import sys, eio_agents
from pathlib import Path
bundle = Path({str(BUNDLE)!r}).read_bytes()
record = eio_agents.convert(bundle)
assert eio_agents.verify(record, bundle)["valid"]
print(sorted(module for module in sys.modules if module.startswith(("eio_agents._legacy", "eio_agents._vendored", "proofagent_harness"))))
"""
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert completed.stdout.strip() == "[]"
