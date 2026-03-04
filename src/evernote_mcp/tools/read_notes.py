"""MCP tool registration for read-only note operations."""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from evernote_mcp.evernote.client import EvernoteGateway

DEFAULT_SEARCH_OFFSET = 0
DEFAULT_SEARCH_MAX_RESULTS = 20

SearchQuery = Annotated[
    str,
    Field(
        description=(
            "Evernote search expression. Use plain keywords or Evernote operators "
            "such as intitle:, notebook:, tag:, or created:. Use this tool first "
            "when you need a note GUID for follow-up read or write operations."
        )
    ),
]
SearchOffset = Annotated[
    int,
    Field(
        ge=0,
        description=(
            "Zero-based pagination offset. Use 0 for the first page, then advance "
            "by the previous max_results value to inspect additional matches."
        ),
    ),
]
SearchMaxResults = Annotated[
    int,
    Field(
        ge=1,
        description=(
            "Maximum number of matches to return. Smaller pages such as 5-20 "
            "usually make it easier to identify the correct note before reading "
            "or mutating it."
        ),
    ),
]
NoteGuid = Annotated[
    str,
    Field(
        min_length=1,
        description=(
            "Evernote note GUID returned by search_notes. Pass the GUID exactly as "
            "returned; do not rewrite or infer it."
        ),
    ),
]


def register_read_note_tools(mcp_server: FastMCP, evernote_gateway: EvernoteGateway) -> None:
    """Register read-focused note tools on the provided MCP server.

    Args:
        mcp_server: FastMCP server where tools are registered.
        evernote_gateway: Evernote service wrapper used by tool handlers.
    """

    @mcp_server.tool(name="search_notes")
    def search_notes(
        search_query: SearchQuery,
        offset: SearchOffset = DEFAULT_SEARCH_OFFSET,
        max_results: SearchMaxResults = DEFAULT_SEARCH_MAX_RESULTS,
    ) -> dict:
        """Search note metadata and return candidate notes, not full note bodies.

        Args:
            search_query: Evernote query string. Examples include plain text such
                as `meeting notes`, or structured filters such as
                `intitle:roadmap`, `notebook:Work tag:urgent`, or
                `created:day-7`. Use this tool first when you need a `note_guid`
                for `get_note`, `get_note_metadata`, or any write tool.
            offset: Zero-based pagination offset. Use `0` for the first page.
            max_results: Positive page size. Smaller result pages reduce
                ambiguity and make it easier to pick the correct note.

        Returns:
            Dictionary with keys commonly including:
                `notes`: list of matching note metadata objects. Each item
                    commonly includes `guid`, `title`, `created`, `updated`,
                    `notebookGuid`, and `tagGuids`.
                `startIndex`: offset used for the returned page.
                `totalNotes`: total number of matches across all pages.
            Evernote may include additional metadata fields.

        Composition:
            Use this tool before any note-specific read or write action.
            Feed a returned note `guid` into `get_note`, `get_note_metadata`,
            `append_to_note_plaintext`, `set_note_title`, `add_tags_by_name`,
            or `move_note`.

        Failure modes:
            Raises `EvernoteApiError` if the Evernote search request fails or
            the upstream transport is unavailable.
        """

        return evernote_gateway.search_notes(
            search_query=search_query,
            offset=offset,
            max_results=max_results,
        )

    @mcp_server.tool(name="get_note")
    def get_note(note_guid: NoteGuid) -> dict:
        """Fetch a full note, including the ENML body, for a known note GUID.

        Args:
            note_guid: Evernote note GUID returned by `search_notes`.

        Returns:
            Dictionary with keys commonly including:
                `guid`: stable Evernote note identifier.
                `title`: current note title.
                `content`: full note body as ENML, not plain text.
                `contentLength`: serialized ENML length.
                `created`, `updated`, `deleted`: Evernote timestamps when
                    available.
                `notebookGuid`: parent notebook GUID.
                `tagGuids`: attached Evernote tag GUIDs.
                `attributes`: nested note metadata when available.
            Evernote may include additional fields.

        Composition:
            Use `search_notes` first if you do not already have the note GUID.
            Prefer `get_note_metadata` when you only need identifiers,
            timestamps, notebook placement, or tags.
            Use this tool before `append_to_note_plaintext` when you need to
            inspect the current body and avoid duplicate edits.

        Failure modes:
            Raises `EvernoteApiError` if the note does not exist, is not
            accessible to the token, or the Evernote API request fails.
        """

        return evernote_gateway.get_note(note_guid=note_guid)

    @mcp_server.tool(name="get_note_metadata")
    def get_note_metadata(note_guid: NoteGuid) -> dict:
        """Fetch note metadata without returning the full ENML body.

        Args:
            note_guid: Evernote note GUID returned by `search_notes`.

        Returns:
            Dictionary with keys commonly including:
                `guid`: stable Evernote note identifier.
                `title`: current note title.
                `created`, `updated`, `deleted`: Evernote timestamps when
                    available.
                `notebookGuid`: parent notebook GUID.
                `tagGuids`: attached Evernote tag GUIDs.
                `attributes`: nested note metadata when available.
            This tool intentionally omits the large `content` field.

        Composition:
            Use `search_notes` first to resolve the correct `note_guid`.
            Prefer this tool over `get_note` when you only need identifiers or
            note placement before calling `move_note`, `add_tags_by_name`, or
            `set_note_title`.

        Failure modes:
            Raises `EvernoteApiError` if the note does not exist, is not
            accessible to the token, or the Evernote API request fails.
        """

        return evernote_gateway.get_note_metadata(note_guid=note_guid)
