"""EIO-Agents — reference library for the Evaluation Intelligence Ontology (EIO) and Portable Evaluation Records
(PER). This release bundles the 0.6 EIO ontology and emits PER 2.1.0 for every new record (bundle format 3.0.0 in);
a bundle without native scoring inputs gets `scores: null`, and legacy records stay verifiable under their pinned
identities (historical stored reports require their producer adapter).

One deterministic projection of an evaluation bundle (archive schema 3) to a PER record, plus
validation, verification and "why" explanations, for the producer of a record and for any verifier or
store that re-derives it. A stored producer report (archive schema 1 or 2) is not a bundle: it
must first be converted to a bundle by its producer's adapter. No evaluator model, clock, environment or network is used by `convert`.

The package root is lazy (PEP 562): `import eio_agents` imports no submodule, and `import eio_agents.ontology` (or any
other neutral subpackage) never loads `eio_agents.api` (the rc1 staging areas `_legacy` and `_vendored` were deleted at
step L4). The public names below are resolved from their defining module on first attribute access.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

__version__ = "0.8.3"

# public name -> the module that defines it (every lookup below is an explicit import; no dynamic import, no discovery)
# eio_agents.api (projection, verifier and the predicate catalogue, in process)
_API = ("convert", "convert_file", "predicates", "resolve", "standards", "validate", "verify")
_PER = ("canonical_bytes", "per_sha256", "write")                          # eio_agents.per
_VALIDATION = ("explain", "finding_evidence", "findings_at_turn", "metric_card", "targets")  # eio_agents.validation
_BASE = ("ConversionError",)                                               # eio_agents.base.errors
_BUILD = ("build_bundle",)                                                 # eio_agents.per.build

__all__ = ["ConversionError", "build_bundle", "canonical_bytes", "convert", "convert_file", "explain",
           "finding_evidence", "findings_at_turn", "metric_card", "per_sha256", "predicates", "resolve", "standards",
           "targets", "validate", "verify", "write", "__version__"]

if TYPE_CHECKING:  # for type checkers only; never executed
    from eio_agents.api import convert, convert_file, predicates, resolve, standards, validate, verify
    from eio_agents.base.errors import ConversionError
    from eio_agents.per import canonical_bytes, per_sha256, write
    from eio_agents.per.build import build_bundle
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
    elif name in _BUILD:
        import eio_agents.per.build as module
    else:
        raise AttributeError(f"module 'eio_agents' has no attribute {name!r}")
    return getattr(module, name)


def __dir__():
    return sorted(set(globals()) | set(__all__))
