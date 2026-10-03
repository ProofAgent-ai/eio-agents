"""Issue 0.8-native synthetic vectors without modifying historical v0_6 fixtures."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tests/data/native"), str(ROOT / "src")]

from author_native import author, pinned  # noqa: E402
from full_native_score_case import reissued_cited_bundle, source_complete_bundle  # noqa: E402
from eio_agents import __version__, canonical_bytes, convert, validate, verify  # noqa: E402
from eio_agents.validation import validate_bundle  # noqa: E402

CURRENT = ROOT / "tests/data/native/v0_8"
OLD_2_0 = ROOT / "tests/data/native/v0_6/source-complete.per.jcs"
OLD_2_0_SHA = "9ea9b9f30cad6d6f827914480e0d0ee1f15c8ecb71828829bbcd7bcbb29b9ecc"


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


def main() -> None:
    assert __version__ == "0.8.0"
    assert hashlib.sha256(OLD_2_0.read_bytes()).hexdigest() == OLD_2_0_SHA
    native, cited, complete = author(), reissued_cited_bundle(), source_complete_bundle()
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
        assert bundle["header"]["eio_agents"]["version"] == "0.8.0", name
        assert validate_bundle(bundle) == [], name
        record = convert(bundle)
        assert validate(record) == [], name
        result = verify(record, bundle)
        assert result["valid"] and result["digest_match"], (name, result)
    assert json.loads(outputs["source-complete.per.jcs"])["header"]["per_version"] == "2.1.0"
    CURRENT.mkdir(parents=True, exist_ok=True)
    for name, payload in outputs.items():
        target = CURRENT / name
        target.write_bytes(payload)
        print(f"{target.relative_to(ROOT)} sha256:{hashlib.sha256(payload).hexdigest()}")
    assert hashlib.sha256(OLD_2_0.read_bytes()).hexdigest() == OLD_2_0_SHA


if __name__ == "__main__":
    main()
