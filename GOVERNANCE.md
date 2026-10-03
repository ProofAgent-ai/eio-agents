# Governance

This document describes who maintains EIO-Agents, how decisions are made, how the EIO and PER specifications change, and
how releases are versioned.

## Current state

EIO-Agents, EIO and PER are created and maintained by ProofAgent. Today this is a single-vendor project: the
maintainers work for one company, and there is no second, independent implementation. Neutral, multi-party governance
(for example a W3C Community Group or a foundation project) is a goal, not a fact. This document will change when that
happens.

## Maintainers

| Maintainer | Contact | Role |
|---|---|---|
| ProofAI LLC / ProofAgent | support@proofagent.ai | Project maintenance and release authority |

ProofAgent reviews and merges changes, runs the proposal process, cuts releases and enforces the
[Code of Conduct](CODE_OF_CONDUCT.md). Maintainer access is granted by ProofAI LLC after a record of sustained
contributions; no unappointed individual is represented as a maintainer.

## Decisions

Decisions are made after public review: a proposal is accepted when ProofAgent's release authority approves it after
the review period of its change class. Objections are discussed in the open. A normative change (Class C) requires
an explicit approval from ProofAI LLC's release authority.

## Change classes

| Class | Scope | Review |
|---|---|---|
| A: editorial | Documentation, comments and docstrings | One maintainer |
| B: library | Library code with identical record bytes | One maintainer, and every gate green |
| C: normative | EIO data, EIO or PER schemas, the witness rule, claim states, release rules, digests, PER fields, or any change to record bytes | The proposal process below |

[CONTRIBUTING.md](CONTRIBUTING.md) lists the gates and the byte rules.

## Proposals to change EIO or PER

A change of meaning in EIO or PER (a new or changed predicate, evidence type, claim state, witness rule, release rule,
scoring rule or record field) follows this process:

1. **Proposal.** Open an issue labelled "EIO change proposal". Name the affected ids, the current and the proposed
   semantics, the effect on records and digests, and the compatibility impact.
2. **Public comment.** The proposal stays open for comment for at least 14 days.
3. **Implementation.** A pull request implements the change, with the version bumps the EIO versioning rule requires,
   regenerated digests, the diff of the regenerated golden records, and a BREAKING entry in the EIO changelog when meaning
   changes.
4. **Approval.** ProofAI LLC's release authority approves the pull request.
5. **Release.** The change ships in a new EIO release (and, if the record format changes, a new PER version), bundled in a
   new library release.

### Mapping changes

Framework and control mappings are provisional and express evidence relevance, not certification. A proposal to add,
correct or remove a mapping names the framework and control id and explains why the mapped predicates give relevant
evidence for that control. Because mappings live in the EIO data, an accepted mapping change is released as a Class C
change, and it stays marked `provisional` with `legal_review_required: true` until the project has a legal review process.

## Versioning and releases

EIO-Agents has three version lines; [docs/versioning.md](docs/versioning.md) explains them in full.

- **Library (`eio-agents`).** [PEP 440](https://peps.python.org/pep-0440/) versions with the meaning of Semantic
  Versioning. While the major version is 0, a MINOR bump may break the API. `.devN` versions are development builds and
  are never published; public pre-releases use `aN`, `bN` and `rcN`. A release that changes record bytes bumps the MINOR
  version and says "Record bytes change: yes" in the changelog.
- **EIO releases.** Each EIO release has its own version (`0.6.0` bundled with EIO-Agents `0.8.0`) and follows the
  EIO versioning rule: while the major version is 0, a change of meaning bumps the MINOR version of the changed module
  and of the release; additive changes bump PATCH or MINOR; text changes bump PATCH. Modules are pinned by exact version
  and sha256 in the manifest and in `RELEASE-DIGESTS.json`. EIO releases are recorded in
  `src/eio_agents/ontology/data/CHANGELOG.md`.
- **PER versions.** Each PER version has a versioned JSON Schema `$id`. The `0.8.0` source-complete native route uses
  `2.1.0` for scored native bundles; `2.0.0` and the `2.0.0-rc3-draft` partial route remain historical, and rc1 is
  historical adapter scope. A PER version identifies a wire contract; it does not claim a second independent
  implementation or certification.

Each library release bundles one EIO release and may read or produce more than one PER version according to the bundle;
`eio-agents version` distinguishes the current native contract from historical identifiers.

### Release process

1. Update [CHANGELOG.md](CHANGELOG.md): the version, the date, the bundled EIO release and PER version, and whether record
   bytes change.
2. Set the version in `pyproject.toml` and `src/eio_agents/__init__.py` (a test checks that they agree).
3. Run every gate on a clean checkout.
4. Tag the release as `vX.Y.Z` and publish it. A release that contains a Class C change needs explicit sign-off from
   ProofAI LLC's release authority.

## Changes to this document

Changes to this governance document are Class C changes: they need a public pull request, at least 14 days for comment,
and explicit approval from ProofAI LLC's release authority.
