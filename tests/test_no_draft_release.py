"""Release gate: EIO-Agents 0.8.0 produces nothing that says "draft" (owner request, extending decision #46).

Every `convert` route (a source-complete native bundle, a native bundle without scoring inputs, an adapter bundle, a
legacy `bundle_draft` 2 bundle and each example converter's output), `build_bundle`, `eio-agents version`,
`standards()` and the help of every CLI subcommand are serialized and searched for "draft"; the only allowed
occurrence is the JSON Schema dialect URL. Legacy draft bundles and records stay valid and verifiable, read-only.
"""
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

import eio_agents
from eio_agents import cli
from eio_agents.api import _legacy_convert
from eio_agents.per.bundle import stage_digest
from eio_agents.schemas import BUNDLE_SCHEMA, BUNDLE_SCHEMA_ID, PER_SCHEMA_2_1_0, bundle_schema
from eio_agents.validation import validate_bundle
from released_version import library_version

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "tests" / "data" / "native"
CURRENT = NATIVE / "v0_8"
LEGACY = NATIVE / "legacy_draft2"
EXAMPLES = ROOT / "examples"
DIALECT = "https://json-schema.org/draft/2020-12/schema"
PER_2_1_0_ID = "https://www.proofagent.ai/eio-agents/schema/per/2.1.0/per.schema.json"
SUBCOMMANDS = ("project", "validate", "verify", "explain", "evidence", "resolve", "predicates", "version")


def drafts(value) -> list[str]:
    """Every "draft" in the serialized value, with context, outside the JSON Schema dialect URL."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = text.replace(DIALECT, "")
    low = text.lower()
    out, i = [], low.find("draft")
    while i != -1:
        out.append(text[max(0, i - 60): i + 20])
        i = low.find("draft", i + 1)
    return out


def adapter_bundle() -> dict:
    """A bundle of an adapter producer (provenance and every stage record say adapter), from the native vector."""
    b = json.loads((CURRENT / "native.bundle.json").read_text(encoding="utf-8"))
    b["provenance"]["producer"]["kind"] = "adapter"
    for stage in b["stage_records"]:
        stage["producer"] = "adapter"
    for stage in b["stage_records"]:
        stage["output_sha256"] = stage_digest(b, stage["sections"])
    return b


def _module(path: Path):
    spec = importlib.util.spec_from_file_location("no_draft_" + "_".join(path.parent.parts[-2:]), path)
    module = importlib.util.module_from_spec(spec)
    before, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = before
    return module


def example_bundles() -> dict[str, dict]:
    """The bundle each example converter writes from its own input."""
    out = {}
    custom = _module(EXAMPLES / "custom_report" / "convert.py")
    out["custom_report"] = custom.to_bundle(json.loads((EXAMPLES / "custom_report" / "my_report.json").read_text("utf-8")))
    out["native/proofagent"] = _module(EXAMPLES / "native" / "proofagent" / "run_eval.py").evaluate()[0]
    deepeval = _module(EXAMPLES / "adapters" / "deepeval" / "convert.py")
    out["adapters/deepeval"] = deepeval.to_bundle(*deepeval.load(str(EXAMPLES / "adapters" / "deepeval" / "test_run.json")))
    for name, data in (("inspect_ai", "eval_log.json"), ("otel_genai", "traces.json"), ("promptfoo", "results.json")):
        module = _module(EXAMPLES / "adapters" / name / "convert.py")
        out[f"adapters/{name}"] = module.to_bundle(json.loads((EXAMPLES / "adapters" / name / data).read_text("utf-8")))
    return out


def routes() -> dict[str, dict]:
    bundles = {
        "native source-complete": json.loads((CURRENT / "source-complete.bundle.json").read_text(encoding="utf-8")),
        "native without scoring inputs": json.loads((CURRENT / "native.bundle.json").read_text(encoding="utf-8")),
        "native cited": json.loads((CURRENT / "synthetic-cited-native.bundle.json").read_text(encoding="utf-8")),
        "adapter": adapter_bundle(),
        "legacy bundle_draft 2, without scoring inputs": json.loads((LEGACY / "native.bundle.json").read_text("utf-8")),
        "legacy bundle_draft 2, source-complete": json.loads((LEGACY / "source-complete.bundle.json").read_text("utf-8")),
    }
    if (EXAMPLES / "custom_report" / "convert.py").is_file():          # an unpacked sdist has no examples/
        bundles.update({f"example {k}": v for k, v in example_bundles().items()})
    return bundles


ROUTES = routes()


@pytest.mark.parametrize("name", sorted(ROUTES))
def test_every_route_emits_a_verifiable_per_2_1_0_without_draft(name):
    bundle = ROUTES[name]
    record = eio_agents.convert(copy.deepcopy(bundle))
    assert record["header"]["per_version"] == "2.1.0"
    assert record["header"]["schema_uri"] == PER_2_1_0_ID
    assert record["header"]["release_semantics"] == record["release_recommendation"]["semantics"] == "2.2"
    assert drafts(eio_agents.canonical_bytes(record).decode("utf-8")) == []
    assert eio_agents.validate(record) == []
    result = eio_agents.verify(record, bundle)
    assert result["valid"] and result["digest_match"], result["failures"]
    if record["scores"] is None:                    # no scoring inputs: no score is guessed, and the reason is stated
        assert any(row["limitation_id"] == "per.lim.scoring_profile.none" and row["field_path"] == "/scores"
                   for row in record["limitations"])
        assert record["release_recommendation"]["state"] in ("REVIEW", "BLOCK")       # readiness withheld: never PASS
    if "legacy" not in name:                        # every new bundle carries the released bundle format
        assert bundle.get("bundle_version") == "3.0.0" and "bundle_draft" not in bundle
        assert drafts(bundle) == []


def test_routes_cover_native_unscored_adapter_and_examples():
    kinds = {(b["provenance"]["producer"]["kind"], b.get("native_scoring") is not None) for b in ROUTES.values()}
    assert {("native", True), ("native", False), ("adapter", False)} <= kinds
    if (EXAMPLES / "custom_report" / "convert.py").is_file():
        assert sum(name.startswith("example ") for name in ROUTES) == 6


def test_build_bundle_writes_the_released_bundle_format():
    report = json.loads((ROOT / "tests" / "data" / "report" / "travel_report.json").read_text(encoding="utf-8"))
    from build_reference import build_arguments                                # the report -> build_bundle arguments
    bundle = eio_agents.build_bundle(**build_arguments(report))
    assert bundle["bundle_version"] == "3.0.0" and "bundle_draft" not in bundle
    assert drafts(bundle) == []
    assert validate_bundle(bundle) == []
    record = eio_agents.convert(bundle)
    assert record["header"]["per_version"] == "2.1.0" and drafts(record) == []


def test_version_standards_and_help_say_no_draft(capsys):
    standards = eio_agents.standards()
    assert drafts(standards) == []
    assert standards["per_version"] == "2.1.0" and standards["per_schema_id"] == PER_2_1_0_ID
    assert standards["bundle_version"] == "3.0.0" and standards["bundle_schema_id"] == BUNDLE_SCHEMA_ID
    assert cli.main(["version"]) == 0
    out = capsys.readouterr().out
    assert drafts(out) == [] and json.loads(out)["per_version"] == "2.1.0"
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    texts = [capsys.readouterr().out]
    for cmd in SUBCOMMANDS:
        with pytest.raises(SystemExit):
            cli.main([cmd, "--help"])
        texts.append(capsys.readouterr().out)
    assert all(t.startswith("usage: eio-agents") for t in texts)
    assert [drafts(t) for t in texts] == [[]] * len(texts)


def test_the_current_schemas_say_no_draft_beyond_the_dialect():
    for path in (PER_SCHEMA_2_1_0, BUNDLE_SCHEMA):
        assert drafts(path.read_text(encoding="utf-8")) == [], path.name
    assert bundle_schema()["$id"] == BUNDLE_SCHEMA_ID == "urn:eio-agents:schema:bundle:3.0.0"
    assert hashlib.sha256(PER_SCHEMA_2_1_0.read_bytes()).hexdigest() == (
        "b014591877aeef1821d3f1da5bc7a3a75516abc60033f2d91a16cbc08aca8219")          # the PER 2.1.0 schema is unchanged


# ---------------------------------------------------------------- legacy, read-only

LEGACY_SHA256 = {
    "native.bundle.json": "64a20b27985a241622cfdce791c5445a40d1237416e895ae6152353b0cd7e8fa",
    "native.per.jcs": "1af8da7f1fe681b2d60ccecf681e9fa8a7c850a7c56ca7390500ec92ebb471f6",
    "source-complete.bundle.json": "3867d8f2eded2d4d7b3b70fb0d469325c55626de0d4c5dc5b89ff34d7a115389",
    "source-complete.per.jcs": "8ea058de14e379fcca8478cbba89c6a9682826eb039f62b6080d1cabd37c1177",
}


def test_legacy_draft_bundles_and_records_still_validate_and_verify():
    for name, digest in LEGACY_SHA256.items():
        assert hashlib.sha256((LEGACY / name).read_bytes()).hexdigest() == digest, name
    for stem in ("native", "source-complete"):
        bundle_bytes = (LEGACY / f"{stem}.bundle.json").read_bytes()
        assert json.loads(bundle_bytes)["bundle_draft"] == 2
        assert validate_bundle(bundle_bytes) == []                  # read byte for byte with its pinned schema
        record = json.loads((LEGACY / f"{stem}.per.jcs").read_bytes())
        assert eio_agents.validate(record) == []
        with library_version("0.8.0"):                              # re-derived under the version that issued it
            result = eio_agents.verify(record, bundle_bytes)
        assert result["valid"] and result["digest_match"], (stem, result["failures"])
    rc3 = json.loads((LEGACY / "native.per.jcs").read_bytes())
    assert rc3["header"]["per_version"] == "2.0.0-rc3-draft"       # the legacy identity it was issued with
    # the same legacy bundle converts to PER 2.1.0 today
    assert eio_agents.convert((LEGACY / "native.bundle.json").read_bytes())["header"]["per_version"] == "2.1.0"
    published = json.loads((NATIVE / "v0_6" / "source-complete.per.jcs").read_bytes())
    assert published["header"]["per_version"] == "2.0.0" and eio_agents.validate(published) == []
    for path in sorted((NATIVE / "v0_6").glob("*.bundle.json")):
        assert validate_bundle(path.read_bytes()) == [], path.name


def test_a_new_bundle_never_selects_a_legacy_record_identity():
    bundle = json.loads((CURRENT / "native.bundle.json").read_text(encoding="utf-8"))
    legacy_shaped = _legacy_convert(copy.deepcopy(bundle))           # what the pre-0.8.0 routing would have produced
    assert legacy_shaped["header"]["per_version"] == "2.0.0-rc3-draft"
    result = eio_agents.verify(legacy_shaped, bundle)
    assert not result["valid"] and not result["digest_match"]


def test_a_forged_unscored_per_2_1_0_is_rejected():
    bundle = json.loads((CURRENT / "native.bundle.json").read_text(encoding="utf-8"))
    record = eio_agents.convert(copy.deepcopy(bundle))
    assert record["scores"] is None and record["release_recommendation"]["state"] == "REVIEW"
    forgeries = []
    passed = copy.deepcopy(record)
    passed["release_recommendation"]["state"], passed["release_recommendation"]["decisive"] = "PASS", []
    forgeries.append(passed)
    dropped = copy.deepcopy(record)
    dropped["release_recommendation"]["decisive"].pop()
    forgeries.append(dropped)
    unexplained = copy.deepcopy(record)
    unexplained["limitations"] = [row for row in unexplained["limitations"] if row["field_path"] != "/scores"]
    forgeries.append(unexplained)
    scored = copy.deepcopy(record)
    scored["scores"] = json.loads((CURRENT / "source-complete.per.jcs").read_bytes())["scores"]
    forgeries.append(scored)
    for forged in forgeries:
        assert eio_agents.validate(forged) != []
        assert not eio_agents.verify(forged, bundle)["valid"]
