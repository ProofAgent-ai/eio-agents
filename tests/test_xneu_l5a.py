"""Focused tests for the L5a neutral-release scan, before the release batch."""
import importlib.util
import sys
from pathlib import Path

import pytest

from eio_agents.validation.checker import VER6

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("xneu_l5a", ROOT / "tools/xneu_l5a.py")
xneu = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = xneu
SPEC.loader.exec_module(xneu)


def test_scan_detects_branded_schema_property_and_text(tmp_path):
    path = tmp_path / "test.schema.json"
    doc = {"properties": {"harness_llm": {"description": "Harness LLM result"}}}
    issues = xneu._scan_doc(path, tmp_path, doc, schema=True)
    assert {item.rule for item in issues} == {"branded schema/context term", "ProofAgent-specific release text or IRI"}


def test_scan_detects_branded_jsonld_term(tmp_path):
    path = tmp_path / "per.jsonld"
    issues = xneu._scan_doc(path, tmp_path, {"@context": {"per:harness_llm": "https://example.test/model"}}, schema=True)
    assert {item.rule for item in issues} == {"branded schema/context term", "non-neutral JSON-LD term IRI"}


def test_scan_detects_bare_brand_name(tmp_path):
    path = tmp_path / "module.yaml"
    assert xneu._scan_doc(path, tmp_path, {"description": "Distributed with ProofAgent"})


def test_scan_accepts_neutral_schema_words(tmp_path):
    path = tmp_path / "test.schema.json"
    doc = {"$id": "https://w3id.org/eio-agents/schema/0.5.0/test.schema.json",
           "properties": {"evaluator_models": {"description": "Models used in the evaluation."}}}
    assert xneu._scan_doc(path, tmp_path, doc, schema=True) == []


def test_scan_accepts_publisher_uri_but_not_branded_prose(tmp_path):
    path = tmp_path / "candidate.jsonld"
    assert xneu._scan_doc(path, tmp_path, {"@context": {"eiop": "https://www.proofagent.ai/eio-agents/prop/"}}, schema=True) == []
    assert xneu._scan_doc(path, tmp_path, {"description": "ProofAgent-specific result"})


def test_historical_rc1_schema_is_not_in_candidate_set():
    source = Path(xneu.__file__).read_text(encoding="utf-8")
    assert 'per_schemas / "per-2.0.0-rc2-draft.schema.json"' in source
    assert 'per_schemas / "per-2.0.schema.json"' not in source


def test_current_isolated_candidate_has_no_xneu_findings():
    issues = xneu.scan(ROOT)
    assert issues == []


def test_verifier_statement_uses_neutral_model_name():
    assert "evaluator model" in VER6
    assert "harness LLM" not in VER6


@pytest.mark.parametrize(
    ("document", "schema"),
    [
        ({"mappings": [{"source": "legacy.check.obeyed_injected_instruction"}]}, False),
        ({"stages": [{"harness_node": "planner"}]}, False),
        ({"scoring": {"legacy_profiles": ["eio.profile.old"]}}, False),
        ({"profiles": [{"id": "eio.profile.pai-decision-principle"}]}, False),
        ({"profiles": [{"id": "eio.profile.legacy-scoring-harness-2x"}]}, False),
        ({"@context": {"claim": "https://example.invalid/eio/id/claim"}}, True),
    ],
    ids=[
        "legacy-id",
        "harness-node-key",
        "legacy-profiles-key",
        "pai-id-segment",
        "harness-profile-document",
        "non-neutral-term-iri",
    ],
)
def test_required_xneu_classes_are_detected(tmp_path, document, schema):
    """Pin concrete §6.1 X-NEU rules without altering the non-loadable candidate."""
    path = tmp_path / ("candidate.jsonld" if schema else "candidate.yaml")
    assert xneu._scan_doc(path, tmp_path, document, schema=schema)


def test_loaded_module_references_fail_closed():
    doc = {"imports": [{"module": "eio.core.entities"}, {"module": "eio.mapping.moved"}]}
    issues = xneu._missing_module_refs(doc, "module.yaml", {"eio.core.entities"})
    assert [(item.location, item.rule) for item in issues] == [
        ("$/imports/1/module", "unloaded module reference eio.mapping.moved")
    ]


def test_standard_external_jsonld_vocabularies_are_not_ours(tmp_path):
    path = tmp_path / "candidate.jsonld"
    doc = {"@context": {"xsd": "http://www.w3.org/2001/XMLSchema#",
                        "dct": "http://purl.org/dc/terms/",
                        "eiop": "https://w3id.org/eio-agents/prop/"}}
    assert xneu._scan_doc(path, tmp_path, doc, schema=True) == []


def test_pai_prose_and_profile_reference_are_not_misclassified(tmp_path):
    path = tmp_path / "candidate.yaml"
    doc = {"description": "PAI-aware margin used by the old release.",
           "scoring": {"fraction_definitions": [{"id": "eio.profile.legacy-scoring-harness-2x"}]}}
    assert xneu._scan_doc(path, tmp_path, doc) == []
