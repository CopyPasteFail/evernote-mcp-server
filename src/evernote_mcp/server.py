"""MCP server construction and tool registration."""

from __future__ import annotations

from fastmcp import FastMCP

from evernote_mcp.core.config import AppConfig, load_config_from_environment
from evernote_mcp.core.logging import configure_application_logging
from evernote_mcp.core.policies import set_read_only_mode
from evernote_mcp.evernote.client import EvernoteGateway
from evernote_mcp.tools.notebooks import register_notebook_tools
from evernote_mcp.tools.read_notes import register_read_note_tools
from evernote_mcp.tools.write_notes import register_write_note_tools


def build_mcp_server(
    app_config: AppConfig | None = None,
    evernote_gateway: EvernoteGateway | None = None,
) -> FastMCP:
    """Construct and configure the FastMCP server with all Evernote tools.

    Args:
        app_config: Optional pre-loaded config, primarily for testing.
        evernote_gateway: Optional injected Evernote gateway dependency.

    Returns:
        Fully configured FastMCP server with read and write tools registered.

    Concurrency:
        Tool registration is performed once during startup and is process-local.
    """

    resolved_config = app_config or load_config_from_environment()
    configure_application_logging(resolved_config.log_level)
    set_read_only_mode(resolved_config.read_only)

    resolved_evernote_gateway = evernote_gateway or EvernoteGateway(
        authentication_token=resolved_config.evernote_token,
        is_sandbox=resolved_config.evernote_sandbox,
    )

    mcp_server = FastMCP("evernote-mcp-server")
    register_notebook_tools(mcp_server, resolved_evernote_gateway)
    register_read_note_tools(mcp_server, resolved_evernote_gateway)
    register_write_note_tools(mcp_server, resolved_evernote_gateway)

    return mcp_server
