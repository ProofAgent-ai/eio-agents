"""Limitations (03 §7.13): the limitation catalogue and one limitation row.

The catalogue is data, `data/limitations.json`: the 48 ids of the 04 §5.13 table, parsed from it once, in table order. It
is the one closed catalogue of PER 2.0.0-rc1 (CONS-17): an id it does not list fails the conversion. The split into a core
catalogue and declared adapter catalogues is L5a.
"""
import json
from pathlib import Path

from eio_agents.base.errors import ConversionError, require

CATALOGUE = Path(__file__).resolve().parent / "data" / "limitations.json"


def load_catalogue(path=CATALOGUE):
    """id -> (status, field_path, reason, impact, next_step); field_path is the first catalogue path of the row."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return {r["id"]: (r["status"], r["paths"][0], r["reason"], r["impact"], r["next_step"]) for r in doc["limitations"]}


def catalogue_paths(path=CATALOGUE):
    """id -> every catalogue path of the row (a path may hold `{name}` placeholders, one pointer token each)."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return {r["id"]: list(r["paths"]) for r in doc["limitations"]}


def limitation(catalogue, lid, path=None, **params):
    """One limitation row of `lid`: the catalogue texts with `params` filled in, at `path` (default: the catalogue path)."""
    return limitation_row(catalogue, lid, path, params)


def limitation_row(catalogue, lid, path, params):
    """`limitation` with the parameters as a dict (a producer's parameter may have any name: L3 fix round 2, no untyped
    error for a name such as 'path')."""
    require(lid in catalogue, "UNKNOWN_LIMITATION", f"{lid} is not in 04 §5.13")
    st, default_path, reason, impact, nxt = catalogue[lid]
    try:
        path = path or default_path.format(**params)
        return {"limitation_id": lid, "field_path": path, "status": st, "reason": reason.format(**params),
                "impact": impact.format(**params), "next_step": nxt.format(**params)}
    except (KeyError, IndexError, ValueError) as e:      # a parameter the catalogue text names is missing (L3 fix round 2)
        raise ConversionError(f"TEMPLATE_PARAMS: {lid}: the parameters {sorted(params)!r:.120} do not fill its catalogue "
                              f"texts ({type(e).__name__}: {str(e)[:60]})", code="TEMPLATE_PARAMS") from e
