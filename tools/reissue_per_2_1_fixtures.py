"""Reissue only the new PER 2.1 synthetic golden; never rewrite published 2.0 fixtures."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src")]

from eio_agents import canonical_bytes, convert, validate, verify  # noqa: E402

OLD = ROOT / "tests/data/native/v0_6/source-complete.per.jcs"
BUNDLE = ROOT / "tests/data/native/v0_6/source-complete.bundle.json"
NEW = ROOT / "tests/data/native/per_2_1/source-complete.per.jcs"
OLD_SHA = "9ea9b9f30cad6d6f827914480e0d0ee1f15c8ecb71828829bbcd7bcbb29b9ecc"
BUNDLE_SHA = "0660c2a2fb554a0ed7a312109b998384b0aa98960bdd861d2e7263035cdbd6f3"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    assert digest(OLD) == OLD_SHA and digest(BUNDLE) == BUNDLE_SHA
    bundle = BUNDLE.read_bytes()
    record = convert(bundle)
    assert record["header"]["per_version"] == "2.1.0"
    assert validate(record) == []
    result = verify(record, bundle)
    assert result["valid"] and result["digest_match"]
    NEW.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_bytes(record)
    NEW.write_bytes(payload)
    assert digest(OLD) == OLD_SHA and digest(BUNDLE) == BUNDLE_SHA
    print(f"{NEW.relative_to(ROOT)} sha256:{hashlib.sha256(payload).hexdigest()}")


if __name__ == "__main__":
    main()
