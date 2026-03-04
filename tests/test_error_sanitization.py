"""Security-focused tests that prevent secret leakage in error messages."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from evernote_mcp import __main__ as main_module

pytest.importorskip("evernote")

from evernote_mcp.evernote.client import EvernoteApiError, EvernoteGateway


def test_main_returns_sanitized_fatal_message_without_raw_exception_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ensure CLI fatal errors do not expose potentially sensitive exception messages."""

    def raise_runtime_error_with_secret(_: str) -> None:
        raise RuntimeError("token sk-should-not-appear")

    monkeypatch.setattr(main_module, "run_server_with_transport", raise_runtime_error_with_secret)
    monkeypatch.setattr(main_module.sys, "argv", ["evernote_mcp"])

    exit_code = main_module.main()
    captured_output = capsys.readouterr()

    assert exit_code == 1
    assert "RuntimeError" in captured_output.err
    assert "sk-should-not-appear" not in captured_output.err


def test_call_note_store_method_raises_sanitized_error_without_raw_exception_text() -> None:
    """Ensure wrapped Evernote API errors avoid exposing raw upstream message contents."""

    def list_notebooks_method(_: str) -> None:
        raise ValueError("api token should-not-appear")

    gateway = EvernoteGateway.__new__(EvernoteGateway)
    gateway._authentication_token = "test-token"
    gateway._note_store = SimpleNamespace(listNotebooks=list_notebooks_method)

    with pytest.raises(EvernoteApiError) as raised_error:
        gateway._call_note_store_method("listNotebooks")

    assert "ValueError" in str(raised_error.value)
    assert "should-not-appear" not in str(raised_error.value)
