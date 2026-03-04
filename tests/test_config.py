"""Unit tests for configuration parsing behavior."""

from __future__ import annotations

import pytest

from evernote_mcp.core.config import ConfigurationError, load_config_from_environment


def test_load_config_from_environment_defaults_read_only_to_true() -> None:
    environment_mapping = {"EVERNOTE_TOKEN": "token-value"}

    loaded_config = load_config_from_environment(environment_mapping)

    assert loaded_config.evernote_token == "token-value"
    assert loaded_config.read_only is True
    assert loaded_config.log_level == "INFO"


def test_load_config_from_environment_accepts_read_only_false() -> None:
    environment_mapping = {
        "EVERNOTE_TOKEN": "token-value",
        "READ_ONLY": "false",
        "LOG_LEVEL": "debug",
    }

    loaded_config = load_config_from_environment(environment_mapping)

    assert loaded_config.read_only is False
    assert loaded_config.log_level == "DEBUG"


def test_load_config_from_environment_fails_when_token_missing() -> None:
    with pytest.raises(ConfigurationError, match="EVERNOTE_TOKEN"):
        load_config_from_environment({})


def test_load_config_from_environment_fails_for_invalid_read_only_value() -> None:
    environment_mapping = {
        "EVERNOTE_TOKEN": "token-value",
        "READ_ONLY": "maybe",
    }

    with pytest.raises(ConfigurationError, match="READ_ONLY"):
        load_config_from_environment(environment_mapping)
