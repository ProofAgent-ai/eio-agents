"""Resolvers: `RESOLVER_READS`, the evidence kinds each deterministic resolver reads (MAP-20, PER-706), and the MAP-20
natural-resolver rule.

EIO does not declare which kinds a resolver reads (an EIO gap), so the table is code. The verifier keeps its own copy on
purpose (independent implementation). The registry of resolver ids is the loaded release (`Ontology.resolver_kind`,
`Ontology.resolver_ids`).
"""

RESOLVER_READS = {"eio.resolver.tool-receipt": {"TOOL_RECEIPT"}, "eio.resolver.typed-absence": {"TYPED_ABSENCE"},
                  "eio.resolver.state-transition": {"STATE_FACT", "STATE_TRANSITION"}, "eio.resolver.paired-comparison": {"CALCULATION"},
                  "eio.resolver.exact-span": {"AGENT_SPAN"}, "eio.resolver.arithmetic": {"AGENT_SPAN", "CALCULATION"}}


def natural_resolver(eio, resolver, predicate, decided_by, cited_kinds):
    """MAP-20 / PER-706: the resolver a deterministic claim names. A declared `resolver` is the claim's natural resolver
    only when the claim cites a kind that resolver reads and the release lists it for the predicate; else None."""
    if decided_by != "deterministic" or not resolver:
        return None
    if not any(k in RESOLVER_READS.get(resolver, ()) for k in cited_kinds):
        return None
    return resolver if resolver in eio.resolver_ids(predicate) else None
