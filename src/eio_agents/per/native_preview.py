"""The internal neutral null-score projection, routed by the packaged API.

The historical projector first enforces bundle/stage/privacy rules. This
finalization then expresses its result in the neutral rc3 shape, validated
against the legacy rc3 schema. It is an intermediate: `eio_agents.convert`
turns it into PER 2.1.0 (`native_full_wire`), and the rc3 identity is returned
as is only to re-derive legacy records already issued.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from eio_agents.base.version import VERSION
from eio_agents.base.canon import H, jb, sd
from eio_agents.base.errors import ConversionError, require
from eio_agents.ontology import load as load_ontology
from eio_agents.per import bundle as B
from eio_agents.per.catalogue_split import (
    RC1_TO_CORE_ID,
    load_core_limitations,
    merge_catalogues,
    migrate_rc1_core_row,
    validate_record_catalogues,
)
from eio_agents.per.limitations import CATALOGUE as RC1_LIMITATIONS
from eio_agents.per.privacy import decisive_entry_text, gate_reason_text, vocabulary
from eio_agents.per.projection import project
from eio_agents.semantics import why as sem_why

SCHEMA_URI = "urn:eio-agents:diagnostic:per:2.0.0-rc3-neutral-preview"
PUBLIC_RC3_SCHEMA_URI = "https://w3id.org/eio-agents/per/2.0.0-rc3-draft/per.schema.json"
# Exact spelling is a proposal for owner review, not a stable published id.
NO_SCORING_PROFILE_ID = "per.lim.scoring_profile.none"
PREVIEW_SCHEMA = Path(__file__).resolve().parents[1] / "schemas/per/per-2.0.0-rc3-neutral-preview.schema.json"
PUBLIC_RC3_SCHEMA = Path(__file__).resolve().parents[1] / "schemas/per/per-2.0.0-rc3-draft.schema.json"


def _admit_jury_consensus(schema):
    """This internal projection's schema with the one rule PER 2.1.1 changes: a PROVEN finding may be decided by a jury
    consensus (`semantic`, EIO-Agents 0.8.4). Applied in memory to a projection holding such a finding, which is then
    finalized to PER 2.1.1; the published rc3 schemas are never changed."""
    then = schema["$defs"]["finding"]["allOf"][3]["then"]["properties"]["decided_by"]
    require(then == {"enum": ["deterministic", "human"]}, "NATIVE_PREVIEW_SCHEMA", "unexpected PROVEN proof rule")
    then["enum"] = ["deterministic", "human", "semantic"]
    return schema


def _replace_ids(value, old_to_new: dict[str, str]):
    if isinstance(value, dict):
        return {key: _replace_ids(item, old_to_new) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_ids(item, old_to_new) for item in value]
    return old_to_new.get(value, value) if isinstance(value, str) else value


def _evaluator_models(telemetry: dict) -> list[dict]:
    """The evaluator models the bundle declares in `provenance.telemetry.evaluator_models`, as the projection carried
    them (the role sealed as a label, the model in clear): `{model, role}` each, in declared order, the model null when
    the producer names none for that role. No declaration gives an empty list. The record's provenance keeps the rows
    that name a model (PER 2.1.0 requires one there); its telemetry keeps every declared row."""
    models = telemetry.get("evaluator_models")
    if models is None:
        return []
    require(isinstance(models, list) and all(
        isinstance(m, dict) and set(m) == {"role", "model"} and isinstance(m["role"], str) and m["role"] != ""
        and (m["model"] is None or (isinstance(m["model"], str) and m["model"] != "")) for m in models),
        "BUNDLE_INPUT", "provenance.telemetry.evaluator_models must be a list of {role, model} objects, the role a "
        "non-empty string and the model a non-empty string or null")
    return [{"model": m["model"], "role": m["role"]} for m in models]


def _neutralize(old: dict, bundle: dict, ontology) -> dict:
    rec = copy.deepcopy(old)
    head = rec["header"]
    policy_rules = (bundle["scope"]["policy"] or {}).get("rules") or {}
    head["schema_uri"] = SCHEMA_URI if policy_rules.get("min_score") is not None else PUBLIC_RC3_SCHEMA_URI
    head["converter"] = {"name": "eio_agents.convert", "version": VERSION}
    head["per_semantics_version"] = f"2@{VERSION}+eio{head['eio']['release']}.{head['eio']['ontology_digest']}"
    head.pop("adjudication_source", None)

    producer = bundle["provenance"]["producer"]
    rec["provenance"]["producer"]["kind"] = producer["kind"]
    models = _evaluator_models(rec["telemetry"])
    rec["provenance"]["evaluator_models"] = [m for m in models if m["model"] is not None]
    rec["telemetry"]["evaluator_models"] = models
    rec["provenance"]["inputs"].pop("traps", None)
    rec["provenance"]["inputs"].pop("checks_version", None)
    rec["provenance"]["run"].pop("config_fingerprint", None)
    rec["telemetry"].pop("harness_llm", None)

    fidelity = {c["id"]: c["parameters"]["fidelity"] for c in bundle["claims"]}
    ids: dict[str, str] = {}
    for claim in rec["claims"]:
        old_id = claim["id"]
        params = claim["parameters"]
        params["source_key"] = params.pop("legacy_check", None)
        params["fidelity"] = fidelity[old_id]
        params["scenario"] = params.pop("trap", None)
        params.pop("mapping_relation", None)
        params.pop("legacy_decided_by", None)
        params.pop("state_source", None)
        if params["votes"] is not None:
            params["votes"].pop("archive_observed", None)
            params["votes"].pop("archive_total", None)
        ids[old_id] = sd({"run_id": claim["run_id"], "predicate": claim["predicate"],
                          "predicate_version": claim["predicate_version"],
                          "source_key": params["source_key"],
                          "turn_indices": sorted(claim["turn_indices"])})
    require(len(set(ids.values())) == len(ids), "NATIVE_PREVIEW", "neutral claim id collision")
    rec = _replace_ids(rec, ids)
    # Claim IDs embedded inside rendered decisive-list strings are not standalone
    # JSON values, so _replace_ids cannot remap them. Rebuild from post-remap
    # structured rows, then rerender the summary from the registered template.
    release = rec["release_recommendation"]
    explanation = release["explanation"]
    if "decisive_list" in explanation["params"]:
        explanation["params"]["decisive_list"] = [decisive_entry_text(rec, row) for row in release["decisive"]]
        explanation["summary"] = sem_why.render(ontology, explanation["template_id"], explanation["params"])
    # The no-critical-recurrence gate reason names its claims by id in text too: rebuild it from the post-remap rows.
    for gate_row in release.get("gate_results") or []:
        if gate_row.get("gate") == "eio.gate.no-critical-recurrence" and gate_row.get("claim_ids"):
            gate_explanation = gate_row["explanation"]
            gate_explanation["params"]["reason"] = gate_reason_text(vocabulary(ontology), rec, gate_row)
            gate_explanation["summary"] = sem_why.render(ontology, gate_explanation["template_id"],
                                                         gate_explanation["params"])
    rec["claims"].sort(key=lambda c: (tuple(c["turn_indices"]), c["predicate"], c["id"]))

    for turn in rec["evidence"]["turns"]:
        turn["scenario"] = turn.pop("trap", None)
    for finding in rec["findings"]:
        finding["scenarios"] = finding.pop("traps", [])
        finding["fidelity"] = finding.pop("mapping_relation")
    rec["evidence"]["completeness"].pop("sentinel_locations", None)
    rec["evidence"]["completeness"].pop("code_check_offsets", None)

    if rec["scores"] is None:
        rec["limitations"].append({
            "limitation_id": NO_SCORING_PROFILE_ID,
            "field_path": "/scores",
            "status": "NOT_SUPPLIED",
            "reason": "No scoring profile was declared for this evaluation.",
            "impact": "Readiness and score-dependent release rules were not evaluated.",
            "next_step": "Declare an applicable scoring profile and re-evaluate.",
        })
    core = merge_catalogues(load_core_limitations(), head, kind="limitations")
    old = {row["id"]: row for row in json.loads(RC1_LIMITATIONS.read_text(encoding="utf-8"))["limitations"]}
    require(all(row["limitation_id"] in old for row in rec["limitations"]),
            "UNKNOWN_LIMITATION", "native preview emitted an undeclared rc1 limitation")
    rec["limitations"] = [migrate_rc1_core_row(row, old[row["limitation_id"]], core,
                                                RC1_TO_CORE_ID.get(row["limitation_id"]))
                          for row in rec["limitations"]]
    rec["limitations"].sort(key=lambda row: (row["field_path"], row["limitation_id"]))
    validate_record_catalogues(rec)
    return rec


def project_native_preview(bundle, *, ontology):
    """The internal neutral null-score projection of one native bundle (legacy rc3 identity). New records never carry
    it: `eio_agents.convert` finalizes it to PER 2.1.0; it is returned as is only to re-derive legacy rc3 records."""
    b = B.read(bundle)
    require(b["provenance"]["producer"]["kind"] == "native", "NATIVE_PREVIEW", "producer must be native")
    return _project_neutral(b, ontology=ontology)


def project_neutral(bundle, *, ontology):
    """The internal neutral null-score projection of a native or adapter bundle, the input of the PER 2.1.0
    finalization (`native_full_wire.project_unscored_per`)."""
    # the projector validates the bundle sections first, then takes a native or adapter producer only
    return _project_neutral(B.read(bundle), ontology=ontology)


def _project_neutral(b, *, ontology):
    # The old projector can load its own release when ontology is None, but
    # native finalization also renders release explanations.  Both stages
    # must see the *same* verified release object, including through the
    # public convert(bundle) default path.
    if ontology is None:
        ontology = load_ontology()
    old = project(b, ontology=ontology, bridge_native_rc2=True)
    rec = _neutralize(old, b, ontology)
    schema_path = PREVIEW_SCHEMA if rec["header"]["schema_uri"] == SCHEMA_URI else PUBLIC_RC3_SCHEMA
    schema = json.loads(schema_path.read_text())
    if any(f.get("proof_status") == "PROVEN" and f.get("decided_by") == "semantic" for f in rec.get("findings") or []):
        schema = _admit_jury_consensus(schema)
    bad = list(Draft202012Validator(schema).iter_errors(rec))
    require(not bad, "NATIVE_PREVIEW_SCHEMA", f"{len(bad)} schema problems; first: {bad[0].message[:120]}" if bad else "")
    return rec


def verify_native_preview(record, bundle, *, ontology):
    """Preview-only round-trip diagnostic, not the independent public verifier.

    `eio_agents.verify` runs the separate validation unit's canonical form and
    source checks. This helper stays in the producer unit and uses its own
    canonical form only to compare preview bytes.
    """
    b = B.read(bundle)
    schema_path = PREVIEW_SCHEMA if record["header"]["schema_uri"] == SCHEMA_URI else PUBLIC_RC3_SCHEMA
    schema = json.loads(schema_path.read_text())
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(record),
                    key=lambda e: (list(e.absolute_path), e.message))
    if errors:
        return {"valid": False, "code": "SCHEMA", "detail": errors[0].message[:120]}
    try:
        validate_record_catalogues(record)
    except ConversionError as exc:
        return {"valid": False, "code": exc.code}
    if record["header"]["archive_sha256"] != H(jb(b)):
        return {"valid": False, "code": "ARCHIVE_DIGEST"}
    expected = project_native_preview(b, ontology=ontology)
    same = jb(record) == jb(expected)
    return {"valid": same, "code": "OK" if same else "REPRODUCTION",
            "per_sha256": H(jb(record))}
