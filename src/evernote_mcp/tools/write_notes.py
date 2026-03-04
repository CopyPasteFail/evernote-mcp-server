"""MCP tool registration for write-capable note operations."""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from evernote_mcp.core.policies import require_writes_enabled
from evernote_mcp.evernote.client import EvernoteGateway

NoteGuid = Annotated[
    str,
    Field(
        min_length=1,
        description=(
            "Evernote note GUID returned by search_notes. Pass the GUID exactly "
            "as returned by Evernote."
        ),
    ),
]
PlaintextContent = Annotated[
    str,
    Field(
        description=(
            "Plain text to store in the note. Do not send ENML or HTML. Newlines "
            "are preserved when converted to Evernote ENML."
        )
    ),
]
NoteTitle = Annotated[
    str,
    Field(
        description=(
            "Human-readable note title. Keep it concise and pass the full desired "
            "title value."
        )
    ),
]
NotebookGuid = Annotated[
    str,
    Field(
        min_length=1,
        description=(
            "Notebook GUID returned by list_notebooks. Pass it unchanged to place "
            "or move a note into that notebook."
        ),
    ),
]
TagNames = Annotated[
    list[str],
    Field(
        description=(
            "List of human-readable tag names. Blank names are ignored and "
            "duplicates are removed case-insensitively. Missing tags are created "
            "automatically."
        )
    ),
]
OptionalNotebookGuid = Annotated[
    str | None,
    Field(
        description=(
            "Optional notebook GUID from list_notebooks. Omit to create the note "
            "in Evernote's default notebook."
        )
    ),
]
OptionalTagNames = Annotated[
    list[str] | None,
    Field(
        description=(
            "Optional list of tag names to attach during note creation. Missing "
            "tags are created automatically."
        )
    ),
]


def _enforce_write_policy() -> None:
    """Apply the shared write gate before any mutating Evernote action.

    Raises:
        WriteAccessError: If the server is running in read-only mode.
    """

    require_writes_enabled()


def register_write_note_tools(mcp_server: FastMCP, evernote_gateway: EvernoteGateway) -> None:
    """Register write note tools while enforcing the shared write policy.

    Args:
        mcp_server: FastMCP server where tools are registered.
        evernote_gateway: Evernote service wrapper used by tool handlers.
    """

    @mcp_server.tool(name="append_to_note_plaintext")
    def append_to_note_plaintext(
        note_guid: NoteGuid,
        plaintext_content: PlaintextContent,
    ) -> dict:
        """Append plain text to an existing note body without replacing it.

        Args:
            note_guid: Evernote note GUID returned by `search_notes`.
            plaintext_content: Plain text to append. Do not send ENML or HTML.
                Newlines are preserved and the text is appended inside a new
                ENML `<div>`.

        Returns:
            Updated note dictionary with keys commonly including:
                `guid`: stable Evernote note identifier.
                `title`: current note title.
                `content`: full ENML body after the append.
                `updated`: Evernote update timestamp.
                `notebookGuid`: current notebook GUID.
                `tagGuids`: attached Evernote tag GUIDs.
            Evernote may include additional fields.

        Composition:
            Use `search_notes` first to resolve the correct `note_guid`.
            Use `get_note` first when you need to inspect the current body and
            avoid duplicate or misplaced appends.

        Failure modes:
            Raises `WriteAccessError` when the server is in read-only mode.
            Raises `EvernoteApiError` if the note cannot be fetched or updated.
            Raises `ValueError` if the existing note body is not valid ENML.
        """

        _enforce_write_policy()
        return evernote_gateway.append_to_note_plaintext(
            note_guid=note_guid,
            plaintext_content=plaintext_content,
        )

    @mcp_server.tool(name="set_note_title")
    def set_note_title(note_guid: NoteGuid, new_title: NoteTitle) -> dict:
        """Replace the title of an existing note.

        Args:
            note_guid: Evernote note GUID returned by `search_notes`.
            new_title: Full title string that should replace the existing title.

        Returns:
            Updated note dictionary with keys commonly including:
                `guid`: stable Evernote note identifier.
                `title`: updated note title.
                `updated`: Evernote update timestamp.
                `notebookGuid`: current notebook GUID.
                `tagGuids`: attached Evernote tag GUIDs when available.
            Evernote may include additional fields.

        Composition:
            Use `search_notes` first to resolve the note.
            Use `get_note_metadata` first if you want to confirm the existing
            title before changing it.

        Failure modes:
            Raises `WriteAccessError` when the server is in read-only mode.
            Raises `EvernoteApiError` if the note does not exist, the title is
            rejected by Evernote, or the update request fails.
        """

        _enforce_write_policy()
        return evernote_gateway.set_note_title(note_guid=note_guid, new_title=new_title)

    @mcp_server.tool(name="add_tags_by_name")
    def add_tags_by_name(note_guid: NoteGuid, tag_names: TagNames) -> dict:
        """Attach tags to a note by name, creating missing tags automatically.

        Args:
            note_guid: Evernote note GUID returned by `search_notes`.
            tag_names: Human-readable tag names. Blank strings are ignored and
                duplicates are removed case-insensitively before the update.

        Returns:
            Updated note dictionary with keys commonly including:
                `guid`: stable Evernote note identifier.
                `title`: note title.
                `tagGuids`: complete set of attached Evernote tag GUIDs after the
                    update.
                `updated`: Evernote update timestamp.
                `notebookGuid`: current notebook GUID.
            The response contains Evernote tag GUIDs, not the original tag names.

        Composition:
            Use `search_notes` first to resolve the note.
            Use `get_note_metadata` first if you need to inspect the note's
            current `tagGuids` before adding more tags.

        Failure modes:
            Raises `WriteAccessError` when the server is in read-only mode.
            Raises `EvernoteApiError` if the note update fails or Evernote
            cannot list or create tags.
        """

        _enforce_write_policy()
        return evernote_gateway.add_tags_by_name(note_guid=note_guid, tag_names=tag_names)

    @mcp_server.tool(name="move_note")
    def move_note(note_guid: NoteGuid, destination_notebook_guid: NotebookGuid) -> dict:
        """Move a note into another notebook.

        Args:
            note_guid: Evernote note GUID returned by `search_notes`.
            destination_notebook_guid: Notebook GUID returned by
                `list_notebooks`.

        Returns:
            Updated note dictionary with keys commonly including:
                `guid`: stable Evernote note identifier.
                `title`: note title.
                `notebookGuid`: updated destination notebook GUID.
                `updated`: Evernote update timestamp.
                `tagGuids`: attached Evernote tag GUIDs when available.
            Evernote may include additional fields.

        Composition:
            Use `search_notes` first to resolve the note to move.
            Use `list_notebooks` first to find the destination
            `destination_notebook_guid`.
            Use `get_note_metadata` before or after the move if you need to
            confirm notebook placement without fetching full ENML content.

        Failure modes:
            Raises `WriteAccessError` when the server is in read-only mode.
            Raises `EvernoteApiError` if the note or destination notebook is not
            accessible or the update request fails.
        """

        _enforce_write_policy()
        return evernote_gateway.move_note(
            note_guid=note_guid,
            destination_notebook_guid=destination_notebook_guid,
        )

    @mcp_server.tool(name="create_note")
    def create_note(
        title: NoteTitle,
        plaintext_body: PlaintextContent,
        notebook_guid: OptionalNotebookGuid = None,
        tag_names: OptionalTagNames = None,
    ) -> dict:
        """Create a new note from plain text content.

        Args:
            title: Human-readable note title.
            plaintext_body: Plain text note body. Do not send ENML or HTML.
                Newlines are preserved when the body is converted to ENML.
            notebook_guid: Optional destination notebook GUID from
                `list_notebooks`. Omit to use Evernote's default notebook.
            tag_names: Optional human-readable tag names to attach. Missing tags
                are created automatically. Blank names are ignored and
                duplicates are removed case-insensitively.

        Returns:
            Created note dictionary with keys commonly including:
                `guid`: new Evernote note GUID for later reads or edits.
                `title`: created note title.
                `content`: ENML body generated from the provided plain text.
                `created`, `updated`: Evernote timestamps.
                `notebookGuid`: notebook GUID used for creation.
                `tagGuids`: attached Evernote tag GUIDs when tags were applied.
            Evernote may include additional fields.

        Composition:
            Use `list_notebooks` first when the note must go into a specific
            notebook.
            The returned `guid` can be passed directly into `get_note`,
            `get_note_metadata`, `append_to_note_plaintext`,
            `set_note_title`, `add_tags_by_name`, or `move_note`.

        Failure modes:
            Raises `WriteAccessError` when the server is in read-only mode.
            Raises `EvernoteApiError` if Evernote rejects the note creation,
            the notebook is invalid, or tag creation fails.
        """

        _enforce_write_policy()
        return evernote_gateway.create_note(
            title=title,
            plaintext_body=plaintext_body,
            notebook_guid=notebook_guid,
            tag_names=tag_names,
        )
