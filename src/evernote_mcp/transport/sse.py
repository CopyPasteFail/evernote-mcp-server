"""Placeholder for future SSE transport support."""

from __future__ import annotations

SSE_NOT_IMPLEMENTED_MESSAGE = (
    "SSE transport is planned but not implemented yet in v0.1. "
    "Use --transport stdio."
)


def run_sse_transport() -> None:
    """Fail explicitly because SSE transport is intentionally out of scope for v0.1.

    Raises:
        NotImplementedError: Always raised until SSE transport is implemented.
    """

    raise NotImplementedError(SSE_NOT_IMPLEMENTED_MESSAGE)
