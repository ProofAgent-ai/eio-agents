# Verification

A PER record is meant to be checked, not trusted. This page describes what EIO-Agents `0.8.0` checks, what those checks
establish, what they do not, and how the library's own conformance is tested.

- [validate and verify](#validate-and-verify)
- [The checks](#the-checks)
- [What verification establishes](#what-verification-establishes)
- [Using verification in a pipeline](#using-verification-in-a-pipeline)
- [How the verifier is tested](#how-the-verifier-is-tested)
- [How the EIO release is checked](#how-the-eio-release-is-checked)
- [Running every gate](#running-every-gate)

## validate and verify

- `validate(record)` checks the record on its own, in process: the PER JSON Schema of its declared `per_version`
  (rc3 partial, historical PER 2.0.0, or current PER 2.1.0; JSON Schema draft 2020-12, with formats) and every EIO rule that can be
  recomputed from the record and the bundled EIO release.
- `verify(record, bundle)` runs the same checks, then VER-5 against the record's evaluation bundle (every ref and digest
  the bundle's sources determine, recomputed per locator kind), re-projects the bundle and compares `per_sha256` of the
  two, all in process. The result is valid only when no check fails and the digests match.
- `validate_bundle(bundle)` checks a bundle before it is projected: its text as I-JSON (no lone surrogate included), its
  schema and the name rules the schema cannot state (names given once and in NFC, a state snapshot named by
  `sources.state_field`, layout names that are identifiers and pointers of identifier and index tokens), its stage
  records, the adapter-only producer-declared section and the release's closed vocabularies (a context artifact's data
  class and kind, scenario labels and context links included).
- From L3 fix round 1, VER-5 (`D2`) also checks, with the verifier's own code, that every producer-chosen text of the
  record is the bundle's or the release's (the sources a ref names, context-search terms and names, named-call terms,
  layout names and pointers) and reproduces no confidential content the bundle carries, and that the record's
  `provenance.inputs.context_artifacts` are the bundle's sources; `A1` checks the data classes the record states; `C3`
  and `F1` read a STATE_FACT as a witness only for a predicate whose evidence contract names it.
- From L3 fix round 2, `validate_bundle` (`B3`) and VER-5 (`D2`) check, with the verifier's own reading of a text
  (`validation.validate.Content`: verbatim, normalized, case-folded, snake, kebab and camel case folded), that no
  name the record carries (declared context-artifact names, layout names, archive-pointer keys and pointers,
  tool-call names, retrieval sources, scenario labels, context-link keys) and no other string of the bundle that
  a record carries in clear holds withheld content; `D2` also checks every string of the record itself (the
  record-wide rule), outside three named exemptions: the PROD-42 excerpt of a turn span (the agent's answer or the
  user's question; a policy excerpt is checked), the agent's goal and role, and a tool-call name that a withheld
  text names as a whole token. An undeclared searched name is exempt
  from the artifact-text rule only when it equals a declared artifact's file name, and a tool schema exempts a
  named-call term only when its class is public or internal. `C2` requires a human decision to cite a
  HUMAN_SIGNOFF over HUMAN_REVIEW, and `B3` names a data class that is not of the PER schema's form.
- From L3 fix round 3, a tool-call or state value also names a subject when it is of an identifying class of PROD-42
  (a run of four digits or more, two number groups or more, a word of letters and digits), a text is also read with
  its percent-encoding and JSON Pointer escapes decoded, and the tool-name exemption holds only for an
  identifier-shaped name of a tool the bundle observes or a public or internal tool schema declares, not itself of an
  identifying class. `B3` also names a human decision without a HUMAN_SIGNOFF, a claim whose votes are not null
  exactly when it is decided deterministically, and a published reliability rate with a null value.
- From L3 fix round 4, a subject is any scalar of the tool calls and state snapshots (a number as its JSON text) or a
  PROD-42 identifying-class match of a turn's question or answer, a decimal digit of any script reads as its ASCII
  digit and JSON '\\u' escapes are decoded; and `B3` and `D2` apply the identifying-shape backstop
  (`validation.validate.shape_problems`, the verifier's own reading): no string of the bundle that a record carries
  in clear holds an identifying-shaped token (four digits or more whatever separates them, two digit groups or more, a
  word of six letters and digits or more, a long hex or base64 run, an e-mail address, a URL with credentials, a
  secret-key prefix), outside the recorded forms of their fields, the strings the release publishes, a short plain
  decimal, and the words 'base64' and 'sha256'.

These checks return rows of the form `{check, ver, status, detail}`. The `ver` column names the verification requirement
of the PER 2.0 specification that the check implements (for example `VER-4`). A native bundle without scoring inputs
projects `scores: null`. With validated `native_scoring` inputs, projection may include partial metrics/axes;
verification checks those source-derived fields, not producer-supplied score numbers. G/readiness remain withheld where
required source evidence is absent.

## The checks

| Check | What it recomputes |
|---|---|
| S1 | JSON Schema of the declared `header.schema_uri` (draft 2020-12, formats) |
| S2 | Every claim against the EIO evaluation-claim schema |
| S3 | Header: PER 2.x and `per_semantics_version` |
| S4 | `header.eio` digests, recomputed from the bundled release |
| S5 | `relative_path` values in Unicode NFC |
| A1 | Every EIO id exists in the release, with its values |
| A2 | Domain resolution |
| A3 | Coverage: obligations, census, counts |
| E1 | Cited refs resolve, and only cited refs are carried |
| E2 | The witness rule, recomputed for every ref (a producer's flag is never trusted) |
| E3 | `cited_refs_hash` and counts |
| E4 | Declared array orders |
| C1 | Claim ids |
| C2 | Conditional claim parameters and votes |
| C3 | Evidence contracts |
| F1 | Findings: ids, severity, decider, witness, and the W1 precondition of PROVEN (a claim with a witnessing ref inside its contract scope) |
| K1 | Control statuses |
| M1 | Scores: caps, cap reasons, drivers present |
| X1 | Explanations re-render from the registered `eio.template.why` templates |
| X2 | Control and release wording (for example, no control summary may say "compliant") |
| R1 | Gates |
| R2 | The release recommendation and its invariants; for PER 2.1.0 (release semantics 2.2) the no-policy default floor recomputed from the record: with policy source `none`, readiness below 85 (or withheld) or an unmet HARD_BLOCK obligation requires the matching `review_guard` entries and rejects a claimed PASS |
| L1 | Reliability ledgers and rate |
| T1 | Limitations come from the core catalogue or an explicitly declared, digest-checked catalogue |
| P1 | PER Pointers and view ids resolve |
| N1 | Numbers: finite, no negative zero, 4 decimal places, integral counts |
| W1 | From L3s (decision #31): every string of the record, member names included, is listed by the verifier's own closed field table and fits its class (vocabulary member, recorded form, PROD-42 excerpt, `sha256-` fingerprint, a vocabulary member or fingerprint, a strict version or fingerprint, a rendered text); a `sha256-` value nowhere else |
| D1 | `per_sha256` |
| D2 | VER-5 over the bundle's sources: archive identity, run, transcript digest, archive pointer, the names the sources are resolved by, turn digests, every span (an exact or casefold one non-empty), tool receipt, typed absence (plain search terms, no name spelt another way), policy span (no excerpt of a withheld data class, nor of the same bytes under another name) and state fact the sources determine; the context artifacts' data classes and kinds; any other ref non-witnessing, locating no text and carrying no statement; and the claims' decisions; from L3s (decision #31) the comparisons run on the record's clear view (each fingerprint replaced by its bundle text), every fingerprint is that of a text at its field's source path, each vocabulary-or-fingerprint and version-or-fingerprint decision recomputes, and no record string outside an excerpt equals a producer text of the bundle (only with the bundle) |
| D3 | Re-projection is byte-identical (only with the bundle) |
| D4 | For a native scored PER, independently recompute its checked score/profile fields from the bundle and pinned ontology, including the PER 2.1.0 HIGH-review guard and the release semantics 2.2 no-policy default floor guards; reject forged values or unsupported score claims |
| D5 | Independently check new-release native `PROVEN` status against targeted, source-verified proof citations; old pinned 0.4 semantics remain historical |

These checks live in `eio_agents.validation`, which has its own canonical form, digest code, EIO reader and renderer and
imports no projector module (tested); `eio_agents.verify` re-projects the bundle and passes the result in. The mixed checks
are split at their seams (L2): their ProofAgent halves (the legacy crosswalk row of each claim, the harness-2.x profile
checks for scores, proof over the rc1 mapping relation, the premise-check claim `C4`, and the checks against a raw
ProofAgent report and its re-conversion) are the producer verifier's: the ProofAgent adapter's legacy verifier, in the
harness since step L3 (`proofagent_harness.eio_adapter.verify_legacy` runs it next to `eio_agents.verify` over the
adapter's bundle, in process).

## What verification establishes

A valid result with matching digests establishes two things:

1. **Integrity.** The record is well formed, every derived block (findings, controls, scores, gates, the release
   recommendation, explanations) agrees with its claims and evidence under the bundled EIO release, and `per_sha256` is the
   digest of its canonical bytes.
2. **Derivation.** Projecting the given bundle with the same EIO-Agents version produces exactly this record, and the
   record's refs and digests agree with the bundle's sources.

It does not establish:

- that the bundle (or the archive it was read from) came from a real run, or was not edited before projection;
- that the agent, or a jury such as the ProofAgent Harness jury of juror agents, would decide the same way again;
- that a `PROVEN` claim is true. `PROVEN` is the outcome of the EIO evidence rule, not ground truth;
- any certification, attestation or legal conformity. Control statuses show evidence relevance only.

Two more limits apply today:

- Re-derivation uses the same converter that produced the record. A matching digest shows that this implementation
  reproduces the record; an independent check of the conversion needs a second, independent implementation, which does
  not exist yet.
- Records are not signed. A digest shows that a record is unchanged relative to a digest you already trust; it does not
  say who produced it. Signed attestation is planned.

A claim decided only by a semantic resolver (a jury finding) is never `PROVEN` and cannot by itself make the
recommendation BLOCK, and the checks above enforce this for every claim.

## Using verification in a pipeline

- **Producer.** After each run, project the exact bundle bytes, keep the bundle, and publish the record with its
  `per_sha256`.
- **Verifier or store.** On receipt, call `verify(record, bundle)`, or call `convert(bundle)` yourself and compare
  `per_sha256` with the producer's. Keep the record you derived. Do not accept a record supplied by a client without
  re-deriving it.
- **Same version.** Re-derivation reproduces the bytes only with the same EIO-Agents version, because the bundled EIO
  release and the converter are part of the result. `eio-agents version` shows what a build bundles.
- **Server input.** Pass the bundle as bytes or a parsed dict; `convert` never reads a path.

## How the verifier is tested

The older verifier self-tests use a pinned synthetic native PER and inject one defect at a time. They assert that
mutations such as an invalid witness, altered claim or release field, and wrong digest are rejected for that vector.
Historical 0.6/PER 2.0.0 native bytes remain under `tests/data/native/v0_6/`; current 0.8/PER 2.1.0 native bytes are under `tests/data/native/v0_8/`. The single older self-test module
below is not, by itself, a current release gate. Historical producer-specific vectors live in the separate
adapter-compatibility corpus.

```bash
.venv/bin/python -m pytest -q tests/test_verifier_selftest.py
```

The result depends on the source snapshot; run the command and record its actual output for the final package gate.

Other tests:

- **Native producer.** `tests/data/native/v0_8/` holds the current synthetic PER 2.1.0 bundle and byte-pinned PER.
  `v0_6/` and older fixtures directly under `tests/data/native/` keep their historical pins.
- **Adapter compatibility.** Historical producer archives, golden records and stress inputs are retained outside the
  standalone package for the producer adapter's compatibility gate; they are not public package fixtures.
- **Neutral code.** An AST test scans active package code for historical adapter parameters and report keys, and requires
  every remaining occurrence to match an exact, reviewed allowlist; a stale exception also fails.
- **Import surface.** No active module imports the ProofAgent Harness, a network library or a model client.

## How the EIO release is checked

Each EIO module is pinned in the manifest by exact version and sha256, and `eio_agents.ontology.load()` refuses a release
whose bytes differ.

- `module_sha256` = `"sha256:"` + SHA-256 of the raw module file bytes.
- `ontology_sha256` = `"sha256:"` + SHA-256 of the JCS of `{module_id: module_sha256}` over the manifest and every module it
  imports.
- `ontology_digest` = the first 16 hex characters of `ontology_sha256`.

For the pinned EIO 0.6.0 release these are `ontology_sha256`
`sha256:a27cf1f3ab755446c639da6b0e6d3b2c4363c205e6ffa4b44e48876cce72ecc9` and `ontology_digest`
`a27cf1f3ab755446`, over 39 modules; `RELEASE-DIGESTS.json` also pins 12 files (the EIO JSON Schemas, JSON-LD contexts
and reference cases).
Every record carries these digests in its header, and check S4 recomputes them.

`tools/eio_gates.py` checks the release's imports, ids, rules, digests and other invariants. Some historical golden-vector
options in that script still target the external adapter corpus; they are not a standalone package smoke test until the
gate runner is updated and revalidated.

## Running every gate

From the repository root, after `pip install -e ".[test]"`, the following local checks do not require external fixtures:

```bash
.venv/bin/python -m pytest -q tests/test_verifier_selftest.py
.venv/bin/python tools/eio_digests.py
```

The current 0.8 synthetic bundle supports a CLI projection/validate/verify smoke test:

```bash
.venv/bin/eio-agents project tests/data/native/v0_8/source-complete.bundle.json -o native.per.json --jcs native.per.jcs
.venv/bin/eio-agents validate native.per.json
.venv/bin/eio-agents verify native.per.json --bundle tests/data/native/v0_8/source-complete.bundle.json
cmp native.per.jcs tests/data/native/v0_8/source-complete.per.jcs
```

Run it in a private scratch directory with absolute input paths if you do not want outputs in the repository root.
The synthetic smoke and local checks alone do not establish publication readiness. A release gate must additionally
test the exact built package with full source, wheel, Mac/Linux, privacy and reproducibility checks.
