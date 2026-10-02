"""The independent PER verifier (it shares no code with the projector; contract P3) and `explain`.

Its own canonical form and digests (`canon`), EIO reader and limitation catalogue (`reader`), explanation renderer
(`render`), PER Pointers (`pointer`), PROD-42 redaction (`redaction`) and gate rules (`gates`); the record-level checks
(`checker`); the in-process check runs `validate` and `validate_bundle` (`validate`); VER-5 over a bundle's sources and the
digest comparison (`verify`); `explain` (`explain`); and the closed field table of decision #31 with the local
resolver of the record's fingerprints (`privacy`). None of it imports the projector: `eio_agents.verify` re-projects
the bundle and passes the result in. The ProofAgent halves of the mixed checks and the archive checks are the ProofAgent
adapter's legacy verifier (in the ProofAgent Harness since L3).
"""
from eio_agents.validation.explain import explain
from eio_agents.validation.explore import finding_evidence, findings_at_turn, metric_card, resolve_target, targets
from eio_agents.validation.privacy import resolve
from eio_agents.validation.validate import check_one, validate, validate_bundle
from eio_agents.validation.verify import verify

__all__ = ["check_one", "explain", "finding_evidence", "findings_at_turn", "metric_card", "resolve", "resolve_target",
           "targets", "validate", "validate_bundle", "verify"]
