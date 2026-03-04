"""Evernote API gateway used by MCP tool handlers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, cast

from evernote_mcp.evernote.enml import (
    append_plaintext_to_existing_enml,
    build_enml_document,
    escape_plaintext_for_enml,
)
from evernote_mcp.evernote.thrift_client import EvernoteThriftClient


class EvernoteApiError(RuntimeError):
    """Raised when the Evernote API layer returns an error."""


class NoteLike(Protocol):
    """Structural type for EDAM Note objects consumed by gateway write operations."""

    content: str | None
    title: str | None
    notebookGuid: str | None
    tagGuids: list[str] | None


class TagLike(Protocol):
    """Structural type for EDAM Tag objects consumed by gateway tag resolution."""

    guid: str | None
    name: str | None


class EvernoteGateway:
    """Thin service wrapper around Evernote NoteStore operations.

    Args:
        authentication_token: Evernote API token.
        is_sandbox: Whether to use the sandbox endpoint.
        thrift_client: Optional injected Thrift client for tests/custom wiring.
        note_store_url: Optional explicit NoteStore URL override.

    Inputs and outputs:
        Public methods return JSON-serializable dictionaries/lists consumed by MCP
        tool handlers.

    Edge cases:
        The class sanitizes upstream exception messages to avoid leaking sensitive
        data such as tokens or note content.

    Concurrency:
        This wrapper is stateless besides the Thrift client dependency.
    """

    def __init__(
        self,
        authentication_token: str,
        is_sandbox: bool = False,
        thrift_client: EvernoteThriftClient | None = None,
        note_store_url: str | None = None,
    ) -> None:
        self._authentication_token = authentication_token
        self._thrift_client = thrift_client or EvernoteThriftClient(
            authentication_token=authentication_token,
            is_sandbox=is_sandbox,
            note_store_url=note_store_url,
        )

    def list_notebooks(self) -> list[dict[str, Any]]:
        """Return serialized notebooks visible to the authenticated account.

        Returns:
            List of notebook dictionaries. Each item commonly includes `guid`,
            `name`, `defaultNotebook`, `serviceCreated`, `serviceUpdated`, and
            `stack`.

        Composition:
            Used by the `list_notebooks` MCP tool and by callers that need a
            notebook GUID before `create_note` or `move_note`.

        Failure modes:
            Raises `EvernoteApiError` if Evernote notebook listing fails.
        """

        notebooks = self._run_api_call("listNotebooks", self._thrift_client.list_notebooks)
        return self._serialize_evernote_value(notebooks)

    def search_notes(
        self,
        search_query: str,
        offset: int = 0,
        max_results: int = 20,
    ) -> dict[str, Any]:
        """Search notes using Evernote's metadata search endpoint.

        Args:
            search_query: Evernote search syntax string such as plain keywords
                or structured filters like `intitle:`, `notebook:`, or `tag:`.
            offset: Zero-based offset into the result set.
            max_results: Positive page size for the metadata result list.

        Returns:
            Serialized metadata search payload with keys commonly including
            `notes`, `startIndex`, and `totalNotes`.

        Composition:
            Used by the `search_notes` MCP tool as the discovery step for note
            GUIDs consumed by all note-specific read and write operations.

        Failure modes:
            Raises `EvernoteApiError` if Evernote search fails.
        """

        search_result = self._run_api_call(
            "findNotesMetadata",
            lambda: self._thrift_client.search_notes_metadata(
                search_query=search_query,
                offset=offset,
                max_results=max_results,
            ),
        )
        return self._serialize_evernote_value(search_result)

    def get_note(self, note_guid: str) -> dict[str, Any]:
        """Fetch a full note record, including ENML content, for a note GUID.

        Args:
            note_guid: Evernote note GUID returned by a prior metadata search.

        Returns:
            Serialized note dictionary commonly including `guid`, `title`,
            `content`, `contentLength`, `created`, `updated`, `notebookGuid`,
            `tagGuids`, and `attributes`.

        Composition:
            Used by the `get_note` MCP tool and by callers that need the current
            ENML body before computing follow-up edits.

        Failure modes:
            Raises `EvernoteApiError` if the note fetch fails.
        """

        note = self._run_api_call("getNote", lambda: self._thrift_client.get_note(note_guid))
        return self._serialize_evernote_value(note)

    def get_note_metadata(self, note_guid: str) -> dict[str, Any]:
        """Fetch note metadata without the full ENML content payload.

        Args:
            note_guid: Evernote note GUID returned by a prior metadata search.

        Returns:
            Serialized note dictionary commonly including `guid`, `title`,
            `created`, `updated`, `notebookGuid`, `tagGuids`, and `attributes`,
            but intentionally omitting `content`.

        Composition:
            Used by the `get_note_metadata` MCP tool and by write flows that
            need current note placement or identifiers without fetching body
            content.

        Failure modes:
            Raises `EvernoteApiError` if the note fetch fails.
        """

        note = self._run_api_call(
            "getNote",
            lambda: self._thrift_client.get_note_metadata(note_guid),
        )
        return self._serialize_evernote_value(note)

    def append_to_note_plaintext(self, note_guid: str, plaintext_content: str) -> dict[str, Any]:
        """Append plain text to an existing note body and persist the update.

        Args:
            note_guid: Evernote note GUID for the target note.
            plaintext_content: Plain text to append. Newlines are preserved and
                the text is escaped before insertion into ENML.

        Returns:
            Serialized updated note dictionary, including the new ENML `content`.

        Composition:
            Used by the `append_to_note_plaintext` MCP tool after a caller has
            already resolved the target note GUID.

        Failure modes:
            Raises `EvernoteApiError` if the note fetch or update fails.
            Raises `ValueError` if the stored note content is not valid ENML.
        """

        note = cast(
            NoteLike,
            self._call_note_store_method(
            "getNote",
            note_guid,
            True,
            False,
            False,
            False,
            ),
        )
        note.content = append_plaintext_to_existing_enml(note.content or "", plaintext_content)
        updated_note = self._call_note_store_method("updateNote", note)
        return self._serialize_evernote_value(updated_note)

    def set_note_title(self, note_guid: str, new_title: str) -> dict[str, Any]:
        """Replace a note title and persist the update.

        Args:
            note_guid: Evernote note GUID for the target note.
            new_title: Full replacement title string.

        Returns:
            Serialized updated note dictionary with the new `title`.

        Composition:
            Used by the `set_note_title` MCP tool after note discovery.

        Failure modes:
            Raises `EvernoteApiError` if the note fetch or update fails.
        """

        note = cast(
            NoteLike,
            self._call_note_store_method(
            "getNote",
            note_guid,
            False,
            False,
            False,
            False,
            ),
        )
        note.title = new_title
        updated_note = self._call_note_store_method("updateNote", note)
        return self._serialize_evernote_value(updated_note)

    def add_tags_by_name(self, note_guid: str, tag_names: list[str]) -> dict[str, Any]:
        """Attach tags to a note, creating missing tags by name when needed.

        Args:
            note_guid: Evernote note GUID for the target note.
            tag_names: Human-readable tag names. Blank values are ignored and
                duplicates are removed case-insensitively.

        Returns:
            Serialized updated note dictionary with the full `tagGuids` set.

        Composition:
            Used by the `add_tags_by_name` MCP tool. This method converts
            user-facing tag names into Evernote tag GUIDs before persistence.

        Failure modes:
            Raises `EvernoteApiError` if note fetch, tag listing/creation, or
            note update fails.
        """

        note = cast(
            NoteLike,
            self._call_note_store_method(
            "getNote",
            note_guid,
            False,
            False,
            False,
            False,
            ),
        )
        existing_tag_guids = set(note.tagGuids or [])
        resolved_tag_guids = self._resolve_tag_guids_by_name(tag_names)
        note.tagGuids = sorted(existing_tag_guids.union(resolved_tag_guids))
        updated_note = self._call_note_store_method("updateNote", note)
        return self._serialize_evernote_value(updated_note)

    def move_note(self, note_guid: str, destination_notebook_guid: str) -> dict[str, Any]:
        """Move a note to another notebook and persist the update.

        Args:
            note_guid: Evernote note GUID for the target note.
            destination_notebook_guid: Evernote notebook GUID returned by a
                notebook listing call.

        Returns:
            Serialized updated note dictionary with the new `notebookGuid`.

        Composition:
            Used by the `move_note` MCP tool after notebook discovery via
            `list_notebooks`.

        Failure modes:
            Raises `EvernoteApiError` if note fetch or update fails.
        """

        note = cast(
            NoteLike,
            self._call_note_store_method(
            "getNote",
            note_guid,
            False,
            False,
            False,
            False,
            ),
        )
        note.notebookGuid = destination_notebook_guid
        updated_note = self._call_note_store_method("updateNote", note)
        return self._serialize_evernote_value(updated_note)

    def create_note(
        self,
        title: str,
        plaintext_body: str,
        notebook_guid: str | None = None,
        tag_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new note from plain text content and optional metadata.

        Args:
            title: Human-readable note title.
            plaintext_body: Plain text note body. It is escaped and wrapped in
                ENML before being sent to Evernote.
            notebook_guid: Optional notebook GUID. When omitted, Evernote uses
                the default notebook.
            tag_names: Optional human-readable tag names to resolve and attach.

        Returns:
            Serialized created note dictionary commonly including `guid`,
            `title`, `content`, `created`, `updated`, `notebookGuid`, and
            `tagGuids`.

        Composition:
            Used by the `create_note` MCP tool. The returned `guid` becomes the
            input for all subsequent note-specific tools.

        Failure modes:
            Raises `EvernoteApiError` if note creation or tag resolution fails.
        """

        enml_content = build_enml_document(escape_plaintext_for_enml(plaintext_body))
        note = cast(
            NoteLike,
            self._thrift_client.build_note(title=title, content=enml_content),
        )
        if notebook_guid:
            note.notebookGuid = notebook_guid

        if tag_names:
            note.tagGuids = self._resolve_tag_guids_by_name(tag_names)

        created_note = self._call_note_store_method("createNote", note)
        return self._serialize_evernote_value(created_note)

    def delete_note(self, note_guid: str) -> dict[str, Any]:
        """Move a note to Evernote trash and return deletion status metadata.

        Args:
            note_guid: Evernote note GUID for the target note.

        Returns:
            Serialized deletion result dictionary with:
            - `guid`: Original note GUID that was requested for deletion.
            - `deleted`: Always `True` when Evernote accepts the request.
            - `updateSequenceNum`: Evernote USN returned by `deleteNote`, when
              provided by the API.

        Composition:
            Used by the `delete_note` MCP tool after note discovery via
            `search_notes`.

        Failure modes:
            Raises `EvernoteApiError` if Evernote rejects the deletion request
            or the note is inaccessible.
        """

        update_sequence_number = self._run_api_call(
            "deleteNote",
            lambda: self._thrift_client.delete_note(note_guid),
        )
        return {
            "guid": note_guid,
            "deleted": True,
            "updateSequenceNum": self._serialize_evernote_value(update_sequence_number),
        }

    def _resolve_tag_guids_by_name(self, tag_names: list[str]) -> list[str]:
        """Resolve tag names to GUIDs, creating tags that do not yet exist.

        Args:
            tag_names: Candidate tag names from user input.

        Returns:
            Ordered list of resolved GUIDs matching normalized tag names.

        Edge cases:
            Empty strings and case-insensitive duplicates are removed.
        """

        normalized_tag_names = self._normalize_tag_names(tag_names)
        if not normalized_tag_names:
            return []

        existing_tags = cast(
            list[TagLike],
            self._run_api_call("listTags", self._thrift_client.list_tags),
        )
        tag_guid_by_name: dict[str, str] = {}
        for tag in existing_tags:
            tag_name = tag.name
            tag_guid = tag.guid
            if not tag_name or not tag_guid:
                continue
            tag_guid_by_name[tag_name.strip().lower()] = tag_guid

        resolved_tag_guids: list[str] = []
        for normalized_tag_name in normalized_tag_names:
            normalized_tag_name_key = normalized_tag_name.lower()
            existing_guid = tag_guid_by_name.get(normalized_tag_name_key)
            if existing_guid:
                resolved_tag_guids.append(existing_guid)
                continue

            created_tag = cast(
                TagLike,
                self._run_api_call(
                "createTag",
                lambda: self._thrift_client.create_tag(
                    self._thrift_client.build_tag(name=normalized_tag_name)
                ),
            ),
            )
            if created_tag.guid:
                resolved_tag_guids.append(created_tag.guid)

        return resolved_tag_guids

    def _normalize_tag_names(self, tag_names: list[str]) -> list[str]:
        """Normalize and deduplicate tag names while preserving insertion order."""

        normalized_tag_names: list[str] = []
        seen_tag_name_keys: set[str] = set()

        for tag_name in tag_names:
            normalized_tag_name = tag_name.strip()
            if not normalized_tag_name:
                continue
            normalized_tag_name_key = normalized_tag_name.lower()
            if normalized_tag_name_key in seen_tag_name_keys:
                continue

            normalized_tag_names.append(normalized_tag_name)
            seen_tag_name_keys.add(normalized_tag_name_key)

        return normalized_tag_names

    def _call_note_store_method(self, method_name: str, *arguments: Any) -> Any:
        """Invoke a NoteStore method through the Thrift client.

        Args:
            method_name: Name of the NoteStore method.
            *arguments: Method arguments excluding the auth token.

        Returns:
            Raw Thrift response object.

        Security:
            Any exception is wrapped into a sanitized `EvernoteApiError` that omits
            raw upstream message text.
        """

        return self._run_api_call(
            method_name,
            lambda: self._thrift_client.call_note_store_method(method_name, *arguments),
        )

    def _run_api_call(self, method_name: str, method_callable: Callable[[], Any]) -> Any:
        """Execute an API call and convert failures into sanitized gateway errors.

        Args:
            method_name: Logical Evernote API method name for error context.
            method_callable: Callable that performs the actual API request.

        Returns:
            The raw API response value.

        Concurrency:
            This helper is stateless and safe to call concurrently.
        """

        try:
            return method_callable()
        except Exception as error:
            raise self._build_safe_api_error(method_name, error) from error

    def _build_safe_api_error(self, method_name: str, error: Exception) -> EvernoteApiError:
        """Build a sanitized API error message that avoids leaking sensitive payload data.

        Args:
            method_name: Name of the NoteStore method that failed.
            error: Original exception from the SDK or transport layer.

        Returns:
            EvernoteApiError containing method context and exception type only.

        Security:
            Exception messages are intentionally excluded because they can contain
            authentication tokens, request details, or note content.
        """

        exception_type_name = type(error).__name__
        return EvernoteApiError(
            f"Evernote API call '{method_name}' failed with {exception_type_name}."
        )

    def _serialize_evernote_value(self, value: Any) -> Any:
        """Convert Thrift-style Evernote objects to JSON-serializable Python values.

        Args:
            value: Arbitrary scalar, container, or Thrift object.

        Returns:
            Recursively serialized value containing only JSON-friendly Python types.

        Edge cases:
            Unknown object types are converted to string as a fallback.
        """

        if isinstance(value, (str, int, float, bool)) or value is None:
            return value

        if isinstance(value, list):
            list_value = cast(list[Any], value)
            return [self._serialize_evernote_value(item) for item in list_value]

        if isinstance(value, tuple):
            tuple_value = cast(tuple[Any, ...], value)
            return tuple(self._serialize_evernote_value(item) for item in tuple_value)

        if isinstance(value, dict):
            dictionary_value = cast(dict[Any, Any], value)
            return {
                key: self._serialize_evernote_value(item_value)
                for key, item_value in dictionary_value.items()
            }

        if hasattr(value, "__dict__"):
            serializable_mapping = {
                attribute_name: self._serialize_evernote_value(attribute_value)
                for attribute_name, attribute_value in value.__dict__.items()
                if not attribute_name.startswith("_")
            }
            return serializable_mapping

        return str(value)
