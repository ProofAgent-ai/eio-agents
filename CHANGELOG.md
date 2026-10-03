# Changelog

All notable changes to EIO-Agents (the `eio-agents` library) are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/). Library versions follow
[PEP 440](https://peps.python.org/pep-0440/) with the meaning of Semantic Versioning; see
[docs/versioning.md](docs/versioning.md). EIO releases have their own changelog at
[src/eio_agents/ontology/data/CHANGELOG.md](src/eio_agents/ontology/data/CHANGELOG.md).

Every entry states the bundled EIO release, the PER version, and whether record bytes change. The `.devN` versions
below are development builds; `0.6.0rc1` was a release candidate. No version is a claim of certification.

## [0.8.0] - Pending publication

EIO-Agents 0.8.0 bundles EIO `0.6.0` (`ontology_digest` `a27cf1f3ab755446`) and produces PER `2.1.0` by default,
under release semantics `2.2`, with reference scoring profile `0.3.1`. This is a real 0.8.0 release line; publication remains pending exact local gates and the owner's commit/upload.

### Added

- Native semantic jury votes in `build_bundle()` and reference producer examples for ProofAgent Harness, Inspect AI,
  promptfoo, DeepEval and OpenTelemetry GenAI; a native-versus-export guide explains their evidence limits.
- Versioned PER 2.1.0 source-bound HIGH-review guard: unresolved HIGH/CRITICAL findings force REVIEW and the independent
  verifier rejects a forged state, omitted guard, or mismatched review queue. Published PER 2.0.0 bytes stay immutable.
- Predicate search hints and token-aware suggestions for unknown predicate names.
- Release semantics `2.2` (owner decision #46): a PER 2.1.0 record that declares no policy
  (`release_recommendation.policy.source` `none`) is REVIEW whenever readiness is below the default floor of 85 (or
  withheld) or any HARD_BLOCK obligation is unmet (`coverage.summary.hard_block_unmet > 0`). Two `review_guard`
  decisive entries, `eio.release.default-readiness-floor` (`field_refs` `/scores/readiness/value`) and
  `eio.release.hard-block-unmet` (`obligation_ids`, `field_refs` `/coverage/summary/hard_block_unmet`), state the
  reason in the registered release explanation `eio.why.release.review@1`; no EIO template is added, so the EIO
  release and its digests do not change. BLOCK still requires a proven failure (owner decision #2); the guards are
  never BLOCK. The independent verifier recomputes the guards from the record (R2) and from the bundle (D4) and
  rejects a record that omits them or claims PASS.

### Changed

- PER `2.1.0` is the default (owner decision #46). `eio-agents version` and `eio_agents.standards()` report
  `per_version` `2.1.0`, its schema id, `release_semantics` `2.2` and reference profile `0.3.1`;
  `eio_agents.schemas.per_schema()` defaults to the 2.1.0 schema. No public version string or schema id of a new record
  contains "draft": a PER 2.1.0 record binds the released reference scoring profile `0.3.1` (the rules of
  `0.3.1-draft.1` under a clean version; document digest
  `sha256:c03848dfd14163beef221a7e080d9d515c1853aa83373d0dd36a5b314957aa7d`, was
  `sha256:39907fe651d844cce4b7f893e1a5092deef91ff4168993da4635c9e9bfad45c6`), score basis
  `eio-agents.score-basis/0.3.0` and score kind `reference`, validated by the new
  `schemas/scoring/native-score-block-0.3.1.schema.json`. The packaged 2.1.0 PER schema accepts release semantics
  `2.2` only, the three review-guard ids and the clean score identities, and drops an unreferenced draft score
  definition (SHA-256 `b014591877aeef1821d3f1da5bc7a3a75516abc60033f2d91a16cbc08aca8219`, was
  `bc3052b8eb1de2c691ec3a893802778168ddde36d732c4c0d86caf6143142b04`; the website copy must be re-synced before
  deployment). Published PER 2.0.0 records keep `0.3.1-draft.1`, `eio-agents.score-basis/0.3.0-draft.1` and
  `reference-draft` and stay verifiable; historical release-candidate records keep their pinned identities and are no
  longer defaults. Release semantics `2.1`, used only by unpublished 0.8.0 candidate records, is superseded: such a
  record fails validation instead of being reinterpreted.
- `eio-agents explain --list` and `eio-agents evidence` show `unrated` for a finding with no severity (no in-scope
  obligation targets its predicate), where they printed `None`; `explain --list` now shows every finding's severity.
  Display only: the record keeps `severity: null`. The ontology defines severity through domain obligations only, not
  per predicate, so no severity is defaulted from the predicate.
- Record bytes change: **yes**. The converter and bundle version change from `0.7.0` to `0.8.0`; the 2.1 wire contract,
  model-identifier privacy rule and confidential-by-default system prompt also change projection where applicable.
  Existing 0.7.0 records require their pinned release for exact re-derivation. New 0.8 fixtures are under
  `tests/data/native/v0_8/`; historical 2.0 and 0.7 vectors are not rewritten. Decision #46 reissued the two scored
  PER 2.1.0 vectors with `tools/reissue_0_8_fixtures.py` and `tools/reissue_per_2_1_fixtures.py`:
  `v0_8/source-complete.per.jcs` SHA-256 `8ea058de14e379fcca8478cbba89c6a9682826eb039f62b6080d1cabd37c1177` and
  `per_2_1/source-complete.per.jcs` SHA-256 `ff323f0d72d455c87fd83aa914108cd65f69a2c5db3575f178b2432889b8997b`; the
  bundles are byte-identical.
- Model identifiers are clear only in designated model fields and only when they contain no sensitive-token shape.
  System prompts in `build_bundle()` are model-confidential by default; public excerpts require explicit opt-in.
  Illustrative export crosswalks now skip unsupported checks rather than claiming semantically different predicates.

The 0.8.0 full source, wheel, sdist, privacy, reproducibility and independent verification gates must be recorded
before publication. The former HIGH-review strict xfails are replaced by passing positive and forgery-negative tests.

## [0.7.0]

Developer adoption: build a bundle from your own evaluation report without the library internals. It bundles the same
EIO `0.6.0` (`ontology_digest` `a27cf1f3ab755446`) and emits the same PER `2.0.0` with reference scoring profile
`0.3.1-draft.1`. No EIO data, schema or scoring rule changes, and the projection of an existing bundle is unchanged
apart from the library version it records.

### Added

- `eio_agents.build_bundle(...)` builds an evaluation bundle (archive schema 3) of a native producer from a simple
  report: the turns (user message, agent answer, tool calls), one deterministic check per predicate and turn (passed or
  failed, an optional exact quote of the agent answer or the user message), an optional system prompt with context
  ratings, the frameworks in scope and the telemetry. It computes the evidence refs, claim ids, transcript digest,
  episodes, scenario bindings, applicable controls, proof citations and stage-record digests. What a report does not
  record comes from defaults packaged in the wheel (`eio_agents/per/data/build-defaults.json`); nothing is read from
  the network. See [docs/api.md](docs/api.md#build_bundle).
- Clear typed errors for the common mistakes, each naming the input field: `BUILD_QUOTE` (a quote that is not in the
  turn, with the closest text), `BUILD_PREDICATE` (an unknown predicate, criterion or framework, with close ids),
  `BUILD_TURN`, `BUILD_EVIDENCE` (a check without the evidence its predicate's contract needs that the report could
  supply), `BUILD_PERSONAL_DATA` (a value the record's privacy rules would refuse, such as a dated model name or an
  agent id with four digits, with the rule) and `BUILD_INPUT`.
- `eio_agents.predicates(search=None)` and `eio-agents predicates [--search TEXT] [--json]`: the predicates of the
  bundled release with their version, module, meaning, evidence contract, metrics and number of targeting controls.
- [docs/predicates.md](docs/predicates.md), the predicate reference, generated from the ontology by
  `tools/predicate_reference.py` (a test keeps it in sync); [docs/overview.md](docs/overview.md), a plain-language
  walk from a report to readiness with the computed numbers of a synthetic travel-agent report (a test checks them);
  and [examples/custom_report](examples/custom_report/README.md), a 29-line converter of a report file with its tests.
  The README has a short "Convert your own report" section.

### Changed

- Record bytes change: yes, in the library version only (`header.converter.version`, `header.per_semantics_version`,
  the bundles' `header.eio_agents.version` and the digests over them). The current synthetic fixtures under
  `tests/data/native/v0_6/` are reissued with `tools/reissue_public_fixtures.py`; the source-complete PER 2.0.0 golden
  record is now SHA-256 `ac19e80ebc1c2b31c2f5d2a8e664e4fdb88b49efa12c97071275bb975e7ca0b3`. Historical vectors stay
  pinned. A record made by 0.6.0 re-derives only under 0.6.0.

## [0.6.0] - 2026-10-02

The final 0.6.0 release of the 0.6.0rc1 candidate. It bundles the same EIO `0.6.0` (`ontology_digest`
`a27cf1f3ab755446`), emits the same PER `2.0.0` for source-complete native bundles with reference scoring profile
`0.3.1-draft.1`, and keeps the partial-score `2.0.0-rc3-draft` route. No EIO data, schema or scoring rule changes.

### Changed

- Record bytes change: yes, in the library version only. Every new record names the converter `0.6.0`
  (`header.converter.version` and `header.per_semantics_version`), and a bundle built by this version says so in
  `header.eio_agents.version`; the archive and score digests that cover these headers follow. Claim, finding and ref
  ids, states, scores and explanations are unchanged. The current synthetic fixtures under `tests/data/native/v0_6/`
  are reissued with `tools/reissue_public_fixtures.py`; the source-complete PER 2.0.0 golden record is now SHA-256
  `9ea9b9f30cad6d6f827914480e0d0ee1f15c8ecb71828829bbcd7bcbb29b9ecc`. The historical rc5 vector and the 0.5 fixtures
  stay pinned as they were. A record made by 0.6.0rc1 re-derives only under 0.6.0rc1.
- `eio-agents explain` omits an empty parenthetical from the line it prints: a behavioural finding with no trap label
  shows `failed on turn 3;`, not `failed on turn 3 ();`. Display only: the stored summary and `eio_agents.explain` keep
  the template rendering byte for byte.
- The README is written for PyPI: badges, `pip install eio-agents` (no `--pre`), a note on Python 3.10 or newer (pip's
  "from versions: none" means an older Python), the sample walkthrough, tracing a metric to its claim and quoted
  evidence, and the author. `pyproject.toml` and `CITATION.cff` name Dr. Fouad Bousetouane as an author.
- Releases are published by pushing a tag `v<version>`: `.github/workflows/release.yml` builds and publishes through
  PyPI trusted publishing and runs no tests. The CI workflow runs the test suite in parallel with pytest-xdist.

### Fixed

- `docs/api.md` listed `validate_bundle` as a name of the package root; it is `eio_agents.validation.validate_bundle`
  (`eio_agents.validate_bundle` raises `AttributeError`).
- `docs/cli.md` states what `explain --local` resolves: only the fingerprints among the parameters of the rendered
  explanation, so a finding whose parameters are all ids, numbers and states prints the same text with or without it.

## [0.6.0rc1]

This release candidate bundles EIO
`0.6.0` (`ontology_digest` `a27cf1f3ab755446`), and adds source-complete native PER
`2.0.0` with reference scoring profile `0.3.1-draft.1`. Bundles without a declared proof set retain the
partial-score rc3 route.
Historical rc1 and EIO 0.4 records require their matching adapter and pinned release.
The rc4, L5a/S1b, L3s and L4 notes below describe earlier candidate stages, not the current draft.
Record bytes changed during those stages: R0→R3S for structural privacy at L3s, then R3S→R4 for
the scoring profile and rc2 scores block at L4. The native rc3 draft has its own pinned vectors.

### Changed (PER 2.0.0 release candidate)

- A source-complete native bundle with an explicit proof set selects PER `2.0.0` and
  reference profile `0.3.1-draft.1`. The canonical schema identifier is
  `https://www.proofagent.ai/eio-agents/schema/per/2.0.0/per.schema.json`; website deployment and live verification remain separate gates.
- The draft minimum-score policy review is evaluated when readiness is measured; missing required source inputs
  still withhold the affected score. The historical rc3 partial route remains available.
- Record bytes change: yes. The PER version and schema ID change record headers and their canonical digests. The synthetic
  source-complete PER 2.0.0 vector is pinned at `tests/data/native/v0_6/source-complete.per.jcs`; the historical rc5
  vector is retained as `source-complete.rc5-policy-draft.per.jcs`.
- The release-facing quick start, API, CLI and verification pages identify the current 0.6 synthetic fixture separately
  from historically pinned examples. This documentation correction does not change record bytes.

### Earlier change (unpublished rc4 full-score proposal)

- A source-complete native bundle now projects rc4 full-score PER with independently rederived
  Q/E/C/G, overall readiness, decisive/reportable proof sets and four-component Governance G
  without evidence freshness. Missing required sources withhold the affected score; rc3 bytes
  are never silently interpreted under rc4.
- Added privacy-safe rc4 `explain --list`, numeric axis/metric/readiness summaries, and explicit
  rc4 identifiers in `standards()` while retaining the historical rc3 keys.
- The package-version proposal changes the converter version written into new record headers;
  canonical PER bytes and digests therefore change and must be reissued/gated before promotion.

### Earlier change (L5a/S1b native draft)

- At that stage, the bundled manifest and release digests identified EIO `0.5.0-draft.1` (`ontology_digest`
  `4cbe3a904af9038e`). The neutral native PER schema is `2.0.0-rc3-draft`; its proposed
  `w3id.org` identifier does not establish a live public endpoint.
- Native records use the rc3 draft vocabulary and schema. Validated native scoring inputs can
  produce a partial `reference-draft` score with independent checks; governance (G) and
  readiness remain withheld when the required source evidence is unavailable. The owner #22
  publication hold remains in force.

### Changed (L4: EIO-Agents scoring, post-L3s rebase)

- Added `eio_agents.scoring.engine`: the readiness-index engine with no numeric defaults; parameters come from a
  scoring-profile document. Added the profile registry, attested-profile mechanism and independent B4 schema/digest
  validation. An adapter producer carries its profile document in the bundle; the draft EIO reference-profile API is
  present but its scoring rules remain for S1b.
- Added the PER 2.0.0-rc2-draft schema. `scores.scoring_profile` is `{id, version, sha256}` and G component ids are
  profile-declared. L3s's producer and independent verifier privacy tables now classify these public structural leaves,
  admit only the reviewed harness-2.x/2.1.0 identity and six reviewed G ids for the L4 attested path, and retain all
  fingerprint/resolve behaviour. New attested identities need an explicit trusted approval path before publication;
  digest consistency alone does not make arbitrary identifiers private-safe.
- Removed `_vendored` and `_legacy`, their private-import exemptions and the vendored NOTICE entry. The harness adapter
  owns its copied Report extractors, governance classifier and attested harness-2.x profile document.
- Reissued the same 13 frozen records as R4 from R3S. The reviewed diff changes only rc2/scoring leaves: FIN_3 and EXAM_B
  G 52→46; credit-underwriter replay readiness 80.4→82.2. Claim/finding identities, privacy transformations and release
  states are unchanged. `REFERENCE_R4.md` and `diff/REVIEWED_DIFF.md` in the isolated candidate record the exact digests.

### Changed (L3s: the structural privacy fix, owner decisions #31 and #32)

- The closed field table (`eio_agents.per.privacy`): every string of a projected record, member names included, is a value
  of the release's or the PER schema's vocabulary (checked for membership), a structural value of a recorded form, a
  PROD-42 excerpt, a fingerprint `sha256-<64 hex>` of the exact producer text (plain SHA-256 over its UTF-8 bytes; keyed
  before the first upload), or a text rendered from these. Producer free text (the agent's goal, role and business case,
  model ids, persona names, capsule caveats, policy and profile names, fact sources, tool and retrieval names, context
  artifact and searched file names, metric and component labels, custom scenario labels, limitation parameters) is
  carried as its fingerprint; a summary shows `sha256-` and 12 hex digits, the full value staying in its params. A field
  the table does not list fails closed (`PRIVACY_UNCLASSIFIED`); a record string equal to a producer text of the bundle
  fails too (`PRIVACY_CLEAR_TEXT`). The round 2-4 pattern rules stay as a second layer; declared structural values (D-53)
  stay form-checked until S2.
- A behavioural finding's fingerprint takes its scenario label's record value (a trap-library label in clear, any other
  label as its fingerprint), so the verifier recomputes it from the record.
- The verifier's twin (`eio_agents.validation.privacy`): its own table; the new row W1 (every record string classified
  and of its class); X1 renders a fingerprint in its display form; D2 runs on the record's clear view and checks every
  fingerprint and decision against the bundle (T4) and that no producer text is in clear (T5).
- Record bytes: every record changes in its fingerprinted, decided and rendered fields only; claim ids, finding ids and
  fingerprints, claim states, predicates and turns, the release state, readiness and every score number are unchanged
  (the reviewed re-issue R3S). The golden JCS, the native vector's record and the self-test's FIN_3 record are re-issued.

### Added (L3s)

- `eio_agents.resolve(rec, bundle)`, `eio-agents resolve RECORD BUNDLE` and `eio-agents explain RECORD TARGET --local
  BUNDLE`: every withheld value with its real text from the local bundle (display only; nothing is added to the record).

### Added

- Public documentation: a rewritten README, and `docs/` pages on concepts, the quick start, the Python API, the command
  line, verification, standards coverage, and versioning with the roadmap steps L1 to L6.
- Project files: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), `SECURITY.md`, `GOVERNANCE.md`,
  `CITATION.cff`, `.gitignore` and `.gitattributes`.
- Package metadata: project URLs, keywords and classifiers.
- `py.typed`: the package is marked as typed (`Typing :: Typed`).
- Optional extras `lint` (ruff, pinned), `build` (build, twine) and `dev` (all tools, with pre-commit).
- Development tooling: ruff configuration in `pyproject.toml`, `.pre-commit-config.yaml` (byte-exact paths excluded), a
  CI workflow (lint; tests on Python 3.10 to 3.14; minimum dependency versions; the built wheel tested alone in a clean
  environment; goldens and conformance tools), a manual release workflow with PyPI trusted publishing, issue and pull
  request templates, Dependabot configuration and CODEOWNERS.
- L2a (structure only; record bytes unchanged): `eio_agents.base`, the bottom layer (`base.canon`: JCS, `stable_digest`,
  sha256 strings, number rules; `base.errors`: `ConversionError`, `require`). `eio_agents.adapters`, the producer-adapter
  interface (`ProducerAdapter` protocol with `name`, `version`, `kind = "adapter"`, `to_bundle(raw) -> dict`, and
  `adapter_metadata`), with no registry, no discovery and no entry points. `Ontology.witnessing_anchored(ref)`.
  `convert`, `convert_file` and `verify` take `*, ontology=None`. New tests: `tests/test_layering.py` (the import
  direction of every module, and fresh-process checks that neutral subpackages never load the staging area) and
  `tests/test_adapters.py`.

- L2b (the seam split; record bytes unchanged): the evaluation bundle, archive schema 3 draft 1, as a JSON Schema
  (`eio_agents.schemas.bundle_schema()`, `schemas/bundle/bundle-3.0.0-draft.1.schema.json`), with the contract sections
  header, provenance, sources, scope, context_assessment, graph, claims, ballots, trials, stage_records and limitations,
  plus the adapter-only `producer_declared` section (scenario labels and severity, the producer capability registry, the
  resolved context-link rows and the generic score-input section `{axis, value, components [{id, value}]}`).
  `eio_agents.per.project(bundle, *, ontology=None)`, the neutral projection: section validation, the producer-declared
  acceptance rule (rejected for `kind: native`, `PRODUCER_DECLARED_NOT_ACCEPTED`), stage-record digests, recompute of
  claim ids, span and receipt refs and pooled votes, then the views. A bundle without score inputs projects `scores` as
  null. Neutral halves of the split plan §3.10 seams: `adjudication.pool`, `adjudication.invalid_because`,
  `semantics.scope.qualify`, `semantics.claims.make_claim`, `semantics.findings.findings`, `semantics.proof.claim_proven`
  (rc1 rule unchanged), `semantics.release.gates` and `release`, `semantics.coverage.census`,
  `compliance.select_frameworks`, `resolvers.natural_resolver`, `reliability.reliability_block` over trial records,
  `scoring.ScoreView`, the ref constructors `evidence.refs.span_ref`, `receipt_ref`, `computed_ref`, and `per.header`.
  `ConversionError.code` (the typed error code). The staged adapter `eio_agents._legacy.old_report_converter.to_bundle(raw)`.
  Frozen X-TWIN vectors: `tests/data/bundles/` (3 goldens, 4 stress archives, `SHA256SUMS`), re-frozen with
  `tests/freeze_bundles.py`; new tests `tests/test_bundle.py`.

- L2c (the neutral API; record bytes unchanged: the 3 goldens, 4 stress and 6 replay records equal R0):
  `eio_agents.validation.validate(rec)`, `validate_bundle(bundle)`, `check_one(rec)` and `verify(rec, bundle, *,
  rederived)`, all in process. `eio_agents.verify(rec, bundle)` re-projects the bundle in process and checks it with the
  independent verifier, including VER-5 per locator kind over the bundle's `sources` (turn spans, tool receipts, typed
  absences, context spans and absences, the declared archive pointer, turn digests, claim decisions). Contract §6.2 step
  7: `per.project` validates the record it returns (the PER schema and the release's ids; typed code `PER_INVALID`),
  accepting only the rc1 requirements that carry ProofAgent vocabulary for a native producer, listed with their §5.3 row
  in `per/data/rc1_only.json`. Closed vocabularies of the loaded release checked on every bundle (claim states, evidence
  kinds, source types and anchors, tier, region, autonomy, domains, facts, frameworks, the policy object, severities, and
  the claims, turns and predicates that declared items name; codes `BUNDLE_VOCABULARY` and `BUNDLE_SCOPE`). The witness
  flag and anchor of every ref are recomputed from the release; a turn span must point into the declared turn source; a
  native producer mints no juror citation. `eio_agents.semantics.release.RELEASE_SEMANTICS` (the release-semantics
  version, a core constant) and `metric_label` (gate reasons name the `eio.metric.*` id when no label is declared).
  `eio_agents.scoring.published_metric_set` (the published metric set is the declared scoring profile's; the harness-2.x
  profile data declares the six metrics that carry a harness metric key). `python -m eio_agents`. X-NATIVE vector:
  `tests/data/native/` (a hand-authored native bundle, its expected PER and its pinned rc1-only problem list, written by
  `author_native.py` with EIO-Agents only). New tests: `tests/test_native.py`, `tests/test_verify.py`,
  `tests/test_neutral_constants.py` (the L2 exit AST/constant test with its exact allowlist).

- L2 fix round 1 (the fixes of the final L2 verification; record bytes unchanged: the 3 goldens, 4 stress and 6 replay
  records equal R0, and the X-NATIVE record and its pinned problem list are unchanged): the builders
  `evidence.refs.no_matching_call_ref` (the typed absence of a named tool call over listed turns) and
  `evidence.context_refs.policy_span_ref` (a POLICY_SPAN over a span of an embedded context artifact; the projector's
  context lines use it); `per.bundle.accept_native`, `check_episodes` and `check_native_sources`;
  `per.projection.ProjectionRefStore`. New tests: the verifier's probes and the new rules as `INVALID` cases in
  `tests/test_bundle.py` (among them the 13 bundles that crashed untyped), tests that a declared ref that recomputes is
  accepted, the relaxation rows pinned to their exact rc1 errors (`tests/test_native.py`), the verifier twin of the new
  rules (`tests/test_verify.py`), and the pinned Report-key exclusion set of the AST/constant test.

- L2 fix round 2 (the fixes of the re-verification of L2; record bytes unchanged: the 19 R0 inputs, the 7 frozen
  bundles, the 3 goldens, the X-NATIVE record and its pinned problem list, and the rule-6 context vector):
  `per.bundle.check_names` (step 1, the name rules), `per.bundle.check_context_search` (the context-search recompute shared
  by gaps and absences), `per.bundle.loads` and `validation.validate.loads_bundle` (bundle text as I-JSON), and
  `per.evidence.ref_key` (the 03 §5.6 rule 1 key). New tests: `tests/test_reverify_l2.py` (every (kind, source type,
  anchor) combination of the release, in the projector and in the verifier twin; the re-verification probes; the R-3
  ordering; the I-JSON reader) and 35 `INVALID` cases in `tests/test_bundle.py`.

- L3 (the ProofAgent adapter leaves EIO-Agents; record bytes unchanged: the 19 R0 inputs through the adapter, the 3
  goldens, the 10 frozen bundles, the X-NATIVE record and its pinned problem list): the ProofAgent adapter (the legacy
  crosswalk, the archive schema 1/2 reader, the recipes, the report converter and the legacy verifier) lives in the
  ProofAgent Harness as `proofagent_harness.eio_adapter` (`to_bundle`, `convert_legacy`, `verify_legacy`,
  `ADAPTER_VERSION`), with its tests and fixtures; `_legacy/` holds only the vendored-scorer loader `harness2x` until L4.
  The frozen context bundles `tests/data/bundles/context/` (the FIN_3 and MED_1 bundles with the FIN agent's three
  artifacts, embedded or by digest) replace the stored-report inputs of the neutral tests. The fixes of the L2 exit
  deviations D-29 to D-35 (the final L2 re-verification, F-1 to F-13): `Ontology.data_classes` and
  `Ontology.artifact_kinds` and the verifier reader's own copies; `evidence.refs.state_fact_ref` (a STATE_FACT over a
  declared state snapshot), `evidence.refs.CALL_TERM` and `QUOTE_ANCHORS`; `evidence.context_refs.withheld`,
  `EXCERPTABLE`, `confidential_digests`, `effective` and `casefold_offsets`; `semantics.proof.w1_unmet`;
  `validation.checker.Checker.proof_candidate`; bundle schema draft 1 gains the optional `sources.state_field` and
  `turns[].state` (no frozen bundle changes). New tests: `tests/test_l2_exit_deviations.py` and 30 `INVALID` cases in
  `tests/test_bundle.py` (the re-verification's probes T01-T31 that now fail closed).

### Changed

- L3. `convert` takes an evaluation bundle only: a stored ProofAgent Harness report (archive schema 1 or 2) is refused
  with `BUNDLE_INPUT`, whose message names its converter (`proofagent_harness.eio_adapter.convert_legacy`); the
  stored-report branch of D-4 and its lazy import of `_legacy` are deleted. `harness2x` no longer imports the legacy
  crosswalk (its `lx` argument is read by duck typing). The self-test's neutral share (31 of the 53 injected defects) stays
  here; the adapter's share (22) runs in the harness. Rule changes, each byte-neutral for every gated input, that fail
  closed where L2 failed open or untyped (L2 exit D-29 to D-35): a context artifact's data class and kind must be ids of
  the release (`BUNDLE_VOCABULARY`; an unknown class read as not confidential); a lone surrogate in bundle text or in a
  string of a dict bundle is `BUNDLE_INPUT` (it reached an untyped `UnicodeEncodeError`), a float tool-call index is
  `BUNDLE_RECOMPUTE` (untyped `TypeError`), and a citation key inside a free-form producer field is `PER_INVALID` (untyped
  `KeyError`); a declared ref carries no statement (a declared CALCULATION or TYPED_ABSENCE never converts); PROD-43 reads
  an artifact as the most restrictive declaration of its bytes, and withholds the excerpt of every data class but
  `eio.data.public` and `eio.data.internal` (read fail-closed; the spec names model-confidential); a context text whose
  casefold changes its length is searched through an offset map instead of being skipped (it gave false absences); a
  state fact over a declared state snapshot is rebuilt (the adapter's R-PERSIST recipe converts again, with the frozen
  eio-per oracle's bytes); a claim whose contract check records `no_witnessing_ref` is not PROVEN (W1); named-call terms
  are lower-case ASCII names; an exact or casefold span quotes at least one character; a context-artifact name is in NFC
  (`BUNDLE_SCHEMA` at step 1); a context-search term is plain text and a searched name does not spell an embedded
  artifact's name another way; the same policy text at the same offsets of two artifacts fails closed with its name
  (the 03 §6 collision rule is not implemented until S5). The verifier applies each rule independently (`validate_bundle`
  B0, B1, B3; VER-5 in `D2`; the W1 precondition in `F1` and the cap check).

- L3 fix round 1 (an adversarial verification of the rules above; record bytes unchanged for every gated input). Every
  producer-chosen text that reaches the record is the bundle's or the release's: the layout names `turn_source_ref`,
  `calls_field` and `state_field` are identifiers (`BUNDLE_SCHEMA`), the archive and argument pointers hold identifier
  and index tokens; a ref that no recipe rebuilds names a source the bundle declares (the turn source, the state field,
  a context artifact, a retrieval source) and carries no tool receipt; a native producer's context search names declared
  artifacts with release checklist terms (the gap's control's); an adapter producer may also name a portable file that
  it does not declare and search a printable ASCII phrase of its own checklist; a named-call term is at most 64
  characters; a term that is not a release checklist term (nor, for a named call, part of a declared tool name or tool
  schema) and an undeclared name reproduce no confidential content the bundle carries: three consecutive words of a
  withheld artifact's text, or a whole tool-call or state value that identifies (two words, a digit or an '@')
  (`per.bundle.Withheld`); scenario labels and context-link keys are labels and a context link's `via` is its link
  (`BUNDLE_RECOMPUTE`, `BUNDLE_VOCABULARY`). The record's `provenance.inputs.context_artifacts` must be the bundle's
  `sources.context_artifacts`. PROD-43 withholds the same text in another normal form or with other line ends
  (`evidence.context_refs.normalized_digest`). An integer too long for Python to read or beyond the IEEE 754 double
  range, and in a dict bundle a value JSON has not (a tuple, a set, bytes, an integer member name), are `BUNDLE_INPUT`,
  and the canonical form types such an integer `NON_FINITE` (they raised untyped). A context search reads 'İ' as 'i'
  (`evidence.context_refs.fold`). A STATE_FACT witnesses only a predicate whose evidence contract names STATE_FACT
  (`semantics.proof.witnesses`). The verifier applies each rule with its own code (B0, B1, B3, A1, C3, D2, F1). New tests:
  12 in `tests/test_l2_exit_deviations.py` and 53 `INVALID` cases in `tests/test_bundle.py` (`L3r1`).

- L3 fix round 2 (a second verification of the rules above; record bytes unchanged for every gated input). The names a
  record carries hold no withheld content in any spelling: the declared context-artifact names (a ref's `source_ref`, a
  context search's file names, `provenance.inputs`, the AI-BOM), the layout names, the archive-pointer keys and pointers,
  tool-call names and retrieval sources, scenario labels and context-link keys (`per.bundle.check_withheld_names`,
  `BUNDLE_RECOMPUTE`); a text is read verbatim, normalized (NFKD, invisible characters dropped, look-alike letters read
  as Latin), case-folded and snake, kebab and camel case folded (`per.bundle.words`). The record-wide rule: no string of
  the record, nor of the bundle where a record carries it in clear, carries withheld content (`WITHHELD_CONTENT`), outside
  three named exemptions (the PROD-42 excerpt of a turn span, the agent's goal and role, a tool-call name that a
  withheld text names as a whole token). An undeclared searched name is exempt from the artifact-text rule only when it
  equals a declared artifact's file name, and only a public or internal tool schema exempts a named-call term. A
  limitation's field path is one of its catalogue paths and a completed path names a value of the record (`PER_INVALID`,
  as the verifier reads it); a human decision cites a HUMAN_SIGNOFF over HUMAN_REVIEW (`BUNDLE_RECOMPUTE`). The verifier
  applies each rule with its own code (`B3`, `C2`, `D2`), and `validate_bundle` names a data class that is not of the PER
  schema's form; a policy excerpt is checked by the record-wide rule. A producer limitation whose parameters do not
  fill its catalogue texts (`TEMPLATE_PARAMS`) and a score-input axis that names an unknown context criterion
  (`BUNDLE_SCORE_INPUTS`) raised an untyped KeyError, and a limitation parameter named like an argument of the
  projector's helper an untyped TypeError (the parameters are now read as a dict); `validate_bundle` names the first
  two and an unknown limitation id (`B3`). New tests: 9 in `tests/test_l2_exit_deviations.py` (with the parametrized
  twin-parity cases) and 40 `INVALID` cases in `tests/test_bundle.py` (`L3r2`).
- L3 fix round 3 (a third verification; record bytes unchanged for every gated input). The record-wide rule counts
  PROD-42's identifying classes among the tool-call and state values that name a subject (`per.bundle.subject_value`,
  `identifying_words`): a run of four digits or more, two number groups or more, a word of letters and digits
  ('123-45-6789', '4111 1111 1111 1111', '312 555 0147', 'ACCT88419372', '0000'); a short plain number ('0.5', '42') and
  one word ('lookup') stay out. A text is also read with its percent-encoding and JSON Pointer escapes decoded
  (`per.bundle.decoded`). The tool-name exemption holds only for an identifier-shaped name of a tool the bundle observes
  or a public or internal tool schema declares, that is not itself of an identifying class (a secret key or a URL token
  of a withheld prompt is checked). A published reliability rate with a null value fails closed with `BUNDLE_SCHEMA` (an
  untyped TypeError before); a claim's votes are null if and only if it is decided deterministically
  (`BUNDLE_RECOMPUTE`, as the verifier's `C2` reads it). The verifier applies each rule with its own code (`B3`, `D2`),
  and `validate_bundle` names a human decision without a HUMAN_SIGNOFF. New tests: 21 `INVALID` cases in
  `tests/test_bundle.py` (`L3r3`) and 5 in `tests/test_l2_exit_deviations.py` (`test_r3_*`, with their parametrized
  cases).
- L3 fix round 4 (a fourth verification; record bytes unchanged for every gated input). The subject rule reads every
  scalar of the tool calls and state snapshots (a number as its JSON text: a card number sent as a JSON number) and the
  PROD-42 identifying-class matches of the turns' questions and answers (`per.bundle.turn_subjects`), with every decimal
  digit of any script read as its ASCII digit (`per.bundle.ascii_digit`) and JSON '\\u' escapes decoded
  (`per.bundle.decoded`). New, the identifying-shape backstop (`per.bundle.shape_problems`, `WITHHELD_CONTENT`): no
  string of the bundle that a record carries in clear holds an identifying-shaped token, known subject or not: four
  digits or more whatever separates them, two digit groups or more, a word of six letters and digits or more, sixteen
  hex characters or more, a base64 run, an e-mail address, a URL with credentials, a secret-key prefix; allowed only the
  recorded forms of their fields (digests, claim and ref ids, run ids, short release digests, source revisions, the
  configuration fingerprint, the checks version, run timestamps, versions), a string the release publishes, a short
  plain decimal and the words 'base64' and 'sha256'; a ref's excerpt is PROD-42's. The verifier applies both with its
  own code (`B3`, `D2`). New tests: 30 `INVALID` cases in `tests/test_bundle.py` (`L3r4`) and 6 in
  `tests/test_l2_exit_deviations.py` (`test_r4_*`, with their parametrized cases).

- L2 fix round 2. A ref's witness flag and anchor count for proof only on a ref that `convert` rebuilds from the bundle's
  own sources (a turn span, a tool receipt, a typed absence over the tool calls or over context artifacts, a policy span):
  any other ref is accepted only as a non-witnessing ref that locates no text (no offsets, digests or excerpt), so a
  CALCULATION, a typed absence over the answer or a state ledger, a state fact or a human sign-off with a witnessing
  anchor, and a declared ref quoting a source the bundle does not carry fail closed (`BUNDLE_RECOMPUTE`). A turn ref that
  locates text is always a span of the turn; anchor `turn` cites the whole turn; anchors `line` and `document` belong to a
  POLICY_SPAN. Every name the sources are resolved by names one item: a turn index or a context-artifact name given twice,
  or `context_texts` that are not exactly the embedded artifacts' texts, fail with `BUNDLE_SCHEMA`, and bundle text is read
  as I-JSON (an object member given twice, a NaN or infinite number, undecodable bytes: `BUNDLE_INPUT`; before,
  `per.project` leaked `UnicodeDecodeError`). A bundle nested more than 100 levels fails closed at read time
  (`BUNDLE_INPUT`; before, some depths raised an untyped `RecursionError` late in the projection, whatever the caller's
  stack), and the stored-report branch no longer leaks `RecursionError`. A context gap or
  absence recomputes over every embedded file it names, whatever else it names, and a context absence is always the
  builder's ref. The named-call absence takes non-empty lower-case names only (builder `INVARIANT`, projector
  `BUNDLE_RECOMPUTE`). The evidence block orders refs by the rule 1 key, so a context line that only the scores step
  derives (the Q axis's lines) is placed by the rule instead of raising an untyped `KeyError`. The JCS number and string
  errors and the template parameter error carry their codes (`NON_FINITE`, `LONE_SURROGATE`, `TEMPLATE_PARAM_TYPE`). The
  verifier: VER-5 applies the same rules (names, I-JSON, the declared-ref rule, the whole-turn anchor, receipts over the
  tool-call list, the full statement of an absence, context absences over every embedded file, the nesting limit);
  `validate_bundle` reports bundle text that is not I-JSON or nests too deep (`B0`) and the name rules (`B1`); `verify`
  reports a record without a canonical form (a NaN, nesting too deep) as a failing row instead of raising. The command
  line checks a bundle file from its bytes (`validate`), and a JSON list or nesting too deep no longer gives a traceback.

- L2 fix round 1. `convert` recomputes the computed statements and policy spans of a bundle (contract §6.2 step 2): a
  typed absence over the declared tool calls (the whole ref, rebuilt from sources; a true absence counts 0), a typed
  absence and a context gap over embedded context artifacts, and a POLICY_SPAN, which must point into a declared,
  embedded artifact (no excerpt of model-confidential text, PROD-43). A declared ref with the id of a ref the projector
  derives must be that ref (typed code `BUNDLE_RECOMPUTE`); the shared `RefStore` is unchanged. Until S7 the bundle's
  `graph.episodes` must be the scenario-label grouping of its turns, an unlabelled turn being its own episode. A native
  producer's bundle is its own archive: a declared `header.source_archive` is rejected (`PRODUCER_DECLARED_NOT_ACCEPTED`),
  every stage record must be `producer: native` (`BUNDLE_STAGE_RECORDS`), and its archive pointer, tool-call pointers and
  `transcript_sha256` must recompute from the bundle. Every turn ref, with or without text, must name the declared turn
  source, and every ref's turn must be a turn of the bundle; a turn carries one scenario label; `header.eio` must name the
  loaded release when the stage digests are checked. The step-7 relaxation rows (`per/data/rc1_only.json`) are pinned to
  their exact rc1 errors (no row accepts any message). Bundle schema draft 1 types `ref.tool` (the receipt, required on a
  TOOL_RECEIPT), `ref.statement` (required on a TYPED_ABSENCE), `ref.source_ref` (a string), `ref.span_sha256` and
  `ref.source_sha256` (a digest or null) and `parameters.votes` (null, or non-negative integer counts), so these
  schema-valid bundles fail with `BUNDLE_SCHEMA` instead of an untyped exception. The verifier: VER-5
  also fails a POLICY_SPAN outside the declared artifacts, a turn ref without text outside the declared turn source, an
  episode absence over turns the bundle lacks, and an absence that counts more than 0; the episode of a claim is the
  union of its turns' episodes. `validate_bundle` checks the native-producer rules, and its documentation states that it
  does not recompute.

- L2c: the proof rule reads the declared `parameters.fidelity`: a claim is `PROVEN` iff it is decided deterministically or
  by a human, cites a witnessing anchored ref, and its fidelity is `exact` or its recurrence band `CONFIRMED`. The rc1
  exemption for a claim without a source key is deleted, in the projector and in the verifier; a claim whose declared
  fidelity differs from its rc1 `mapping_relation` fails closed. The verifier's mixed checks are split at their seams:
  the neutral halves (header, EIO ids, domains, orders, claim parameters, findings, controls, scores, release,
  reliability, limitations) are in `eio_agents.validation.checker.Checker`, the ProofAgent halves in
  `_legacy.legacy_verifier.LegacyChecker` (its driver is now `rc1_check_one`). The command line is neutral: `eio-agents
  project | validate | verify | explain | version`; `verify` takes `--bundle`, `validate` also checks a bundle, and a
  missing file is reported without a traceback. `convert` takes JSON bytes or a dict (a path goes to `convert_file`);
  bytes that are not a JSON object raise `ConversionError` with code `BUNDLE_INPUT`. `explain` returns only the
  record's registered `eio.why.*` renderings, and raises `LookupError` for an unknown target or template. `standards()`
  adds `ontology_sha256`, `per_schema_id`, `projector` and `version` (`per_schema` and `converter` are kept for one
  version). A stored ProofAgent report still converts (until L3), through a lazy import, so a bundle never loads
  `eio_agents._legacy`. Bundle schema draft 1: `header.adjudication_source`, `provenance.record.harness_llm`,
  `sources.completeness.sentinel_locations` / `code_check_offsets`, `score_inputs.metrics[].legacy_metric` and
  `sources.archive_pointer.archive_sha256` are optional (a native producer declares none of them); a metric `label` may
  be null; the projector writes the archive digest into the record's archive pointer. A finding without scenario labels
  has `traps: []` and fingerprint input null.
- Development status classifier `3 - Alpha`. Runtime dependencies have upper bounds: `pyyaml>=6.0,<7` and
  `jsonschema>=4.20,<5`.
- `NOTICE` names EIO-Agents, gives the full revision and the correct pin location of the vendored ProofAgent Harness
  files, and adds trademark, framework attribution and licence notes.
- The package license is declared as the SPDX expression `Apache-2.0`, with `LICENSE` and `NOTICE` as license files.
- Docstrings and comments no longer cite internal planning documents. The `convert` docstring now lists the exceptions it
  can raise.
- L2a: the package root is lazy (PEP 562): `import eio_agents` imports no submodule, and `import eio_agents.ontology` (or
  any other public subpackage) no longer loads `eio_agents._legacy`, `eio_agents._vendored` or `eio_agents.api`. The public
  names of the root are unchanged. `api.py` no longer keeps a process-global `Ontology`: without `ontology=` each call
  loads and verifies the bundled release. `ontology` imports only `base` and `schemas`: `STATES` and `norm_token` now live
  in `eio_agents.ontology` (`semantics` re-exports `STATES`), and the witness rule is defined by `Ontology` (the
  `evidence.witness` functions delegate to it), so `semantics` no longer imports `evidence`.

- L2b: `eio_agents.convert` projects an evaluation bundle (archive schema 3); a stored ProofAgent report (schema 1 or 2)
  goes through the staged adapter first, `project(to_bundle(raw))`, with identical bytes. It also accepts JSON text. The
  rc1 converter's ProofAgent reads (the policy step, intake, recipes, consensus log, reliability report, harness-2.x score
  values and Report fields) now write bundle fields; everything after that reads only the bundle.
  `evidence.refs.no_call_ref` takes `source_ref` and `calls_field` (no ProofAgent layout is assumed);
  `reliability.band_of` reads a bundle trial record `{claim_id, ledger_key, trial_kind, reproduced_in, passes}`.
  `CONVERTER` and `SCHEMA_URI` moved to `eio_agents.per.header` (the converter module re-exports them).

### Removed

- L3: the modules `_legacy.legacy_crosswalk`, `_legacy.schema12_adapter`, `_legacy.legacy_recipes`,
  `_legacy.old_report_converter` and `_legacy.legacy_verifier` (moved to `proofagent_harness.eio_adapter`); the recipe for
  authoritative checker records (its records failed `validate()`; the adapter fails such an archive closed
  with `CHECKER_AUTHORITATIVE_UNSUPPORTED`); the child-process regeneration of the legacy verifier (`GENERATOR`,
  `c_regen`, `c_determinism`: the adapter's `verify_legacy` re-converts in process); `api._convert_stored_report`;
  `tests/freeze_bundles.py` (the adapter's suite regenerates the frozen bundles).
- L2c: `api._archive_path` and `api._run_check` (temporary files and captured output); the subprocess re-conversion in
  `verify` (the rc1 regeneration `c_regen` / `c_determinism` stays in `_legacy.legacy_verifier` for its own command line);
  the `convert` command (`project` replaces it); reading a path or JSON text in `convert`.
- Two unused imports in the tests.
- L2b: `eio_agents.scoring.AX`, the harness-2.x axis-key table (the score inputs are keyed by EIO axis id).
- L2a: the modules `eio_agents.errors` and `eio_agents.semantics.canon` (moved to `eio_agents.base.errors` and
  `eio_agents.base.canon`; no alias), and `norm_token` from `eio_agents.semantics.scope` (now in `eio_agents.ontology`).

## [0.1.0.dev1] - 2026-09-28

Bundles EIO 0.4.0 and PER 2.0.0-rc1. Record bytes change: no; the golden records are byte-identical to `0.1.0.dev0`.

### Added

- Console script `eio-agents` (it replaces `per`); `eio-agents version` prints the library version, which is the
  distribution version (tested).
- `eio_agents.ontology.load()` returns an explicit `Ontology` object. Every call reads and verifies the release and
  returns a new object; there is no process-global cache.
- `eio_agents.validation`: the independent parts of the reference verifier (its own canonical form and digests, EIO
  reader, limitation catalogue, explanation renderer, PER Pointers, redaction and gate rules, the record-level checks, and
  `explain`). It imports no converter module (tested).
- `tools/eio_digests.py`, which computes and checks `RELEASE-DIGESTS.json`, and `tools/eio_gates.py`, which runs the 37
  EIO build gates and their 40 negative vectors against the bundled release.
- The verifier self-test (53 injected defects) as `tests/test_verifier_selftest.py`, with its fixtures bundled.
- A dependency test: no module outside the vendored scorer and its loader imports ProofAgent Harness, imports it
  dynamically, writes `sys.modules`, loads code by path or discovers plugins.

### Changed

- Distribution renamed to `eio-agents`, import package `eio_agents`.
- The package is split into neutral subpackages (`ontology`, `schemas`, `semantics`, `evidence`, `resolvers`,
  `adjudication`, `reliability`, `compliance`, `scoring`, `per`, `validation`). The code that reads ProofAgent Harness
  reports is staged in `_legacy`, and the vendored harness-2.x scorer is in `_vendored` (step L1; see
  [docs/versioning.md](docs/versioning.md#roadmap-steps)).
- The EIO data moved to `ontology/data/`, and the EIO and PER schemas to `schemas/eio/` and `schemas/per/`, byte for byte.
- The limitation catalogue (48 ids) is a data file, `per/data/limitations.json`. Nothing parses Markdown at run time.
- The verifier reads only the bundled release: it has no environment variable and no default path into another
  repository.
- The public API is unchanged.

### Removed

- The standards sync tool: this repository is where the EIO data and schemas are authored.
- The standalone explanation script, superseded by `explain`.

## [0.1.0.dev0] - 2026-09-27

Bundles EIO 0.4.0 (`ontology_digest` `ed5389af5235e4b8`) and PER 2.0.0-rc1. First package.

### Added

- `convert`, `validate`, `verify` and `explain`, and the `per` command line.
- Conversion and checking logic moved from the conformance tools of the PER 2.0 specification. It reproduces their golden
  records byte for byte.

[Unreleased]: https://github.com/ProofAgent-ai/eio-agents/commits/main
