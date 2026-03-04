"""MCP tool registration for write-capable note operations."""

from __future__ import annotations

from fastmcp import FastMCP

from evernote_mcp.core.policies import require_writes_enabled
from evernote_mcp.evernote.client import EvernoteGateway


def _enforce_write_policy() -> None:
    """Apply the shared write gate before any mutating Evernote action."""

    require_writes_enabled()


def register_write_note_tools(mcp_server: FastMCP, evernote_gateway: EvernoteGateway) -> None:
    """Register write note tools while enforcing the shared write policy.

    Args:
        mcp_server: FastMCP server where tools are registered.
        evernote_gateway: Evernote service wrapper used by tool handlers.
    """

    @mcp_server.tool(name="append_to_note_plaintext")
    def append_to_note_plaintext(note_guid: str, plaintext_content: str) -> dict:
        """Append plaintext content to an existing note body."""

        _enforce_write_policy()
        return evernote_gateway.append_to_note_plaintext(
            note_guid=note_guid,
            plaintext_content=plaintext_content,
        )

    @mcp_server.tool(name="set_note_title")
    def set_note_title(note_guid: str, new_title: str) -> dict:
        """Update the title of an existing note."""

        _enforce_write_policy()
        return evernote_gateway.set_note_title(note_guid=note_guid, new_title=new_title)

    @mcp_server.tool(name="add_tags_by_name")
    def add_tags_by_name(note_guid: str, tag_names: list[str]) -> dict:
        """Attach tags to a note by tag names, creating missing tags when required."""

        _enforce_write_policy()
        return evernote_gateway.add_tags_by_name(note_guid=note_guid, tag_names=tag_names)

    @mcp_server.tool(name="move_note")
    def move_note(note_guid: str, destination_notebook_guid: str) -> dict:
        """Move a note to a different notebook."""

        _enforce_write_policy()
        return evernote_gateway.move_note(
            note_guid=note_guid,
            destination_notebook_guid=destination_notebook_guid,
        )

    @mcp_server.tool(name="create_note")
    def create_note(
        title: str,
        plaintext_body: str,
        notebook_guid: str | None = None,
        tag_names: list[str] | None = None,
    ) -> dict:
        """Create a new note with optional notebook and tag metadata."""

        _enforce_write_policy()
        return evernote_gateway.create_note(
            title=title,
            plaintext_body=plaintext_body,
            notebook_guid=notebook_guid,
            tag_names=tag_names,
        )
