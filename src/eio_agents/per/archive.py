"""The archive digest `archive_sha256` for archive schemas 2 and 3 (03 §5.4, PER-1)."""
from eio_agents.base.canon import H, jb
from eio_agents.base.errors import require


def archive_sha256(archive):
    """sha256 over the JCS bytes of the archive. Schema 1 has its own frozen rule, read by the ProofAgent adapter; any
    other schema fails closed."""
    schema = archive.get("archive_schema")
    require(schema in (2, 3) and not isinstance(schema, bool), "ARCHIVE_SCHEMA",
            f"archive_sha256 covers archive schemas 2 and 3, not {schema!r}")
    return H(jb(archive))
