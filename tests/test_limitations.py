"""Neutral core and content-addressed producer limitation catalogues."""

import copy
import json
from pathlib import Path

import pytest

from eio_agents.api import convert
from eio_agents.base.errors import ConversionError
from eio_agents.per.catalogue_split import (
    embed_catalogue,
    load_core_limitations,
    merge_catalogues,
    render_limitation_row,
    validate_record_catalogues,
    verify_limitation_row,
)


NATIVE = Path(__file__).parent / "data/native/v0_6/native.bundle.json"
ROW_FIELDS = {"id", "status", "paths", "raised_when", "reason", "impact", "next_step"}


def _declared():
    return embed_catalogue(
        {
            "id": "producer.synthetic.lim",
            "version": "1.0.0",
            "limitations": [
                {
                    "id": "producer.synthetic.lim.source_missing",
                    "status": "NOT_CAPTURED",
                    "paths": ["/provenance/producer/source"],
                    "raised_when": "synthetic source was not captured",
                    "reason": "The synthetic source was not recorded.",
                    "impact": "Source-level reproduction is limited.",
                    "next_step": "Record a source identifier.",
                }
            ],
        }
    )


def test_core_catalogue_rows_are_unique_typed_and_merge_without_declarations():
    core = load_core_limitations()
    assert core["id"] == "per.lim.core"
    rows = core["limitations"]
    ids = [row["id"] for row in rows]
    assert rows and len(ids) == len(set(ids))
    assert all(identifier.startswith("per.lim.") for identifier in ids)
    assert all(set(row) == ROW_FIELDS for row in rows)
    merged = merge_catalogues(core, {}, kind="limitations")
    assert set(merged) == set(ids)


def test_declared_catalogue_is_content_addressed_and_rows_are_verifiable():
    core = load_core_limitations()
    declaration = _declared()
    header = {"declared_limitation_catalogues": [declaration]}
    merged = merge_catalogues(core, header, kind="limitations")
    lid = "producer.synthetic.lim.source_missing"
    assert set(merged) == {row["id"] for row in core["limitations"]} | {lid}
    row = render_limitation_row(merged, lid)
    verify_limitation_row(row, merged)
    tampered = copy.deepcopy(declaration)
    tampered["limitations"][0]["reason"] = "Changed without re-signing."
    with pytest.raises(ConversionError, match="CATALOGUE_DIGEST"):
        merge_catalogues(core, {"declared_limitation_catalogues": [tampered]}, kind="limitations")
    with pytest.raises(ConversionError, match="CATALOGUE_COLLISION"):
        merge_catalogues(core, {"declared_limitation_catalogues": [declaration, declaration]}, kind="limitations")


def test_native_record_limitation_rows_verify_without_external_catalogue():
    bundle = json.loads(NATIVE.read_text(encoding="utf-8"))
    record = convert(bundle)
    merged = validate_record_catalogues(record)
    assert all(row["limitation_id"] in merged for row in record["limitations"])
    forged = copy.deepcopy(record)
    forged["limitations"][0]["limitation_id"] = "producer.undeclared.lim.unknown"
    with pytest.raises(ConversionError, match="UNKNOWN_LIMITATION"):
        validate_record_catalogues(forged)


def test_limitation_parameters_reject_free_text():
    merged = merge_catalogues(load_core_limitations(), {}, kind="limitations")
    with pytest.raises(ConversionError, match="LIMITATION_PARAM"):
        render_limitation_row(merged, "per.lim.anchor.no_quote", ref="a private name", turn=3)
