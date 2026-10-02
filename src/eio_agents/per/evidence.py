"""The evidence block of a record: the ref order (03 §5.6 rule 1) and the refs a record cites."""

KIND_ORDER = ["AGENT_SPAN", "TOOL_RECEIPT", "TYPED_ABSENCE", "CALCULATION", "STATE_FACT", "STATE_TRANSITION", "USER_INPUT",
              "RETRIEVAL", "POLICY_SPAN", "PROVENANCE", "HUMAN_SIGNOFF"]                                     # 03 §5.6 rule 1


def ref_key(r):
    """03 §5.6 rule 1: the position of a ref in `evidence.refs[]`, by turn (turn-less last), kind order, char_start (null
    first) and id. It is a total order over refs, so it places a ref whenever the projector derives it."""
    return (r["turn_index"] is None, r["turn_index"] or 0, KIND_ORDER.index(r["kind"]),
            -1 if r["char_start"] is None else r["char_start"], r["id"])


def order_refs(refs, claims):
    """Refs (id -> ref) ordered by `ref_key`; each claim's evidence is re-ordered in place to match. Returns (the ordered
    refs, ref id -> position)."""
    ref_list = sorted(refs.values(), key=ref_key)
    ref_order = {r["id"]: i for i, r in enumerate(ref_list)}
    for c in claims:
        c["evidence"].sort(key=lambda r: ref_order[r])
    return ref_list, ref_order


def cited_ref_ids(rec):
    """Every ref id a record (or part of one) cites: string lists under evidence, evidence_refs and counterevidence, and
    string values of ref and ref_id."""
    out = set()

    def walk(o):
        if isinstance(o, dict):
            for kk, vv in o.items():
                if kk in ("evidence", "evidence_refs", "counterevidence") and isinstance(vv, list) and all(isinstance(x, str) for x in vv):
                    out.update(vv)
                elif kk in ("ref", "ref_id") and isinstance(vv, str):
                    out.add(vv)
                else:
                    walk(vv)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(rec)
    return out
