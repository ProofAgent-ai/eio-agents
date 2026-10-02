"""Shared fixtures of the EIO-Agents suite."""
import pytest

from eio_agents import ontology


@pytest.fixture(scope="session")
def eio():
    """The bundled EIO release, loaded once for the tests that read it: `ontology.load()` builds a new one on every call."""
    return ontology.load()
