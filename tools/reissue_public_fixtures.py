"""Historical 0.6 fixture reissuer; never run against a newer package.

Historical vectors in tests/data/native/ are intentionally immutable. This
script uses the checked-in native author functions and no Harness adapter.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tests" / "data" / "native"), str(ROOT / "src")]

from author_native import author, pinned  # noqa: E402
from full_native_score_case import reissued_cited_bundle, source_complete_bundle  # noqa: E402
from eio_agents import __version__, canonical_bytes, convert, validate, verify  # noqa: E402
from eio_agents.validation import validate_bundle  # noqa: E402

CURRENT = ROOT / "tests" / "data" / "native" / "v0_6"
HISTORICAL = ROOT / "tests" / "data" / "native"
HISTORICAL_SHA = "12a212d955be08e8371de00486b294f9ec776885e9e86a8915c1434bbf1ec305"


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


def main() -> None:
    if __version__ != "0.6.0":
        raise SystemExit("v0_6 bytes are historical; use tools/reissue_0_8_fixtures.py for EIO-Agents 0.8.0")
    old = HISTORICAL / "native.bundle.json"
    assert hashlib.sha256(old.read_bytes()).hexdigest() == HISTORICAL_SHA
    assert CURRENT.is_dir() and CURRENT.parent == HISTORICAL

    native = author()
    cited = reissued_cited_bundle()
    complete = source_complete_bundle()
    native_per, native_problems = pinned(native)
    outputs = {
        "native.bundle.json": _json_bytes(native),
        "native.per.jcs": native_per,
        "native.rc1_problems.json": _json_bytes(native_problems),
        "synthetic-cited-native.bundle.json": _json_bytes(cited),
        "source-complete.bundle.json": _json_bytes(complete),
        "source-complete.per.jcs": canonical_bytes(convert(complete)),
    }
    for name, bundle in (("native", native), ("cited", cited), ("complete", complete)):
        assert validate_bundle(bundle) == [], name
        record = convert(bundle)
        assert validate(record) == [], name
        result = verify(record, bundle)
        assert result["valid"] and result["digest_match"], (name, result)
    for name, payload in outputs.items():
        target = CURRENT / name
        assert target.is_file(), f"refusing to create unexpected fixture: {target}"
        target.write_bytes(payload)
        print(f"{name} sha256:{hashlib.sha256(payload).hexdigest()}")
    assert hashlib.sha256(old.read_bytes()).hexdigest() == HISTORICAL_SHA


if __name__ == "__main__":
    main()
