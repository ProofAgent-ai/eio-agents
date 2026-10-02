"""Neutral core and self-contained, digest-pinned third-party declarations."""

import copy
import json
from pathlib import Path

import pytest

from eio_agents.base.errors import ConversionError
from eio_agents.api import convert, validate, verify
from eio_agents.ontology import Ontology
from eio_agents.validation.reader import EIO
from eio_agents.per.catalogue_split import (
    catalogue_sha256,
    embed_catalogue,
    load_core_limitations,
    merge_catalogues,
    migrate_rc1_core_row,
    render_limitation_row,
    verify_limitation_row,
    validate_record_catalogues,
)
from eio_agents.per.native_preview import verify_native_preview

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_EIO_DATA = ROOT / "src/eio_agents/ontology/data"


def _declared_catalogue():
    """Synthetic third-party declaration; no producer-specific preview is needed."""
    return embed_catalogue({
        "id": "vendor.eio.lim",
        "version": "1.0.0",
        "limitations": [{
            "id": "vendor.eio.lim.run_id.not_captured",
            "status": "NOT_CAPTURED",
            "paths": ["/provenance/run/run_id"],
            "raised_when": "synthetic test bundle lacks a run id",
            "reason": "The run id was not captured.",
            "impact": "This record cannot be linked to a specific run.",
            "next_step": "Record the run id in producer provenance.",
        }],
    })


def _sample(row):
    return {
        "limitation_id": row["id"],
        "field_path": row["paths"][0].replace("{ref}", "ref1").replace("{finding_id}", "finding1"),
        "status": row["status"],
        "reason": row["reason"].replace("{hits}", "2").replace("{calls}", "1").replace("{total}", "3"),
        "impact": row["impact"],
        "next_step": row["next_step"],
    }


def test_core_declared_split_is_exact_and_neutral():
    core = load_core_limitations()
    adapter = _declared_catalogue()
    assert len(core["limitations"]) == 26
    assert len(adapter["limitations"]) == 1
    assert all(row["id"].startswith("per.lim.") for row in core["limitations"])
    assert all(row["id"].startswith("vendor.eio.lim.") for row in adapter["limitations"])
    assert "proofagent" not in json.dumps(core).lower()
    assert adapter["sha256"] == catalogue_sha256(adapter)
    merged = merge_catalogues(core, {"declared_limitation_catalogues": [adapter]}, kind="limitations")
    assert len(merged) == 27


def test_declared_rows_validate_without_adapter_install():
    core = load_core_limitations()
    adapter = _declared_catalogue()
    merged = merge_catalogues(core, {"declared_limitation_catalogues": [adapter]}, kind="limitations")
    row = adapter["limitations"][0]
    verify_limitation_row(_sample(row), merged)
    with pytest.raises(ConversionError, match="UNKNOWN_LIMITATION"):
        verify_limitation_row({**_sample(row), "limitation_id": "vendor.undeclared.lim"}, merged)


def test_per_header_is_sufficient_to_validate_declared_adapter_row():
    adapter = _declared_catalogue()
    row = _sample(adapter["limitations"][0])
    record = {"header": {"declared_limitation_catalogues": [adapter]}, "limitations": [row]}
    assert row["limitation_id"] in validate_record_catalogues(record)
    record["header"]["declared_limitation_catalogues"] = []
    with pytest.raises(ConversionError, match="UNKNOWN_LIMITATION"):
        validate_record_catalogues(record)


def test_digest_collision_namespace_and_text_fail_closed():
    core = load_core_limitations()
    adapter = _declared_catalogue()
    header = {"declared_limitation_catalogues": [adapter]}
    altered = copy.deepcopy(adapter)
    altered["limitations"][0]["reason"] += " altered"
    with pytest.raises(ConversionError, match="CATALOGUE_DIGEST"):
        merge_catalogues(core, {"declared_limitation_catalogues": [altered]}, kind="limitations")
    colliding = copy.deepcopy(adapter)
    colliding["limitations"][0]["id"] = core["limitations"][0]["id"]
    colliding = embed_catalogue({k: v for k, v in colliding.items() if k != "sha256"})
    with pytest.raises(ConversionError, match="CATALOGUE_ID|CATALOGUE_COLLISION"):
        merge_catalogues(core, {"declared_limitation_catalogues": [colliding]}, kind="limitations")
    with pytest.raises(ConversionError, match="CATALOGUE_COLLISION"):
        merge_catalogues(core, {"declared_limitation_catalogues": [adapter, adapter]}, kind="limitations")
    merged = merge_catalogues(core, header, kind="limitations")
    wrong_text = _sample(adapter["limitations"][0])
    wrong_text["impact"] = "Unrelated"
    with pytest.raises(ConversionError, match="LIMITATION_TEXT"):
        verify_limitation_row(wrong_text, merged)


def test_template_declaration_uses_same_digest_and_collision_rules():
    core = {"id": "eio.why.core", "version": "2.0.0-rc2-draft", "templates": [
        {"id": "eio.why.generic@1", "text": "Value {value}", "params": ["value"], "max_length": 600}
    ]}
    declared = embed_catalogue({"id": "vendor.why", "version": "1.0.0", "templates": [
        {"id": "vendor.why.special@1", "text": "Special {value}", "params": ["value"], "max_length": 600}
    ]})
    merged = merge_catalogues(core, {"declared_template_catalogues": [declared]}, kind="templates")
    assert set(merged) == {"eio.why.generic@1", "vendor.why.special@1"}
    assert "vendor.why.special@1" not in merge_catalogues(core, {}, kind="templates")


def test_limitation_placeholders_cannot_launder_producer_free_text():
    core = merge_catalogues(load_core_limitations(), {}, kind="limitations")
    lid = "per.lim.severity.none"
    path = "/findings/4f8b54fd10edb0bcd760/severity"
    private = "customer@example.org secret case note"
    with pytest.raises(ConversionError, match="LIMITATION_PARAM"):
        render_limitation_row(core, lid, path=path, predicate=private)
    valid = render_limitation_row(core, lid, path=path, predicate="eio.predicate.authority-or-deadline-invented")
    bad = {**valid, "reason": f"No in-scope coverage obligation targets {private}."}
    with pytest.raises(ConversionError, match="LIMITATION_TEXT"):
        verify_limitation_row(bad, core)
    old = next(row for row in json.loads((ROOT / "src/eio_agents/per/data/limitations.json").read_text())["limitations"]
               if row["id"] == lid)
    old_row = {**valid, "reason": old["reason"].format(predicate=private),
               "next_step": old["next_step"].format(predicate=private)}
    with pytest.raises(ConversionError, match="LIMITATION_PARAM"):
        migrate_rc1_core_row(old_row, old, core)


def test_native_preview_core_rows_pass_and_tamper_fails_closed():
    """The isolated candidate's pinned ontology and native bundle are one release."""
    ontology = Ontology(CANDIDATE_EIO_DATA)
    bundle = json.loads((ROOT / "tests/data/native/v0_6/native.bundle.json").read_text(encoding="utf-8"))
    record = convert(bundle, ontology=ontology)
    assert all(row["limitation_id"] in validate_record_catalogues(record) for row in record["limitations"])
    assert validate(record, eio=EIO(ontology.root)) == []
    assert verify(record, bundle, ontology=ontology)["valid"] is True
    assert verify_native_preview(record, bundle, ontology=ontology)["valid"]
    bad = copy.deepcopy(record)
    bad["limitations"][0]["next_step"] = "Not the pinned core catalogue text"
    assert validate(bad, eio=EIO(ontology.root))
    assert verify(bad, bundle, ontology=ontology)["valid"] is False
    assert verify_native_preview(bad, bundle, ontology=ontology)["valid"] is False


def test_active_rc2_header_checks_declared_catalogue_digest_collision_and_privacy():
    ontology = Ontology(CANDIDATE_EIO_DATA)
    bundle = json.loads((ROOT / "tests/data/native/v0_6/native.bundle.json").read_text(encoding="utf-8"))
    record = convert(bundle, ontology=ontology)
    adapter = _declared_catalogue()
    declared = copy.deepcopy(record)
    declared["header"]["declared_limitation_catalogues"] = [adapter]
    problems = validate(declared, eio=EIO(ontology.root))
    assert not any(row["check"].startswith("S1 ") for row in problems)  # active rc2 schema accepts the header field
    assert not any(row["check"].startswith("T1 ") for row in problems)  # digest-pinned declaration is understood
    assert any(row["check"].startswith("W1 ") for row in problems)  # arbitrary declaration text is not privacy-approved

    changed = copy.deepcopy(declared)
    changed["header"]["declared_limitation_catalogues"][0]["limitations"][0]["reason"] += " changed"
    assert any(row["check"].startswith("T1 ") for row in validate(changed, eio=EIO(ontology.root)))

    duplicated = copy.deepcopy(declared)
    duplicated["header"]["declared_limitation_catalogues"].append(adapter)
    assert any(row["check"].startswith("T1 ") for row in validate(duplicated, eio=EIO(ontology.root)))

    unknown = copy.deepcopy(record)
    unknown["limitations"][0]["limitation_id"] = "vendor.undeclared.lim"
    assert any(row["check"].startswith("T1 ") for row in validate(unknown, eio=EIO(ontology.root)))

    core_template_id = next(iter(EIO(ontology.root).templates))
    templ = embed_catalogue({"id": "vendor.why", "version": "1.0.0", "templates": [
        {"id": core_template_id, "text": "Private customer@example.org", "params": [], "max_length": 100}
    ]})
    template_collision = copy.deepcopy(record)
    template_collision["header"]["declared_template_catalogues"] = [templ]
    assert any(row["check"].startswith("T1 ") for row in validate(template_collision, eio=EIO(ontology.root)))

    distinct = embed_catalogue({"id": "vendor.why", "version": "1.0.0", "templates": [
        {"id": "vendor.why.special@1", "text": "Private customer@example.org", "params": [], "max_length": 100}
    ]})
    template_declared = copy.deepcopy(record)
    template_declared["header"]["declared_template_catalogues"] = [distinct]
    valid_structure = validate(template_declared, eio=EIO(ontology.root))
    assert not any(row["check"].startswith("S1 ") or row["check"].startswith("T1 ") for row in valid_structure)
    assert any(row["check"].startswith("W1 ") for row in valid_structure)
    template_tampered = copy.deepcopy(template_declared)
    template_tampered["header"]["declared_template_catalogues"][0]["templates"][0]["text"] += " altered"
    assert any(row["check"].startswith("T1 ") for row in validate(template_tampered, eio=EIO(ontology.root)))
