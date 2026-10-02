"""Compatibility entrypoint for the isolated native rc2 migration candidate.

The implementation now lives in the packaged native route. This tool retains
the earlier focused tests without maintaining a second projection algorithm.
"""
from eio_agents.per.native_preview import (
    NO_SCORING_PROFILE_ID,
    SCHEMA_URI,
    project_native_preview,
    verify_native_preview,
)

__all__ = ["NO_SCORING_PROFILE_ID", "SCHEMA_URI", "project_native_preview", "verify_native_preview"]
