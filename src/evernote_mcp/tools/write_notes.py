"""MCP tool registration for write-capable note operations."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from evernote_mcp.core.mcp_server_protocol import MCPServerProtocol
from evernote_mcp.core.policies import require_writes_enabled
from evernote_mcp.evernote.client import EvernoteGateway

NoteGuid = Annotated[
    str,
    Field(
        min_length=1,
        description="Evernote note GUID.",
    ),
]
PlaintextContent = Annotated[
    str,
    Field(
        description="Plain text content. Do not send ENML or HTML. Newlines are preserved."
    ),
]
NoteTitle = Annotated[
    str,
    Field(
        description="Human-readable note title.",
    ),
]
NotebookGuid = Annotated[
    str,
    Field(
        min_length=1,
        description="Evernote notebook GUID.",
    ),
]
TagNames = Annotated[
    list[str],
    Field(
        description="Tag names. Blank names are ignored; missing tags are created automatically."
    ),
]
OptionalNotebookGuid = Annotated[
    str | None,
    Field(
        description="Optional destination notebook GUID. Omit for Evernote's default notebook."
    ),
]
OptionalTagNames = Annotated[
    list[str] | None,
    Field(
        description="Optional tag names. Missing tags are created automatically."
    ),
]
AnchorText = Annotated[
    str,
    Field(
        min_length=1,
        description="Existing visible text that identifies the insertion location.",
    ),
]
InsertionPosition = Annotated[
    Literal["before", "after"],
    Field(
        description="Insert before or after the matching block.",
    ),
]
AnchorOccurrence = Annotated[
    int,
    Field(
        ge=1,
        description="One-based match number when the anchor appears more than once.",
    ),
]


def _enforce_write_policy() -> None:
    """Apply the shared write gate before any mutating Evernote action.

    Raises:
        WriteAccessError: If the server is running in read-only mode.
    """

    require_writes_enabled()


def register_write_note_tools(
    mcp_server: MCPServerProtocol,
    evernote_gateway: EvernoteGateway,
) -> None:
    """Register write note tools while enforcing the shared write policy.

    Args:
        mcp_server: MCP server where tools are registered.
        evernote_gateway: Evernote service wrapper used by tool handlers.
    """

    def append_to_note_plaintext(
        note_guid: NoteGuid,
        plaintext_content: PlaintextContent,
    ) -> dict[str, Any]:
        """Append plaintext to a note. Requires writes enabled."""

        _enforce_write_policy()
        return evernote_gateway.append_to_note_plaintext(
            note_guid=note_guid,
            plaintext_content=plaintext_content,
        )

    def set_note_title(note_guid: NoteGuid, new_title: NoteTitle) -> dict[str, Any]:
        """Replace a note title. Requires writes enabled."""

        _enforce_write_policy()
        return evernote_gateway.set_note_title(note_guid=note_guid, new_title=new_title)

    def insert_into_note_plaintext(
        note_guid: NoteGuid,
        anchor_text: AnchorText,
        plaintext_content: PlaintextContent,
        position: InsertionPosition = "after",
        occurrence: AnchorOccurrence = 1,
    ) -> dict[str, Any]:
        """Insert plaintext before or after a visible text anchor in a note.

        Use a distinctive anchor. Requires writes enabled.
        """

        _enforce_write_policy()
        return evernote_gateway.insert_plaintext_near_anchor(
            note_guid=note_guid,
            anchor_text=anchor_text,
            plaintext_content=plaintext_content,
            position=position,
            occurrence=occurrence,
        )

    def add_tags_by_name(note_guid: NoteGuid, tag_names: TagNames) -> dict[str, Any]:
        """Add tags to a note, creating missing tags. Requires writes enabled."""

        _enforce_write_policy()
        return evernote_gateway.add_tags_by_name(note_guid=note_guid, tag_names=tag_names)

    def move_note(
        note_guid: NoteGuid,
        destination_notebook_guid: NotebookGuid,
    ) -> dict[str, Any]:
        """Move a note to another notebook. Requires writes enabled."""

        _enforce_write_policy()
        return evernote_gateway.move_note(
            note_guid=note_guid,
            destination_notebook_guid=destination_notebook_guid,
        )

    def create_note(
        title: NoteTitle,
        plaintext_body: PlaintextContent,
        notebook_guid: OptionalNotebookGuid = None,
        tag_names: OptionalTagNames = None,
    ) -> dict[str, Any]:
        """Create a plaintext note, optionally in a notebook with tags.

        Requires writes enabled.
        """

        _enforce_write_policy()
        return evernote_gateway.create_note(
            title=title,
            plaintext_body=plaintext_body,
            notebook_guid=notebook_guid,
            tag_names=tag_names,
        )

    def delete_note(note_guid: NoteGuid) -> dict[str, Any]:
        """Move a note to Evernote trash. Requires writes enabled."""

        _enforce_write_policy()
        return evernote_gateway.delete_note(note_guid=note_guid)

    mcp_server.tool(name="append_to_note_plaintext")(append_to_note_plaintext)
    mcp_server.tool(name="insert_into_note_plaintext")(insert_into_note_plaintext)
    mcp_server.tool(name="set_note_title")(set_note_title)
    mcp_server.tool(name="add_tags_by_name")(add_tags_by_name)
    mcp_server.tool(name="move_note")(move_note)
    mcp_server.tool(name="create_note")(create_note)
    mcp_server.tool(name="delete_note")(delete_note)
