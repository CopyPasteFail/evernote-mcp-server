"""Token storage utilities for Evernote OAuth bootstrap credentials."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

CONFIG_DIRECTORY_RELATIVE_PATH = Path(".config") / "evernote-mcp-server"
XDG_CONFIG_HOME_ENVIRONMENT_VARIABLE = "XDG_CONFIG_HOME"
TOKEN_FILE_NAME = "token.json"  # nosec B105
TOKEN_FILE_PERMISSIONS = 0o600
CONFIG_DIRECTORY_PERMISSIONS = 0o700


class AuthStorageError(RuntimeError):
    """Raised when reading or writing the persisted OAuth token fails."""


@dataclass(frozen=True)
class SavedAccessToken:
    """Represents the persisted Evernote access token payload.

    Attributes:
        access_token: Evernote OAuth access token (EDAM authentication token).
        created_at: ISO-8601 UTC timestamp indicating when the token was persisted.
        sandbox: Whether the token was minted against Evernote sandbox endpoints.
    """

    access_token: str
    created_at: str
    sandbox: bool


def get_config_directory_path(home_directory: Path | None = None) -> Path:
    """Return the Evernote MCP config directory path.

    Args:
        home_directory: Optional home directory override for deterministic tests.

    Returns:
        Absolute path to `$XDG_CONFIG_HOME/evernote-mcp-server` when
        `XDG_CONFIG_HOME` is set to a non-empty value; otherwise
        `~/.config/evernote-mcp-server`.
    """

    if home_directory is not None:
        return home_directory / CONFIG_DIRECTORY_RELATIVE_PATH

    xdg_config_home = _get_xdg_config_home_path()
    if xdg_config_home is not None:
        return xdg_config_home / CONFIG_DIRECTORY_RELATIVE_PATH.name

    return Path.home() / CONFIG_DIRECTORY_RELATIVE_PATH


def get_token_file_path(home_directory: Path | None = None) -> Path:
    """Return the absolute path of the persisted token JSON file.

    Args:
        home_directory: Optional home directory override for deterministic tests.

    Returns:
        Absolute path to the token file.
    """

    return get_config_directory_path(home_directory=home_directory) / TOKEN_FILE_NAME


def load_saved_access_token(home_directory: Path | None = None) -> SavedAccessToken | None:
    """Read the persisted access token from disk if present.

    Args:
        home_directory: Optional home directory override for deterministic tests.

    Returns:
        Parsed `SavedAccessToken` when the file exists and is valid; otherwise `None`
        when no persisted token file is found.

    Raises:
        AuthStorageError: If token JSON is malformed, missing required fields, or unreadable.

    Security:
        This function never logs or prints token values.
    """

    token_file_path = get_token_file_path(home_directory=home_directory)
    if not token_file_path.exists():
        return None

    try:
        token_document = json.loads(token_file_path.read_text(encoding="utf-8"))
    except OSError as os_error:
        raise AuthStorageError(
            f"Failed reading saved token file at {token_file_path}."
        ) from os_error
    except json.JSONDecodeError as json_error:
        raise AuthStorageError(
            f"Saved token file at {token_file_path} is not valid JSON."
        ) from json_error

    return _parse_saved_token_document(token_document, token_file_path)


def persist_access_token(
    access_token: str,
    sandbox: bool,
    home_directory: Path | None = None,
    created_at: datetime | None = None,
) -> Path:
    """Persist a newly acquired access token to a secured JSON file.

    Args:
        access_token: OAuth access token to store.
        sandbox: Whether the token belongs to Evernote sandbox.
        home_directory: Optional home directory override for deterministic tests.
        created_at: Optional timestamp override used by tests.

    Returns:
        Absolute path to the token file written to disk.

    Raises:
        AuthStorageError: If writing the token file fails.

    Security:
        The token file is written with permission mode `600` and no token values are
        emitted to stdout/stderr.
    """

    token_file_path = get_token_file_path(home_directory=home_directory)
    token_file_path.parent.mkdir(
        parents=True,
        exist_ok=True,
        mode=CONFIG_DIRECTORY_PERMISSIONS,
    )
    _set_directory_permissions(token_file_path.parent)

    resolved_created_at = created_at or datetime.now(timezone.utc)
    token_document: dict[str, str | bool] = {
        "access_token": access_token,
        "created_at": resolved_created_at.isoformat(),
        "sandbox": sandbox,
    }

    temporary_file_path = token_file_path.with_suffix(".tmp")
    try:
        with os.fdopen(
            os.open(
                temporary_file_path,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                TOKEN_FILE_PERMISSIONS,
            ),
            "w",
            encoding="utf-8",
        ) as temporary_file:
            json.dump(token_document, temporary_file, indent=2)
            temporary_file.write("\n")

        os.replace(temporary_file_path, token_file_path)
        os.chmod(token_file_path, TOKEN_FILE_PERMISSIONS)
    except OSError as os_error:
        raise AuthStorageError(
            f"Failed writing saved token file at {token_file_path}."
        ) from os_error
    finally:
        if temporary_file_path.exists():
            temporary_file_path.unlink(missing_ok=True)

    return token_file_path


def _parse_saved_token_document(
    token_document: Any,
    token_file_path: Path,
) -> SavedAccessToken:
    """Validate and normalize the token JSON document.

    Args:
        token_document: Parsed JSON payload loaded from disk.
        token_file_path: Source path for error context.

    Returns:
        Normalized `SavedAccessToken` instance.

    Raises:
        AuthStorageError: If required fields are missing or invalid.
    """

    if not isinstance(token_document, dict):
        raise AuthStorageError(
            f"Saved token file at {token_file_path} must contain a JSON object."
        )

    token_document_dictionary = cast(dict[str, object], token_document)
    raw_access_token = token_document_dictionary.get("access_token", "")
    raw_created_at = token_document_dictionary.get("created_at", "")
    raw_sandbox = token_document_dictionary.get("sandbox", False)

    if not isinstance(raw_access_token, str) or not raw_access_token.strip():
        raise AuthStorageError(
            f"Saved token file at {token_file_path} is missing a valid access_token field."
        )
    if not isinstance(raw_created_at, str) or not raw_created_at.strip():
        raise AuthStorageError(
            f"Saved token file at {token_file_path} is missing a valid created_at field."
        )
    if not isinstance(raw_sandbox, bool):
        raise AuthStorageError(
            f"Saved token file at {token_file_path} has a non-boolean sandbox field."
        )

    return SavedAccessToken(
        access_token=raw_access_token.strip(),
        created_at=raw_created_at.strip(),
        sandbox=raw_sandbox,
    )


def _set_directory_permissions(config_directory_path: Path) -> None:
    """Best-effort hardening for config directory permissions.

    Args:
        config_directory_path: Directory containing the persisted token file.

    Behavior:
        Attempts to set mode `700` on POSIX systems. Permission updates are skipped
        on unsupported platforms without failing the auth flow.
    """

    try:
        os.chmod(config_directory_path, CONFIG_DIRECTORY_PERMISSIONS)
    except OSError:
        return


def _get_xdg_config_home_path() -> Path | None:
    """Return `XDG_CONFIG_HOME` when set to a non-empty value.

    Returns:
        Expanded path from `XDG_CONFIG_HOME` or `None` when unset or empty.
    """

    xdg_config_home = os.getenv(XDG_CONFIG_HOME_ENVIRONMENT_VARIABLE)
    if xdg_config_home is None:
        return None

    normalized_xdg_config_home = xdg_config_home.strip()
    if not normalized_xdg_config_home:
        return None

    return Path(normalized_xdg_config_home).expanduser()
