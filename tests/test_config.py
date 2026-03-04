"""Unit tests for configuration parsing behavior."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from evernote_mcp.core.config import ConfigurationError, load_config_from_environment
from evernote_mcp.evernote.auth_storage import SavedAccessToken


def _build_saved_access_token(sandbox: bool = False) -> SavedAccessToken:
    """Build deterministic saved-token payload used by config tests."""

    return SavedAccessToken(
        access_token="saved-token",
        created_at=datetime.now(UTC).isoformat(),
        sandbox=sandbox,
    )


def test_load_config_from_environment_defaults_read_only_to_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure defaults resolve when only persisted token exists."""

    monkeypatch.setattr(
        "evernote_mcp.core.config.load_saved_access_token",
        lambda: _build_saved_access_token(sandbox=False),
    )

    loaded_config = load_config_from_environment({})

    assert loaded_config.evernote_token == "saved-token"
    assert loaded_config.evernote_sandbox is False
    assert loaded_config.read_only is True
    assert loaded_config.log_level == "INFO"


def test_load_config_from_environment_accepts_read_only_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure READ_ONLY=false is respected with persisted token auth."""

    monkeypatch.setattr(
        "evernote_mcp.core.config.load_saved_access_token",
        lambda: _build_saved_access_token(sandbox=False),
    )

    loaded_config = load_config_from_environment(
        {
            "READ_ONLY": "false",
            "LOG_LEVEL": "debug",
        }
    )

    assert loaded_config.read_only is False
    assert loaded_config.log_level == "DEBUG"


def test_load_config_from_environment_accepts_evernote_sandbox_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure sandbox mode can be enabled while using saved token auth."""

    monkeypatch.setattr(
        "evernote_mcp.core.config.load_saved_access_token",
        lambda: _build_saved_access_token(sandbox=True),
    )

    loaded_config = load_config_from_environment({"EVERNOTE_SANDBOX": "true"})

    assert loaded_config.evernote_sandbox is True


def test_load_config_from_environment_fails_when_saved_token_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure startup guidance is clear when no persisted token exists."""

    monkeypatch.setattr("evernote_mcp.core.config.load_saved_access_token", lambda: None)

    with pytest.raises(ConfigurationError, match="python -m evernote_mcp auth"):
        load_config_from_environment({})


def test_load_config_from_environment_fails_for_invalid_read_only_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure invalid READ_ONLY literals still fail with clear validation."""

    monkeypatch.setattr(
        "evernote_mcp.core.config.load_saved_access_token",
        lambda: _build_saved_access_token(sandbox=False),
    )

    with pytest.raises(ConfigurationError, match="READ_ONLY"):
        load_config_from_environment({"READ_ONLY": "maybe"})


def test_load_config_from_environment_fails_for_invalid_sandbox_value() -> None:
    """Ensure invalid EVERNOTE_SANDBOX literals fail before token resolution."""

    with pytest.raises(ConfigurationError, match="EVERNOTE_SANDBOX"):
        load_config_from_environment({"EVERNOTE_SANDBOX": "sometimes"})


def test_load_config_uses_saved_token_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure persisted token is used as runtime authentication token."""

    monkeypatch.setattr(
        "evernote_mcp.core.config.load_saved_access_token",
        lambda: _build_saved_access_token(sandbox=False),
    )

    loaded_config = load_config_from_environment({})

    assert loaded_config.evernote_token == "saved-token"
