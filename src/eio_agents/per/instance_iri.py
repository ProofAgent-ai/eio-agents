"""Deterministic UUIDv5 instance IRIs for a separate neutral JSON-LD view.

The namespace and name recipe are versioned release strings.
The view never rewrites compact PER ids or their canonical report digest.
"""
from __future__ import annotations

import re
import uuid

_ID = re.compile(r"[0-9a-f]{20}\Z")
_KINDS = frozenset({"claim", "ref", "finding"})
PROPOSED_NAMESPACE_NAME = "https://www.proofagent.ai/eio-agents/instances"
PROPOSED_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, PROPOSED_NAMESPACE_NAME)
_ROWS = (("claim", "claims", "id", "eioid:eio.entity.evaluation-claim"),
         ("ref", "evidence", "id", "eioid:eio.entity.evidence-ref"),
         ("finding", "findings", "finding_id", "eioid:eio.entity.finding"))


def instance_iri(namespace: uuid.UUID, kind: str, compact_id: str) -> str:
    """Map an existing compact id to a kind-separated, absolute UUIDv5 IRI."""
    if not isinstance(namespace, uuid.UUID):
        raise TypeError("namespace must be a UUID selected for the release")
    if kind not in _KINDS:
        raise ValueError("kind must be claim, ref, or finding")
    if not isinstance(compact_id, str) or _ID.fullmatch(compact_id) is None:
        raise ValueError("compact_id must be exactly 20 lowercase hex characters")
    return f"urn:uuid:{uuid.uuid5(namespace, f'eio-agents:{kind}:{compact_id}')}"


def jsonld_instance_view(record: dict) -> dict:
    """Materialize only typed identity nodes; no producer text enters the view.

    This is deliberately separate from the canonical PER. An invalid or duplicate
    compact identifier fails closed rather than aliasing two evidence objects.
    """
    graph = []
    for kind, section, key, class_iri in _ROWS:
        rows = record["evidence"]["refs"] if section == "evidence" else record[section]
        seen = set()
        for row in rows:
            compact_id = row[key]
            iri = instance_iri(PROPOSED_NAMESPACE, kind, compact_id)
            if compact_id in seen:
                raise ValueError(f"duplicate {kind} compact id")
            seen.add(compact_id)
            graph.append({"@id": iri, "@type": class_iri, "per:compact_id": compact_id})
    return {"@context": {"@version": 1.1,
                         "eioid": "https://www.proofagent.ai/eio-agents/id/",
                         "per": "https://www.proofagent.ai/eio-agents/per/terms/"},
            "@graph": graph}
