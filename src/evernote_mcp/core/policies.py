"""Policy helpers for runtime safety controls."""

from __future__ import annotations

DEFAULT_READ_ONLY_MODE = True
WRITE_BLOCKED_MESSAGE = "Write operations are disabled. Set READ_ONLY=false to enable write operations."

_active_read_only_mode = DEFAULT_READ_ONLY_MODE


class WriteAccessError(PermissionError):
    """Raised when a write operation is requested while write access is disabled."""


def set_read_only_mode(is_read_only: bool) -> None:
    """Set the active read-only policy mode for the current process.

    Args:
        is_read_only: True to block write operations, False to allow writes.

    Concurrency:
        Policy state is process-local and intentionally simple for this server process.
    """

    global _active_read_only_mode
    _active_read_only_mode = is_read_only


def writes_allowed() -> bool:
    """Return whether write operations are currently allowed.

    Returns:
        True when writes are enabled, False when write operations must be blocked.
    """

    return not _active_read_only_mode


def require_writes_enabled() -> None:
    """Enforce the write policy and raise when writes are disabled.

    Raises:
        WriteAccessError: If the server is running in read-only mode.
    """

    if not writes_allowed():
        raise WriteAccessError(WRITE_BLOCKED_MESSAGE)
