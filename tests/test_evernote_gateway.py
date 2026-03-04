"""Unit tests for Evernote gateway behavior with mocked Thrift clients."""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import Mock

from evernote_mcp.evernote.client import EvernoteGateway


def test_client_module_imports_without_oauth2() -> None:
    """Ensure gateway module import does not depend on the legacy oauth2 package."""

    imported_module = importlib.import_module("evernote_mcp.evernote.client")

    assert hasattr(imported_module, "EvernoteGateway")


def test_search_notes_calls_thrift_client_with_expected_arguments() -> None:
    """Ensure search parameters are forwarded to the Thrift client correctly."""

    mocked_thrift_client = SimpleNamespace(
        search_notes_metadata=Mock(return_value={"notes": []}),
    )
    gateway = EvernoteGateway(authentication_token="token", thrift_client=mocked_thrift_client)

    gateway.search_notes(search_query="intitle:project", offset=3, max_results=10)

    mocked_thrift_client.search_notes_metadata.assert_called_once_with(
        search_query="intitle:project",
        offset=3,
        max_results=10,
    )


def test_get_note_metadata_calls_metadata_method_on_thrift_client() -> None:
    """Ensure metadata reads call the dedicated metadata method, not full note fetch."""

    mocked_thrift_client = SimpleNamespace(
        get_note_metadata=Mock(return_value=SimpleNamespace(guid="note-guid")),
    )
    gateway = EvernoteGateway(authentication_token="token", thrift_client=mocked_thrift_client)

    serialized_note_metadata = gateway.get_note_metadata("note-guid")

    mocked_thrift_client.get_note_metadata.assert_called_once_with("note-guid")
    assert serialized_note_metadata["guid"] == "note-guid"
