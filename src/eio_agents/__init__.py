"""EIO-Agents — reference library for the Evaluation Intelligence Ontology (EIO) and PER 2.0 evaluation
records. This release candidate bundles the 0.6 EIO ontology and emits PER 2.0.0 for source-complete native scoring;
incomplete records retain the explicitly labeled partial PER 2.0.0-rc3-draft schema;
historical rc1/rc2 records require their pinned historical release and producer adapter.

One deterministic projection of an evaluation bundle (archive schema 3) to a PER 2.0 record, plus
validation, verification and "why" explanations, for the producer of a record and for any verifier or
store that re-derives it. A stored producer report (archive schema 1 or 2) is not a bundle: it
must first be converted to a bundle by its producer's adapter. No evaluator model, clock, environment or network is used by `convert`.

The package root is lazy (PEP 562): `import eio_agents` imports no submodule, and `import eio_agents.ontology` (or any
other neutral subpackage) never loads `eio_agents.api` (the rc1 staging areas `_legacy` and `_vendored` were deleted at
step L4). The public names below are resolved from their defining module on first attribute access.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

__version__ = "0.6.0rc1"

# public name -> the module that defines it (every lookup below is an explicit import; no dynamic import, no discovery)
_API = ("convert", "convert_file", "resolve", "standards", "validate", "verify")      # eio_agents.api (projection and verifier, in process)
_PER = ("canonical_bytes", "per_sha256", "write")                          # eio_agents.per
_VALIDATION = ("explain", "finding_evidence", "findings_at_turn", "metric_card", "targets")  # eio_agents.validation
_BASE = ("ConversionError",)                                               # eio_agents.base.errors

__all__ = ["ConversionError", "canonical_bytes", "convert", "convert_file", "explain", "finding_evidence",
           "findings_at_turn", "metric_card", "per_sha256", "resolve", "standards", "targets", "validate", "verify",
           "write", "__version__"]

if TYPE_CHECKING:  # for type checkers only; never executed
    from eio_agents.api import convert, convert_file, resolve, standards, validate, verify
    from eio_agents.base.errors import ConversionError
    from eio_agents.per import canonical_bytes, per_sha256, write
    from eio_agents.validation import explain, finding_evidence, findings_at_turn, metric_card, targets


def __getattr__(name: str):
    if name in _API:
        import eio_agents.api as module
    elif name in _PER:
        import eio_agents.per as module
    elif name in _VALIDATION:
        import eio_agents.validation as module
    elif name in _BASE:
        import eio_agents.base.errors as module
    else:
        raise AttributeError(f"module 'eio_agents' has no attribute {name!r}")
    return getattr(module, name)


def __dir__():
    return sorted(set(globals()) | set(__all__))
