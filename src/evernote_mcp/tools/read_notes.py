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
            "Evernote search expression. Supports plain keywords and operators such "
            "as intitle:, notebook:, tag:, and created:. Use search_notes first to "
            "find note GUIDs for all note-specific tools."
        )
    ),
]
SearchOffset = Annotated[
    int,
    Field(
        ge=0,
        description=(
            "Zero-based result offset. Use 0 for the first page, then add the "
            "previous max_results value for the next page."
        ),
    ),
]
SearchMaxResults = Annotated[
    int,
    Field(
        ge=1,
        description=(
            "Maximum matches in one page. Use smaller values (for example 5-10) "
            "when disambiguating similar notes, and larger values for broad "
            "scans."
        ),
    ),
]
NoteGuid = Annotated[
    str,
    Field(
        min_length=1,
        description=(
            "Evernote note GUID from search_notes notes[].guid. Pass it unchanged "
            "as note_guid to note-specific tools."
        ),
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
        """Search note metadata only. This tool does not return ENML note content.

        Args:
            search_query: Evernote query string. Examples include plain text such
                as `meeting notes`, or structured filters such as
                `intitle:roadmap`, `notebook:Work tag:urgent`, or `created:day-7`.
            offset: Zero-based pagination offset. Use `0` for the first page.
            max_results: Positive page size.

        Use first:
            Use before `get_note`, `get_note_metadata`, and all write tools when
            you do not already know the target `note_guid`.
            When many notes look similar, start with a smaller `max_results`,
            inspect top matches, then refine `search_query`.

        Returns keys:
            `notes`, `startIndex`, `totalNotes`.
            `notes[]` items usually include `guid`, `title`, `created`,
            `updated`, `notebookGuid`, and `tagGuids`.
            Use `notes[i].guid` as `note_guid` in follow-up tools.

        Fails when:
            Raises `EvernoteApiError` if the Evernote search request fails.
        """

        return evernote_gateway.search_notes(
            search_query=search_query,
            offset=offset,
            max_results=max_results,
        )

    def get_note(note_guid: NoteGuid) -> dict[str, Any]:
        """Fetch a full note, including the ENML body, for a known note GUID.

        Args:
            note_guid: Evernote note GUID returned by `search_notes`.

        Use first:
            If `note_guid` is unknown, call `search_notes` first.
            Prefer `get_note_metadata` when title/notebook/tag checks are enough,
            so you avoid loading full ENML content.

        Returns keys:
            `guid`, `title`, `content`, `contentLength`, `created`, `updated`,
            `deleted`, `notebookGuid`, `tagGuids`, `attributes`.
            Evernote may include additional fields.

        Fails when:
            Raises `EvernoteApiError` if the note does not exist, is not
            accessible to the token, or the Evernote API request fails.
        """

        return evernote_gateway.get_note(note_guid=note_guid)

    def get_note_metadata(note_guid: NoteGuid) -> dict[str, Any]:
        """Fetch note metadata without returning the full ENML body.

        Args:
            note_guid: Evernote note GUID returned by `search_notes`.

        Use first:
            If `note_guid` is unknown, call `search_notes` first.
            Prefer this tool over `get_note` when body content is unnecessary.

        Returns keys:
            `guid`, `title`, `created`, `updated`, `deleted`, `notebookGuid`,
            `tagGuids`, `attributes`.
            This tool intentionally omits `content`.
            Use `guid` as `note_guid` for write tools, and use `notebookGuid` to
            validate move targets before `move_note`.

        Fails when:
            Raises `EvernoteApiError` if the note does not exist, is not
            accessible to the token, or the Evernote API request fails.
        """

        return evernote_gateway.get_note_metadata(note_guid=note_guid)

    mcp_server.tool(name="search_notes")(search_notes)
    mcp_server.tool(name="get_note")(get_note)
    mcp_server.tool(name="get_note_metadata")(get_note_metadata)
