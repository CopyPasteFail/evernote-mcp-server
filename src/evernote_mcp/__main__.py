"""CLI entrypoint for launching the Evernote MCP server."""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

from evernote_mcp.core.config import ConfigurationError, load_config_from_environment

SUPPORTED_TRANSPORT_CHOICES = ("stdio", "sse")


def build_argument_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser for server startup.

    Returns:
        Configured argument parser instance.
    """

    argument_parser = argparse.ArgumentParser(description="Evernote MCP server")
    argument_parser.add_argument(
        "--transport",
        default="stdio",
        choices=SUPPORTED_TRANSPORT_CHOICES,
        help="Transport to use (v0.1 supports stdio only).",
    )
    return argument_parser


def run_server_with_transport(transport_name: str) -> None:
    """Build the server and run it using the selected transport.

    Args:
        transport_name: Transport mode selected from CLI options.

    Raises:
        NotImplementedError: When requesting SSE transport in v0.1.
        ConfigurationError: When required environment config is invalid.
    """

    if transport_name == "sse":
        from evernote_mcp.transport.sse import run_sse_transport

        run_sse_transport()
        return

    from evernote_mcp.server import build_mcp_server
    from evernote_mcp.transport.stdio import run_stdio_transport

    app_config = load_config_from_environment()
    mcp_server = build_mcp_server(app_config=app_config)
    run_stdio_transport(mcp_server)


def format_safe_fatal_error_message(unhandled_error: Exception) -> str:
    """Format a fatal error message without exposing raw exception text.

    Args:
        unhandled_error: Uncaught exception raised during startup or runtime.

    Returns:
        Human-readable message with exception type only.

    Security:
        The original exception message is not included because upstream libraries
        may embed sensitive values such as auth tokens or note content.
    """

    exception_type_name = type(unhandled_error).__name__
    return (
        "Fatal error: unexpected "
        f"{exception_type_name}. Check application logs for additional context."
    )


def load_environment_from_dotenv() -> None:
    """Load `.env` values into the process environment when present.

    Behavior:
        Reads `.env` from the current working directory if it exists.
        Existing environment variables are preserved and not overridden.
        Missing `.env` files are ignored without raising an error.

    Security:
        No environment values are logged by this function.
    """

    load_dotenv(override=False)


def main() -> int:
    """Run the Evernote MCP CLI process.

    Returns:
        Integer process exit code.
    """

    load_environment_from_dotenv()
    argument_parser = build_argument_parser()
    parsed_arguments = argument_parser.parse_args()

    try:
        run_server_with_transport(parsed_arguments.transport)
    except ConfigurationError as configuration_error:
        print(f"Configuration error: {configuration_error}", file=sys.stderr)
        return 2
    except NotImplementedError as not_implemented_error:
        print(not_implemented_error, file=sys.stderr)
        return 3
    except Exception as unhandled_error:  # pragma: no cover
        print(format_safe_fatal_error_message(unhandled_error), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
