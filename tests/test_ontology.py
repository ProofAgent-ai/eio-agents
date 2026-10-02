"""`eio_agents.ontology.load()`: pins and digests verified, RELEASE-DIGESTS reproduced, legacy adjunct served outside it."""
import hashlib
import shutil

import pytest
import yaml

from eio_agents import ontology
from eio_agents.base.errors import ConversionError
from eio_agents.ontology import DATA_DIR, Ontology

LEGACY_ATTRS = ["legacy", "checks_version", "reach", "rows_reaching", "metric_order", "metric_of_legacy", "crosswalk",
                "links", "trap_severity"]


def test_load_returns_a_new_verified_release_per_call():
    """No process-global cache: every call reads and verifies the release, and callers hold the object they need."""
    o, again = ontology.load(), ontology.load()
    assert isinstance(o, Ontology) and isinstance(again, Ontology) and again is not o
    assert (again.modules, again.ontology_sha256) == (o.modules, o.ontology_sha256)
    assert not hasattr(ontology, "_load") and not hasattr(ontology.load, "cache_info")
    man = yaml.safe_load((DATA_DIR / "manifest.yaml").read_bytes())
    assert o.pins == {i["module"]: {"version": str(i["version"]), "sha256": i["sha256"]} for i in man["imports"]}
    assert all(o.modules[m] == pin["sha256"] for m, pin in o.pins.items())
    assert set(o.modules) == set(o.pins) | {"eio.manifest.public"}
    assert len(man["imports"]) == 38
    assert len(o.modules) == len(man["imports"]) + 1 == 39


def test_release_digests_reproduce(eio):
    o, d = eio, ontology.release_digests()
    assert (d["release"], d["modules"], d["ontology_sha256"], d["ontology_digest"]) == (
        o.release, o.modules, o.ontology_sha256, o.ontology_digest)
    # Exact current-release pin: re-review independently before publication.
    assert o.ontology_sha256 == d["ontology_sha256"] == (
        "sha256:a27cf1f3ab755446c639da6b0e6d3b2c4363c205e6ffa4b44e48876cce72ecc9"
    )
    assert o.ontology_digest == d["ontology_digest"] == "a27cf1f3ab755446"
    for rel, pin in d["files"].items():
        assert "sha256:" + hashlib.sha256(ontology.release_file(rel).read_bytes()).hexdigest() == pin, rel


def test_module_accessor(eio):
    o = eio
    assert o.module("eio.mapping.metrics")["eio"]["id"] == "eio.mapping.metrics"
    with pytest.raises(ConversionError, match="EIO_MODULE_ABSENT"):
        o.module("eio.mapping.legacy")
    with pytest.raises(ConversionError, match="EIO_MODULE_ABSENT"):
        o.module("eio.mapping.traps")
    with pytest.raises(ConversionError, match="EIO_MODULE_ABSENT"):
        o.module("eio.mapping.none")


def test_legacy_adjunct_is_not_on_the_ontology(eio):
    """The legacy adjunct is the ProofAgent adapter's `LegacyCrosswalk` (in the harness since L3; its rows are checked in
    tests/eio_adapter/test_legacy_crosswalk.py there), read through the generic module accessor, never an `Ontology`
    attribute."""
    o = eio
    assert not [a for a in LEGACY_ATTRS if hasattr(o, a)]
    assert len(o.metrics) == 9


def test_load_fails_closed_on_a_changed_module(tmp_path):
    root = tmp_path / "eio"
    shutil.copytree(DATA_DIR, root)
    f = root / "core" / "flow.yaml"
    f.write_bytes(f.read_bytes() + b"\n# changed\n")
    with pytest.raises(ConversionError, match="EIO_DIGEST_PIN: eio.core.flow"):
        ontology.load(root)
