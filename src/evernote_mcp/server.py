"""MCP server construction and tool registration."""

from __future__ import annotations

from importlib import import_module
from typing import cast

from evernote_mcp.core.config import AppConfig, load_config_from_environment
from evernote_mcp.core.logging import configure_application_logging
from evernote_mcp.core.mcp_server_protocol import MCPServerProtocol
from evernote_mcp.core.policies import set_read_only_mode
from evernote_mcp.evernote.client import EvernoteGateway
from evernote_mcp.tools.notebooks import register_notebook_tools
from evernote_mcp.tools.read_notes import register_read_note_tools
from evernote_mcp.tools.write_notes import register_write_note_tools

FASTMCP_MODULE_NAME = "fastmcp"
FASTMCP_CLASS_NAME = "FastMCP"
MCP_SERVER_NAME = "evernote-mcp-server"


def _build_fastmcp_server(server_name: str) -> MCPServerProtocol:
    """Create a FastMCP server instance without static import dependency coupling.

    Args:
        server_name: Human-readable server identifier passed to FastMCP.

    Returns:
        MCP server object that satisfies `MCPServerProtocol`.

    Raises:
        RuntimeError: If `fastmcp.FastMCP` cannot be loaded or instantiated.

    Concurrency:
        This function is process-local and side-effect-free other than importing
        the target module once through Python's import cache.
    """

    try:
        fastmcp_module = import_module(FASTMCP_MODULE_NAME)
        fastmcp_class = getattr(fastmcp_module, FASTMCP_CLASS_NAME)
        fastmcp_instance = fastmcp_class(server_name)
    except (ImportError, AttributeError, TypeError) as error:
        raise RuntimeError(
            "Unable to construct MCP server. Ensure the `fastmcp` dependency is installed."
        ) from error

    return cast(MCPServerProtocol, fastmcp_instance)


def build_mcp_server(
    app_config: AppConfig | None = None,
    evernote_gateway: EvernoteGateway | None = None,
) -> MCPServerProtocol:
    """Construct and configure the FastMCP server with all Evernote tools.

    Args:
        app_config: Optional pre-loaded config, primarily for testing.
        evernote_gateway: Optional injected Evernote gateway dependency.

    Returns:
        Fully configured MCP server with read and write tools registered.

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

    mcp_server = _build_fastmcp_server(MCP_SERVER_NAME)
    register_notebook_tools(mcp_server, resolved_evernote_gateway)
    register_read_note_tools(mcp_server, resolved_evernote_gateway)
    register_write_note_tools(mcp_server, resolved_evernote_gateway)

    return mcp_server
