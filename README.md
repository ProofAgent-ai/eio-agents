# EIO-Agents

EIO-Agents is a framework-agnostic semantic layer for AI-agent evaluation. An evaluation framework produces evidence; the Evaluation Intelligence Ontology (EIO) standardizes evidence-linked claims and results; EIO-Agents turns a native evaluation bundle into a content-addressed Portable Evaluation Record (PER). The Python reference library validates the record, independently checks it against the bundle, and explains findings with cited evidence. ProofAgent Harness is one example evaluation framework, not a requirement or the semantic authority.

Explore the [EIO-Agents ontology, framework mappings, and PER schema reference](https://www.proofagent.ai/eio-agents/schema/) on the ProofAgent website. The versioned files are also bundled in the Python package for offline use.

The `0.6.0rc1` package is a release candidate, not a certification of evaluated agents. The bundled ontology identifies as EIO `0.6.0`. Source-complete native bundles with an explicit proof set produce PER **2.0.0**, whose canonical JSON Schema `$id` is [`https://www.proofagent.ai/eio-agents/schema/per/2.0.0/per.schema.json`](https://www.proofagent.ai/eio-agents/schema/per/2.0.0/per.schema.json). The reference scoring profile remains `0.3.1-draft.1`. Incomplete or unscored native bundles retain the explicitly versioned partial `2.0.0-rc3-draft` route and must not be presented as PER 2.0.0.

## Try evaluation evidence as a native bundle

Use Python 3.10 or newer. From this repository root, supply a native archive-schema-3 bundle authored for the bundled
EIO `0.6.0` release. Use the current synthetic fixture under `tests/data/native/v0_6/` below; older fixtures
directly under `tests/data/native/` are pinned to earlier releases.

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/eio-agents version
.venv/bin/eio-agents project tests/data/native/v0_6/source-complete.bundle.json \
  -o native.per.json --jcs native.per.jcs
.venv/bin/eio-agents validate native.per.json
.venv/bin/eio-agents verify native.per.json \
  --bundle tests/data/native/v0_6/source-complete.bundle.json
.venv/bin/eio-agents explain native.per.json --list
```

`project` writes a readable local PER and canonical JCS bytes, and prints the actual PER version. `validate` checks the record; `verify` independently checks its cited proof and any numeric score against the supplied local bundle, re-derives the record, and checks the digest. An explicit source-complete proof set selects PER 2.0.0; a bundle without one retains the historical partial route with a CLI warning. Missing source evidence can withhold metrics or readiness. A native bundle without scoring inputs still produces `scores: null`. None of these checks proves that an agent is safe, accurate, or production-ready.

The checked-in `tests/data/native/v0_6/source-complete.bundle.json` is synthetic and projects a scored PER 2.0.0 record; its score is a test result, not a safety certification. Use `eio-agents explain native.per.json <target>` to inspect a target from `--list`, or `eio-agents evidence native.per.json <finding-id>` for cited PER evidence. Template-backed `explain --local path/to/your-0.6-bundle.json` can reveal withheld local text; do not upload that output without a privacy review. See the [native quick start](https://github.com/ProofAgent-ai/eio-agents/blob/main/docs/quickstart.md) for the command sequence and boundaries.

The source bundle and the portable PER are separate local files. The caller may retain and analyze the bundle under its own access controls. PER privacy checks prevent unclassified source text from being copied into the portable record; they do not make arbitrary raw bundles safe to share.

## Boundaries

- A source-complete native `native_scoring` section with an explicit proof set can yield a PER 2.0.0 record containing a `reference-draft` score, independently checked by D4, while D5 checks cited proof status. The minimum-score policy rule is evaluated only when readiness is measured. Missing inputs leave affected metrics/axes and readiness withheld; G uses four components without a freshness input. No score or accuracy improvement is claimed. Without native scoring inputs, `scores: null` remains valid only on the separately labeled partial route.
- Historical ProofAgent reports (archive schemas 1 and 2) are **not** native bundles. Their conversion and verification require the matching historical ProofAgent adapter and pinned EIO release. Old branded fixtures and compatibility tests are outside this standalone candidate.
- The ontology's framework mappings are provisional evidence-relevance links, not legal compliance, SOC 2 certification, or attestation.
- This release candidate has one implementation. Digest matching and re-projection test internal consistency, not whether the underlying evaluation or human/agent judgment was correct.
- Third-party declared template text remains privacy-gated. A fully populated synthetic record demonstrates the full-score wire; it does not establish that a real evaluator has captured complete trustworthy inputs, improved accuracy, or achieved publication readiness.

## Development checks

```bash
.venv/bin/pip install -e '.[test]'
.venv/bin/python -m pytest -q tests
.venv/bin/python tools/eio_gates.py
```

The `v0_6` source-complete synthetic fixture provides a runnable, byte-pinned PER 2.0.0 smoke test; it does not establish real-world accuracy or replace the full Mac/Linux, privacy, reproducibility and packaged-install gates. Older native fixtures and the historical adapter compatibility corpus have separate pins and tests. `ruff check .`, offline wheel/sdist build, and `twine check --strict` are additional release checks. A passing test suite alone does not authorize publication.

## Project and license

ProofAI LLC maintains EIO-Agents under the ProofAgent brand. The package can be used by other evaluators without a ProofAgent product. The code, ontology data, and schemas are Apache-2.0 licensed; see [LICENSE](https://github.com/ProofAgent-ai/eio-agents/blob/main/LICENSE) and [NOTICE](https://github.com/ProofAgent-ai/eio-agents/blob/main/NOTICE). Framework names and identifiers remain their owners' property. For support or private security reports, contact [support@proofagent.ai](mailto:support@proofagent.ai) and follow [SECURITY.md](https://github.com/ProofAgent-ai/eio-agents/blob/main/SECURITY.md). Source: [ProofAgent-ai/eio-agents](https://github.com/ProofAgent-ai/eio-agents).
