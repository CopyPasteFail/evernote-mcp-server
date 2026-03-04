"""Unit tests for write access policy helpers."""

from __future__ import annotations

import pytest

from evernote_mcp.core.policies import (
    WriteAccessError,
    require_writes_enabled,
    set_read_only_mode,
    writes_allowed,
)


def test_writes_allowed_returns_false_when_read_only_mode_enabled() -> None:
    set_read_only_mode(True)

    assert writes_allowed() is False


def test_writes_allowed_returns_true_when_read_only_mode_disabled() -> None:
    set_read_only_mode(False)

    assert writes_allowed() is True


def test_require_writes_enabled_raises_meaningful_error_when_disabled() -> None:
    set_read_only_mode(True)

    with pytest.raises(WriteAccessError, match="Set READ_ONLY=false"):
        require_writes_enabled()


def test_require_writes_enabled_succeeds_when_writes_allowed() -> None:
    set_read_only_mode(False)

    require_writes_enabled()
