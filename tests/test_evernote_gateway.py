"""Unit tests for Evernote gateway behavior with mocked Thrift clients."""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest

from evernote_mcp.evernote.client import EvernoteApiError, EvernoteGateway
from evernote_mcp.evernote.thrift_client import EvernoteThriftClient


def test_client_module_imports_without_oauth2() -> None:
    """Ensure gateway module import does not depend on the legacy oauth2 package."""

    imported_module = importlib.import_module("evernote_mcp.evernote.client")

    assert hasattr(imported_module, "EvernoteGateway")


def test_search_notes_calls_thrift_client_with_expected_arguments() -> None:
    """Ensure search parameters are forwarded to the Thrift client correctly."""

    mocked_thrift_client = SimpleNamespace(
        search_notes_metadata=Mock(return_value={"notes": []}),
    )
    gateway = EvernoteGateway(
        authentication_token="token",
        thrift_client=cast(EvernoteThriftClient, mocked_thrift_client),
    )

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
    gateway = EvernoteGateway(
        authentication_token="token",
        thrift_client=cast(EvernoteThriftClient, mocked_thrift_client),
    )

    serialized_note_metadata = gateway.get_note_metadata("note-guid")

    mocked_thrift_client.get_note_metadata.assert_called_once_with("note-guid")
    assert serialized_note_metadata["guid"] == "note-guid"


def test_delete_note_calls_thrift_client_and_returns_serialized_status() -> None:
    """Ensure note deletion forwards GUID and returns a stable status payload."""

    mocked_thrift_client = SimpleNamespace(
        delete_note=Mock(return_value=987654),
    )
    gateway = EvernoteGateway(
        authentication_token="token",
        thrift_client=cast(EvernoteThriftClient, mocked_thrift_client),
    )

    deletion_result = gateway.delete_note("note-guid")

    mocked_thrift_client.delete_note.assert_called_once_with("note-guid")
    assert deletion_result == {
        "guid": "note-guid",
        "deleted": True,
        "updateSequenceNum": 987654,
    }


def test_insert_plaintext_near_anchor_updates_note_with_usn_match() -> None:
    """Ensure rich note insertion preserves ENML and uses optimistic concurrency."""

    note = SimpleNamespace(
        guid="note-guid",
        title="Existing note",
        content=(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">'
            "<en-note><h1>Heading</h1><div>anchor block</div></en-note>"
        ),
        updateSequenceNum=123,
    )
    updated_note = SimpleNamespace(guid="note-guid", content="")
    mocked_thrift_client = SimpleNamespace(
        call_note_store_method=Mock(
            side_effect=[
                note,
                SimpleNamespace(updated=True, note=updated_note),
            ]
        ),
    )
    gateway = EvernoteGateway(
        authentication_token="token",
        thrift_client=cast(EvernoteThriftClient, mocked_thrift_client),
    )

    serialized_note = gateway.insert_plaintext_near_anchor(
        note_guid="note-guid",
        anchor_text="anchor block",
        plaintext_content="inserted <safe>",
        position="after",
        occurrence=1,
    )

    assert "inserted &lt;safe&gt;" in note.content
    mocked_thrift_client.call_note_store_method.assert_any_call(
        "getNote",
        "note-guid",
        True,
        False,
        False,
        False,
    )
    mocked_thrift_client.call_note_store_method.assert_any_call(
        "updateNoteIfUsnMatches",
        note,
    )
    assert serialized_note["guid"] == "note-guid"


def test_insert_plaintext_near_anchor_raises_when_usn_does_not_match() -> None:
    """Ensure concurrent edits are reported instead of overwritten."""

    note = SimpleNamespace(
        guid="note-guid",
        title="Existing note",
        content=(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">'
            "<en-note><div>anchor block</div></en-note>"
        ),
        updateSequenceNum=123,
    )
    mocked_thrift_client = SimpleNamespace(
        call_note_store_method=Mock(
            side_effect=[
                note,
                SimpleNamespace(updated=False, note=SimpleNamespace(guid="note-guid")),
            ]
        ),
    )
    gateway = EvernoteGateway(
        authentication_token="token",
        thrift_client=cast(EvernoteThriftClient, mocked_thrift_client),
    )

    with pytest.raises(EvernoteApiError, match="changed before update"):
        gateway.insert_plaintext_near_anchor(
            note_guid="note-guid",
            anchor_text="anchor block",
            plaintext_content="inserted",
        )
