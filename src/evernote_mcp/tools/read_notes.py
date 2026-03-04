"""MCP tool registration for read-only note operations."""

from __future__ import annotations

from fastmcp import FastMCP

from evernote_mcp.evernote.client import EvernoteGateway


def register_read_note_tools(mcp_server: FastMCP, evernote_gateway: EvernoteGateway) -> None:
    """Register read-focused note tools on the provided MCP server.

    Args:
        mcp_server: FastMCP server where tools are registered.
        evernote_gateway: Evernote service wrapper used by tool handlers.
    """

    @mcp_server.tool(name="search_notes")
    def search_notes(search_query: str, offset: int = 0, max_results: int = 20) -> dict:
        """Search note metadata with Evernote query syntax."""

        return evernote_gateway.search_notes(
            search_query=search_query,
            offset=offset,
            max_results=max_results,
        )

    @mcp_server.tool(name="get_note")
    def get_note(note_guid: str) -> dict:
        """Fetch full note details, including ENML content, by note GUID."""

        return evernote_gateway.get_note(note_guid=note_guid)

    @mcp_server.tool(name="get_note_metadata")
    def get_note_metadata(note_guid: str) -> dict:
        """Fetch note metadata by note GUID without full content payload."""

        return evernote_gateway.get_note_metadata(note_guid=note_guid)
