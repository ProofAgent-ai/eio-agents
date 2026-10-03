# Versioning and roadmap

EIO-Agents has three version lines: the library, the EIO release it bundles, and the PER version it produces. This page
explains each one, how they relate, what changes a record's digest, and the implementation steps cited elsewhere.

- [Three version lines](#three-version-lines)
- [The library](#the-library)
- [EIO releases](#eio-releases)
- [PER versions](#per-versions)
- [What changes a record's bytes](#what-changes-a-records-bytes)
- [Roadmap steps](#roadmap-steps)

## Three version lines

| Line | Current | Where it is reported |
|---|---|---|
| Library (`eio-agents`) | `0.8.0` | `eio_agents.__version__`, `eio-agents version` |
| EIO release | `0.6.0` (`ontology_digest` `a27cf1f3ab755446`) | `standards()["eio_release"]`, every record's `header.eio` |
| PER version | `2.1.0` (the default), release semantics `2.2` | `standards()["per_version"]` and `standards()["release_semantics"]`; each record's `header.per_version`, `header.schema_uri` and `header.release_semantics` |

This library release bundles one EIO release and produces PER 2.1.0 by default. Published PER 2.0.0 and the
historical release-candidate records stay verifiable under their own pinned identities; they are not defaults and
`eio-agents version` does not report them.

## The library

- Versions follow [PEP 440](https://peps.python.org/pep-0440/), with the meaning of Semantic Versioning.
- While the major version is 0, a MINOR bump may break the API.
- `.devN` identifies a development build and `rcN` a pre-release candidate. Each public release requires an explicit
  release decision and packaging gate; a version label alone does not certify an evaluated agent.
- A library release that changes record bytes bumps the MINOR version (while in 0.x), and its changelog entry says
  "Record bytes change: yes". Every changelog entry names the bundled EIO release and PER version.

The library changelog is [CHANGELOG.md](../CHANGELOG.md).

## EIO releases

An EIO release is a set of versioned YAML modules plus JSON Schemas, a JSON-LD context and reference cases, in
`src/eio_agents/ontology/data/` and `src/eio_agents/schemas/eio/`. The manifest (`eio.manifest.public`) pins each module by
exact version and sha256.

The versioning rule carried by the current 0.6.0 manifest (also recorded as EIO-1 in the
[historical EIO changelog](../src/eio_agents/ontology/data/CHANGELOG.md)):

- While the release major version is 0, a breaking change (a change of meaning) bumps the MINOR version of the changed
  module and of the release, and is listed under BREAKING.
- An additive change bumps PATCH or MINOR.
- A text or comment change bumps PATCH.
- Import pins are exact; there are no version ranges.

A predicate's version identifies its proposition: when it applies, when it is satisfied or violated, its polarity, its
unknown policy, its evidence contract and what it subsumes. Changing how a predicate is resolved, without changing the
proposition, does not change its version. Claim ids and finding ids depend on the predicate version, so they stay stable
while the proposition does.

Release digests:

- `module_sha256` = `"sha256:"` + SHA-256 of the raw module file bytes;
- `ontology_sha256` = `"sha256:"` + SHA-256 of the JCS of `{module_id: module_sha256}` over the manifest and every module
  it imports;
- `ontology_digest` = the first 16 hex characters of `ontology_sha256`.

All of them, per module and per pinned file, are in `RELEASE-DIGESTS.json`. `tools/eio_digests.py` checks that the file
reproduces; `tools/eio_digests.py --write` regenerates it after an intended change.

Because the digest is over raw bytes, even a comment change in a module is a new EIO release and changes the digest of
every record. EIO data changes therefore follow the proposal process in [GOVERNANCE.md](../GOVERNANCE.md).

## PER versions

A PER record states its version in `header.per_version` and its schema in `header.schema_uri`, which is the `$id` of a
versioned JSON Schema (2020-12). The header also names the EIO release (with its digests) and the converter that
produced the record.

- `2.0.0-rc1` is the historical adapter compatibility format. Its schema is titled "ProofAgent Evaluation Record"; its `$id` is
  `https://proofagent.ai/schemas/per/2.0.0-rc1/per.schema.json`.
- The default is `2.1.0`, with `$id` `https://www.proofagent.ai/eio-agents/schema/per/2.1.0/per.schema.json`. The
  package embeds the schema for offline validation; the website endpoint requires a separate deployment and live
  check. Published PER `2.0.0` remains a separately validated historical schema.
- A PER 2.1.0 record binds reference scoring profile `0.3.1` (`eio-agents.reference-scoring`), score basis
  `eio-agents.score-basis/0.3.0` and score kind `reference`. These are the rules of the historical `0.3.1-draft.1`
  profile under a released version (owner decision #46); the profile document's version, status, description and gaps
  differ, so its digest differs (`sha256:c03848df...57aa7d`; the historical document is `sha256:39907fe6...ad45c6`).
  Published PER 2.0.0 records keep `0.3.1-draft.1`, `eio-agents.score-basis/0.3.0-draft.1` and `reference-draft`.
- Release semantics `2.2` (PER 2.1.0): `2.1` plus the no-policy default floor. When a record declares no policy
  (`release_recommendation.policy.source` is `none`), the state is REVIEW whenever readiness is below 85 (or withheld)
  or any HARD_BLOCK obligation is unmet (`coverage.summary.hard_block_unmet > 0`). The decisive entries
  `eio.release.default-readiness-floor` and `eio.release.hard-block-unmet` (kind `review_guard`, effect REVIEW) state
  the reason in the release explanation (`eio.why.release.review@1`). BLOCK still requires a proven failure. The
  release semantics `2.1` of the unpublished 0.8.0 candidate is superseded: a record that carries it fails validation
  rather than being reinterpreted under 2.2.
- The historical release-candidate schemas (`2.0.0-rc1` to `2.0.0-rc5`, whose identifiers name them as drafts)
  remain pinned for historical interpretation; full source verification of those records requires the pinned
  historical release candidate, not reinterpretation by the new scoring gate. A bundle without native scoring inputs
  still projects to the pinned partial rc3 identity; the CLI marks such a record as partial/historical. A wire version
  is not a claim of independent implementation or certification.

## What changes a record's bytes

A record's `per_sha256` changes when any of these change:

- the canonical native bundle content (or an adapter's source-archive identity);
- the bundled EIO release (any module byte, which changes `ontology_digest`);
- the PER schema version;
- conversion code whose output changes.

Re-deriving a record therefore needs the same library version that produced it. Keep the version (from
`header.converter`, `header.eio` and `eio-agents version`) with every stored record and archive.

## Roadmap steps

EIO-Agents was split out of the ProofAgent Harness conversion code in steps. The statuses below describe the
standalone `0.8.0` implementation boundary; they do not claim completed Harness integration. The changelog and
release gates govern each shipped artifact.

| Step | What it does | Status |
|---|---|---|
| **L1-L3** | Neutral package and archive-schema-3 API; historical report conversion and its verifier checks move to the producer adapter. | Standalone package path implemented; adapter compatibility has separate gates. |
| **L4/S1b** | Vendored harness scorer removed; readiness engine, scoring-profile registry and native claims-derived scoring added. G/readiness remain withheld where source evidence is insufficient. | PER 2.1.0 can derive full scores when sources are complete. |
| **L5a** | Neutral PER records, versioned ProofAgent-hosted EIO schema/context identities, and core-plus-declared catalogues replace historical package vocabulary. Compact PER claim/ref/finding ids remain stable; a deterministic UUIDv5 JSON-LD instance view does not rewrite PER bytes. | Versioned `www.proofagent.ai/eio-agents/schema/` identities are pinned in package data. |
| **L5b** | Publish reviewed specification documents and schema at a stable public location. | Public URL resolution and package-byte parity are release checks, separate from local library behavior. |
| **L6** | ProofAgent Harness produces and verifies its records through EIO-Agents plus its adapter. | Separate integration gate; not established by standalone tests. |

Historical draft schemas may still contain `w3id.org` identifiers and remain pinned to their original bytes.
The current EIO 0.6.0 and PER 2.1.0 identities use versioned
`www.proofagent.ai/eio-agents/schema/` URLs. Those exact bytes must resolve at
their declared URLs for a public release. Individual ontology term dereferencing
is not provided by the schema download route and must not be implied.
