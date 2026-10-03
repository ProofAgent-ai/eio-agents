"""The PER header (03 §7.1): the rc1 header constants and the header builder.

This is the private historical adapter projection header (legacy, read-only).
The neutral projection replaces its converter identity and schema URI in
`native_preview`, and every new record is finalized to PER 2.1.0; neither
legacy constant is advertised by the standalone public `standards()` API.
The release-semantics version is the core constant
`eio_agents.semantics.release.RELEASE_SEMANTICS`.
"""
from eio_agents.per.archive import archive_sha256
from eio_agents.semantics.release import RELEASE_SEMANTICS

CONVERTER = {"name": "proofagent_harness.per.convert", "version": "0.13.0"}
SCHEMA_URI = "https://proofagent.ai/schemas/per/2.0.0-rc2-draft/per.schema.json"


def archive_identity(bundle):
    """(archive_sha256, archive_schema) of the record of `bundle`, as read (before any projection step). A bundle
    converted from a stored archive names that archive (`header.source_archive`); a native bundle is its own archive
    (schema 3, digest by the JCS rule)."""
    src = bundle["header"]["source_archive"]
    if src is not None:
        return src["archive_sha256"], src["archive_schema"]
    return archive_sha256(bundle), bundle["archive_schema"]


def header(eio, bundle, per_version, identity):
    """The PER header of a bundle; `identity` is its `archive_identity`, taken when the bundle was read."""
    digest, schema = identity
    h = {"per_version": per_version,
            "per_semantics_version": f"2@{CONVERTER['version']}+eio{eio.release}.{eio.ontology_digest}",
            "release_semantics": RELEASE_SEMANTICS, "converter": dict(CONVERTER),
            "eio": {"release": eio.release, "ontology_digest": eio.ontology_digest, "ontology_sha256": eio.ontology_sha256,
                    "modules": dict(eio.modules)},
            "archive_sha256": digest, "archive_schema": schema, "adjudication_source": bundle["header"].get("adjudication_source"),
            "schema_uri": SCHEMA_URI}
    if "adjudication_source" not in bundle["header"]:     # an rc1 adapter field (adapter extension at L5a, §5.3)
        del h["adjudication_source"]
    return h
