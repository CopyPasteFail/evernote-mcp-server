"""Stdio transport runner for the MCP server."""

from __future__ import annotations

from evernote_mcp.core.mcp_server_protocol import MCPServerProtocol


def run_stdio_transport(mcp_server: MCPServerProtocol) -> None:
    """Run the MCP server over stdio transport.

    Args:
        mcp_server: Configured MCP server instance.
    """

    try:
        mcp_server.run(transport="stdio")
    except TypeError:
        mcp_server.run()
