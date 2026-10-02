"""The verifier checks embedded catalogues without calling the producer parser."""
import copy
import json
from pathlib import Path

from eio_agents.validation.canon import jb, sha
from eio_agents.validation.checker import Checker
from eio_agents.validation.reader import EIO, EIO_DIR, load_catalogue

NATIVE = Path(__file__).parent / "data/native/v0_6/native.per.jcs"


def _record():
    return json.loads(NATIVE.read_text(encoding="utf-8"))


def _problems(record):
    return Checker(record, EIO(EIO_DIR), load_catalogue(), "native").c_limitations()[0]


def _declared():
    doc = {"id": "example.limits", "version": "1.0.0", "limitations": [{
        "id": "example.limits.missing", "status": "NOT_SUPPLIED",
        "paths": ["/subject/agent/version"], "raised_when": "synthetic version not supplied",
        "reason": "No agent version was supplied.",
        "impact": "Version comparison is unavailable.",
        "next_step": "Supply an agent version.",
    }]}
    return {**doc, "sha256": sha(jb(doc))}


def test_verifier_accepts_native_core_and_digest_pinned_declaration():
    record = _record()
    assert _problems(record) == []
    declaration = _declared()
    record["header"]["declared_limitation_catalogues"] = [declaration]
    record["limitations"].append({"limitation_id": declaration["limitations"][0]["id"],
                                  "field_path": "/subject/agent/version", "status": "NOT_SUPPLIED",
                                  "reason": "No agent version was supplied.",
                                  "impact": "Version comparison is unavailable.",
                                  "next_step": "Supply an agent version."})
    assert _problems(record) == []


def test_verifier_rejects_tamper_collision_and_unapproved_free_text():
    good = _record()
    good["header"]["declared_limitation_catalogues"] = [_declared()]
    good["limitations"].append({"limitation_id": "example.limits.missing",
                                "field_path": "/subject/agent/version", "status": "NOT_SUPPLIED",
                                "reason": "No agent version was supplied.",
                                "impact": "Version comparison is unavailable.",
                                "next_step": "Supply an agent version."})
    assert _problems(good) == []

    tampered = copy.deepcopy(good)
    tampered["header"]["declared_limitation_catalogues"][0]["limitations"][0]["reason"] = "Different text."
    assert any("CATALOGUE_DIGEST" in problem for problem in _problems(tampered))

    collision = copy.deepcopy(good)
    collision["header"]["declared_limitation_catalogues"].append(copy.deepcopy(_declared()))
    assert any("CATALOGUE_COLLISION" in problem for problem in _problems(collision))

    free_text = copy.deepcopy(good)
    free_text["limitations"][-1]["reason"] = "customer@example.invalid"
    assert any("LIMITATION_TEXT" in problem for problem in _problems(free_text))
