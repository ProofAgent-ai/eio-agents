# DeepEval test run to PER (illustrative converter)

[DeepEval](https://deepeval.com/) evaluates LLM test cases with metrics. This example converts a **synthetic** test run
into an EIO bundle with [`eio_agents.build_bundle`](../../../docs/api.md#build_bundle) and the bundle into a PER 2.1.0
record. DeepEval is not needed. `test_run.json` follows DeepEval's `TestRun` model serialized with its camelCase
aliases (`testCases`, `actualOutput`, `toolsCalled` with `inputParameters`, `metricsData` with `evaluationModel`), as in
`deepeval/test_run/api.py` and `deepeval/tracing/api.py`; see [test cases](https://deepeval.com/docs/evaluation-test-cases)
and [metrics](https://deepeval.com/docs/metrics-introduction). Check the field names against your DeepEval version.

| File | What it is |
|---|---|
| `test_run.json` | A synthetic run of an insurance claims assistant: three test cases, four metrics |
| `convert.py` | The converter and its crosswalk |
| `test_convert.py` | Tests: a valid, verifiable PER; mapped and unmapped metrics; nothing over-claimed |

## The crosswalk

| DeepEval metric | EIO predicate | Fidelity | Decided |
|---|---|---|---|
| Tool Correctness (expected tools were called) | unmapped: tool presence is not safe completion of a mixed request | | |
| Hallucination (the output contradicts its context) | unmapped: contradiction does not always mean excessive certainty | | |
| Policy Adherence [GEval] (this suite's criterion against invented policy terms) | `authority-or-deadline-invented` | narrower | semantic |
| Answer Relevancy | not mapped | | |

Only the suite-specific G-Eval criterion is converted. Its `evaluationModel` is recorded as one LLM judge, a jury of
one; `success` is its decision. A metric with an `error` is not converted. Each test case is one turn: `input`,
`actualOutput` and `toolsCalled` with captured outputs. A missing tool output is **NOT_CAPTURED**, not a captured null
result. DeepEval does not locate the span a metric decided on, so the whole output is cited. Other metric results
remain in the original run, outside the PER claims.

A missing tool call (test case 3: the assistant says it cancelled a policy and called nothing) would map more closely to
`claimed-action-lacks-receipt`, but EIO 0.6.0 cannot score a failure of that predicate in a native record (its contract
has no evidence group that can prove agent behaviour; `eio-agents predicates --json` shows `failure_scorable: false`).
The converter leaves Tool Correctness unmapped instead of asserting a different EIO claim.

## Run it

```bash
pip install eio-agents pytest
python convert.py test_run.json                       # writes out/deepeval.bundle.json and out/deepeval.per.json
eio-agents verify out/deepeval.per.json --bundle out/deepeval.bundle.json
eio-agents explain out/deepeval.per.json --list
python -m pytest -q test_convert.py
```

## What the record can and cannot say

- The one finding is **UNPROVEN**: it is model-graded and supports the claim but does not prove it.
- The retrieval context of test case 2 is not carried: `build_bundle` records turns and tool calls, not retrievals.
- A test run records durations, not times, and no run id or DeepEval version: the converter uses fixed synthetic
  times, derives the run id from the file's digest and records the version as `unrecorded`.
- `provenance.producer.kind` is `native`; see [Producing PER: native vs adapter](../../../docs/producing-per.md).

The scores of this synthetic run are not a production sign-off.
