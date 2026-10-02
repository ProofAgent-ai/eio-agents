"""Standalone privacy contract over a native schema-3 producer.

Historical producer-specific cases are preserved in the external adapter
compatibility corpus. These tests deliberately use only the
packaged neutral ontology and a hand-authored native bundle.
"""

import copy
import hashlib
import json
import random
from pathlib import Path

import pytest

import eio_agents
from eio_agents.base.errors import ConversionError
from eio_agents.per import privacy as PV
from eio_agents.per.bundle import stage_digest
from eio_agents.per.catalogue_split import validate_record_catalogues
from eio_agents.schemas import per_schema
from eio_agents.validation import privacy as TW
from eio_agents.validation.reader import EIO, EIO_DIR


NATIVE = Path(__file__).parent / "data" / "native" / "v0_6/native.bundle.json"
MARKER = "zqxjvwmarkerkqzv"


@pytest.fixture(scope="module")
def native_pair(eio):
    bundle = json.loads(NATIVE.read_text(encoding="utf-8"))
    record = eio_agents.convert(copy.deepcopy(bundle), ontology=eio)
    assert eio_agents.validate(record) == []
    return bundle, record


@pytest.fixture(scope="module")
def reader():
    return EIO(EIO_DIR)


@pytest.fixture(scope="module")
def catalogue(native_pair):
    return validate_record_catalogues(native_pair[1])


def _codes(eio, record, producer=frozenset()):
    return {code for code, _ in PV.problems(eio, record, producer)}


def _restamp(bundle):
    for stage in bundle["stage_records"]:
        stage["output_sha256"] = stage_digest(bundle, stage["sections"])
    return bundle


def test_fingerprint_is_exact_utf8_sha256_and_display_is_short():
    for value in ("acme/support-llm-2", "Café", "Café", ""):
        expected = "sha256-" + hashlib.sha256(value.encode("utf-8")).hexdigest()
        assert PV.fingerprint(value) == TW.fingerprint(value) == expected
        assert len(expected) == 71
    assert PV.fingerprint("Café") != PV.fingerprint("Café")
    fingerprint = PV.fingerprint("x")
    assert PV.display(fingerprint) == TW.shown(fingerprint) == fingerprint[:19]


def test_native_record_seals_producer_names_and_validates(eio, reader, catalogue, native_pair):
    bundle, record = native_pair
    assert record["subject"]["agent"]["model"] == PV.fingerprint(bundle["provenance"]["agent"]["model"])
    assert record["subject"]["agent"]["agent_id"] == PV.fingerprint(bundle["provenance"]["agent"]["agent_id"])
    assert PV.problems(eio, record) == []
    assert TW.record_problems(record, reader, catalogue) == []
    assert eio_agents.validate(record) == []
    result = eio_agents.verify(record, bundle, ontology=eio)
    assert result["valid"] and result["digest_match"]


def test_unknown_record_path_fails_closed_in_both_privacy_checkers(eio, reader, catalogue, native_pair):
    _, record = native_pair
    bad = copy.deepcopy(record)
    bad["subject"]["agent"]["goal_note"] = PV.fingerprint(MARKER)
    assert "PRIVACY_UNCLASSIFIED" in _codes(eio, bad)
    with pytest.raises(ConversionError) as error:
        PV.check(eio, bad)
    assert error.value.code == "PRIVACY_UNCLASSIFIED"
    assert any("subject.agent.goal_note" in row for row in TW.record_problems(bad, reader, catalogue))


def test_unlisted_map_member_name_fails_closed(eio, reader, catalogue, native_pair):
    _, record = native_pair
    bad = copy.deepcopy(record)
    bad["scope"]["facts"]["the_" + MARKER] = {"value": None, "source": PV.fingerprint("x")}
    assert "PRIVACY_UNCLASSIFIED" in _codes(eio, bad)
    assert any("member name" in row and MARKER in row for row in TW.record_problems(bad, reader, catalogue))


@pytest.mark.parametrize("field", ["agent_id", "model"])
def test_clear_producer_identity_cannot_enter_record(eio, reader, catalogue, native_pair, field):
    bundle, record = native_pair
    bad = copy.deepcopy(record)
    bad["subject"]["agent"][field] = bundle["provenance"]["agent"][field]
    assert _codes(eio, bad)
    assert TW.record_problems(bad, reader, catalogue)
    assert eio_agents.validate(bad)


def test_fingerprint_in_structural_state_is_not_accepted(eio, reader, catalogue, native_pair):
    _, record = native_pair
    bad = copy.deepcopy(record)
    bad["claims"][0]["state"] = PV.fingerprint("APPLICABLE_PASS")
    assert "BUNDLE_VOCABULARY" in _codes(eio, bad)
    assert TW.record_problems(bad, reader, catalogue)


def test_unbound_fingerprint_fails_bundle_rederivation(eio, native_pair):
    bundle, record = native_pair
    bad = copy.deepcopy(record)
    bad["subject"]["agent"]["model"] = PV.fingerprint("a different model")
    result = eio_agents.verify(bad, bundle, ontology=eio)
    assert not result["valid"] and not result["digest_match"]
    assert any(row["check"].startswith("D2") for row in result["failures"])


def test_converter_and_verifier_use_same_closed_table_and_vocabulary(eio, reader):
    assert PV.TABLE == TW.TABLE
    assert PV.OPEN_MAPS == TW.OPEN and PV.SORTED_LISTS == TW.RESORTED
    assert len(PV.TABLE) > 350
    converter, verifier = PV.vocabulary(eio), TW.words(reader)
    assert converter.release == verifier.release
    assert converter.layout == verifier.layout
    assert converter.vocab == verifier.vocab
    assert converter.labels == verifier.labels
    assert converter.check_names == verifier.checks


def test_schema_string_paths_are_classified_or_explicitly_fail_closed():
    """Keep a ledger of schema leaves W1 deliberately rejects until safe policies exist."""
    schema = per_schema()
    definitions = schema["$defs"]
    paths = set()

    def walk(node, path=(), depth=0):
        assert depth <= 14, path
        if not isinstance(node, dict):
            return
        if "$ref" in node:
            walk(definitions[node["$ref"].split("/")[-1]], path, depth + 1)
        variants = [node]
        for key in ("allOf", "anyOf", "oneOf"):
            variants.extend(child for child in node.get(key, []) if isinstance(child, dict))
        for variant in variants:
            typ = variant.get("type")
            if typ == "string" or isinstance(typ, list) and "string" in typ:
                paths.add(path)
            if isinstance(variant.get("const"), str) or any(isinstance(x, str) for x in variant.get("enum", [])):
                paths.add(path)
            for key, child in (variant.get("properties") or {}).items():
                walk(child, path + (key,), depth + 1)
            if isinstance(variant.get("items"), dict):
                walk(variant["items"], path + ("*",), depth + 1)
            for child in variant.get("prefixItems") or []:
                walk(child, path + ("*",), depth + 1)
            if isinstance(variant.get("additionalProperties"), dict):
                walk(variant["additionalProperties"], path + ("<key>",), depth + 1)
            for child in (variant.get("patternProperties") or {}).values():
                walk(child, path + ("<key>",), depth + 1)
            for key in ("then", "else"):
                if key in variant:
                    walk(variant[key], path, depth + 1)

    walk(schema)
    classified = {PV.gpath(path) for path in paths if "params" not in path}
    missing = classified - PV.TABLE.keys()
    intentionally_unclassified = {
        "claims.*.parameters.source_key",  # historical adapter-only key
        "header.declared_limitation_catalogues.*.id",
        "header.declared_limitation_catalogues.*.limitations.*.id",
        "header.declared_limitation_catalogues.*.limitations.*.impact",
        "header.declared_limitation_catalogues.*.limitations.*.next_step",
        "header.declared_limitation_catalogues.*.limitations.*.paths.*",
        "header.declared_limitation_catalogues.*.limitations.*.raised_when",
        "header.declared_limitation_catalogues.*.limitations.*.reason",
        "header.declared_limitation_catalogues.*.limitations.*.status",
        "header.declared_limitation_catalogues.*.sha256",
        "header.declared_limitation_catalogues.*.version",
        "header.declared_template_catalogues.*.id",
        "header.declared_template_catalogues.*.sha256",
        "header.declared_template_catalogues.*.templates.*.id",
        "header.declared_template_catalogues.*.templates.*.text",
        "header.declared_template_catalogues.*.version",
        "provenance.inputs.scenarios.selected.*",  # producer-declared adapter data
        "provenance.inputs.scenarios.selected_digest",
    }
    assert {".".join(path) for path in missing} == intentionally_unclassified


def test_decided_field_sealing_matches_independent_verifier(eio, reader):
    converter, verifier = PV.vocabulary(eio), TW.words(reader)
    rng = random.Random(31)
    pool = sorted(converter.labels)[:40] + sorted(converter.release)[:200:5] + [
        "1.2.3", "01.2.3", "sha256:" + "a" * 64, "/sources/turns", MARKER, "", "Café", "a b",
    ]
    specs = sorted({spec for spec in PV.TABLE.values() if spec[0] in ("ad", "bd", "d")}, key=str)
    assert specs and pool
    for _ in range(1000):
        spec, value = rng.choice(specs), rng.choice(pool)
        assert PV.seal_value(converter, spec, value) == TW.decide(verifier, spec, value)


def test_native_bundle_to_record_decisions_match_twin(eio, reader, native_pair):
    bundle, record = native_pair
    words = TW.words(reader)
    clear_view, problems, clear = TW.clear_view(record, bundle)
    assert clear_view and problems == []
    seen = 0
    for path, value in TW.strings(record):
        spec = TW.TABLE[TW.gen(path)]
        if spec[0] in ("d", "ad", "bd"):
            source_text = clear.get(path, value)
            assert TW.decide(words, spec, source_text) == value
            assert PV.seal_value(PV.vocabulary(eio), spec, source_text) == value
            seen += 1
    assert seen > 20
    assert TW.decision_problems(record, clear, reader) == []
    assert TW.singleton_problems(record, bundle, reader) == []


@pytest.mark.parametrize("source_path,record_path", [
    (("provenance", "agent", "agent_id"), ("subject", "agent", "agent_id")),
    (("provenance", "agent", "model"), ("subject", "agent", "model")),
    (("provenance", "producer", "name"), ("provenance", "producer", "name")),
])
def test_native_identity_marker_is_sealed_but_locally_resolvable(eio, native_pair, source_path, record_path):
    original, _ = native_pair
    bundle = copy.deepcopy(original)
    source = bundle
    for part in source_path[:-1]:
        source = source[part]
    source[source_path[-1]] = MARKER
    if source_path == ("provenance", "producer", "name"):
        bundle["provenance"]["record"]["producer"]["name"] = MARKER
    _restamp(bundle)
    try:
        record = eio_agents.convert(bundle, ontology=eio)
    except ConversionError as error:
        assert error.code  # fail closed is acceptable for an invalid producer identity
        return
    target = record
    for part in record_path:
        target = target[part]
    assert target == PV.fingerprint(MARKER)
    assert MARKER not in json.dumps(record)
    rows = eio_agents.resolve(record, bundle)
    assert any(row["text"] == MARKER and row["fingerprint"] == target for row in rows)
    assert eio_agents.verify(record, bundle, ontology=eio)["digest_match"]


def test_local_resolution_does_not_change_public_record(eio, native_pair):
    bundle, record = native_pair
    before = eio_agents.canonical_bytes(record)
    rows = eio_agents.resolve(record, bundle)
    assert rows
    assert all(row["text"] is not None and PV.fingerprint(row["text"]) == row["fingerprint"] for row in rows)
    assert eio_agents.canonical_bytes(record) == before


def test_resolver_rejects_non_json_bundle_with_typed_error(native_pair):
    _, record = native_pair
    with pytest.raises(ConversionError) as error:
        eio_agents.resolve(record, {"archive_schema": 3, "bad": "\ud800"})
    assert error.value.code == "BUNDLE_INPUT"
