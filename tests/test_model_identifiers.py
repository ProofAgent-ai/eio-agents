"""Model identifiers (0.8.0, a privacy-rule change approved by the maintainer): in the fields that name a model, a model
identifier with its release date or version is accepted by the shape backstop and kept in clear in the record; every
other field, and a model value that is not a model identifier, keeps the full rule."""
import copy
import importlib
import json
import re
from pathlib import Path

import pytest

import eio_agents
from build_reference import build_arguments
from eio_agents import ConversionError, build_bundle

bundle_rules = importlib.import_module("eio_agents.per.bundle")
projector_privacy = importlib.import_module("eio_agents.per.privacy")
verifier_privacy = importlib.import_module("eio_agents.validation.privacy")
verifier_validate = importlib.import_module("eio_agents.validation.validate")

REPORT = json.loads((Path(__file__).parent / "data" / "report" / "travel_report.json").read_text(encoding="utf-8"))
ACCEPTED = ["gpt-4o-2024-08-06", "claude-sonnet-4-5-20250929", "anthropic/claude-opus-4-1@20250805",
            "meta-llama/Llama-3.1-70B-Instruct", "mistral-large-2411", "gemini-2.5-pro-preview-05-06", "openai:gpt-4o",
            "acme/support-llm-2"]
REFUSED = ["john.doe@example.com", "0123456789abcdef0123456789abcdef", "user:secret@host", "my model",
           "a8F3k2L9q0Z7x1C5v6B4n2M8p0", "x" * 101]
SENSITIVE_MODEL_SHAPES = ["john-123-45-6789", "sk-live-abcdefgh", "pk-live-abcdefgh",
                          "ghp_abcdefghijk", "glpat-abcdefgh",
                          "4111-1111-1111-1111"]


def test_the_projector_and_the_verifier_hold_the_same_pattern():
    assert bundle_rules.MODEL_ID == verifier_privacy.MODEL_ID_PATTERN == verifier_validate._MODEL_ID.pattern
    assert (projector_privacy.BD_FORMS["model"].pattern == verifier_privacy.STRICT["model"].pattern
            == bundle_rules.MODEL_ID)
    assert projector_privacy.TABLE == verifier_privacy.TABLE
    assert projector_privacy.TABLE[("subject", "agent", "model")] == ("bd", "model")
    assert projector_privacy.TABLE[("claims", "*", "provenance", "model")] == ("bd", "model")
    assert projector_privacy.TABLE[("subject", "ai_bom", "components", "*", "name")] == ("md", "model")
    assert projector_privacy.TABLE[("subject", "agent", "agent_id")] == ("d", None)


@pytest.mark.parametrize("value", ACCEPTED)
def test_model_identifiers_match(value):
    assert re.fullmatch(bundle_rules.MODEL_ID, value)


@pytest.mark.parametrize("value", REFUSED)
def test_other_values_do_not(value):
    assert not re.fullmatch(bundle_rules.MODEL_ID, value)


@pytest.mark.parametrize("value", SENSITIVE_MODEL_SHAPES)
def test_a_model_shaped_sensitive_token_is_not_a_public_identifier(value):
    assert re.fullmatch(bundle_rules.MODEL_ID, value)  # the broad syntax alone is insufficient
    assert not bundle_rules.safe_model_identifier(value)
    assert not verifier_privacy.safe_model_identifier(value)
    args = copy.deepcopy(build_arguments(REPORT))
    args["agent"]["model"] = value
    with pytest.raises(ConversionError) as caught:
        build_bundle(**args)
    assert caught.value.code == "BUILD_PERSONAL_DATA" and "agent['model']" in str(caught.value)


def _built(model, jury_model=None, **changes):
    args = copy.deepcopy(build_arguments(REPORT))
    args["agent"]["model"] = model
    args["checks"].append({"turn": 2, "predicate": "prohibited-part-clearly-refused", "decided_by": "semantic",
                           "model": jury_model or model, "quote": "I can only manage bookings made in your own name.",
                           "jury": [{"persona": "strict", "observed": True}, {"persona": "lenient", "observed": True}]})
    for path, value in changes.items():
        target = args
        *head, last = path.split(".")
        for part in head:
            target = target[int(part)] if part.isdigit() else target[part]
        target[last] = value
    bundle = build_bundle(**args)
    record = eio_agents.convert(bundle)
    result = eio_agents.verify(record, bundle)
    assert result["valid"] and result["digest_match"], result["failures"]
    return bundle, record


@pytest.mark.parametrize("model", ACCEPTED[:6])
def test_a_dated_model_is_accepted_and_kept_in_clear(model):
    bundle, record = _built(model)
    assert record["subject"]["agent"]["model"] == model
    rows = record["subject"]["ai_bom"]["components"]
    assert [r["name"] for r in rows if r["kind"] == "machine-learning-model"] == [model]
    assert all(r["name"].startswith("sha256-") for r in rows if r["kind"] != "machine-learning-model")   # file names
    assert [c["provenance"]["model"] for c in record["claims"] if c["decided_by"] == "semantic"] == [model]
    assert record["subject"]["agent"]["agent_id"].startswith("sha256-")
    assert model not in {row["text"] for row in eio_agents.resolve(record, bundle)}        # nothing left to resolve


def test_a_value_that_is_not_a_model_identifier_stays_fingerprinted():
    bundle, record = _built("Acme Support Model", jury_model="Acme Jury")
    assert record["subject"]["agent"]["model"] == projector_privacy.fingerprint("Acme Support Model")
    assert next(c for c in record["claims"] if c["decided_by"] == "semantic")["provenance"]["model"] == \
        projector_privacy.fingerprint("Acme Jury")
    texts = {row["text"] for row in eio_agents.resolve(record, bundle)}
    assert {"Acme Support Model", "Acme Jury"} <= texts


@pytest.mark.parametrize("field, value, where", [
    ("agent", {"id": "bot-12345", "version": "1.0.0", "model": "gpt-4o-2024-08-06"}, "agent['id']"),
    ("agent", {"id": "travel-bot", "version": "1.0.0", "model": "john.doe@example.com"}, "agent['model']"),
    ("agent", {"id": "travel-bot", "version": "1.0.0", "model": "0123456789abcdef0123456789abcdef"}, "agent['model']"),
])
def test_identifying_values_are_still_refused(field, value, where):
    args = copy.deepcopy(build_arguments(REPORT))
    args[field] = value
    with pytest.raises(ConversionError) as caught:
        build_bundle(**args)
    assert caught.value.code == "BUILD_PERSONAL_DATA" and where in str(caught.value)


def test_a_date_outside_a_model_field_keeps_the_full_rule():
    args = copy.deepcopy(build_arguments(REPORT))
    args["turns"][0]["tools"][0]["name"] = "search_2024_08_06"
    with pytest.raises(ConversionError, match="turn 1, tool call 0: 'name'"):
        build_bundle(**args)


def test_a_clear_model_value_in_the_record_must_be_a_model_identifier(eio):
    _, record = _built("gpt-4o-2024-08-06")
    bad = copy.deepcopy(record)
    bad["subject"]["agent"]["model"] = "Acme Support Model"
    assert any(code == "PER_INVALID" and "subject/agent/model" in detail
               for code, detail in projector_privacy.problems(eio, bad))
    assert eio_agents.validate(bad)


@pytest.mark.parametrize("value", SENSITIVE_MODEL_SHAPES)
def test_a_record_with_a_clear_sensitive_model_fails_independent_validation(value):
    _, record = _built("acme/support-llm-2")
    bad = copy.deepcopy(record)
    bad["subject"]["agent"]["model"] = value
    assert any("subject/agent/model" in str(failure) for failure in eio_agents.validate(bad))
