"""Versioned, producer-independent PER score-basis normalization (draft)."""

from eio_agents.validation.canon import jb, sha


SCORE_BASIS_VERSION = "eio-agents.score-basis/0.2.0-draft.1"
SCORE_ONLY_LIMITATIONS = frozenset({"per.lim.scoring_profile.none"})


class ScoreBasisError(ValueError):
    """The received PER cannot be normalized into the draft score basis."""


def score_basis_sha256(record, *, scored):
    """Hash received PER except scores and the exact score-only limitation.

    The normalization never invokes a producer or inserts a guessed row. It
    preserves every other field and limitation in its received order and uses
    the package's RFC 8785/JCS bytes. A scored PER carrying the null-score
    limitation is contradictory and rejected rather than silently dropped.
    """
    if not isinstance(record, dict) or type(scored) is not bool:
        raise ScoreBasisError("score basis needs a PER object and explicit scored state")
    rows = record.get("limitations")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ScoreBasisError("PER limitations are not a typed array")
    ids = [row.get("limitation_id") for row in rows]
    if len(ids) != len(set(ids)):
        raise ScoreBasisError("PER limitations duplicate an identifier")
    if scored and (record.get("scores") is None or SCORE_ONLY_LIMITATIONS.intersection(ids)):
        raise ScoreBasisError("scored PER is null or retains a null-score limitation")
    if not scored and record.get("scores") is not None:
        raise ScoreBasisError("unscored PER carries scores")
    if not scored and ids.count("per.lim.scoring_profile.none") != 1:
        raise ScoreBasisError("unscored PER needs exactly one null-score limitation")
    basis = {key: value for key, value in record.items() if key != "scores"}
    basis["limitations"] = [row for row in rows if row["limitation_id"] not in SCORE_ONLY_LIMITATIONS]
    return sha(jb(basis))
