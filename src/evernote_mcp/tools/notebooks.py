"""MCP tool registration for notebook-oriented operations."""

from __future__ import annotations

from fastmcp import FastMCP

from evernote_mcp.evernote.client import EvernoteGateway


def register_notebook_tools(mcp_server: FastMCP, evernote_gateway: EvernoteGateway) -> None:
    """Register notebook read tools on the provided MCP server instance.

    Args:
        mcp_server: FastMCP server where tools are registered.
        evernote_gateway: Evernote service wrapper used by tool handlers.
    """

    @mcp_server.tool(name="list_notebooks")
    def list_notebooks() -> list[dict]:
        """List notebooks visible to the authenticated Evernote account."""

        return evernote_gateway.list_notebooks()
