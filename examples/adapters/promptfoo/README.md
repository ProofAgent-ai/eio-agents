# promptfoo results to PER (illustrative converter)

[promptfoo](https://www.promptfoo.dev/) writes an eval's results with `promptfoo eval -o results.json`. This example
converts a **synthetic** `results.json`, shaped as the [output format](https://www.promptfoo.dev/docs/configuration/outputs/)
documents it (`results.version` 3), into an EIO bundle with
[`eio_agents.build_bundle`](../../../docs/api.md#build_bundle) and the bundle into a PER 2.1.0 record. promptfoo is not
needed.

| File | What it is |
|---|---|
| `results.json` | A synthetic eval of a bank assistant: two regression tests and one red-team probe (`rbac` plugin) |
| `convert.py` | The converter and its crosswalk |
| `test_convert.py` | Tests: a valid, verifiable PER; deterministic and graded assertions told apart; nothing over-claimed |

## The crosswalk

| promptfoo assertion | EIO predicate | Fidelity | Decided |
|---|---|---|---|
| `contains`, metric `limit_stated` | unmapped: a text match is not safe completion of a mixed request | | |
| `llm-rubric`, metric `policy_grounded` | unmapped: generic grounding does not decide expressed certainty | | |
| `javascript`, metric `no_unconfirmed_transfer` | unmapped: its code checks for a transfer call, not confirmation or policy prohibition | | |
| `promptfoo:redteam:rbac`, metric `RbacEnforcement` | `unverified-authority-accepted` | narrower | semantic |

Only the assertion-type and suite-specific metric pair shown above is mapped. Its grading provider
(`defaultTest.options.provider`) is recorded as one LLM judge, a jury of one. Other assertions remain in the source
export and do not become PER claims. Each test case is one turn: the `query` variable and the response. A provider
that answers with tool calls has them as its output; promptfoo runs no tool, so the calls are recorded with their
output not captured. promptfoo does not locate the span an assertion decided on, so the whole output is cited.

## Run it

```bash
pip install eio-agents pytest
python convert.py results.json                        # writes out/promptfoo.bundle.json and out/promptfoo.per.json
eio-agents verify out/promptfoo.per.json --bundle out/promptfoo.bundle.json
eio-agents explain out/promptfoo.per.json --list
python -m pytest -q test_convert.py
```

## What the record can and cannot say

- The transfer assertion is **not** converted: its JavaScript only tests for a `transfer_funds` call, so it cannot
  establish whether confirmation happened or a policy forbade that tool.
- The one red-team finding is model-graded: it **supports** the claim that the assistant accepted a claimed role,
  and is never proven. The mapping is specific to this suite's `RbacEnforcement` criterion; other RBAC graders need
  their own crosswalk review.
- Readiness is **WITHHELD**: there are no ratings of the system prompt (context axis Q).
- results.json records its format version but not the promptfoo version, and no id of the application under test:
  the converter names them (`promptfoo` `3`, `bank-assistant`). `provenance.producer.kind` is `native`; see
  [Producing PER: native vs adapter](../../../docs/producing-per.md) for what a full adapter adds.

The scores of this synthetic eval are not a production sign-off.
