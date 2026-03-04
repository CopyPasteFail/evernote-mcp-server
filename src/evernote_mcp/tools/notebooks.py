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

        Returns:
            List of notebook dictionaries. Each item commonly includes:
                `guid`: notebook GUID used by `create_note` and `move_note`.
                `name`: human-readable notebook name.
                `defaultNotebook`: whether Evernote treats this as the default.
                `serviceCreated`, `serviceUpdated`: Evernote timestamps when
                    available.
                `stack`: notebook stack name when configured.
            Evernote may include additional notebook metadata fields.

        Composition:
            Use this tool before `create_note` when the note must be created in a
            specific notebook.
            Use this tool before `move_note` to resolve the destination
            `notebook_guid`.

        Failure modes:
            Raises `EvernoteApiError` if notebook listing fails or the upstream
            Evernote request cannot be completed.
        """

        return evernote_gateway.list_notebooks()
