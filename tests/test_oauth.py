"""Unit tests for OAuth bootstrap flow orchestration with mocked dependencies."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from evernote_mcp.evernote import oauth as oauth_module
from evernote_mcp.evernote.oauth import (
    OAuthBootstrapResult,
    OAuthCallbackPayload,
    OAuthEndpoints,
    OAuthFlowError,
    open_authorization_url,
    resolve_oauth_endpoints,
    run_oauth_bootstrap,
)


class _StubCallbackListener:
    """Minimal callback listener stub used for deterministic OAuth tests."""

    def __init__(self, callback_payload: OAuthCallbackPayload) -> None:
        self.callback_url = "http://127.0.0.1:41235/callback"
        self._callback_payload = callback_payload
        self.received_timeout_seconds: int | None = None

    def __enter__(self) -> _StubCallbackListener:
        return self

    def __exit__(self, exception_type: object, exception_value: object, traceback: object) -> None:
        return None

    def wait_for_callback(self, timeout_seconds: int) -> OAuthCallbackPayload:
        self.received_timeout_seconds = timeout_seconds
        return self._callback_payload


class _StubRequestTokenSession:
    """Session stub for the request-token and authorization-url steps."""

    def __init__(self) -> None:
        self.request_token_url: str | None = None
        self.authorization_base_url: str | None = None

    def fetch_request_token(self, request_token_url: str) -> dict[str, str]:
        self.request_token_url = request_token_url
        return {
            "oauth_token": "request-oauth-token",
            "oauth_token_secret": "request-secret",
        }

    def authorization_url(self, authorize_url: str) -> str:
        self.authorization_base_url = authorize_url
        return f"{authorize_url}?oauth_token=request-oauth-token"


class _StubAccessTokenSession:
    """Session stub for the access-token exchange step."""

    def __init__(self) -> None:
        self.access_token_url: str | None = None

    def fetch_access_token(self, access_token_url: str) -> dict[str, str]:
        self.access_token_url = access_token_url
        return {"oauth_token": "final-access-token"}


def test_run_oauth_bootstrap_completes_and_persists_token() -> None:
    """Ensure successful flow orchestrates request, callback, exchange, and persist steps."""

    created_session_kwargs: list[dict[str, str]] = []
    request_session = _StubRequestTokenSession()
    access_session = _StubAccessTokenSession()
    captured_authorization_urls: list[str] = []
    persisted_payloads: list[tuple[str, bool]] = []
    callback_listener = _StubCallbackListener(
        OAuthCallbackPayload(
            oauth_token="request-oauth-token",
            oauth_verifier="oauth-verifier",
        )
    )

    def build_oauth_session(**kwargs: str) -> _StubRequestTokenSession | _StubAccessTokenSession:
        created_session_kwargs.append(kwargs)
        if "resource_owner_key" in kwargs:
            return access_session
        return request_session

    def open_authorization_url(authorization_url: str) -> bool:
        captured_authorization_urls.append(authorization_url)
        return True

    def persist_token(access_token: str, sandbox: bool) -> Path:
        persisted_payloads.append((access_token, sandbox))
        return Path("/tmp/test-token.json")

    oauth_bootstrap_result = run_oauth_bootstrap(
        consumer_key="consumer-key",
        consumer_secret="consumer-secret",
        sandbox=False,
        timeout_seconds=15,
        oauth_session_factory=build_oauth_session,
        callback_listener_factory=lambda: callback_listener,
        authorization_url_opener=open_authorization_url,
        token_persister=persist_token,
    )

    assert isinstance(oauth_bootstrap_result, OAuthBootstrapResult)
    assert oauth_bootstrap_result.token_file_path == Path("/tmp/test-token.json")
    assert oauth_bootstrap_result.sandbox is False

    assert request_session.request_token_url == "https://www.evernote.com/oauth"
    assert request_session.authorization_base_url == "https://www.evernote.com/OAuth.action"
    assert access_session.access_token_url == "https://www.evernote.com/oauth"

    assert callback_listener.received_timeout_seconds == 15
    assert captured_authorization_urls == [
        "https://www.evernote.com/OAuth.action?oauth_token=request-oauth-token"
    ]
    assert persisted_payloads == [("final-access-token", False)]

    assert created_session_kwargs[0] == {
        "client_key": "consumer-key",
        "client_secret": "consumer-secret",
        "callback_uri": "http://127.0.0.1:41235/callback",
    }
    assert created_session_kwargs[1] == {
        "client_key": "consumer-key",
        "client_secret": "consumer-secret",
        "resource_owner_key": "request-oauth-token",
        "resource_owner_secret": "request-secret",
        "verifier": "oauth-verifier",
    }


def test_run_oauth_bootstrap_fails_when_callback_token_mismatches_request_token() -> None:
    """Ensure callback/request token mismatch fails fast before access-token exchange."""

    request_session = _StubRequestTokenSession()

    def build_oauth_session(**kwargs: str) -> _StubRequestTokenSession:
        return request_session

    callback_listener = _StubCallbackListener(
        OAuthCallbackPayload(
            oauth_token="different-request-token",
            oauth_verifier="oauth-verifier",
        )
    )

    with pytest.raises(OAuthFlowError, match="did not match"):
        run_oauth_bootstrap(
            consumer_key="consumer-key",
            consumer_secret="consumer-secret",
            sandbox=False,
            oauth_session_factory=build_oauth_session,
            callback_listener_factory=lambda: callback_listener,
            authorization_url_opener=lambda _authorization_url: True,
            token_persister=lambda _access_token, _sandbox: Path("/tmp/test-token.json"),
        )


def test_resolve_oauth_endpoints_returns_sandbox_endpoints_when_enabled() -> None:
    """Ensure sandbox mode resolves all OAuth URLs to sandbox host."""

    resolved_endpoints = resolve_oauth_endpoints(sandbox=True)

    assert resolved_endpoints == OAuthEndpoints(
        request_token_url="https://sandbox.evernote.com/oauth",
        authorize_url="https://sandbox.evernote.com/OAuth.action",
        access_token_url="https://sandbox.evernote.com/oauth",
    )


def test_open_authorization_url_prefers_wsl_powershell_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure WSL mode attempts powershell opener before other browser strategies."""

    subprocess_invocations: list[list[str]] = []

    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    monkeypatch.setattr(
        oauth_module,
        "which",
        lambda command_name: (
            "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
            if command_name == "powershell.exe"
            else None
        ),
    )
    monkeypatch.setattr(
        oauth_module.subprocess,
        "run",
        lambda arguments, stdout, stderr, check: (
            subprocess_invocations.append(arguments) or SimpleNamespace(returncode=0)
        ),
    )

    def fail_if_called(*args: object, **kwargs: object) -> bool:
        raise AssertionError("webbrowser.open should not be called when powershell succeeds")

    monkeypatch.setattr(oauth_module.webbrowser, "open", fail_if_called)

    assert open_authorization_url("https://example.com/oauth") is True
    assert subprocess_invocations[0][0].endswith("powershell.exe")
