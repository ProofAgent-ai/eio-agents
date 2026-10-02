"""The producer-adapter extension point (split plan §4.4): the interface a producer adapter implements.

A producer adapter turns one producer's own raw output (for example a stored evaluation report) into an EIO bundle,
the only input `eio_agents.convert` will take (§4.1). EIO-Agents has no plugin hooks: an adapter plugs in with **data**.
It returns a bundle dict and declares, inside that bundle, the producer-specific documents the bundle depends on (by
digest). This module only states the shape of an adapter; it holds

- no registry of adapters,
- no plugin discovery and no entry points (§4.1 "No plugin discovery": output never depends on which packages are
  installed),
- no adapter implementation. The ProofAgent adapter lives in the harness (`proofagent_harness.eio_adapter`, since
  step L3).

A caller holds an adapter object and calls it; nothing here looks one up:

    bundle = my_adapter.to_bundle(raw)
    producer = adapter_metadata(my_adapter)   # {"name", "version", "kind": "adapter"}, e.g. for provenance.producer

`adapters` imports only `eio_agents.base`.
"""
from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from eio_agents.base.errors import require

ADAPTER_KIND = "adapter"  # `provenance.producer.kind` of every bundle an adapter produces (§4.4, N8); a native producer is "native"


@runtime_checkable
class ProducerAdapter(Protocol):
    """A producer adapter: metadata plus one pure call.

    - `name`: the producer (or adapter) name, a non-empty string.
    - `version`: the adapter version, a non-empty string.
    - `kind`: always `"adapter"`.
    - `to_bundle(raw)`: the producer's raw output -> an EIO bundle dict. It must be deterministic (no clock, environment,
      network or random source) and fail closed with `eio_agents.ConversionError`.
    """

    name: str
    version: str
    kind: Literal["adapter"]

    def to_bundle(self, raw: Any) -> dict[str, Any]:
        ...


def adapter_metadata(adapter: Any) -> dict[str, str]:
    """`{name, version, kind}` of a producer adapter, checked. Fails closed (`ConversionError`, code `ADAPTER_METADATA`)
    when the object is not a `ProducerAdapter`, a field is empty or not a string, or `kind` is not `"adapter"`."""
    require(isinstance(adapter, ProducerAdapter) and callable(getattr(adapter, "to_bundle", None)), "ADAPTER_METADATA",
            "not a producer adapter: name, version, kind and to_bundle(raw) are required")
    meta = {"name": adapter.name, "version": adapter.version, "kind": adapter.kind}
    for key, value in meta.items():
        require(isinstance(value, str) and value != "", "ADAPTER_METADATA", f"{key} must be a non-empty string")
    require(meta["kind"] == ADAPTER_KIND, "ADAPTER_METADATA", f"kind must be {ADAPTER_KIND!r}, not {meta['kind']!r}")
    return meta
