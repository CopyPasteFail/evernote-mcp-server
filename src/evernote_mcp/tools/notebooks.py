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
        """List notebooks available to the authenticated Evernote account.

        Use first:
            Use before `create_note` or `move_note` when you need a target
            notebook GUID.
            Also use when you need to map `get_note_metadata.notebookGuid` to a
            human-readable notebook name before deciding a move.

        Returns keys:
            List of notebook objects. Each item usually includes `guid`, `name`,
            `defaultNotebook`, `serviceCreated`, `serviceUpdated`, and `stack`.
            Use `notebooks[i].guid` as `notebook_guid` or
            `destination_notebook_guid` in write tools, and compare with
            note `notebookGuid` values from note read tools.

        Fails when:
            Raises `EvernoteApiError` if notebook listing fails or the upstream
            Evernote request cannot be completed.
        """

        return evernote_gateway.list_notebooks()
