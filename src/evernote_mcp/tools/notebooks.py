"""MCP tool registration for notebook-oriented operations."""

from __future__ import annotations

from typing import Any

from evernote_mcp.core.mcp_server_protocol import MCPServerProtocol
from evernote_mcp.evernote.client import EvernoteGateway


def register_notebook_tools(
    mcp_server: MCPServerProtocol,
    evernote_gateway: EvernoteGateway,
) -> None:
    """Register notebook read tools on the provided MCP server instance.

    Args:
        mcp_server: MCP server where tools are registered.
        evernote_gateway: Evernote service wrapper used by tool handlers.
    """

    def list_notebooks() -> list[dict[str, Any]]:
        """List notebooks available to the authenticated account."""

        return evernote_gateway.list_notebooks()

    mcp_server.tool(name="list_notebooks")(list_notebooks)
