"""JSON Schemas shipped with EIO-Agents: EIO in `eio/`; in `per/` the default PER 2.1.0 schema, published PER 2.0.0
and the pinned historical release-candidate schemas; the evaluation bundle (archive schema 3) in `bundle/`; and the
scoring-profile document and score-block schemas in `scoring/`.

The EIO schemas are the files RELEASE-DIGESTS.json pins as `schemas/<name>` (see `eio_agents.ontology.release_file`).
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EIO_SCHEMA_DIR = HERE / "eio"
EIO_SCHEMA_CURRENT_DIR = EIO_SCHEMA_DIR / "0.6.0"
PER_SCHEMA_DIR = HERE / "per"
PER_SCHEMA_RC1 = PER_SCHEMA_DIR / "per-2.0.schema.json"
PER_SCHEMA_RC2 = PER_SCHEMA_DIR / "per-2.0.0-rc2-draft.schema.json"
PER_SCHEMA_RC2_NATIVE_PREVIEW = PER_SCHEMA_DIR / "per-2.0.0-rc2-neutral-preview.schema.json"
PER_SCHEMA = PER_SCHEMA_DIR / "per-2.0.0-rc3-draft.schema.json"
PER_SCHEMA_NATIVE_PREVIEW = PER_SCHEMA_DIR / "per-2.0.0-rc3-neutral-preview.schema.json"
PER_SCHEMA_RC4 = PER_SCHEMA_DIR / "per-2.0.0-rc4-draft.schema.json"
PER_SCHEMA_RC5_POLICY = PER_SCHEMA_DIR / "per-2.0.0-rc5-policy-draft.schema.json"
PER_SCHEMA_2_0_0 = PER_SCHEMA_DIR / "per-2.0.0.schema.json"
PER_SCHEMA_2_1_0 = PER_SCHEMA_DIR / "per-2.1.0.schema.json"
PER_SCHEMAS = {"2.0.0-rc1": PER_SCHEMA_RC1, "2.0.0-rc2-draft": PER_SCHEMA_RC2,
               "2.0.0-rc2-neutral-preview": PER_SCHEMA_RC2_NATIVE_PREVIEW,
               "2.0.0-rc3-draft": PER_SCHEMA,
               "2.0.0-rc3-neutral-preview": PER_SCHEMA_NATIVE_PREVIEW,
               "2.0.0-rc4-draft": PER_SCHEMA_RC4,
               "2.0.0-rc5-policy-draft": PER_SCHEMA_RC5_POLICY,
               "2.0.0": PER_SCHEMA_2_0_0, "2.1.0": PER_SCHEMA_2_1_0}      # per_version -> schema file
PER_CONTEXT = PER_SCHEMA_DIR / "per-2.0-rc3-draft.context.jsonld"
BUNDLE_SCHEMA_DIR = HERE / "bundle"
BUNDLE_SCHEMA = BUNDLE_SCHEMA_DIR / "bundle-3.0.0-draft.2.schema.json"
SCORING_PROFILE_SCHEMA = HERE / "scoring" / "scoring-profile-0.2.0-draft.1.schema.json"


def eio_schema(name: str) -> dict:
    """A schema from the current EIO release; historical files remain in ``eio/``."""
    return json.loads((EIO_SCHEMA_CURRENT_DIR / name).read_text(encoding="utf-8"))


def per_schema(per_version: str = "2.1.0") -> dict:
    """The PER JSON Schema of an exact version; the default is PER 2.1.0 (owner decision #46). A historical version
    is named explicitly."""
    return json.loads(PER_SCHEMAS[per_version].read_text(encoding="utf-8"))


def current_native_per_schema() -> dict:
    """The current source-complete native PER schema (2.1.0 in EIO-Agents 0.8.0)."""
    return per_schema("2.1.0")


def bundle_schema() -> dict:
    """The evaluation-bundle JSON Schema (archive schema 3, draft 2): the input of `eio_agents.convert`."""
    return json.loads(BUNDLE_SCHEMA.read_text(encoding="utf-8"))


def scoring_profile_schema() -> dict:
    """The scoring-profile document JSON Schema (draft 0.2.0; `eio_agents.scoring.profiles`)."""
    return json.loads(SCORING_PROFILE_SCHEMA.read_text(encoding="utf-8"))
