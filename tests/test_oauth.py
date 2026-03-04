"""Unit tests for OAuth bootstrap flow orchestration with mocked dependencies."""

from __future__ import annotations

from pathlib import Path
import sys
import types
from typing import Callable
from urllib.parse import urlparse

import pytest

try:
    __import__("requests_oauthlib")
except ModuleNotFoundError:  # pragma: no cover - local test env compatibility
    requests_oauthlib_module = types.ModuleType("requests_oauthlib")
    requests_oauthlib_module.OAuth1Session = object  # type: ignore[attr-defined]
    sys.modules["requests_oauthlib"] = requests_oauthlib_module

from evernote_mcp.evernote import oauth as oauth_module
from evernote_mcp.evernote.auth_storage import AuthStorageError
from evernote_mcp.evernote.oauth import (
    OAuthBootstrapResult,
    OAuthCallbackListener,
    OAuthCallbackPayload,
    OAuthEndpoints,
    OAuthFlowError,
    OAuthSessionProtocol,
    open_authorization_url,
    resolve_oauth_endpoints,
    run_oauth_bootstrap,
)


class _StubCallbackListener(OAuthCallbackListener):
    """Minimal callback listener stub used for deterministic OAuth tests."""

    def __init__(self, callback_payload: OAuthCallbackPayload) -> None:
        self._callback_url = "http://127.0.0.1:41235/callback"
        self._callback_payload = callback_payload
        self.received_timeout_seconds: int | None = None

    @property
    def callback_url(self) -> str:
        return self._callback_url

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

    def authorization_url(
        self,
        url: str,
        request_token: str | None = None,
        **kwargs: object,
    ) -> str:
        del request_token, kwargs
        self.authorization_base_url = url
        return f"{url}?oauth_token=request-oauth-token"

    def fetch_request_token(
        self,
        url: str,
        realm: str | None = None,
        **request_kwargs: object,
    ) -> dict[str, str]:
        del realm, request_kwargs
        self.request_token_url = url
        return {
            "oauth_token": "request-oauth-token",
            "oauth_token_secret": "request-secret",
        }

    def fetch_access_token(
        self,
        url: str,
        verifier: str | None = None,
        **request_kwargs: object,
    ) -> dict[str, str]:
        del url, verifier, request_kwargs
        raise AssertionError("Request-token session should not exchange access tokens.")


class _StubAccessTokenSession:
    """Session stub for the access-token exchange step."""

    def __init__(self) -> None:
        self.access_token_url: str | None = None

    def authorization_url(
        self,
        url: str,
        request_token: str | None = None,
        **kwargs: object,
    ) -> str:
        del url, request_token, kwargs
        raise AssertionError("Access-token session should not build authorization URLs.")

    def fetch_request_token(
        self,
        url: str,
        realm: str | None = None,
        **request_kwargs: object,
    ) -> dict[str, str]:
        del url, realm, request_kwargs
        raise AssertionError("Access-token session should not request OAuth request tokens.")

    def fetch_access_token(
        self,
        url: str,
        verifier: str | None = None,
        **request_kwargs: object,
    ) -> dict[str, str]:
        del verifier, request_kwargs
        self.access_token_url = url
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

    def build_oauth_session(**kwargs: str) -> OAuthSessionProtocol:
        created_session_kwargs.append(kwargs)
        if "resource_owner_key" in kwargs:
            return access_session
        return request_session

    def build_callback_listener() -> OAuthCallbackListener:
        return callback_listener

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
        callback_listener_factory=build_callback_listener,
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

    def build_oauth_session(**kwargs: str) -> OAuthSessionProtocol:
        del kwargs
        return request_session

    def build_callback_listener() -> OAuthCallbackListener:
        return callback_listener

    def open_url(_authorization_url: str) -> bool:
        return True

    def persist_token(_access_token: str, _sandbox: bool) -> Path:
        return Path("/tmp/test-token.json")

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
            callback_listener_factory=build_callback_listener,
            authorization_url_opener=open_url,
            token_persister=persist_token,
        )


def test_run_oauth_bootstrap_wraps_token_persistence_failure_with_actionable_error() -> None:
    """Ensure token write failures are surfaced as actionable OAuth flow errors."""

    request_session = _StubRequestTokenSession()
    access_session = _StubAccessTokenSession()
    callback_listener = _StubCallbackListener(
        OAuthCallbackPayload(
            oauth_token="request-oauth-token",
            oauth_verifier="oauth-verifier",
        )
    )

    def build_oauth_session(**kwargs: str) -> OAuthSessionProtocol:
        if "resource_owner_key" in kwargs:
            return access_session
        return request_session

    def build_callback_listener() -> OAuthCallbackListener:
        return callback_listener

    def open_url(_authorization_url: str) -> bool:
        return True

    def fail_token_persist(_access_token: str, _sandbox: bool) -> Path:
        raise AuthStorageError("Failed writing saved token file at /tmp/token.json.")

    with pytest.raises(OAuthFlowError, match="token file could not be written"):
        run_oauth_bootstrap(
            consumer_key="consumer-key",
            consumer_secret="consumer-secret",
            sandbox=False,
            oauth_session_factory=build_oauth_session,
            callback_listener_factory=build_callback_listener,
            authorization_url_opener=open_url,
            token_persister=fail_token_persist,
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

    class _CompletedProcessStub:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode

    def resolve_command(command_name: str) -> str | None:
        if command_name == "powershell.exe":
            return "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
        return None

    def run_subprocess(
        arguments: list[str],
        stdout: object,
        stderr: object,
        check: bool,
    ) -> _CompletedProcessStub:
        del stdout, stderr, check
        subprocess_invocations.append(arguments)
        return _CompletedProcessStub(returncode=0)

    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    monkeypatch.setattr(oauth_module, "which", resolve_command)
    monkeypatch.setattr(oauth_module.subprocess, "run", run_subprocess)

    def fail_if_called(*args: object, **kwargs: object) -> bool:
        raise AssertionError("webbrowser.open should not be called when powershell succeeds")

    monkeypatch.setattr(oauth_module.webbrowser, "open", fail_if_called)

    assert open_authorization_url("https://example.com/oauth") is True
    assert subprocess_invocations[0][0].endswith("powershell.exe")


def test_callback_listener_returns_explicit_callback_url_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure listener can bind one address while returning an explicit callback URL."""

    bound_server_addresses: list[tuple[str, int]] = []

    class _FakeHttpServer:
        def __init__(
            self,
            server_address: tuple[str, int],
            handler_class: type[object],
            callback_path: str,
        ) -> None:
            del handler_class
            self.server_address = (
                server_address[0],
                41555 if server_address[1] == 0 else server_address[1],
            )
            self.callback_path = callback_path
            bound_server_addresses.append(self.server_address)

        def serve_forever(self, poll_interval: float = 0.2) -> None:
            del poll_interval

        def shutdown(self) -> None:
            return

        def server_close(self) -> None:
            return

    class _FakeThread:
        def __init__(
            self,
            target: Callable[..., object],
            kwargs: dict[str, float],
            daemon: bool,
        ) -> None:
            del target, kwargs, daemon

        def start(self) -> None:
            return

        def join(self, timeout: float = 1.0) -> None:
            del timeout
            return

    monkeypatch.setattr(oauth_module, "OAuthCallbackHttpServer", _FakeHttpServer)
    monkeypatch.setattr(oauth_module.threading, "Thread", _FakeThread)

    explicit_callback_url = "http://127.0.0.1:8765/callback"
    with OAuthCallbackListener(
        callback_host="0.0.0.0",
        callback_port=0,
        explicit_callback_url=explicit_callback_url,
    ) as callback_listener:
        assert callback_listener.callback_url == explicit_callback_url
        assert bound_server_addresses[0][0] == "0.0.0.0"
        assert bound_server_addresses[0][1] > 0


def test_callback_listener_derives_callback_url_from_random_bound_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure random-port binding still returns a callback URL with actual port."""

    class _FakeHttpServer:
        def __init__(
            self,
            server_address: tuple[str, int],
            handler_class: type[object],
            callback_path: str,
        ) -> None:
            del handler_class
            self.server_address = (
                server_address[0],
                40111 if server_address[1] == 0 else server_address[1],
            )
            self.callback_path = callback_path

        def serve_forever(self, poll_interval: float = 0.2) -> None:
            del poll_interval

        def shutdown(self) -> None:
            return

        def server_close(self) -> None:
            return

    class _FakeThread:
        def __init__(
            self,
            target: Callable[..., object],
            kwargs: dict[str, float],
            daemon: bool,
        ) -> None:
            del target, kwargs, daemon

        def start(self) -> None:
            return

        def join(self, timeout: float = 1.0) -> None:
            del timeout
            return

    monkeypatch.setattr(oauth_module, "OAuthCallbackHttpServer", _FakeHttpServer)
    monkeypatch.setattr(oauth_module.threading, "Thread", _FakeThread)

    with OAuthCallbackListener(
        callback_host="127.0.0.1",
        callback_port=0,
    ) as callback_listener:
        parsed_callback_url = urlparse(callback_listener.callback_url)

        assert parsed_callback_url.scheme == "http"
        assert parsed_callback_url.hostname == "127.0.0.1"
        assert parsed_callback_url.path == "/callback"
        assert parsed_callback_url.port == 40111
