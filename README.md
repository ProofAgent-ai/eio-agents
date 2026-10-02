# EIO-Agents

[![Evaluation stack: agent infrastructure, evaluation framework, EIO-Agents semantic layer, and Portable Evaluation Record](https://raw.githubusercontent.com/ProofAgent-ai/eio-agents/main/docs/eio-agents-stack.svg)](https://www.proofagent.ai/eio-agents/schema/)

**The framework-agnostic semantic layer for AI-agent evaluation.** EIO-Agents uses the Evaluation Intelligence Ontology (EIO) to turn an evaluator's observations into evidence-linked claims and a versioned Portable Evaluation Record (PER). It also validates, verifies, and explains that record.

[Explore EIO and its schemas](https://www.proofagent.ai/eio-agents/schema/) · [See a PER example](https://www.proofagent.ai/eio-agents/per) · [Read the quick start](https://github.com/ProofAgent-ai/eio-agents/blob/main/docs/quickstart.md)

## From evaluation to evidence

| You provide | EIO-Agents produces | You can check |
|---|---|---|
| A native evaluation bundle with observed turns, sources, and decisions | A PER with cited claims, findings, measured or withheld scores, provenance, and a content digest | Schema and semantic validity, source consistency, and a human-readable explanation |

ProofAgent Harness is one possible evaluation producer; EIO-Agents does not require it. The raw bundle remains local. Review a PER before sharing it, because permitted redacted excerpts and metadata can still be sensitive.

## Install

With Python 3.10 or newer:

```bash
pip install --pre eio-agents
```

`--pre` is needed while the current release is a release candidate. The package depends only on `pyyaml` and `jsonschema` and installs the `eio-agents` command.

## Try the synthetic example

Download the **synthetic** sample bundle, then project, validate, verify, and explain it:

```bash
curl -fsSLO https://raw.githubusercontent.com/ProofAgent-ai/eio-agents/v0.6.0rc1/tests/data/native/v0_6/source-complete.bundle.json
eio-agents project source-complete.bundle.json -o native.per.json --jcs native.per.jcs
eio-agents validate native.per.json
eio-agents verify native.per.json --bundle source-complete.bundle.json
eio-agents explain native.per.json --list
eio-agents explain native.per.json readiness
```

The last command prints:

```text
Readiness: 42.0448/100 (recorded). Raw weighted score: 42.0448/100.
```

Use a target from `explain --list` to inspect one finding or score, then `eio-agents evidence native.per.json <finding-id>` to locate its cited evidence. `verify --bundle` re-derives the PER and checks its digest against the local source; it does **not** prove the original evaluation or an agent is safe. The sample's score is not a production sign-off.

## Versions and limits

- **Package:** `0.6.0rc1` · **ontology:** EIO `0.6.0` · **source-complete record:** PER `2.0.0`. The reference scoring profile is `0.3.1-draft.1`; missing inputs leave affected values **WITHHELD**, never guessed. Older partial records retain their own historical versions.
- **Open format:** PER 2.0.0 uses [JSON Schema Draft 2020-12](https://www.proofagent.ai/eio-agents/schema/per/2.0.0/per.schema.json) and EIO publishes a JSON-LD context. It is a versioned ProofAgent specification, **not** a W3C- or ISO-ratified standard or a compliance certification.
- **Framework mappings:** provisional evidence-relevance links, not legal or regulatory compliance determinations. Historical ProofAgent report conversion requires the matching adapter and pinned EIO release.

For local-text privacy boundaries, CLI targets, and your own bundle, see [the quick start](https://github.com/ProofAgent-ai/eio-agents/blob/main/docs/quickstart.md). For the complete record structure and dashboard-style example, see [the PER guide](https://www.proofagent.ai/eio-agents/per).

## Develop and contribute

```bash
git clone https://github.com/ProofAgent-ai/eio-agents.git && cd eio-agents
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/python -m pytest -q tests
.venv/bin/python tools/eio_gates.py
```

Created by **Dr. Fouad Bousetouane**. Maintained by **ProofAI LLC** under the ProofAgent brand. Code, ontology data, and schemas are [Apache-2.0 licensed](https://github.com/ProofAgent-ai/eio-agents/blob/main/LICENSE); see [NOTICE](https://github.com/ProofAgent-ai/eio-agents/blob/main/NOTICE), [contribution guidelines](https://github.com/ProofAgent-ai/eio-agents/blob/main/CONTRIBUTING.md), and [security policy](https://github.com/ProofAgent-ai/eio-agents/blob/main/SECURITY.md). Support and private security reports: [support@proofagent.ai](mailto:support@proofagent.ai).
