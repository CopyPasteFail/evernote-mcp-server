"""Unit tests for Thrift transport lifecycle management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from evernote_mcp.evernote import thrift_client as thrift_client_module
from evernote_mcp.evernote.thrift_client import EvernoteThriftClient


@dataclass
class StubHttpTransport:
    """Simple HTTP transport test double that tracks lifecycle method calls."""

    service_url: str
    open_calls: int = 0
    close_calls: int = 0

    def open(self) -> None:
        """Record one open call."""

        self.open_calls += 1

    def close(self) -> None:
        """Record one close call."""

        self.close_calls += 1


def _install_transport_factory_stub(monkeypatch: pytest.MonkeyPatch) -> list[StubHttpTransport]:
    """Patch Thrift HTTP transport constructor with a deterministic in-memory stub.

    Args:
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        List populated with every created transport instance.
    """

    created_transports: list[StubHttpTransport] = []

    def build_stub_transport(service_url: str) -> StubHttpTransport:
        stub_transport = StubHttpTransport(service_url=service_url)
        created_transports.append(stub_transport)
        return stub_transport

    monkeypatch.setattr(thrift_client_module.THttpClient, "THttpClient", build_stub_transport)
    return created_transports


def test_call_note_store_method_opens_and_closes_transport_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure successful NoteStore calls open and close transport exactly once."""

    created_transports = _install_transport_factory_stub(monkeypatch)

    class StubNoteStoreClient:
        """Minimal NoteStore client test double used by this test case."""

        def __init__(self, protocol: Any) -> None:
            self._protocol = protocol

        def listNotebooks(self, authentication_token: str) -> list[str]:
            assert authentication_token == "test-token"
            return ["notebook-guid-1"]

    monkeypatch.setattr(thrift_client_module.NoteStore, "Client", StubNoteStoreClient)

    thrift_client = EvernoteThriftClient(
        authentication_token="test-token",
        note_store_url="https://example.com/edam/note/test-account",
    )

    notebook_guids = thrift_client.call_note_store_method("listNotebooks")

    assert notebook_guids == ["notebook-guid-1"]
    assert len(created_transports) == 1
    assert created_transports[0].open_calls == 1
    assert created_transports[0].close_calls == 1


def test_call_note_store_method_closes_transport_when_service_call_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure failing NoteStore calls still close transport in a finally block."""

    created_transports = _install_transport_factory_stub(monkeypatch)

    class StubFailingNoteStoreClient:
        """Minimal NoteStore client that raises from the requested API method."""

        def __init__(self, protocol: Any) -> None:
            self._protocol = protocol

        def listNotebooks(self, authentication_token: str) -> None:
            assert authentication_token == "test-token"
            raise RuntimeError("simulated-note-store-error")

    monkeypatch.setattr(thrift_client_module.NoteStore, "Client", StubFailingNoteStoreClient)

    thrift_client = EvernoteThriftClient(
        authentication_token="test-token",
        note_store_url="https://example.com/edam/note/test-account",
    )

    with pytest.raises(RuntimeError, match="simulated-note-store-error"):
        thrift_client.call_note_store_method("listNotebooks")

    assert len(created_transports) == 1
    assert created_transports[0].open_calls == 1
    assert created_transports[0].close_calls == 1
