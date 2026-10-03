# Producing a PER: native or from an export

EIO-Agents is the semantic layer between an evaluation framework and a Portable Evaluation Record (PER). Both routes below end with a versioned PER and a local source bundle for verification. Choose the route by **when** the evidence is captured, not by the name of the framework.

| | Native producer | Export converter or adapter |
|---|---|---|
| Evidence captured | During the evaluation run | Afterward, from a saved report or trace export |
| EIO predicates | Checks can be authored against predicates directly | An explicit crosswalk maps producer checks to predicates |
| Fidelity | `exact` only if the check actually decided that exact predicate | Often `narrower`; the original scorer may measure less than the predicate |
| Missing evidence | Can be collected before the run ends | Cannot be reconstructed from an incomplete export |
| Source for verification | The native bundle | The built bundle **and**, for a full adapter, the original export bytes |

## Native: capture and decide in the run

The evaluator records the agent's turns, tool calls, decisions, and their cited evidence as they happen. It calls `eio_agents.build_bundle(...)`, then `eio_agents.convert(bundle)`. Keep the bundle beside the PER: `eio-agents verify record.per.json --bundle run.bundle.json` re-derives the record and compares its digest. The [scripted native example](../examples/native/proofagent/README.md) shows the pattern; ProofAgent Harness is being integrated along this route.

`build_bundle` makes a **native** bundle (`provenance.producer.kind = native`). Its input is a concise report, not every possible EIO evidence form. Add only decisions and citations the evaluation actually observed. A model judgement supports a claim but does not, on its own, prove a failure. Missing required source facts leave affected scores **WITHHELD**; do not fill them with guesses.

## Export: map what the other tool really measured

A converter reads a saved evaluation export, maps each supported result to an EIO predicate, builds a bundle, then converts it. The [custom report](../examples/custom_report/README.md), [Inspect](../examples/adapters/inspect_ai/README.md), [DeepEval](../examples/adapters/deepeval/README.md), [promptfoo](../examples/adapters/promptfoo/README.md), and [OpenTelemetry GenAI](../examples/adapters/otel_genai/README.md) examples show small, synthetic crosswalks. They deliberately skip unmapped or undecidable results instead of treating them as passes. Their `build_bundle` output is still **native**; these examples are not full attested source-archive adapters.

For a full producer adapter, `eio_agents.adapters.ProducerAdapter` defines a `to_bundle(raw)` boundary. An adapter-produced archive declares adapter and crosswalk identity by digest, records the original source-archive identity, and uses adapter stage records. EIO validation accepts producer-declared scoring only under the adapter rules. That is a separate, stricter implementation than the small `build_bundle` examples. Historical ProofAgent reports use the adapter in `proofagent_harness.eio_adapter` and their pinned EIO release; feeding those reports directly to `convert` is not supported. See the [API reference](api.md#eio_agentsadapters) and [verification limits](verification.md).

## Check and share responsibly

```bash
eio-agents validate record.per.json
eio-agents verify record.per.json --bundle run.bundle.json
eio-agents explain record.per.json --list
```

Validation checks the PER against its declared schema and semantic rules. Verification additionally re-derives the PER from the supplied source bundle and compares digests. It detects post-hoc edits to that source; it **does not** establish that the original evaluator was complete, unbiased, or correct in the world. Preserve the exact package/ontology release used to issue a record. Keep raw bundles and exports local unless their disclosure is authorized, and review the PER's permitted excerpts and metadata before publishing it.
