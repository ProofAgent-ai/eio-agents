"""PER 2.0 records: the version, the archive digest, the evidence block (`KIND_ORDER`, `order_refs`, `cited_ref_ids`), the
capsule fields, the limitation catalogue (`limitations`) and record io (`canonical_bytes`, `per_sha256`, `pretty`,
`write_record`, `write`), and `project`, the projection of an evaluation bundle to a PER (`eio_agents.convert`; defined in
`eio_agents.per.projection`)."""
from eio_agents.per.archive import archive_sha256
from eio_agents.per.capsule import CAPSULE_FIELDS
from eio_agents.per.evidence import KIND_ORDER, cited_ref_ids, order_refs
from eio_agents.per.io import canonical_bytes, per_sha256, pretty, write, write_record

PER_VERSION = "2.0.0-rc3-draft"   # provisional S1b proof-rule release; historical rc1/rc2 remain pinned

from eio_agents.per.projection import project  # noqa: E402  (imports PER_VERSION-free modules only)

__all__ = ["CAPSULE_FIELDS", "KIND_ORDER", "PER_VERSION", "archive_sha256", "canonical_bytes", "cited_ref_ids", "order_refs",
           "per_sha256", "pretty", "project", "write", "write_record"]
