"""The bottom layer of EIO-Agents: the canonical form and digests (`canon`: RFC 8785 JCS, `stable_digest`, sha256 strings,
the number rules) and the error type (`errors`: `ConversionError`, `require`).

`base` imports only the standard library, and every other `eio_agents` module may import it. The independent verifier
(`eio_agents.validation`) is the exception: it keeps its own JCS and digests (contract P3) and never imports `base`.
"""
