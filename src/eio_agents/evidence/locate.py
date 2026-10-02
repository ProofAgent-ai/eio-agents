"""`locate`: the offsets of a cited text in its source (03 §7.5.1 rule 2)."""


def locate(q, S):
    """03 §7.5.1 rule 2: exact, then casefold where casefolding preserves length; never fuzzy.
    Returns (start, end, anchor) or None."""
    if not q:
        return None
    i = S.find(q)
    if i >= 0:
        return i, i + len(q), "exact"
    if len(S.casefold()) == len(S) and len(q.casefold()) == len(q):
        i = S.casefold().find(q.casefold())
        if i >= 0:
            return i, i + len(q), "casefold"
    return None
