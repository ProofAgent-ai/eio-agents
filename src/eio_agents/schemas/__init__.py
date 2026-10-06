"""JSON Schemas shipped with EIO-Agents: EIO in `eio/`; in `per/` the PER 2.1.0 schema (every new record), published
PER 2.0.0 and the legacy release-candidate schemas; the evaluation bundle 3.0.0 (archive schema 3) in `bundle/`, with
the legacy bundle schemas; and the scoring-profile document and score-block schemas in `scoring/`.

Legacy schemas (PER 2.0.0-rc1 to rc5, bundle `bundle_draft` 1 and 2, the `*-draft*` scoring schemas) are kept byte for
byte, read-only, so that records and bundles already issued stay valid and verifiable. Nothing new selects them by
default: a reader picks one only from the identity an existing artifact declares.

The EIO schemas are the files RELEASE-DIGESTS.json pins as `schemas/<name>` (see `eio_agents.ontology.release_file`).
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EIO_SCHEMA_DIR = HERE / "eio"
EIO_SCHEMA_CURRENT_DIR = EIO_SCHEMA_DIR / "0.6.0"
PER_SCHEMA_DIR = HERE / "per"
# legacy, read-only: the release-candidate schemas of records already issued (never selected for a new record)
PER_SCHEMA_RC1 = PER_SCHEMA_DIR / "per-2.0.schema.json"
PER_SCHEMA_RC2 = PER_SCHEMA_DIR / "per-2.0.0-rc2-draft.schema.json"
PER_SCHEMA_RC2_NATIVE_PREVIEW = PER_SCHEMA_DIR / "per-2.0.0-rc2-neutral-preview.schema.json"
PER_SCHEMA = PER_SCHEMA_DIR / "per-2.0.0-rc3-draft.schema.json"
PER_SCHEMA_NATIVE_PREVIEW = PER_SCHEMA_DIR / "per-2.0.0-rc3-neutral-preview.schema.json"
PER_SCHEMA_RC4 = PER_SCHEMA_DIR / "per-2.0.0-rc4-draft.schema.json"
PER_SCHEMA_RC5_POLICY = PER_SCHEMA_DIR / "per-2.0.0-rc5-policy-draft.schema.json"
PER_SCHEMA_2_0_0 = PER_SCHEMA_DIR / "per-2.0.0.schema.json"
PER_SCHEMA_2_1_0 = PER_SCHEMA_DIR / "per-2.1.0.schema.json"
PER_SCHEMA_2_1_1 = PER_SCHEMA_DIR / "per-2.1.1.schema.json"   # 2.1.0 plus jury-consensus proof (EIO-Agents 0.8.4)
PER_SCHEMAS = {"2.0.0-rc1": PER_SCHEMA_RC1, "2.0.0-rc2-draft": PER_SCHEMA_RC2,
               "2.0.0-rc2-neutral-preview": PER_SCHEMA_RC2_NATIVE_PREVIEW,
               "2.0.0-rc3-draft": PER_SCHEMA,
               "2.0.0-rc3-neutral-preview": PER_SCHEMA_NATIVE_PREVIEW,
               "2.0.0-rc4-draft": PER_SCHEMA_RC4,
               "2.0.0-rc5-policy-draft": PER_SCHEMA_RC5_POLICY,
               "2.0.0": PER_SCHEMA_2_0_0, "2.1.0": PER_SCHEMA_2_1_0,
               "2.1.1": PER_SCHEMA_2_1_1}      # per_version -> schema file
PER_CONTEXT = PER_SCHEMA_DIR / "per-2.0-rc3-draft.context.jsonld"   # legacy JSON-LD context of rc3 records
BUNDLE_SCHEMA_DIR = HERE / "bundle"
BUNDLE_VERSION = "3.0.0"                              # the bundle format of every new bundle (`bundle_version`)
BUNDLE_SCHEMA = BUNDLE_SCHEMA_DIR / "bundle-3.0.0.schema.json"
BUNDLE_SCHEMA_ID = "urn:eio-agents:schema:bundle:3.0.0"
# legacy, read-only: bundles already issued with `bundle_draft` 1 or 2 (the ProofAgent Harness adapter emits 2)
LEGACY_BUNDLE_SCHEMAS = {1: BUNDLE_SCHEMA_DIR / "bundle-3.0.0-draft.1.schema.json",
                         2: BUNDLE_SCHEMA_DIR / "bundle-3.0.0-draft.2.schema.json"}
# legacy, read-only: the adapter-declared scoring-profile document schema (harness-2.x documents)
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


def bundle_schema(bundle: object = None) -> dict:
    """The evaluation-bundle JSON Schema: bundle format 3.0.0 (archive schema 3), the input of `eio_agents.convert`.
    Given a bundle, the schema of the format it declares: a legacy bundle that carries `bundle_draft` 1 or 2 (and no
    `bundle_version`) is read with its pinned legacy schema; anything else with the 3.0.0 schema."""
    path = BUNDLE_SCHEMA
    if isinstance(bundle, dict) and "bundle_version" not in bundle:
        draft = bundle.get("bundle_draft")
        if type(draft) is int and draft in LEGACY_BUNDLE_SCHEMAS:
            path = LEGACY_BUNDLE_SCHEMAS[draft]
    return json.loads(path.read_text(encoding="utf-8"))


def scoring_profile_schema() -> dict:
    """The legacy adapter-declared scoring-profile document JSON Schema (0.2.0; `eio_agents.scoring.profiles`)."""
    return json.loads(SCORING_PROFILE_SCHEMA.read_text(encoding="utf-8"))
