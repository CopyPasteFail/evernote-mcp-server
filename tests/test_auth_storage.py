"""Unit tests for persisted OAuth token storage behavior."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from evernote_mcp.evernote.auth_storage import (
    AuthStorageError,
    get_token_file_path,
    load_saved_access_token,
    persist_access_token,
)


def test_get_token_file_path_uses_xdg_config_home_when_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Ensure token path resolves under `XDG_CONFIG_HOME` when provided."""

    xdg_config_home_directory = tmp_path / "xdg-config-home"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config_home_directory))

    assert get_token_file_path() == (
        xdg_config_home_directory / "evernote-mcp-server" / "token.json"
    )


def test_persist_access_token_writes_expected_json_structure(tmp_path: Path) -> None:
    """Ensure persisted token JSON includes required fields and values."""

    created_at = datetime(2026, 3, 5, 12, 0, 0, tzinfo=UTC)

    written_token_file_path = persist_access_token(
        access_token="access-token-value",
        sandbox=True,
        home_directory=tmp_path,
        created_at=created_at,
    )

    assert written_token_file_path == get_token_file_path(home_directory=tmp_path)

    token_document = json.loads(written_token_file_path.read_text(encoding="utf-8"))
    assert token_document == {
        "access_token": "access-token-value",
        "created_at": created_at.isoformat(),
        "sandbox": True,
    }


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not stable on Windows")
def test_persist_access_token_uses_restricted_file_permissions(tmp_path: Path) -> None:
    """Ensure token file permissions are restricted to owner read/write."""

    written_token_file_path = persist_access_token(
        access_token="access-token-value",
        sandbox=False,
        home_directory=tmp_path,
    )

    file_mode = written_token_file_path.stat().st_mode & 0o777
    assert file_mode == 0o600


def test_load_saved_access_token_returns_none_when_token_file_missing(tmp_path: Path) -> None:
    """Ensure missing token file is treated as absent credentials, not an error."""

    assert load_saved_access_token(home_directory=tmp_path) is None


def test_load_saved_access_token_reads_previously_persisted_token(tmp_path: Path) -> None:
    """Ensure saved token payload can be loaded back into structured object."""

    persist_access_token(
        access_token="persisted-access-token",
        sandbox=False,
        home_directory=tmp_path,
    )

    loaded_token = load_saved_access_token(home_directory=tmp_path)

    assert loaded_token is not None
    assert loaded_token.access_token == "persisted-access-token"
    assert loaded_token.sandbox is False


def test_load_saved_access_token_raises_for_invalid_json(tmp_path: Path) -> None:
    """Ensure malformed token files fail with actionable storage context."""

    token_file_path = get_token_file_path(home_directory=tmp_path)
    token_file_path.parent.mkdir(parents=True, exist_ok=True)
    token_file_path.write_text("not-json", encoding="utf-8")

    with pytest.raises(AuthStorageError, match="not valid JSON"):
        load_saved_access_token(home_directory=tmp_path)
