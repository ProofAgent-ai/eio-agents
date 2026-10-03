# OpenTelemetry GenAI traces to PER (illustrative converter)

This example reads a **synthetic OTLP JSON export** containing GenAI `invoke_agent`, `chat`, and `execute_tool` spans. It maps selected `gen_ai.evaluation.result` events into EIO checks, builds a native EIO bundle with `build_bundle`, and produces a Portable Evaluation Record (PER). It needs neither an OpenTelemetry collector nor an online service.

| File | Purpose |
|---|---|
| `traces.json` | Three synthetic agent invocations, with tool spans and evaluation events |
| `convert.py` | OTLP parsing and the explicit evaluation-to-predicate crosswalk |
| `test_convert.py` | Validity, source verification, mapping, tamper, and trace-boundary tests |

## Run

From this directory, after installing EIO-Agents and pytest:

```bash
python convert.py traces.json
eio-agents validate out/otel.per.json
eio-agents verify out/otel.per.json --bundle out/otel.bundle.json
eio-agents explain out/otel.per.json --list
python -m pytest -q test_convert.py
```

The synthetic export produces **PER 2.1.0, one claim, no findings**. Overall readiness is **WITHHELD** because the export has no context ratings. This is not a production verdict. The other two evaluation events remain in the source export; EIO does not turn them into unsupported claims.

## What is mapped

| Evaluation name | EIO predicate | Fidelity | Decision source |
|---|---|---|---|
| `answer_groundedness` | unmapped: grounding does not always decide expressed certainty | | |
| `tool_policy` | unmapped: a generic tool-policy failure does not establish lack of authorization | | |
| `prohibited_disclosure_refused` (this suite's criterion) | `prohibited-part-clearly-refused` | narrower | LLM judge named by the event's `eio.evaluator.model` |

One `invoke_agent` span becomes one turn; its direct `chat` and `execute_tool` children must share its **trace ID**. Only the suite-specific `pass` or `fail` evaluation event above, attached to a chat span, is mapped; unknown names and other labels are skipped. The synthetic evaluator records its judge model in `eio.evaluator.model`, a **suite-owned attribute**, not a standard GenAI semantic-convention key. A mapped LLM event without that provenance fails instead of inventing a model identity. An LLM evaluation is a jury of one and cannot by itself prove a finding. The evaluator event does not locate an exact answer span, so the converter cites the whole final answer and does **not** claim exact fidelity.

This is a narrow example, not a general OTLP adapter. It expects JSON-encoded text messages and tool arguments/results in span attributes, one user message in the first chat, a final assistant message, and the fields shown by `traces.json`. It does not reconstruct nested agent calls, streaming output, multimodal content, sampled-out spans, or evaluation events attached elsewhere. Missing required turns or chat spans fail rather than producing an empty PER; an export combining different agents, models, or producer scopes also fails instead of attributing them all to one subject. Check your instrumentation's conventions and export shape before adapting it. [OpenTelemetry's GenAI attribute registry](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/) notes that recorded input/output messages can contain sensitive information and may be filtered or truncated.

The generated `out/otel.bundle.json` contains the full source transcript and tool values. Keep it local. The PER may carry permitted short excerpts and metadata; inspect it before sharing. `provenance.producer.kind` is `native` here because `build_bundle` creates a native bundle. A full source-archive adapter would declare adapter identity, crosswalk digest, and original export identity; this example does **not** claim those guarantees. See [Producing PER: native vs adapter](../../../docs/producing-per.md).
