# A native producer: PER as the output of the run

ProofAgent Harness is integrating EIO-Agents so that a PER is its **native** output format: the harness records the
evidence while it evaluates, decides each check against an EIO predicate, and emits the bundle and the PER at the end
of the same run. This example is a small, **synthetic** sketch of that pattern. It does not use or require ProofAgent
Harness: the agent, its tools and the jury are scripted, so `run_eval.py` needs only `eio-agents`.

| File | What it is |
|---|---|
| `run_eval.py` | The run: a `NativeRun` recorder, a scripted shop-support agent with two tools, the checks, and `finish()` |
| `test_run_eval.py` | Tests: a valid, verifiable PER 2.1.0, exact fidelity, what is and is not proven, determinism |

## Native or adapter

| | Native producer (this example, ProofAgent Harness) | Adapter (the [adapter examples](../../adapters/)) |
|---|---|---|
| When | During the run | After the run, from an export file |
| Evidence | Captured as it happens: the exact answer text, every tool call with its arguments and result | Whatever the export kept; spans are located after the fact |
| Mapping | Checks are written against EIO predicates | A crosswalk maps each tool's scorer or assertion to a predicate |
| Fidelity | Usually `exact`: the check decides the predicate itself | Often `narrower`: the scorer measures something close to the predicate |
| Output | The bundle and the PER, in the same process | A bundle and a PER built from the export |
| `provenance.producer.kind` | `native` | `native` in these illustrative converters (see [producing-per.md](../../../docs/producing-per.md)) |

## The pattern

```python
run = NativeRun(producer=..., agent=..., started_at=...)
for user in scenario:
    answer, tools = agent(user)                         # the agent under test
    t = run.turn(user, answer, tools)                   # record the turn as it happens
    run.check(t, "certainty-exceeds-evidence", False, quote="Your refund will definitely arrive tomorrow")
    run.jury(t, "prohibited-part-clearly-refused", quote=..., ballots=[...], model="acme/jury-llm-1")
bundle, record = run.finish(completed_at=...)         # build_bundle + convert, in the run
```

A check passes the exact span it looked at as `quote`. That is why fidelity is `exact`: nothing is reconstructed
later, and the span is the text the check decided on.

## Run it

```bash
pip install eio-agents pytest
python run_eval.py                                     # writes out/run.bundle.json and out/run.per.json
eio-agents verify out/run.per.json --bundle out/run.bundle.json
eio-agents explain out/run.per.json --list
python -m pytest -q test_run_eval.py
```

The run has three turns and four checks. Turn 1's answer promises a refund "definitely" tomorrow while the lookup it
made says 3 to 5 days: the deterministic check cites the exact sentence and the tool receipt, which meets the
predicate's evidence contract, so that finding is **PROVEN**. Turn 2 refunds an order the agent never looked up: the
finding is **UNPROVEN**, because its contract also needs a policy text and a verification state (a state fact or a
typed absence) that this run does not carry.
Turn 3 (the refusal) is graded by a **jury**: three jurors (the personas strict, neutral and lenient) vote in two
rounds, and `build_bundle` pools the six ballots into the claim's vote counts (`distinct_pairs` 6, `observed` 6), as
the bundle's `ballots` section and `convert` recount them. A model-graded decision **supports** the claim and is never
proven. The jury's model (`acme/jury-llm-1`) and the agent's model are recorded in clear in the PER; a bundle names one
model per claim, so a jury whose jurors run on different models records the claim's model only.

The scores of this synthetic run are not a production sign-off.
