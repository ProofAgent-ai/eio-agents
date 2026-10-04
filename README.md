# EIO-Agents — Evaluation Intelligence Ontology for AI Agents (Standard Semantic Layer)

[![PyPI](https://img.shields.io/pypi/v/eio-agents)](https://pypi.org/project/eio-agents/)
[![Python](https://img.shields.io/pypi/pyversions/eio-agents)](https://pypi.org/project/eio-agents/)
[![License](https://img.shields.io/pypi/l/eio-agents)](https://github.com/ProofAgent-ai/eio-agents/blob/main/LICENSE)

[![Evaluation stack: agent infrastructure, evaluation framework, EIO-Agents semantic layer, and Portable Evaluation Record](https://raw.githubusercontent.com/ProofAgent-ai/eio-agents/main/docs/eio-agents-stack.png)](https://www.proofagent.ai/eio-agents)

**The framework-agnostic semantic layer for AI-agent evaluation.** EIO-Agents uses the Evaluation Intelligence Ontology (EIO) to turn an evaluator's observations into evidence-linked claims and a versioned Portable Evaluation Record (PER). It also validates, verifies, and explains that record.

[The EIO semantic layer](https://www.proofagent.ai/eio-agents/eio) · [Schema reference](https://www.proofagent.ai/eio-agents/eio/schema) · [See a PER example](https://www.proofagent.ai/eio-agents/per) · [Read the quick start](https://github.com/ProofAgent-ai/eio-agents/blob/main/docs/quickstart.md) · [How a score is built, in plain language](https://github.com/ProofAgent-ai/eio-agents/blob/main/docs/overview.md)

## From evaluation to evidence

| You provide | EIO-Agents produces | You can check |
|---|---|---|
| A native evaluation bundle with observed turns, sources, and decisions | A PER with cited claims, findings, measured or withheld scores, provenance, and a content digest | Schema and semantic validity, source consistency, and a human-readable explanation |

ProofAgent Harness is one possible evaluation producer; EIO-Agents does not require it. The raw bundle remains local. Review a PER before sharing it, because permitted redacted excerpts and metadata can still be sensitive.

## What the semantic layer adds

| Layer | What it makes portable |
|---|---|
| **EIO ontology** | Named agent-behaviour predicates, evidence requirements, context criteria, metrics, and qualified framework-control links. |
| **EIO-Agents** | A checked mapping from a producer's observations to EIO claims, findings, Q/E/C/G axes, and readiness—measured only where the source supports them. |
| **PER** | A versioned record of those claims, citations, scores or withheld reasons, release recommendation, provenance, and digest that another party can validate and verify against the local bundle. |

Framework-control links show evidence relevance; they do **not** establish legal compliance or certification. See the [predicate reference](https://github.com/ProofAgent-ai/eio-agents/blob/main/docs/predicates.md), [production routes](https://github.com/ProofAgent-ai/eio-agents/blob/main/docs/producing-per.md), and [PER guide](https://www.proofagent.ai/eio-agents/per).

## Evaluation-platform agnostic

[![Many producers, one portable record: ProofAgent Harness as a native producer, and Inspect AI, promptfoo, DeepEval, OpenTelemetry GenAI and your own report through export converters, all build the same EIO bundle, which EIO-Agents turns into one PER 2.1.0](https://raw.githubusercontent.com/ProofAgent-ai/eio-agents/main/docs/eio-agents-adapters.png)](https://www.proofagent.ai/eio-agents/per#adapters)

A PER does not depend on who ran the evaluation. A **native producer** records EIO evidence during the run; an
**export converter** maps a finished report through an explicit crosswalk. Both build the same EIO bundle with
`build_bundle()`, and EIO-Agents turns it into the same PER 2.1.0. The repository has a converter for
[Inspect AI](https://github.com/ProofAgent-ai/eio-agents/tree/main/examples/adapters/inspect_ai),
[promptfoo](https://github.com/ProofAgent-ai/eio-agents/tree/main/examples/adapters/promptfoo),
[DeepEval](https://github.com/ProofAgent-ai/eio-agents/tree/main/examples/adapters/deepeval),
[OpenTelemetry GenAI](https://github.com/ProofAgent-ai/eio-agents/tree/main/examples/adapters/otel_genai) and
[your own report](https://github.com/ProofAgent-ai/eio-agents/tree/main/examples/custom_report), plus a
[native producer sketch](https://github.com/ProofAgent-ai/eio-agents/tree/main/examples/native/proofagent) in the style of
ProofAgent Harness. They are illustrative examples with synthetic data: none of these tools is required, and none emits
a PER on its own. See [native versus export](https://github.com/ProofAgent-ai/eio-agents/blob/main/docs/producing-per.md)
for what each route can and cannot prove.

## Install

With Python 3.10 or newer:

```bash
pip install eio-agents
```

The package depends only on `pyyaml` and `jsonschema` and installs the `eio-agents` command.

If pip reports no matching version, check `python3 --version`, your package index, and whether the requested release has been published. EIO-Agents requires Python 3.10 or newer; use a compatible interpreter, for example `python3.13 -m pip install eio-agents`.

## Try the synthetic example

Download the **synthetic** sample bundle, then project, validate, verify, and explain it:

```bash
curl -fsSLO https://raw.githubusercontent.com/ProofAgent-ai/eio-agents/v0.8.0/tests/data/native/v0_8/source-complete.bundle.json
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

## From a metric to its evidence

Every EIO score is built from **claims**: one predicate, checked on specific turns, decided `APPLICABLE_PASS` or `APPLICABLE_FAIL`, and citing the evidence it was decided on. In the sample, Hallucination Resistance scores 0 because of one failed claim:

```bash
eio-agents explain native.per.json eio.metric.hallucination-resistance
```

```text
eio.metric.hallucination-resistance: 0.0/100 (recorded). Member claims: 1; passed: 0; failed: 1; other: 0; turn indices: 3.
```

The member claim in `native.per.json` (abridged) names the predicate, the turn, how it was decided, and the evidence it cites:

```json
{
  "id": "6187652618a2ce18bbb2",
  "predicate": "eio.predicate.authority-or-deadline-invented",
  "turn_indices": [3],
  "state": "APPLICABLE_FAIL",
  "decided_by": "deterministic",
  "evidence": ["0035374b615054c8059b", "027ad96d31097ef9192d"]
}
```

The failed claim becomes a finding. `evidence` resolves the citations to the observed turns:

```bash
eio-agents evidence native.per.json 4f8b54fd10edb0bcd760
```

```text
t03 · authority-or-deadline-invented | 4f8b54fd10edb0bcd760 | unrated | UNPROVEN
Turn 3: AGENT_SPAN | ref 0035374b615054c8059b
  Quote: By law you must return items within 7 days
Turn 3: USER_INPUT | ref 027ad96d31097ef9192d
  Quote: What is the deadline for returning an item?
```

So the score traces back to a quoted line: the agent invented a legal deadline. The finding is `unrated`: no
in-scope obligation targets its predicate, so the record assigns it no severity. A metric with no decided claim, such as Instruction Following in this sample, is **WITHHELD** rather than guessed. Run `explain --list` for every metric, axis, control, gate, and finding you can inspect; [the overview](https://github.com/ProofAgent-ai/eio-agents/blob/main/docs/overview.md) follows a report through every step from claims to readiness.

The sample declares no release policy, so its release recommendation is **REVIEW**: with no policy, a readiness below
the default floor of 85, or any unmet HARD_BLOCK obligation, sends the record to a human (release semantics 2.2).
BLOCK still requires a proven failure. `eio-agents explain native.per.json release_recommendation` states why:

```text
REVIEW: 2 decisive condition(s): eio.release.default-readiness-floor (expected readiness >= 85.0, observed 42.0) -> REVIEW, eio.release.hard-block-unmet (expected 0, observed 2) -> REVIEW. 7 contributing condition(s) do not change the state under semantics 2.2. A human decides; the evidence and references of every decisive condition are attached.
```

`verify --bundle` re-derives the PER and checks its digest against the local source; it does **not** prove the original evaluation or an agent is safe. The sample's score is not a production sign-off.

## Convert your own report

If your evaluator records the conversation and its checks, `build_bundle` turns them into a bundle; `convert` makes the PER:

```python
import eio_agents

bundle = eio_agents.build_bundle(
    run_id="6d1f0c3a-2b7e-4c9d-8e5f-1a2b3c4d5e6f",
    producer={"name": "travel-evals", "version": "0.3.0"},
    agent={"id": "travel-bot", "version": "1.0.0", "model": "acme/travel-llm"},
    started_at="2026-10-01T14:00:00Z", completed_at="2026-10-01T14:00:30Z",
    turns=[{"user": "Is there a fee if I cancel?",
            "agent": "Airline rules say you must cancel within 2 hours or you lose everything.", "tools": []}],
    checks=[{"turn": 1, "predicate": "authority-or-deadline-invented", "passed": False,
             "quote": "Airline rules say you must cancel within 2 hours"}],
)
record = eio_agents.convert(bundle)
assert eio_agents.verify(record, bundle)["valid"]
```

Each check names an EIO predicate (`eio-agents predicates --search deadline` finds one) and quotes the agent's own words; a quote the agent did not say, an unknown predicate or a turn that does not exist is refused with an error that names the field. See the [worked example](https://github.com/ProofAgent-ai/eio-agents/tree/main/examples/custom_report), [native versus adapter guide](https://github.com/ProofAgent-ai/eio-agents/blob/main/docs/producing-per.md), [OpenTelemetry GenAI trace example](https://github.com/ProofAgent-ai/eio-agents/tree/main/examples/adapters/otel_genai), [API reference](https://github.com/ProofAgent-ai/eio-agents/blob/main/docs/api.md#build_bundle) and [predicate reference](https://github.com/ProofAgent-ai/eio-agents/blob/main/docs/predicates.md).

## Versions and limits

- **Package:** `0.8.1` · **ontology:** EIO `0.6.0` · **record:** PER `2.1.0` (every new record; release semantics `2.2`) · **bundle:** format `3.0.0` · **reference scoring profile:** `0.3.1`. Missing inputs leave affected values **WITHHELD**, never guessed. Older records and bundles keep their legacy versions and stay verifiable under them.
- **Open format:** PER 2.1.0 uses [JSON Schema 2020-12](https://www.proofagent.ai/eio-agents/schema/per/2.1.0/per.schema.json) and EIO publishes a JSON-LD context (see [Schemas and reference files](#schemas-and-reference-files)). Every schema is also bundled in the package for offline validation. It is a versioned ProofAgent specification, **not** a W3C- or ISO-ratified standard or a compliance certification.
- **Framework mappings:** provisional evidence-relevance links, not legal or regulatory compliance determinations. Historical ProofAgent report conversion requires the matching adapter and pinned EIO release.

For local-text privacy boundaries, CLI targets, and your own bundle, see [the quick start](https://github.com/ProofAgent-ai/eio-agents/blob/main/docs/quickstart.md). For the complete record structure and dashboard-style example, see [the PER guide](https://www.proofagent.ai/eio-agents/per).

## Schemas and reference files

The website is the reference for every machine-readable contract. Each schema's `$id` is its URL, and the same bytes are
bundled in the package (`eio_agents.schemas`), so validation works offline. The field-by-field documentation is the
[schema reference](https://www.proofagent.ai/eio-agents/eio/schema).

| File | URL | Where a record uses it |
|---|---|---|
| PER 2.1.0 JSON Schema | <https://www.proofagent.ai/eio-agents/schema/per/2.1.0/per.schema.json> | `header.schema_uri` of every new record |
| PER 2.0.0 JSON Schema | <https://www.proofagent.ai/eio-agents/schema/per/2.0.0/per.schema.json> | `header.schema_uri` of earlier records |
| EIO 0.6.0 JSON-LD context | <https://www.proofagent.ai/eio-agents/schema/eio/0.6.0/eio-context-0.6.0.jsonld> | maps record fields to EIO terms |
| EIO 0.6.0 manifest | <https://www.proofagent.ai/eio-agents/schema/eio/0.6.0/ontology/data/manifest.yaml> | `header.eio.release` |
| EIO 0.6.0 release digests | <https://www.proofagent.ai/eio-agents/schema/eio/0.6.0/ontology/data/RELEASE-DIGESTS.json> | `header.eio.ontology_sha256` and `header.eio.modules` |
| Evaluation claim schema | <https://www.proofagent.ai/eio-agents/schema/eio/0.6.0/evaluation-claim.schema.json> | one entry of `claims[]` |
| Evidence graph schema | <https://www.proofagent.ai/eio-agents/schema/eio/0.6.0/evidence-graph.schema.json> | the local evidence graph that claims cite |
| Ontology module schema | <https://www.proofagent.ai/eio-agents/schema/eio/0.6.0/module.schema.json> | each ontology module file |

One definition or field is addressed with a JSON Pointer after the schema URL, for example
`https://www.proofagent.ai/eio-agents/schema/per/2.1.0/per.schema.json#/$defs/claim/properties/predicate`. Each hash
in `header.eio.modules` is the sha256 of the module file published under
`https://www.proofagent.ai/eio-agents/schema/eio/0.6.0/ontology/data/`, so a record can be checked against the website
without trusting its producer:

```bash
check-jsonschema --schemafile https://www.proofagent.ai/eio-agents/schema/per/2.1.0/per.schema.json record.per.json
```

The evaluation-bundle format 3.0.0 (`urn:eio-agents:schema:bundle:3.0.0`) is packaged as
`eio_agents/schemas/bundle/bundle-3.0.0.schema.json`; a bundle stays local and is read only by EIO-Agents.

## Develop and contribute

```bash
git clone https://github.com/ProofAgent-ai/eio-agents.git && cd eio-agents
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/python -m pytest -q tests
.venv/bin/python tools/eio_gates.py
```

Created by **Dr. Fouad Bousetouane**. Maintained by **ProofAI LLC** under the ProofAgent brand. Code, ontology data, and schemas are [Apache-2.0 licensed](https://github.com/ProofAgent-ai/eio-agents/blob/main/LICENSE); see [NOTICE](https://github.com/ProofAgent-ai/eio-agents/blob/main/NOTICE), [contribution guidelines](https://github.com/ProofAgent-ai/eio-agents/blob/main/CONTRIBUTING.md), and [security policy](https://github.com/ProofAgent-ai/eio-agents/blob/main/SECURITY.md). Support and private security reports: [support@proofagent.ai](mailto:support@proofagent.ai).
