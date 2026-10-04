"""EIO-Agents 0.8.1: declared evaluator models reach the record, and a producer can disclose an explicitly empty set of
prohibited tools with the catalogue limitation `per.lim.tool_policy.empty`. Each test fails on 0.8.0."""
import copy
import json
from pathlib import Path

import pytest

import eio_agents
from eio_agents import ConversionError, canonical_bytes, convert, validate, verify
from eio_agents.base import version as library
from eio_agents.per.catalogue_split import load_core_limitations, merge_catalogues, verify_limitation_row
from eio_agents.validation import validate_bundle
from full_native_score_case import reseal_stages

DATA = Path(__file__).parent / "data/native/v0_8"
STEMS = ("native", "source-complete")
MODELS = [{"role": "planner", "model": "openai/gpt-4.1-nano"},
          {"role": "jury", "model": "fake/test"},
          {"role": "semantic_decider", "model": None}]
TOOL_POLICY_EMPTY = "per.lim.tool_policy.empty"


def _bundle(stem, *, models=None, limitations=()):
    """A 0.8 vector bundle restamped by this library version, with optional evaluator models and producer limitations."""
    bundle = json.loads((DATA / f"{stem}.bundle.json").read_text(encoding="utf-8"))
    bundle["header"]["eio_agents"]["version"] = library.VERSION
    if models is not None:
        bundle["provenance"]["telemetry"]["evaluator_models"] = copy.deepcopy(models)
    bundle["limitations"].extend(copy.deepcopy(list(limitations)))
    return reseal_stages(bundle)


def _checked(bundle):
    assert validate_bundle(json.dumps(bundle).encode("utf-8")) == []
    record = convert(bundle)
    assert validate(record) == []
    result = verify(record, bundle)
    assert result["valid"] and result["digest_match"], result["failures"]
    return record


# ------------------------------------------------------------------------------------------------- evaluator models
@pytest.mark.parametrize("stem", STEMS)
def test_declared_evaluator_models_reach_the_record_and_verify(stem):
    record = _checked(_bundle(stem, models=MODELS))
    telemetry = record["telemetry"]["evaluator_models"]
    provenance = record["provenance"]["evaluator_models"]
    # every declared row in telemetry, in declared order; the model in clear, the role sealed as a label
    assert [row["model"] for row in telemetry] == ["openai/gpt-4.1-nano", "fake/test", None]
    assert all(row["role"].startswith("sha256-") for row in telemetry)
    assert len({row["role"] for row in telemetry}) == 3
    # provenance keeps the rows that name a model (PER 2.1.0 requires a model string there)
    assert provenance == [row for row in telemetry if row["model"] is not None]
    assert [row["model"] for row in provenance] == ["openai/gpt-4.1-nano", "fake/test"]


@pytest.mark.parametrize("stem", STEMS)
def test_evaluator_models_are_bound_by_the_digest(stem):
    bundle = _bundle(stem, models=MODELS)
    record = convert(bundle)
    forged = copy.deepcopy(record)
    forged["telemetry"]["evaluator_models"][0]["model"] = "fake/other"
    forged["provenance"]["evaluator_models"][0]["model"] = "fake/other"
    result = verify(forged, bundle)
    assert not result["digest_match"] and not result["valid"]


@pytest.mark.parametrize("models", [None, []])
def test_no_declared_evaluator_models_keeps_empty_lists(models):
    record = _checked(_bundle("native", models=models))
    assert record["telemetry"]["evaluator_models"] == [] and record["provenance"]["evaluator_models"] == []


@pytest.mark.parametrize("models", [[{"role": "jury"}], [{"role": "jury", "model": ""}],
                                    [{"role": "jury", "model": "fake/test", "temperature": 0}]])
def test_malformed_evaluator_models_fail_closed(models):
    with pytest.raises(ConversionError) as error:
        convert(_bundle("native", models=models))
    assert error.value.code == "BUNDLE_INPUT"


# ----------------------------------------------------------------------------------- empty tool-prohibition set
def test_empty_tool_prohibition_limitation_is_a_core_catalogue_row():
    core = {row["id"]: row for row in load_core_limitations()["limitations"]}
    row = core[TOOL_POLICY_EMPTY]
    assert row["status"] == "NOT_SUPPLIED" and row["paths"] == ["/coverage/obligations"]
    assert row["reason"] == "The producer declared no prohibited tools."
    assert "empty set" in row["impact"] and "Forbidden-tool obligations" in row["impact"]
    rc1 = {r["id"]: r for r in json.loads((Path(eio_agents.__file__).parent / "per/data/limitations.json")
                                          .read_text(encoding="utf-8"))["limitations"]}
    assert rc1[TOOL_POLICY_EMPTY] == row                                 # the projector's catalogue says the same


@pytest.mark.parametrize("stem", STEMS)
@pytest.mark.parametrize("path", [None, "/coverage/obligations"])
def test_producer_discloses_an_empty_tool_prohibition_set(stem, path):
    bundle = _bundle(stem, limitations=[{"id": TOOL_POLICY_EMPTY, "path": path, "params": {}}])
    record = _checked(bundle)
    rows = [row for row in record["limitations"] if row["limitation_id"] == TOOL_POLICY_EMPTY]
    assert rows == [{"limitation_id": TOOL_POLICY_EMPTY, "field_path": "/coverage/obligations", "status": "NOT_SUPPLIED",
                     **{k: v for k, v in load_core_limitations_row().items() if k in ("reason", "impact", "next_step")}}]
    assert record["limitations"] == sorted(record["limitations"], key=lambda r: (r["field_path"], r["limitation_id"]))


def test_empty_tool_prohibition_row_rejects_freehand_text_and_other_paths():
    catalogue = merge_catalogues(load_core_limitations(), {}, kind="limitations")
    row = {"limitation_id": TOOL_POLICY_EMPTY, "field_path": "/coverage/obligations", "status": "NOT_SUPPLIED",
           **{k: v for k, v in load_core_limitations_row().items() if k in ("reason", "impact", "next_step")}}
    verify_limitation_row(row, catalogue)
    for bad in ({**row, "reason": "The producer prohibited nothing at all."}, {**row, "field_path": "/scores"},
                {**row, "status": "NOT_CAPTURED"}):
        with pytest.raises(ConversionError):
            verify_limitation_row(bad, catalogue)
    with pytest.raises(ConversionError):
        convert(_bundle("native", limitations=[{"id": TOOL_POLICY_EMPTY, "path": "/scores", "params": {}}]))


def load_core_limitations_row():
    return next(row for row in load_core_limitations()["limitations"] if row["id"] == TOOL_POLICY_EMPTY)


# ------------------------------------------------------------------------------ the patch release changes no projection
@pytest.mark.parametrize("stem", STEMS)
def test_the_0_8_vectors_differ_at_this_version_in_the_library_stamp_only(stem):
    """The pinned 0.8.0 records re-derive byte for byte under their own stamp (test_current_release_fixtures); at this
    version the record differs only in the converter version, the semantics version and the score digests over them."""
    bundle_bytes = (DATA / f"{stem}.bundle.json").read_bytes()
    pinned = json.loads((DATA / f"{stem}.per.jcs").read_bytes())
    record = json.loads(canonical_bytes(convert(bundle_bytes)))
    assert record["header"]["converter"]["version"] == eio_agents.__version__ == library.VERSION
    assert validate(record) == []
    assert verify(record, bundle_bytes)["digest_match"]

    def changed(a, b, at=""):
        if isinstance(a, dict) and isinstance(b, dict) and set(a) == set(b):
            return [p for k in a for p in changed(a[k], b[k], f"{at}/{k}")]
        if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
            return [p for i, (x, y) in enumerate(zip(a, b)) for p in changed(x, y, f"{at}/{i}")]
        return [] if a == b else [at]

    allowed = {"/header/converter/version", "/header/per_semantics_version", "/scores/score_sha256",
               "/scores/score_basis_sha256"}
    diff = set(changed(pinned, record))
    assert {"/header/converter/version", "/header/per_semantics_version"} <= diff <= allowed
