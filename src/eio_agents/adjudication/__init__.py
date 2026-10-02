"""Adjudication: ballot pooling over distinct (persona, round) pairs (03 §7.6.4; 01 §7.5 B2-B3) and the grounding reason
order of an EVIDENCE_INVALID claim (03 §7.6).

Both read bundle objects only: ballots `{persona, round, observed}` (the bundle `ballots` section) and source texts (the
bundle `sources` section). How a producer's run log becomes ballots is the producer's (adapter's) part.
"""


def pool(ballots):
    """The vote counts of one claim from its ballots. A (persona, round) pair counts once: `observed` when all its
    non-null ballots are true, `not_observed` when all are false, `split` when both occur; a pair with only null ballots
    does not count."""
    pairs = {}
    for b in ballots:
        pairs.setdefault((b["persona"], b["round"]), set()).add(b["observed"])
    valid = {k: s - {None} for k, s in pairs.items() if s - {None}}
    return {"distinct_pairs": len(valid), "observed": sum(1 for s in valid.values() if s == {True}),
            "not_observed": sum(1 for s in valid.values() if s == {False}),
            "split": sum(1 for s in valid.values() if s == {True, False})}


def invalid_because(cited_texts, other_turn_answers, question):
    """The EVIDENCE_INVALID reason, verified against the sources (never taken from an evaluator's label): a cited text that
    is agent output of another turn, else text of this turn's question (not agent output), else found in no source."""
    for text in cited_texts:
        if text and any(text in x for x in other_turn_answers):
            return "cited_span_other_turn"
    for text in cited_texts:
        if text and text in question:
            return "cited_span_not_agent"
    return "cited_span_not_found"
