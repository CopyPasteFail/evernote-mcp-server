"""Evernote OAuth 1.0a bootstrap flow for first-time token acquisition."""

from __future__ import annotations

import os
import subprocess  # nosec B404
import threading
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from shutil import which
from typing import Callable
from urllib.parse import parse_qs, urlparse

from requests_oauthlib import OAuth1Session

from evernote_mcp.evernote.auth_storage import AuthStorageError, persist_access_token

EVERNOTE_PRODUCTION_OAUTH_REQUEST_TOKEN_URL = "https://www.evernote.com/oauth"  # nosec B105
EVERNOTE_PRODUCTION_OAUTH_AUTHORIZE_URL = "https://www.evernote.com/OAuth.action"
EVERNOTE_PRODUCTION_OAUTH_ACCESS_TOKEN_URL = "https://www.evernote.com/oauth"  # nosec B105

EVERNOTE_SANDBOX_OAUTH_REQUEST_TOKEN_URL = "https://sandbox.evernote.com/oauth"  # nosec B105
EVERNOTE_SANDBOX_OAUTH_AUTHORIZE_URL = "https://sandbox.evernote.com/OAuth.action"
EVERNOTE_SANDBOX_OAUTH_ACCESS_TOKEN_URL = "https://sandbox.evernote.com/oauth"  # nosec B105

DEFAULT_CALLBACK_HOST = "127.0.0.1"
DEFAULT_CALLBACK_PORT = 0
DEFAULT_CALLBACK_PATH = "/callback"
DEFAULT_AUTH_TIMEOUT_SECONDS = 180


class OAuthFlowError(RuntimeError):
    """Raised when OAuth bootstrap cannot complete successfully."""


@dataclass(frozen=True)
class OAuthEndpoints:
    """OAuth endpoint URLs for either Evernote production or sandbox."""

    request_token_url: str
    authorize_url: str
    access_token_url: str


@dataclass(frozen=True)
class OAuthCallbackPayload:
    """Parsed OAuth callback query values received from the local HTTP callback."""

    oauth_token: str
    oauth_verifier: str


@dataclass(frozen=True)
class OAuthBootstrapResult:
    """Result object returned after successful OAuth bootstrap completion."""

    token_file_path: Path
    sandbox: bool


class OAuthCallbackHttpServer(HTTPServer):
    """Local callback server that captures exactly one OAuth callback payload.

    This server stores callback values and signals a thread event so the CLI can
    continue the OAuth flow as soon as the browser callback is received.
    """

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        callback_path: str,
    ):
        super().__init__(server_address, handler_class)
        self.callback_path = callback_path
        self.callback_event = threading.Event()
        self.callback_payload: OAuthCallbackPayload | None = None


class OAuthCallbackRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler that accepts the OAuth redirect callback only."""

    server: OAuthCallbackHttpServer

    def do_GET(self) -> None:  # noqa: N802
        """Handle Evernote OAuth callback query and release waiting flow thread.

        Inputs:
            HTTP GET request expected at `/callback` with `oauth_token` and
            `oauth_verifier` query parameters.

        Outputs:
            Returns a short success/failure HTML response to the browser and stores
            callback values in the shared server instance when valid.
        """

        parsed_url = urlparse(self.path)
        if parsed_url.path != self.server.callback_path:
            self._write_html_response(status_code=404, html_body="<h1>Not Found</h1>")
            return

        query_parameters = parse_qs(parsed_url.query)
        oauth_token = _extract_single_query_value(query_parameters, "oauth_token")
        oauth_verifier = _extract_single_query_value(query_parameters, "oauth_verifier")

        if not oauth_token or not oauth_verifier:
            self._write_html_response(
                status_code=400,
                html_body="<h1>Authorization failed</h1><p>Missing callback parameters.</p>",
            )
            return

        self.server.callback_payload = OAuthCallbackPayload(
            oauth_token=oauth_token,
            oauth_verifier=oauth_verifier,
        )
        self.server.callback_event.set()
        self._write_html_response(
            status_code=200,
            html_body=(
                "<h1>Authorization complete</h1>"
                "<p>You can close this tab and return to the terminal.</p>"
            ),
        )

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        """Silence default request logs to keep CLI output clean and secret-safe."""

        return

    def _write_html_response(self, status_code: int, html_body: str) -> None:
        """Write a minimal HTML response for OAuth callback interactions."""

        encoded_body = html_body.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded_body)))
        self.end_headers()
        self.wfile.write(encoded_body)


class OAuthCallbackListener:
    """Context manager that owns the callback HTTP server lifecycle.

    It binds on a configurable host/port, starts serving in a background thread,
    and guarantees clean shutdown on exit.
    """

    def __init__(
        self,
        callback_host: str = DEFAULT_CALLBACK_HOST,
        callback_port: int = DEFAULT_CALLBACK_PORT,
        callback_path: str = DEFAULT_CALLBACK_PATH,
        explicit_callback_url: str | None = None,
    ) -> None:
        self._callback_host = callback_host
        self._callback_port = callback_port
        self._callback_path = callback_path
        self._explicit_callback_url = explicit_callback_url
        self._http_server: OAuthCallbackHttpServer | None = None
        self._server_thread: threading.Thread | None = None

    def __enter__(self) -> OAuthCallbackListener:
        """Start the callback HTTP server and return the listener instance."""

        self._http_server = OAuthCallbackHttpServer(
            server_address=(self._callback_host, self._callback_port),
            handler_class=OAuthCallbackRequestHandler,
            callback_path=self._callback_path,
        )
        self._server_thread = threading.Thread(
            target=self._http_server.serve_forever,
            kwargs={"poll_interval": 0.2},
            daemon=True,
        )
        self._server_thread.start()
        return self

    def __exit__(self, exception_type: object, exception_value: object, traceback: object) -> None:
        """Stop and close the callback HTTP server regardless of flow outcome."""

        if self._http_server is not None:
            self._http_server.shutdown()
            self._http_server.server_close()

        if self._server_thread is not None:
            self._server_thread.join(timeout=1.0)

    @property
    def callback_url(self) -> str:
        """Return the callback URL passed to Evernote request-token step."""

        if self._explicit_callback_url:
            return self._explicit_callback_url

        if self._http_server is None:
            raise RuntimeError("OAuth callback listener is not started.")

        callback_port = self._http_server.server_address[1]
        return f"http://{self._callback_host}:{callback_port}{self._callback_path}"

    def wait_for_callback(self, timeout_seconds: int) -> OAuthCallbackPayload:
        """Wait for callback payload until timeout.

        Args:
            timeout_seconds: Maximum wait time before failing the flow.

        Returns:
            Parsed callback payload containing token and verifier.

        Raises:
            OAuthFlowError: If callback is not received before timeout or payload is missing.
        """

        if self._http_server is None:
            raise RuntimeError("OAuth callback listener is not started.")

        callback_arrived = self._http_server.callback_event.wait(timeout=timeout_seconds)
        if not callback_arrived:
            raise OAuthFlowError(
                "Timed out waiting for OAuth callback. "
                "Try running `python -m evernote_mcp auth` again."
            )

        callback_payload = self._http_server.callback_payload
        if callback_payload is None:
            raise OAuthFlowError("OAuth callback did not include required verifier values.")

        return callback_payload


def resolve_oauth_endpoints(sandbox: bool) -> OAuthEndpoints:
    """Resolve OAuth endpoint URLs based on sandbox toggle.

    Args:
        sandbox: Whether OAuth should run against sandbox endpoints.

    Returns:
        Endpoint triple for request-token, authorize, and access-token steps.
    """

    if sandbox:
        return OAuthEndpoints(
            request_token_url=EVERNOTE_SANDBOX_OAUTH_REQUEST_TOKEN_URL,
            authorize_url=EVERNOTE_SANDBOX_OAUTH_AUTHORIZE_URL,
            access_token_url=EVERNOTE_SANDBOX_OAUTH_ACCESS_TOKEN_URL,
        )

    return OAuthEndpoints(
        request_token_url=EVERNOTE_PRODUCTION_OAUTH_REQUEST_TOKEN_URL,
        authorize_url=EVERNOTE_PRODUCTION_OAUTH_AUTHORIZE_URL,
        access_token_url=EVERNOTE_PRODUCTION_OAUTH_ACCESS_TOKEN_URL,
    )


def run_oauth_bootstrap(
    consumer_key: str,
    consumer_secret: str,
    sandbox: bool,
    listen_host: str = DEFAULT_CALLBACK_HOST,
    listen_port: int = DEFAULT_CALLBACK_PORT,
    callback_url: str | None = None,
    timeout_seconds: int = DEFAULT_AUTH_TIMEOUT_SECONDS,
    oauth_session_factory: Callable[..., OAuth1Session] = OAuth1Session,
    callback_listener_factory: Callable[[], OAuthCallbackListener] | None = None,
    authorization_url_opener: Callable[[str], bool] | None = None,
    token_persister: Callable[[str, bool], Path] = persist_access_token,
) -> OAuthBootstrapResult:
    """Execute full OAuth 1.0a bootstrap and persist resulting access token.

    Args:
        consumer_key: Evernote OAuth consumer key issued by Evernote support.
        consumer_secret: Evernote OAuth consumer secret issued by Evernote support.
        sandbox: Whether to use sandbox OAuth endpoints.
        listen_host: Host/IP for temporary local callback listener bind.
        listen_port: Port for temporary callback listener bind (`0` means random free port).
        callback_url: Optional explicit callback URL sent to Evernote.
        timeout_seconds: Max wait for local callback verifier.
        oauth_session_factory: Injectable OAuth session constructor for tests.
        callback_listener_factory: Injectable callback listener constructor for tests.
        authorization_url_opener: Optional injectable browser-opening function.
        token_persister: Injectable token persistence function.

    Returns:
        `OAuthBootstrapResult` with saved token file path and sandbox metadata.

    Raises:
        OAuthFlowError: If any OAuth step fails or returns malformed payload.

    Security:
        Token values are never printed. Only file path and non-secret status details
        are emitted to stdout.
    """

    resolved_authorization_url_opener = authorization_url_opener or open_authorization_url
    oauth_endpoints = resolve_oauth_endpoints(sandbox=sandbox)
    resolved_callback_listener_factory = callback_listener_factory or (
        lambda: OAuthCallbackListener(
            callback_host=listen_host,
            callback_port=listen_port,
            callback_path=DEFAULT_CALLBACK_PATH,
            explicit_callback_url=callback_url,
        )
    )

    with resolved_callback_listener_factory() as callback_listener:
        oauth_request_session = oauth_session_factory(
            client_key=consumer_key,
            client_secret=consumer_secret,
            callback_uri=callback_listener.callback_url,
        )
        request_token_payload = _fetch_request_token(
            oauth_request_session=oauth_request_session,
            request_token_url=oauth_endpoints.request_token_url,
        )

        request_oauth_token = _require_oauth_payload_field(
            request_token_payload,
            "oauth_token",
            "request token",
        )
        request_oauth_token_secret = _require_oauth_payload_field(
            request_token_payload,
            "oauth_token_secret",
            "request token",
        )

        authorization_url = oauth_request_session.authorization_url(oauth_endpoints.authorize_url)
        browser_opened = resolved_authorization_url_opener(authorization_url)
        if not browser_opened:
            print("Browser auto-open failed. Open this URL manually:")
        else:
            print("Opened browser for Evernote authorization.")
        print(authorization_url)

        callback_payload = callback_listener.wait_for_callback(timeout_seconds=timeout_seconds)
        if callback_payload.oauth_token != request_oauth_token:
            raise OAuthFlowError(
                "OAuth callback token did not match the request token. "
                "Run the auth flow again to get a fresh authorization URL."
            )

    oauth_access_session = oauth_session_factory(
        client_key=consumer_key,
        client_secret=consumer_secret,
        resource_owner_key=request_oauth_token,
        resource_owner_secret=request_oauth_token_secret,
        verifier=callback_payload.oauth_verifier,
    )
    access_token_payload = _fetch_access_token(
        oauth_access_session=oauth_access_session,
        access_token_url=oauth_endpoints.access_token_url,
    )
    access_token = _require_oauth_payload_field(
        access_token_payload,
        "oauth_token",
        "access token",
    )

    try:
        token_file_path = token_persister(access_token, sandbox)
    except AuthStorageError as auth_storage_error:
        raise OAuthFlowError(
            "OAuth succeeded but the token file could not be written. "
            "If using Docker with a named volume, initialize volume ownership once "
            "as root before running auth; alternatively use a writable host bind mount."
        ) from auth_storage_error

    return OAuthBootstrapResult(token_file_path=token_file_path, sandbox=sandbox)


def open_authorization_url(authorization_url: str) -> bool:
    """Attempt to open the authorization URL in a browser.

    Args:
        authorization_url: Fully qualified OAuth authorization URL.

    Returns:
        True when a browser launch command appears successful, otherwise False.

    Behavior:
        In WSL environments, attempts `powershell.exe Start-Process` first.
        Then tries `xdg-open` when available, and finally Python's
        `webbrowser.open` implementation.
    """

    if _open_authorization_url_via_wsl_powershell(authorization_url):
        return True

    xdg_open_path = which("xdg-open")
    if xdg_open_path:
        try:
            completed_process = subprocess.run(  # nosec B603
                [xdg_open_path, authorization_url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if completed_process.returncode == 0:
                return True
        except OSError:
            pass

    try:
        return bool(webbrowser.open(authorization_url, new=2, autoraise=True))
    except webbrowser.Error:
        return False


def _open_authorization_url_via_wsl_powershell(authorization_url: str) -> bool:
    """Attempt to open URL through Windows shell when running inside WSL.

    Args:
        authorization_url: Fully qualified OAuth authorization URL.

    Returns:
        True when `powershell.exe` launch appears successful, otherwise False.
    """

    wsl_distribution_name = os.environ.get("WSL_DISTRO_NAME", "").strip()
    if not wsl_distribution_name:
        return False

    powershell_path = which("powershell.exe")
    if not powershell_path:
        return False

    try:
        completed_process = subprocess.run(  # nosec B603
            [
                powershell_path,
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "Start-Process",
                authorization_url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return False

    return completed_process.returncode == 0


def _fetch_request_token(oauth_request_session: OAuth1Session, request_token_url: str) -> dict[str, str]:
    """Fetch and validate the OAuth request token response payload."""

    try:
        return oauth_request_session.fetch_request_token(request_token_url)
    except Exception as error:  # pragma: no cover - exercised via injected tests
        raise OAuthFlowError(
            "Failed to fetch Evernote OAuth request token. "
            "Check consumer credentials and network access."
        ) from error


def _fetch_access_token(oauth_access_session: OAuth1Session, access_token_url: str) -> dict[str, str]:
    """Fetch and validate the OAuth access token response payload."""

    try:
        return oauth_access_session.fetch_access_token(access_token_url)
    except Exception as error:  # pragma: no cover - exercised via injected tests
        raise OAuthFlowError(
            "Failed to exchange verifier for Evernote access token. "
            "Run the auth flow again."
        ) from error


def _require_oauth_payload_field(
    oauth_payload: dict[str, str],
    field_name: str,
    payload_label: str,
) -> str:
    """Extract and validate a required non-empty field from OAuth payload data."""

    field_value = oauth_payload.get(field_name, "").strip()
    if not field_value:
        raise OAuthFlowError(
            f"Evernote OAuth {payload_label} response did not include '{field_name}'."
        )
    return field_value


def _extract_single_query_value(
    query_parameters: dict[str, list[str]],
    field_name: str,
) -> str:
    """Return one normalized query-string value or an empty string when absent."""

    raw_values = query_parameters.get(field_name, [])
    if not raw_values:
        return ""
    return raw_values[0].strip()
