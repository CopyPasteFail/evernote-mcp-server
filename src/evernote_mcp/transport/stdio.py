"""Stdio transport runner for the MCP server."""

from __future__ import annotations

from fastmcp import FastMCP


def run_stdio_transport(mcp_server: FastMCP) -> None:
    """Run the MCP server over stdio transport.

    Args:
        mcp_server: Configured FastMCP server instance.
    """

    try:
        mcp_server.run(transport="stdio")
    except TypeError:
        mcp_server.run()
