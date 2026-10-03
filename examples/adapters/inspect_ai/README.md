# Inspect eval log to PER (illustrative converter)

[Inspect](https://inspect.aisi.org.uk/) writes one log per evaluation run. This example converts a **synthetic** log,
shaped as the [eval log format](https://inspect.aisi.org.uk/eval-logs.html) documents it, into an EIO bundle with
[`eio_agents.build_bundle`](../../../docs/api.md#build_bundle) and the bundle into a PER 2.1.0 record. Inspect is not
needed: `eval_log.json` is a static file (`inspect log dump` prints the same JSON for a real `.eval` log).

| File | What it is |
|---|---|
| `eval_log.json` | A synthetic log: an airline support task, three samples, three scorers |
| `convert.py` | The converter and its crosswalk |
| `test_convert.py` | Tests: a valid, verifiable PER; the mapping; nothing over-claimed |

## The crosswalk

| Inspect scorer | EIO predicate | Fidelity | Decided |
|---|---|---|---|
| `includes` (the target text is in the answer) | unmapped: not safe completion of a mixed request | | |
| `model_graded_fact` (an LLM grader checks the facts) | unmapped: factuality alone does not decide expressed certainty | | |
| `confirm_before_cancel` (this suite's custom scorer) | `protected-action-requires-verification` | narrower | deterministic |

Each sample becomes one turn: its user message, its last assistant text and every tool call with a captured result.
Only the suite-specific confirmation score becomes a check: `C` passes, `I` fails, and any other value (`N`, no
answer; `P`, partial) is not converted. A missing tool result is **NOT_CAPTURED**, not a captured null receipt. Inspect
does not locate the span a scorer decided on, so the whole answer is cited. Its run id is not a UUID: a stable UUID
version 4 is derived from it. Unmapped scores remain in the original log and do not become PER claims.

## Run it

```bash
pip install eio-agents pytest
python convert.py eval_log.json                       # writes out/inspect.bundle.json and out/inspect.per.json
eio-agents verify out/inspect.per.json --bundle out/inspect.bundle.json
eio-agents explain out/inspect.per.json --list
python -m pytest -q test_convert.py
```

## What the record can and cannot say

- The one finding is **UNPROVEN**. The confirmation failure on sample 2 cites the tool receipt of `cancel_booking`,
  but its evidence contract also needs a policy text and a verification state that the log does not carry. `narrower`
  fidelity says the scorer checked confirmation, not all forms of valid verification.
- Readiness is **WITHHELD**: the log has no ratings of the system prompt, so the context axis Q has no assessor input.
  Add `context_ratings=` to `build_bundle` when your evaluator records them.
- `provenance.producer.kind` is `native`. A full adapter would declare itself and its crosswalk by digest and keep the
  original log as the source archive; this release scores such bundles only through an attested scoring profile. See
  [Producing PER: native vs adapter](../../../docs/producing-per.md).
- A version with a group of three digits (`inspect_ai` `0.3.120`) is refused by the record's privacy rule for
  versions (at most three groups of at most two digits); the synthetic log uses `0.3.99`.

The scores of this synthetic log are not a production sign-off.
