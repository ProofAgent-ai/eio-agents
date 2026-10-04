"""Re-derive a pinned record under the library version that issued it.

A record names the library that converted it (`header.converter.version`, `header.per_semantics_version`, and the score
digests over its header), and a bundle names the library that built it (`header.eio_agents.version`, which turns on the
stage-digest recomputation). A patch release changes only that stamp. `library_version("0.8.0")` stamps the version the
pinned vectors were issued with, so a test proves the current code re-derives them byte for byte, rather than
reissuing them.
"""
from __future__ import annotations

import contextlib
import importlib
from unittest import mock

# every module that reads the library version into a record or a bundle
_STAMPING = ("eio_agents.base.version", "eio_agents.api", "eio_agents.per.bundle", "eio_agents.per.build",
             "eio_agents.per.native_preview")


@contextlib.contextmanager
def library_version(version: str):
    with contextlib.ExitStack() as stack:
        for name in _STAMPING:
            module = importlib.import_module(name)
            assert hasattr(module, "VERSION"), name
            stack.enter_context(mock.patch.object(module, "VERSION", version))
        yield
