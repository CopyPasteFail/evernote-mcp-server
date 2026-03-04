"""Unit tests for auth CLI argument parsing and command routing behavior."""

from __future__ import annotations

import importlib.util
import sys
import types
from typing import Any, cast

import pytest

if importlib.util.find_spec("requests_oauthlib") is None:  # pragma: no cover - local test env compatibility
    requests_oauthlib_module = types.ModuleType("requests_oauthlib")
    casted_requests_oauthlib_module = cast(Any, requests_oauthlib_module)
    casted_requests_oauthlib_module.OAuth1Session = object
    sys.modules["requests_oauthlib"] = requests_oauthlib_module

from evernote_mcp import __main__ as main_module


def test_build_argument_parser_uses_auth_defaults() -> None:
    """Ensure auth CLI options resolve to expected defaults when omitted."""

    argument_parser = main_module.build_argument_parser()
    parsed_arguments = argument_parser.parse_args(["auth"])

    assert parsed_arguments.command == "auth"
    assert parsed_arguments.listen_host == "127.0.0.1"
    assert parsed_arguments.listen_port == 0
    assert parsed_arguments.callback_url is None


def test_build_argument_parser_accepts_custom_auth_values() -> None:
    """Ensure auth CLI options parse custom host/port/callback settings."""

    argument_parser = main_module.build_argument_parser()
    parsed_arguments = argument_parser.parse_args(
        [
            "auth",
            "--listen-host",
            "0.0.0.0",
            "--listen-port",
            "8765",
            "--callback-url",
            "http://127.0.0.1:8765/callback",
        ]
    )

    assert parsed_arguments.command == "auth"
    assert parsed_arguments.listen_host == "0.0.0.0"
    assert parsed_arguments.listen_port == 8765
    assert parsed_arguments.callback_url == "http://127.0.0.1:8765/callback"


def test_build_argument_parser_rejects_invalid_callback_url() -> None:
    """Ensure callback URL validation rejects non-HTTP or non-absolute values."""

    argument_parser = main_module.build_argument_parser()

    try:
        argument_parser.parse_args(
            [
                "auth",
                "--callback-url",
                "https://127.0.0.1:8765/callback",
            ]
        )
    except SystemExit as parse_error:
        assert parse_error.code == 2
    else:  # pragma: no cover - defensive branch
        raise AssertionError("Expected parse error for invalid callback URL.")


def test_build_argument_parser_rejects_invalid_listen_port() -> None:
    """Ensure listener port validation rejects values outside legal port range."""

    argument_parser = main_module.build_argument_parser()

    try:
        argument_parser.parse_args(["auth", "--listen-port", "70000"])
    except SystemExit as parse_error:
        assert parse_error.code == 2
    else:  # pragma: no cover - defensive branch
        raise AssertionError("Expected parse error for invalid listen port.")


def test_main_ignores_auth_flags_for_serve_command(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ensure serve mode ignores auth-only flags and routes to server startup."""

    observed_transports: list[str] = []

    def run_server_with_transport(transport_name: str) -> None:
        observed_transports.append(transport_name)

    def fail_if_auth_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("run_auth_command should not run for serve command.")

    monkeypatch.setattr(main_module, "run_server_with_transport", run_server_with_transport)
    monkeypatch.setattr(main_module, "run_auth_command", fail_if_auth_called)
    monkeypatch.setattr(
        main_module.sys,
        "argv",
        [
            "evernote_mcp",
            "serve",
            "--transport",
            "stdio",
            "--listen-host",
            "0.0.0.0",
            "--listen-port",
            "8765",
            "--callback-url",
            "http://127.0.0.1:8765/callback",
        ],
    )

    exit_code = main_module.main()
    captured_output = capsys.readouterr()

    assert exit_code == 0
    assert observed_transports == ["stdio"]
    assert captured_output.err == ""
