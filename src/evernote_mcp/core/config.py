"""Application configuration loading and validation utilities."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

EVERNOTE_TOKEN_ENV_NAME = "EVERNOTE_TOKEN"  # nosec B105
EVERNOTE_SANDBOX_ENV_NAME = "EVERNOTE_SANDBOX"
READ_ONLY_ENV_NAME = "READ_ONLY"
LOG_LEVEL_ENV_NAME = "LOG_LEVEL"

EVERNOTE_SANDBOX_DEFAULT_VALUE = "false"
READ_ONLY_DEFAULT_VALUE = "true"
DEFAULT_LOG_LEVEL = "INFO"

TRUE_BOOLEAN_VALUES = {"1", "true", "yes", "on"}
FALSE_BOOLEAN_VALUES = {"0", "false", "no", "off"}


class ConfigurationError(ValueError):
    """Raised when required environment configuration is missing or invalid."""


@dataclass(frozen=True)
class AppConfig:
    """Configuration values consumed by the Evernote MCP server.

    Attributes:
        evernote_token: Authentication token used for Evernote API requests.
        evernote_sandbox: Whether to use Evernote's sandbox API endpoints.
        read_only: Whether write operations are blocked by policy.
        log_level: Logging verbosity level for the process.
    """

    evernote_token: str
    evernote_sandbox: bool
    read_only: bool
    log_level: str


def parse_boolean_environment_value(raw_value: str, variable_name: str) -> bool:
    """Parse a human-friendly environment variable value into a boolean.

    Args:
        raw_value: Raw string value from the environment.
        variable_name: Name of the environment variable for error context.

    Returns:
        Parsed boolean value.

    Raises:
        ConfigurationError: If the value does not map to a supported boolean literal.
    """

    normalized_value = raw_value.strip().lower()
    if normalized_value in TRUE_BOOLEAN_VALUES:
        return True
    if normalized_value in FALSE_BOOLEAN_VALUES:
        return False

    raise ConfigurationError(
        f"Invalid value for {variable_name}: '{raw_value}'. "
        "Use one of: true, false, 1, 0, yes, no, on, off."
    )


def resolve_read_only_mode(environment: Mapping[str, str] | None = None) -> bool:
    """Resolve read-only mode from environment with a secure default.

    Args:
        environment: Optional environment mapping for deterministic testing.

    Returns:
        True when write operations should be blocked, False otherwise.

    Edge cases:
        Missing READ_ONLY defaults to True so writes are disabled by default.
    """

    source_environment = os.environ if environment is None else environment
    raw_read_only_value = source_environment.get(READ_ONLY_ENV_NAME, READ_ONLY_DEFAULT_VALUE)
    return parse_boolean_environment_value(raw_read_only_value, READ_ONLY_ENV_NAME)


def load_config_from_environment(environment: Mapping[str, str] | None = None) -> AppConfig:
    """Load and validate application configuration from environment variables.

    Args:
        environment: Optional environment mapping. Defaults to process environment.

    Returns:
        Parsed and validated AppConfig object.

    Raises:
        ConfigurationError: If required values are missing or invalid.

    Security notes:
        The token value is validated but never logged by this function.
    """

    source_environment = os.environ if environment is None else environment

    evernote_token = source_environment.get(EVERNOTE_TOKEN_ENV_NAME, "").strip()
    if not evernote_token:
        raise ConfigurationError(
            f"Missing required environment variable: {EVERNOTE_TOKEN_ENV_NAME}."
        )

    raw_evernote_sandbox = source_environment.get(
        EVERNOTE_SANDBOX_ENV_NAME,
        EVERNOTE_SANDBOX_DEFAULT_VALUE,
    )
    evernote_sandbox = parse_boolean_environment_value(
        raw_evernote_sandbox,
        EVERNOTE_SANDBOX_ENV_NAME,
    )
    read_only_mode = resolve_read_only_mode(source_environment)
    raw_log_level = source_environment.get(LOG_LEVEL_ENV_NAME, DEFAULT_LOG_LEVEL)
    normalized_log_level = raw_log_level.strip().upper() or DEFAULT_LOG_LEVEL

    return AppConfig(
        evernote_token=evernote_token,
        evernote_sandbox=evernote_sandbox,
        read_only=read_only_mode,
        log_level=normalized_log_level,
    )
