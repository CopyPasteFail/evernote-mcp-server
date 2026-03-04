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
            "Evernote note GUID from search_notes notes[].guid. Pass it unchanged "
            "as note_guid. Also use create_note result guid for follow-up edits."
        ),
    ),
]
PlaintextContent = Annotated[
    str,
    Field(
        description=(
            "Plain text content. Do not send ENML or HTML. Newlines are "
            "preserved when converted to Evernote ENML."
        )
    ),
]
NoteTitle = Annotated[
    str,
    Field(
        description=(
            "Full human-readable note title value."
        )
    ),
]
NotebookGuid = Annotated[
    str,
    Field(
        min_length=1,
        description=(
            "Evernote notebook GUID from list_notebooks[].guid. Pass it unchanged "
            "as notebook_guid or destination_notebook_guid."
        ),
    ),
]
TagNames = Annotated[
    list[str],
    Field(
        description=(
            "List of human-readable tag names. Blank names are ignored, "
            "duplicates are removed case-insensitively, and missing tags are "
            "created automatically."
        )
    ),
]
OptionalNotebookGuid = Annotated[
    str | None,
    Field(
        description=(
            "Optional notebook GUID from list_notebooks[].guid. Omit to create in "
            "Evernote's default notebook."
        )
    ),
]
OptionalTagNames = Annotated[
    list[str] | None,
    Field(
        description=(
            "Optional tag names to attach during creation. Missing tags are "
            "created automatically."
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

        Use first:
            If `note_guid` is unknown, call `search_notes` first.
            Call `get_note` first when you need to inspect current trailing
            content and avoid duplicate or out-of-order appends.

        Returns keys:
            `guid`, `title`, `content`, `updated`, `notebookGuid`, `tagGuids`.
            Evernote may include additional fields.

        Fails when:
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

        Use first:
            If `note_guid` is unknown, call `search_notes` first.
            Call `get_note_metadata` first when you need to confirm current title
            or notebook placement without loading full ENML content, or to avoid
            renaming to an already-correct title.

        Returns keys:
            `guid`, `title`, `updated`, `notebookGuid`, `tagGuids`.
            Evernote may include additional fields.

        Fails when:
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

        Use first:
            If `note_guid` is unknown, call `search_notes` first.
            Call `get_note_metadata` first when you need existing `tagGuids`
            without loading full ENML content, especially to avoid redundant
            retagging.

        Returns keys:
            `guid`, `title`, `tagGuids`, `updated`, `notebookGuid`.
            The response includes Evernote tag GUIDs, not original tag names.

        Fails when:
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

        Use first:
            If `note_guid` is unknown, call `search_notes` first.
            Call `list_notebooks` first to resolve
            `destination_notebook_guid`.
            Call `get_note_metadata` when you need notebook/tag checks without
            loading full ENML content, especially to avoid moving to the current
            notebook by mistake.

        Returns keys:
            `guid`, `title`, `notebookGuid`, `updated`, `tagGuids`.
            Evernote may include additional fields.

        Fails when:
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

        Use first:
            Call `list_notebooks` first when the note must go to a specific
            notebook.
            Call `search_notes` first when duplicate notes are possible and you
            need to confirm a similar title does not already exist.

        Returns keys:
            `guid`, `title`, `content`, `created`, `updated`, `notebookGuid`,
            `tagGuids`.
            Use returned `guid` as `note_guid` in all note-specific tools.

        Fails when:
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

    @mcp_server.tool(name="delete_note")
    def delete_note(note_guid: NoteGuid) -> dict:
        """Move an existing note to Evernote trash (soft delete).

        Args:
            note_guid: Evernote note GUID returned by `search_notes`.

        Use first:
            If `note_guid` is unknown, call `search_notes` first.
            Call `get_note_metadata` first when you need to verify title,
            notebook, or update timestamp before deleting.

        Returns keys:
            `guid`, `deleted`, `updateSequenceNum`.
            `deleted` is `true` when Evernote accepts the request.

        Fails when:
            Raises `WriteAccessError` when the server is in read-only mode.
            Raises `EvernoteApiError` if the note does not exist, is not
            accessible, or the delete request fails.
        """

        _enforce_write_policy()
        return evernote_gateway.delete_note(note_guid=note_guid)
