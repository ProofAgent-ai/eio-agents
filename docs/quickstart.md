# Native EIO-Agents quick start

An evaluation framework produces evidence; EIO-Agents provides the framework-agnostic semantic
layer that turns evidence-linked claims and results into a PER. ProofAgent Harness is one example
evaluation framework. This local walkthrough uses a synthetic, source-complete native archive-schema-3
bundle at `tests/data/native/v0_8/source-complete.bundle.json`, authored for
EIO `0.6.0`. Running the example needs no paid model call, network service, or upload.
The public website schema endpoint is separate from local package operation.
Older examples directly under `tests/data/native/` are pinned to
an earlier ontology release and are not current 0.6 quick-start inputs.

## Install locally

From the EIO-Agents repository root, use Python 3.10 or newer:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/eio-agents version
```

The version output should report package `0.8.3`, EIO
`0.6.0`, the default PER `2.1.0` with release semantics `2.2`, and reference
profile `0.3.1`. The PER schema identifier is
`https://www.proofagent.ai/eio-agents/schema/per/2.1.0/per.schema.json`. The package embeds the schema for offline validation; live HTTP resolution is checked separately for each release.

## Project and check a local record

From the repository root, project the checked-in 0.8 synthetic bundle:

```bash
.venv/bin/eio-agents project tests/data/native/v0_8/source-complete.bundle.json \
  -o native.per.json --jcs native.per.jcs
.venv/bin/eio-agents validate native.per.json
.venv/bin/eio-agents verify native.per.json \
  --bundle tests/data/native/v0_8/source-complete.bundle.json
.venv/bin/eio-agents explain native.per.json --list
cmp native.per.jcs tests/data/native/v0_8/source-complete.per.jcs
```

`project` writes readable `native.per.json` and canonical
`native.per.jcs` in the current directory; the input bundle remains local.
The final `cmp` checks byte-for-byte equality with the frozen synthetic PER 2.1.0
golden record (SHA-256 `8ea058de14e379fcca8478cbba89c6a9682826eb039f62b6080d1cabd37c1177`).
The example yields measured readiness `42.0448` and `REVIEW` under release semantics 2.2: it declares no policy,
its readiness is below the default floor of 85 and two HARD_BLOCK obligations are unmet; these are fixture outputs, not an agent-safety or deployment verdict.
`validate` checks the declared PER version, and `verify` checks source
consistency and re-derives the record from the supplied bundle. An explicit
source-complete proof set gets a reference score block in PER 2.1.0; a bundle
without native scoring inputs gets PER 2.1.0 with `scores: null`. Missing required source inputs withhold
the affected score or readiness. These checks do not prove that the evaluation
or the agent's behaviour is accurate in the world.

## Inspect evidence and explanations

Substitute ids returned by `explain --list` for `TARGET_ID` and `FINDING_ID`:

```bash
.venv/bin/eio-agents explain native.per.json release_recommendation
.venv/bin/eio-agents explain native.per.json TARGET_ID
.venv/bin/eio-agents evidence native.per.json FINDING_ID
```

The output and recommendation depend on your bundle. A record-level `BLOCK`,
`REVIEW`, or `PASS` is a result of the versioned release rules, not a safety certification.
Withheld readiness is not a numerical grade. To display local source text
behind fingerprints, add `--local tests/data/native/v0_8/source-complete.bundle.json` to
`explain`. Keep that output local: it may reveal text intentionally withheld
from the portable PER.

## Current boundaries

- Native bundles without scoring inputs intentionally have `scores: null`.
  Validated `native_scoring` inputs can yield measured or withheld metrics
  and axes. The PER 2.1.0 minimum-score policy rule is evaluated only when readiness
  is measured.
- Historical producer reports require their pinned producer adapter and
  historical EIO release.
- Embedded third-party template text remains privacy-gated. A release requires
  disclosure review, identifier sign-off, and complete package gates on its
  exact artifacts.
