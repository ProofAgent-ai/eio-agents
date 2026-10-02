"""Claim semantics: ids (`ids`), the claim builder (`claims`), scope rules (`scope`), coverage (`coverage`), proof status
(`proof`), findings (`findings`), gates and release (`release`), explanations (`why`), and the shared orderings below.
They read bundle objects only (split plan §3.10); the producer's recipes stay with its adapter.

The decision states (`STATES`, in PER enum order) are defined by `eio_agents.ontology`, which checks them against the release;
they are re-exported here with the other orderings. `semantics` depends on `base` and `ontology`, never on `evidence`.
"""
from eio_agents.ontology import STATES  # noqa: F401  (re-exported with the orderings below)

SEVR = {"CRITICAL": 5, "HIGH": 4, "MEDIUM": 3, "LOW": 2, "INFORMATIONAL": 1}
IMP_ORDER = ["NONE", "MONITOR", "WARN", "CONTRIBUTING_BLOCK", "HARD_BLOCK"]
FAULT = {"EVIDENCE_INVALID", "EVIDENCE_INCOMPLETE", "EVALUATOR_ERROR"}
SCORED = {"APPLICABLE_PASS", "APPLICABLE_FAIL"}
