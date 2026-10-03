"""X-NATIVE, L2 form (split plan §6.1): a hand-authored synthetic bundle from a native producer.

`tests/data/native/v0_8/native.bundle.json` is written by `author_native.py` with EIO-Agents builders only. It must pass
`validate_bundle == []`, then `convert`, then `verify` with a digest match. Under rc1, `validate(rec)` returns exactly the
pinned list of rc1-only problems, each naming the §5.3 row that removes it (`v0_8/native.rc1_problems.json`); the expected PER
bytes are pinned in `v0_8/native.per.jcs`. From L5a the list is empty (rc2-draft). The suite runs in the install-alone job
(`venv-eioagents`, where `proofagent_harness` is not importable), and one test projects the bundle with the staging area
blocked.
"""
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

import eio_agents
from eio_agents.per import bundle as B
from eio_agents.per.conformance import rc1_only
from eio_agents.validation import validate_bundle

NATIVE = Path(__file__).parent / "data" / "native"
BUNDLE = NATIVE / "v0_8/native.bundle.json"
HISTORICAL_BUNDLE = NATIVE / "native.bundle.json"


def _author():
    spec = importlib.util.spec_from_file_location("author_native", NATIVE / "author_native.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def bundle():
    return json.loads(BUNDLE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rec(bundle):
    return eio_agents.convert(copy.deepcopy(bundle))


def _historical_record_bytes(rec):
    """Compare all bytes to the immutable vector, excluding only the installed converter release."""
    historical_version = json.loads((NATIVE / "v0_8/native.per.jcs").read_bytes())["header"]["converter"]["version"]
    historical = copy.deepcopy(rec)
    header = historical["header"]
    header["converter"]["version"] = historical_version
    header["per_semantics_version"] = (
        f"2@{historical_version}+eio{header['eio']['release']}.{header['eio']['ontology_digest']}"
    )
    return eio_agents.canonical_bytes(historical)


def test_the_vector_is_what_the_author_script_writes(bundle):
    """Regenerated with EIO-Agents only (never with harness code); the files are the script's output."""
    mod = _author()
    fresh = mod.author(version=bundle["header"]["eio_agents"]["version"])
    assert fresh == bundle
    body, _ = mod.pinned(fresh)
    assert _historical_record_bytes(json.loads(body)) == (NATIVE / "v0_8/native.per.jcs").read_bytes()


def test_the_bundle_is_native(bundle):
    text = json.dumps(bundle).lower()
    assert "proofagent" not in text and "harness" not in text
    assert bundle["provenance"]["producer"]["kind"] == "native" and bundle["provenance"]["producer"]["name"] == "acme-evals"
    assert {r["producer"] for r in bundle["stage_records"]} == {"native"}
    assert "producer_declared" not in bundle                      # no scenario labels, capability rows or score inputs
    h = bundle["header"]
    assert h["crosswalk"] is None and h["adapter"] is None and h["source_archive"] is None
    assert "catalogue" not in text and "extensions" not in text
    for c in bundle["claims"]:
        assert set(c["parameters"]) <= {"fidelity", "votes"} and c["parameters"]["fidelity"] in ("exact", "narrower")
        assert "legacy_check" not in c["parameters"] and "source_key" not in c["parameters"]     # the id slot is null
    assert all(r["source_type"] != "JUROR_INFERENCE" for r in bundle["graph"]["refs"])


def test_validate_bundle_is_empty(bundle):
    assert validate_bundle(bundle) == []
    assert validate_bundle(BUNDLE.read_bytes()) == []


def test_historical_0_5_bundle_bytes_are_preserved_and_fail_closed():
    old = HISTORICAL_BUNDLE.read_bytes()
    assert hashlib.sha256(old).hexdigest() == "12a212d955be08e8371de00486b294f9ec776885e9e86a8915c1434bbf1ec305"
    assert validate_bundle(old)[0]["status"] == "FAIL"
    with pytest.raises(eio_agents.ConversionError) as error:
        eio_agents.convert(old)
    assert error.value.code == "BUNDLE_RECOMPUTE"


def test_convert_gives_the_pinned_bytes(rec):
    assert rec["header"]["converter"]["version"] == eio_agents.__version__
    assert rec["header"]["per_semantics_version"].startswith(f"2@{eio_agents.__version__}+eio")
    assert _historical_record_bytes(rec) == (NATIVE / "v0_8/native.per.jcs").read_bytes()
    assert rec["scores"] is None                                   # no scoring profile
    assert rec["header"]["archive_schema"] == 3 and "adjudication_source" not in rec["header"]
    assert all(t["scenario"] is None for t in rec["evidence"]["turns"])
    assert rec["evidence"]["archive_pointer"] == {"turns": "/sources/turns", "archive_sha256": rec["header"]["archive_sha256"]}


def test_verify_has_a_digest_match(bundle, rec):
    r = eio_agents.verify(rec, BUNDLE.read_bytes())
    assert r["digest_match"] and r["per_sha256"] == r["rederived_sha256"]
    assert r["failures"] == []


def test_native_rc2_validates_without_rc1_relaxations(rec):
    assert eio_agents.validate(rec) == []


NARROWED = {  # review M-2: (the exact rc1 error its §5.3 row removes, a wider error the old ".*" row accepted)
    ("claims/1/parameters/votes", "anyOf"): (
        "{'distinct_pairs': 3, 'observed': 3, 'not_observed': 0, 'split': 0} is not valid under any of the given schemas",
        "{'distinct_pairs': 3, 'observed': 3, 'not_observed': 0, 'split': 0, 'bogus': 42} is not valid under any of the given schemas"),
    ("evidence/archive_pointer", "additionalProperties"): (
        "Additional properties are not allowed ('turns' was unexpected)",
        "Additional properties are not allowed ('../elsewhere' was unexpected)"),
    ("evidence/refs/1/tool/arguments_pointer", "pattern"): (
        "'/sources/turns/0/tool_calls/0/arguments' does not match "
        "'^/transcript/(0|[1-9][0-9]*)/tools_called/(0|[1-9][0-9]*)/(arguments|args)$'",
        "'/anything' does not match '^/transcript/(0|[1-9][0-9]*)/tools_called/(0|[1-9][0-9]*)/(arguments|args)$'"),
    ("findings/0/traps", "minItems"): ("[] should be non-empty", "[] is too short"),
    ("header/archive_schema", "enum"): ("3 is not one of [1, 2]", "99 is not one of [1, 2]"),
    ("provenance/producer", "additionalProperties"): (
        "Additional properties are not allowed ('name', 'version' were unexpected)",
        "Additional properties are not allowed ('evil', 'name', 'version' were unexpected)"),
    ("provenance/run/run_id_source", "enum"): (
        "'producer' is not one of ['harness', 'archive_digest']", "'banana' is not one of ['harness', 'archive_digest']"),
}


@pytest.mark.parametrize("row", list(NARROWED))
def test_each_relaxation_row_accepts_only_its_exact_rc1_error(row):
    """Review M-2: no row of `per/data/rc1_only.json` accepts any message; each accepts the rc1 error of its §5.3 row. The
    pointer rows accept pointers into the bundle only: the projector requires a native bundle's pointers to resolve into
    its own `/sources` (tests/test_bundle.py `INVALID`, the M-2 entries)."""
    path, validator = row
    exact, wider = NARROWED[row]
    assert rc1_only(path, validator, exact) and rc1_only(path, validator, exact).startswith("§5.3")
    assert rc1_only(path, validator, wider) is None


def test_no_relaxation_row_accepts_any_message():
    from eio_agents.per.conformance import rc1_only_rows
    for path, validator, msg, _row, _applies in rc1_only_rows():
        assert msg.pattern != ".*$" and not msg.match("anything goes"), (path.pattern, validator)


def test_validate_bundle_checks_the_native_producer_rules(bundle):
    """A native bundle declares no source archive and has native stage records only (review M-2, L-6)."""
    b = copy.deepcopy(bundle)
    b["header"]["source_archive"] = {"archive_schema": 2, "archive_sha256": "sha256:" + "ab" * 32}
    b["stage_records"][0]["producer"] = "adapter"
    [row] = validate_bundle(b)
    assert row["check"].startswith("B2") and row["detail"].startswith("2 problem(s); first: a native bundle declares a source archive")


def test_the_proof_rule_requires_a_verified_claim_citation(bundle, rec):
    """The new draft does not upgrade a native FAIL just because fidelity is exact."""
    [f] = rec["findings"]
    assert (f["predicate"], f["fidelity"], f["proof_status"]) == ("eio.predicate.authority-or-deadline-invented", "narrower", "UNPROVEN")
    b = copy.deepcopy(bundle)
    c = next(c for c in b["claims"] if c["state"] == "APPLICABLE_FAIL")
    c["parameters"]["fidelity"] = "exact"
    for r in b["stage_records"]:
        r["output_sha256"] = B.stage_digest(b, r["sections"])
    [f] = eio_agents.convert(b)["findings"]
    assert (f["fidelity"], f["proof_status"]) == ("exact", "UNPROVEN")


def test_the_native_path_loads_no_staging_module():
    """The install-alone form: project, validate and verify the native bundle with `proofagent_harness`,
    `eio_agents._legacy`, `eio_agents._vendored` (deleted at L4; kept blocked as a guard) and `eio_agents.api` unimportable."""
    code = f"""
import sys
class Block:
    def find_spec(self, name, path=None, target=None):
        if name.startswith(("eio_agents._legacy", "eio_agents._vendored", "proofagent_harness")) or name == "eio_agents.api":
            raise ImportError("blocked " + name)
sys.meta_path.insert(0, Block())
from pathlib import Path
import copy
import json
import eio_agents
from eio_agents.per import canonical_bytes
from eio_agents.per.native_preview import project_native_preview
from eio_agents.ontology import load
from eio_agents import validation
b = Path({str(BUNDLE)!r}).read_bytes()
ontology = load()
rec = project_native_preview(b, ontology=ontology)
golden = Path({str(NATIVE / 'v0_8/native.per.jcs')!r}).read_bytes()
historical_version = json.loads(golden)["header"]["converter"]["version"]
assert rec["header"]["converter"]["version"] == eio_agents.__version__
historical = copy.deepcopy(rec)
historical["header"]["converter"]["version"] = historical_version
h = historical["header"]
h["per_semantics_version"] = f"2@{{historical_version}}+eio{{h['eio']['release']}}.{{h['eio']['ontology_digest']}}"
assert canonical_bytes(historical) == golden
assert validation.validate_bundle(b) == []
r = validation.verify(rec, b, rederived=project_native_preview(b, ontology=ontology))
assert r["digest_match"] and r["failures"] == []
print(sorted(m for m in sys.modules if m.startswith(("eio_agents._", "eio_agents.api", "proofagent_harness"))))
"""
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "[]"
