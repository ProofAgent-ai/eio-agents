"""Public API of EIO-Agents (split plan §4.2), in process: no temporary file, no subprocess, no captured output.

    rec = convert(bundle)                          # evaluation bundle (archive schema 3) -> PER 2.0 dict
    body = canonical_bytes(rec)                    # RFC 8785 JCS bytes
    digest = per_sha256(rec)                       # "sha256:<hex>" over the JCS bytes
    problems = validate(rec)                       # the independent verifier's record checks; [] when valid
    report = verify(rec, bundle)                   # validate + VER-5 over the bundle's sources + re-projection digest match
    text = explain(rec, "eio.metric.instruction-following")   # the record's registered eio.why.* renderings
    rows = resolve(rec, bundle)                    # every withheld value (a fingerprint) with its text in the local bundle

`convert` is `eio_agents.per.project` for a bundle, and takes nothing else. A stored producer report (archive
schema 1 or 2, or no `archive_schema`) is not a bundle: its producer's adapter reads it into one, and `convert` refuses it with `BUNDLE_INPUT`
(the stored-report branch of ACCEPTED_DEVIATIONS D-4 was deleted at L3). This module never imports the staging area.
`validate`, `verify` and `explain` are the independent verifier's (`eio_agents.validation`); `verify` re-projects the
bundle here and passes the result to it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import eio_agents.per as per
import eio_agents.schemas as schemas
import eio_agents.validation as validation
from eio_agents.base.errors import ConversionError, require
from eio_agents.base.version import VERSION
from eio_agents.ontology import Ontology, load as load_ontology, release_digests
from eio_agents.per import bundle as per_bundle
from eio_agents.per import canonical_bytes, per_sha256, write  # noqa: F401  (public names)
from eio_agents.per.projection import project
from eio_agents.per.native_preview import project_native_preview
from eio_agents.per.native_full_wire import project_native_full_per
from eio_agents.per import native_full_wire
from eio_agents.per.native_score_preview import candidate_scored_per, project_native_score_preview
from eio_agents.validation import explain, finding_evidence, findings_at_turn, metric_card, targets, validate  # noqa: F401
from eio_agents.validation.reader import EIO

__all__ = ["ConversionError", "canonical_bytes", "convert", "convert_file", "explain", "finding_evidence",
           "findings_at_turn", "metric_card", "per_sha256", "resolve", "standards", "targets", "validate", "verify", "write"]


def standards() -> dict[str, str]:
    """Standards bundled in this build, including the versioned full-score native route.

    The legacy ``per_version``/``per_schema_id`` keys keep their historical
    rc3 meaning; callers must use the explicit native-full keys when a
    source-complete bundle takes the rc4 route. A single default would
    misrepresent one of those records.
    """
    digests = release_digests()
    schema_id = str(schemas.per_schema().get("$id", ""))
    projector = f"eio_agents.convert {VERSION}"
    return {
        "eio_release": str(digests.get("release") or digests.get("eio_release") or ""),
        "ontology_digest": str(digests.get("ontology_digest") or ""),
        "ontology_sha256": str(digests.get("ontology_sha256") or ""),
        "per_version": per.PER_VERSION,
        "per_schema_id": schema_id,
        "projector": projector,
        "version": VERSION,
        "per_schema": schema_id,
        "converter": projector,
        "native_full_per_version": native_full_wire.PER_VERSION,
        "native_full_per_schema_id": native_full_wire.SCHEMA_URI,
        "native_full_scoring_profile_id": native_full_wire.REFERENCE_FULL_ID,
        "native_full_scoring_profile_version": native_full_wire.REFERENCE_FULL_VERSION,
    }


def _read(obj: bytes | bytearray | dict, what: str) -> dict:
    """The parsed input: a dict as given, or JSON bytes. Anything else is a TypeError (a path goes to `convert_file`);
    bytes that are not a JSON object fail closed with `ConversionError` code `BUNDLE_INPUT` (a digit string too long for
    Python's integer conversion included: L3 fix round 1, issue 4)."""
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, (bytes, bytearray)):
        try:
            data: Any = json.loads(bytes(obj).decode("utf-8"))
        except (ValueError, RecursionError) as e:    # JSONDecodeError, UnicodeDecodeError, an integer too long for Python
            raise ConversionError(f"BUNDLE_INPUT: the {what} is not JSON ({str(e)[:200]})", code="BUNDLE_INPUT") from e
        if not isinstance(data, dict):
            raise ConversionError(f"BUNDLE_INPUT: the {what} is not a JSON object", code="BUNDLE_INPUT")
        return data
    raise TypeError(f"the {what} must be bytes or a dict, not {type(obj).__name__} (use convert_file for a path)")


def _is_bundle(obj: dict) -> bool:
    return obj.get("archive_schema") == 3 and not isinstance(obj.get("archive_schema"), bool)


_STORED_REPORT = ("convert takes an evaluation bundle (archive schema 3); a stored producer report (archive "
                  "schema 1 or 2) must first be converted to a bundle by its producer's adapter")


def _native_scored_convert(source: bytes | dict, ontology: Ontology) -> dict[str, Any]:
    """Orchestrate producer and independent prechecks without a per→validation import cycle.

    The intermediate null-score PER gets D1/D2/D5 source checks, not a public
    D3/D4 verdict. The final scored PER is independently reprojected and
    verified by public ``verify`` with D4 after this conversion returns.
    """
    from eio_agents.validation.canon import jb as verifier_jb, sha as verifier_sha
    from eio_agents.validation.native_score import native_proof_status_gate
    from eio_agents.validation.validate import check_one
    from eio_agents.validation.verify import c_sources

    bundle = per_bundle.read(source)
    header = bundle.get("header")
    expected_eio = {
        "release": ontology.release,
        "ontology_digest": ontology.ontology_digest,
        "ontology_sha256": ontology.ontology_sha256,
    }
    require(
        isinstance(header, dict) and header.get("eio") == expected_eio,
        "BUNDLE_RECOMPUTE", "native scored bundle ontology release mismatch",
    )
    unscored = project_native_preview(bundle, ontology=ontology)
    verifier_eio = EIO(ontology.root)
    checks = check_one(unscored, verifier_eio)
    checks.run("D2 refs and digests recompute from the bundle sources", "VER-5",
               lambda: c_sources(unscored, bundle, verifier_eio))
    checks.run("D5 native proof status independently recomputed", "VER-5",
               lambda: native_proof_status_gate(bundle, unscored, verifier_eio))
    failures = [row for row in checks.rows if row[2] == "FAIL"]
    require(not failures, "NATIVE_SCORE_PREVIEW",
            f"null-score source PER failed D1/D2/D5 precheck: {failures[0][0] if failures else ''}")
    source_check = {"valid": True, "digest_match": True, "per_sha256": verifier_sha(verifier_jb(unscored))}
    if "proof_citations" not in (bundle.get("native_scoring") or {}):
        require(ontology.release != "0.6.0", "NATIVE_SCORE_PREVIEW",
                "the new release has no versioned partial-score profile; proof_citations must be declared")
        # An absent citation declaration is unknown, not an asserted empty
        # proof set. Keep the pinned rc3 partial wire; it withholds G/readiness
        # and is independently verified under the old 0.2 profile.
        partial = project_native_score_preview(bundle, unscored, source_check, ontology=ontology)
        return candidate_scored_per(unscored, partial)
    # The 0.3 profile is a new wire contract: the old rc3/0.2 schema and
    # scorer remain packaged for historical pinned runtimes, but new native
    # conversion emits rc4 only after D1/D2/D5 source prechecks.
    return project_native_full_per(bundle, unscored, source_check, ontology=ontology)


def convert(archive: bytes | dict, *, ontology: Ontology | None = None) -> dict[str, Any]:
    """Project an evaluation bundle (archive schema 3; JSON bytes or a dict) into a PER 2.0 record: `eio_agents.per.project`.

    Deterministic and fail-closed: no record is returned when conversion fails, and every failure is a `ConversionError`
    with a typed `code` (a neutral token). Anything that is not a bundle, a stored producer report (archive
    schema 1 or 2) included, fails with `BUNDLE_INPUT`: a stored report converts with its producer's adapter.
    Bundle bytes are read as I-JSON. `ontology` is the
    EIO release to convert under (default: the bundled release, loaded and verified for this call; a caller that converts
    many records loads one with `eio_agents.ontology.load()` and passes it).
    """
    obj = _read(archive, "archive")
    if not _is_bundle(obj):
        raise ConversionError(f"BUNDLE_INPUT: {_STORED_REPORT}", code="BUNDLE_INPUT")
    # bundle bytes are read again as I-JSON (each object member once, finite numbers; review R-2)
    source = bytes(archive) if isinstance(archive, (bytes, bytearray)) else obj
    provenance = obj.get("provenance")
    producer = provenance.get("producer") if isinstance(provenance, dict) else None
    if isinstance(producer, dict) and producer.get("kind") == "native":
        if obj.get("native_scoring") is not None:
            active = ontology if ontology is not None else load_ontology()
            if active.release in ("0.5.0-draft.1", "0.6.0"):
                return cast("dict[str, Any]", _native_scored_convert(source, active))
        return cast("dict[str, Any]", project_native_preview(source, ontology=ontology))
    return cast("dict[str, Any]", project(source, ontology=ontology))


def convert_file(archive_path: str | Path, out: str | Path, jcs_out: str | Path | None = None, *,
                 ontology: Ontology | None = None) -> str:
    """Convert the archive file at `archive_path` and write the pretty record (and optionally the JCS bytes). Returns
    per_sha256. A missing file raises FileNotFoundError."""
    return per.write(convert(Path(archive_path).read_bytes(), ontology=ontology), out, jcs_out)


def resolve(rec: dict[str, Any], bundle: bytes | dict) -> list[dict[str, Any]]:
    """The real text of every withheld value of a record (decision #31), from its local evaluation bundle: a list of
    `{record_pointer, fingerprint, bundle_pointer, text}`, one per fingerprint the record carries (a value, or one inside a
    rendered via, ledger key, formula or limitation text), found at the field's source path of the closed field table or
    else by content address (`eio_agents.validation.privacy.resolve`). Local only: nothing is added to the record, and a
    fingerprint that no text of the bundle gives has `bundle_pointer` and `text` None."""
    b = _read(bundle, "bundle")
    if not _is_bundle(b):
        raise ConversionError("BUNDLE_INPUT: resolve takes the record's evaluation bundle (archive schema 3); read a stored "
                              "report into a bundle with its producer's adapter first", code="BUNDLE_INPUT")
    return validation.resolve(rec, per_bundle.read(bundle))


def verify(rec: dict[str, Any], bundle: bytes | dict, *, ontology: Ontology | None = None) -> dict[str, Any]:
    """Validate the record, re-derive it from its evaluation bundle and compare digests (VER-1, VER-3, VER-4, VER-5), in
    process: the bundle is re-projected with `eio_agents.per.project` and checked against the record by the independent
    verifier (`eio_agents.validation.verify`, including VER-5 per locator kind over the bundle's `sources`).
    Returns `{valid, digest_match, per_sha256, rederived_sha256, failures}`. A stored report is not a bundle: convert it
    with its producer's adapter first (`BUNDLE_INPUT`). Bundle bytes are read as I-JSON, as `convert` reads them
    (`BUNDLE_INPUT` for an object member given twice, a NaN or infinite number, or a lone surrogate in a string; a bundle
    nested more than 100 levels fails the re-projection and VER-5)."""
    b = _read(bundle, "bundle")
    if not _is_bundle(b):
        raise ConversionError("BUNDLE_INPUT: verify takes the record's evaluation bundle (archive schema 3); read a stored "
                              "report into a bundle with its producer's adapter first", code="BUNDLE_INPUT")
    if isinstance(bundle, (bytes, bytearray)):
        b = per_bundle.loads(bundle)                  # bundle bytes are read as I-JSON (review R-2)
    try:
        rederived: Any = convert(b, ontology=ontology)
    except ConversionError as e:
        rederived = e
    verifier_eio = EIO(ontology.root) if ontology is not None else None
    return validation.verify(rec, b, rederived=rederived, eio=verifier_eio)
