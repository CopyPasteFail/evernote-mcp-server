"""MCP tool registration for read-only note operations."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from evernote_mcp.core.mcp_server_protocol import MCPServerProtocol
from evernote_mcp.evernote.client import EvernoteGateway

DEFAULT_SEARCH_OFFSET = 0
DEFAULT_SEARCH_MAX_RESULTS = 20

SearchQuery = Annotated[
    str,
    Field(
        description=(
            "Evernote search expression. Supports keywords and operators such as "
            "intitle:, notebook:, tag:, and created:."
        )
    ),
]
SearchOffset = Annotated[
    int,
    Field(
        ge=0,
        description="Zero-based result offset.",
    ),
]
SearchMaxResults = Annotated[
    int,
    Field(
        ge=1,
        description="Maximum matches to return.",
    ),
]
NoteGuid = Annotated[
    str,
    Field(
        min_length=1,
        description="Evernote note GUID.",
    ),
]


def register_read_note_tools(
    mcp_server: MCPServerProtocol,
    evernote_gateway: EvernoteGateway,
) -> None:
    """Register read-focused note tools on the provided MCP server.

    Args:
        mcp_server: MCP server where tools are registered.
        evernote_gateway: Evernote service wrapper used by tool handlers.
    """

    def search_notes(
        search_query: SearchQuery,
        offset: SearchOffset = DEFAULT_SEARCH_OFFSET,
        max_results: SearchMaxResults = DEFAULT_SEARCH_MAX_RESULTS,
    ) -> dict[str, Any]:
        """Search note metadata using Evernote search syntax.

        Returns matching note IDs and metadata, not note content.
        """

        return evernote_gateway.search_notes(
            search_query=search_query,
            offset=offset,
            max_results=max_results,
        )

    def get_note(note_guid: NoteGuid) -> dict[str, Any]:
        """Get a note including its full ENML body.

        Use only when note content or structure is needed. Use get_note_metadata
        when title, notebook, tags, or timestamps are enough.
        """

        return evernote_gateway.get_note(note_guid=note_guid)

    def get_note_metadata(note_guid: NoteGuid) -> dict[str, Any]:
        """Get a note's title, notebook, tags, and timestamps without its ENML body."""

        return evernote_gateway.get_note_metadata(note_guid=note_guid)

    mcp_server.tool(name="search_notes")(search_notes)
    mcp_server.tool(name="get_note")(get_note)
    mcp_server.tool(name="get_note_metadata")(get_note_metadata)
