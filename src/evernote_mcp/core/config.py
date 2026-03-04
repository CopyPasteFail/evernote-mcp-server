"""Application configuration loading and validation utilities."""

from __future__ import annotations

import os
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from typing import Mapping

from evernote_mcp.evernote.auth_storage import AuthStorageError, SavedAccessToken, load_saved_access_token

EVERNOTE_CONSUMER_KEY_ENV_NAME = "EVERNOTE_CONSUMER_KEY"
EVERNOTE_CONSUMER_SECRET_ENV_NAME = "EVERNOTE_CONSUMER_SECRET"  # nosec B105
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


@dataclass(frozen=True)
class OAuthBootstrapConfig:
    """Configuration required to run the OAuth bootstrap command.

    Attributes:
        consumer_key: Evernote OAuth consumer key.
        consumer_secret: Evernote OAuth consumer secret.
        sandbox: Whether to run OAuth against Evernote sandbox.
    """

    consumer_key: str
    consumer_secret: str
    sandbox: bool


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

    raw_evernote_sandbox = source_environment.get(
        EVERNOTE_SANDBOX_ENV_NAME,
        EVERNOTE_SANDBOX_DEFAULT_VALUE,
    )
    evernote_sandbox = parse_boolean_environment_value(
        raw_evernote_sandbox,
        EVERNOTE_SANDBOX_ENV_NAME,
    )
    evernote_token = resolve_evernote_authentication_token(
        evernote_sandbox=evernote_sandbox,
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


def load_oauth_bootstrap_config_from_environment(
    environment: Mapping[str, str] | None = None,
) -> OAuthBootstrapConfig:
    """Load and validate OAuth bootstrap inputs from environment variables.

    Args:
        environment: Optional environment mapping. Defaults to process environment.

    Returns:
        Parsed and validated OAuth bootstrap config.

    Raises:
        ConfigurationError: If consumer credentials are missing or sandbox value is invalid.
    """

    source_environment = os.environ if environment is None else environment

    consumer_key = source_environment.get(EVERNOTE_CONSUMER_KEY_ENV_NAME, "").strip()
    if not consumer_key:
        raise ConfigurationError(
            f"Missing required environment variable: {EVERNOTE_CONSUMER_KEY_ENV_NAME}."
        )

    consumer_secret = source_environment.get(EVERNOTE_CONSUMER_SECRET_ENV_NAME, "").strip()
    if not consumer_secret:
        raise ConfigurationError(
            f"Missing required environment variable: {EVERNOTE_CONSUMER_SECRET_ENV_NAME}."
        )

    raw_evernote_sandbox = source_environment.get(
        EVERNOTE_SANDBOX_ENV_NAME,
        EVERNOTE_SANDBOX_DEFAULT_VALUE,
    )
    evernote_sandbox = parse_boolean_environment_value(
        raw_evernote_sandbox,
        EVERNOTE_SANDBOX_ENV_NAME,
    )

    return OAuthBootstrapConfig(
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        sandbox=evernote_sandbox,
    )


def resolve_evernote_authentication_token(
    evernote_sandbox: bool,
    token_loader: Callable[[], SavedAccessToken | None] | None = None,
) -> str:
    """Resolve Evernote authentication token from persisted storage.

    Args:
        evernote_sandbox: Sandbox mode resolved for this runtime.
        token_loader: Optional injectable token-loader dependency for deterministic tests.

    Returns:
        Evernote authentication token string.

    Raises:
        ConfigurationError: If no token is available or storage read fails.

    Resolution:
        Persisted token from OAuth bootstrap storage.
    """

    resolved_token_loader = token_loader or load_saved_access_token

    try:
        saved_access_token = resolved_token_loader()
    except AuthStorageError as auth_storage_error:
        raise ConfigurationError(
            "Failed to read saved Evernote token. "
            "Run `python -m evernote_mcp auth` with EVERNOTE_CONSUMER_KEY and "
            "EVERNOTE_CONSUMER_SECRET set."
        ) from auth_storage_error

    if saved_access_token is None:
        raise ConfigurationError(
            "Missing Evernote authentication token. "
            "Run `python -m evernote_mcp auth` with EVERNOTE_CONSUMER_KEY and "
            "EVERNOTE_CONSUMER_SECRET set."
        )

    if saved_access_token.sandbox != evernote_sandbox:
        warnings.warn(
            "Saved Evernote token sandbox setting does not match EVERNOTE_SANDBOX. "
            f"saved_sandbox={saved_access_token.sandbox}, "
            f"runtime_sandbox={evernote_sandbox}.",
            stacklevel=2,
        )

    return saved_access_token.access_token
