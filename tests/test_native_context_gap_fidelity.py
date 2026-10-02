"""A context-gap has no claim mapping; only behavioural findings have one."""
import copy
import json
from pathlib import Path

from eio_agents import convert, validate, verify
from eio_agents.base.canon import H
from eio_agents.ontology import load
from eio_agents.per import bundle as B
from eio_agents.validation.checker import Checker
from eio_agents.validation.reader import EIO, load_catalogue

DATA = Path(__file__).parent / "data/native/v0_6/native.bundle.json"


def _context_bundle():
    bundle = json.loads(DATA.read_text(encoding="utf-8"))
    name, content = "policy.md", "Synthetic customer data policy."
    bundle["sources"]["context_artifacts"].append({
        "artifact_kind": "eio.artifact.knowledge-source", "name": name,
        "sha256": H(content.encode("utf-8")), "code_points": len(content),
        "embedded": True, "data_class": "eio.data.public",
    })
    bundle["sources"]["context_texts"][name] = content
    bundle["sources"]["context_artifacts"].append({
        "artifact_kind": "eio.artifact.knowledge-source", "name": "not_embedded.md",
        "sha256": H(b"An external policy."), "code_points": 19,
        "embedded": False, "data_class": "eio.data.public",
    })
    bundle["context_assessment"] = {"gaps": [{
        "criterion": "eio.context.guardrail-coverage", "control": "personal-data",
        "files_searched": [name, "not_embedded.md"],
        "chars_searched": len(content) + 5, "terms": ["pii"],
    }]}
    bundle["provenance"]["record"]["inputs"]["context_artifacts"] = copy.deepcopy(
        bundle["sources"]["context_artifacts"])
    for stage in bundle["stage_records"]:
        stage["output_sha256"] = B.stage_digest(bundle, stage["sections"])
    return bundle


def test_context_gap_has_null_fidelity_and_independent_validation():
    bundle, ontology = _context_bundle(), load()
    record = convert(bundle, ontology=ontology)
    gaps = [finding for finding in record["findings"] if finding["kind"] == "CONTEXT_GAP"]
    assert len(gaps) == 1
    assert gaps[0]["claim_ids"] == [] and gaps[0]["fidelity"] is None
    assert validate(record, eio=EIO(ontology.root)) == []
    result = verify(record, bundle, ontology=ontology)
    assert result["valid"] and result["digest_match"], result["failures"]


def test_context_gap_cannot_claim_mapping_and_behavioural_cannot_have_null():
    ontology = load()
    record = convert(_context_bundle(), ontology=ontology)
    eio, catalogue = EIO(ontology.root), load_catalogue()
    gap = next(f for f in record["findings"] if f["kind"] == "CONTEXT_GAP")
    gap["fidelity"] = "exact"
    assert validate(record, eio=eio)
    checker = Checker(record, eio, catalogue, "native")
    problems, _ = checker.c_findings()
    assert any("CONTEXT_GAP member fidelity must be None" in problem for problem in problems)

    record = convert(_context_bundle(), ontology=ontology)
    behavioural = next(f for f in record["findings"] if f["kind"] == "BEHAVIOURAL")
    behavioural["fidelity"] = None
    assert validate(record, eio=eio)
