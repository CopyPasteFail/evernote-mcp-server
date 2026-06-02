"""Evernote API gateway used by MCP tool handlers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, cast

from evernote_mcp.evernote.enml import (
    append_plaintext_to_existing_enml,
    build_enml_document,
    escape_plaintext_for_enml,
    insert_plaintext_near_anchor_in_enml,
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

        try:
            note = self._run_api_call("getNote", lambda: self._thrift_client.get_note(note_guid))
        except EvernoteApiError as error:
            if self._error_chain_mentions(error, "EDAMSystemException"):
                metadata = self._safe_get_note_metadata_after_content_failure(note_guid)
                raise EvernoteApiError(
                    "Evernote failed to load full note content with EDAMSystemException. "
                    "Metadata is still available through get_note_metadata; avoid write "
                    "tools that require full ENML content until the note can be fetched. "
                    f"metadata={metadata}"
                ) from error

            raise

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

        note = self._get_note_content_for_write(note_guid)
        updated_content = append_plaintext_to_existing_enml(note.content or "", plaintext_content)
        update_note = self._build_content_update_note(
            source_note=note,
            updated_content=updated_content,
        )
        updated_note = self._call_note_store_method("updateNote", update_note)
        return self._serialize_updated_note(updated_note, fallback_note=update_note)

    def insert_plaintext_near_anchor(
        self,
        note_guid: str,
        anchor_text: str,
        plaintext_content: str,
        position: str = "after",
        occurrence: int = 1,
    ) -> dict[str, Any]:
        """Insert plaintext before or after existing visible text in a rich note.

        Args:
            note_guid: Evernote note GUID for the target note.
            anchor_text: Existing visible text used to locate the insertion point.
            plaintext_content: Plain text to insert. It is escaped before being
                converted into ENML.
            position: Either `before` or `after` the matched top-level block.
            occurrence: One-based match number when the anchor appears multiple
                times.

        Returns:
            Serialized updated note dictionary.

        Failure modes:
            Raises `ValueError` for invalid ENML or missing anchors.
            Raises `EvernoteApiError` if the note changed between fetch and
            update, or if Evernote rejects the request.
        """

        note = self._get_note_content_for_write(note_guid)
        updated_content = insert_plaintext_near_anchor_in_enml(
            existing_enml=note.content or "",
            anchor_text=anchor_text,
            plaintext_content=plaintext_content,
            position=position,
            occurrence=occurrence,
        )
        update_note = self._build_content_update_note(
            source_note=note,
            updated_content=updated_content,
        )
        update_result = self._update_note_with_usn_match_when_available(update_note)
        if getattr(update_result, "updated", True) is False:
            raise EvernoteApiError(
                "Evernote note changed before update; fetch the latest note and retry."
            )

        updated_note = getattr(update_result, "note", update_result)
        return self._serialize_updated_note(updated_note, fallback_note=update_note)

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

        if notebook_guid:
            visible_notebook_name = self._resolve_visible_notebook_name(notebook_guid)
            if visible_notebook_name is None:
                raise EvernoteApiError(
                    "Evernote notebook_guid is not visible from list_notebooks; "
                    "refresh notebooks and retry."
                )

        enml_content = build_enml_document(escape_plaintext_for_enml(plaintext_body))
        note = cast(
            NoteLike,
            self._thrift_client.build_note(title=title, content=enml_content),
        )
        if notebook_guid:
            note.notebookGuid = notebook_guid

        if tag_names:
            note.tagGuids = self._resolve_tag_guids_by_name(tag_names)

        try:
            created_note = self._call_note_store_method("createNote", note)
        except EvernoteApiError as error:
            if notebook_guid and self._error_chain_mentions(error, "EDAMNotFoundException"):
                raise EvernoteApiError(
                    "Evernote createNote rejected a notebook_guid that was visible "
                    "from list_notebooks; refresh notebooks and retry, or create "
                    "the note in the default notebook and move it afterward."
                ) from error

            if self._error_chain_mentions(error, "EDAMSystemException"):
                raise EvernoteApiError(
                    "Evernote rejected createNote with EDAMSystemException. "
                    "Retry later; if using a target notebook, refresh notebooks "
                    "and retry, or create in the default notebook first."
                ) from error

            raise

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

    def _build_content_update_note(
        self,
        *,
        source_note: NoteLike,
        updated_content: str,
    ) -> NoteLike:
        """Build a minimal note object for content-only update operations."""

        build_note = getattr(self._thrift_client, "build_note", None)
        if build_note is None:
            update_note = cast(NoteLike, type("MinimalNote", (), {})())
        else:
            update_note = cast(
                NoteLike,
                build_note(
                    title=source_note.title or "",
                    content=updated_content,
                ),
            )

        update_note.guid = source_note.guid
        update_note.title = source_note.title or ""
        update_note.content = updated_content
        return update_note

    def _get_note_content_for_write(self, note_guid: str) -> NoteLike:
        """Fetch full note content for write flows with clearer failure context."""

        try:
            return cast(
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
        except EvernoteApiError as error:
            if self._error_chain_mentions(error, "EDAMSystemException"):
                metadata = self._safe_get_note_metadata_after_content_failure(note_guid)
                raise EvernoteApiError(
                    "Evernote failed to load full note content for a write operation "
                    "with EDAMSystemException. Metadata is still available through "
                    "get_note_metadata, but write tools that modify ENML need the full "
                    f"note body first. metadata={metadata}"
                ) from error

            raise

    def _safe_get_note_metadata_after_content_failure(self, note_guid: str) -> dict[str, Any]:
        """Best-effort metadata lookup used only to improve content-failure errors."""

        try:
            metadata = self.get_note_metadata(note_guid)
        except EvernoteApiError:
            return {"guid": note_guid, "metadataAvailable": False}

        return {
            "guid": metadata.get("guid", note_guid),
            "title": metadata.get("title"),
            "contentLength": metadata.get("contentLength"),
            "updated": metadata.get("updated"),
            "notebookGuid": metadata.get("notebookGuid"),
            "metadataAvailable": True,
        }

    def _resolve_visible_notebook_name(self, notebook_guid: str) -> str | None:
        """Return the visible notebook name for a GUID, or None when not listed."""

        for notebook in self.list_notebooks():
            if notebook.get("guid") != notebook_guid:
                continue

            notebook_name = notebook.get("name")
            if isinstance(notebook_name, str):
                return notebook_name

            return ""

        return None

    def _update_note_with_usn_match_when_available(self, note: NoteLike) -> Any:
        """Update a note with optimistic concurrency when the client supports it.

        Some Evernote client builds do not expose `updateNoteIfUsnMatches`. In
        that case, fall back to `updateNote` so anchored insertion remains usable
        instead of failing with an AttributeError before reaching Evernote.
        """

        try:
            return self._call_note_store_method("updateNoteIfUsnMatches", note)
        except EvernoteApiError as error:
            if not self._error_chain_mentions(error, "AttributeError"):
                raise

            return self._call_note_store_method("updateNote", note)

    def _error_chain_mentions(self, error: BaseException, text: str) -> bool:
        """Return whether an exception or its causes mention a text fragment."""

        current_error: BaseException | None = error
        while current_error is not None:
            if text in str(current_error):
                return True

            current_error = current_error.__cause__ or current_error.__context__

        return False

    def _serialize_updated_note(
        self,
        updated_note: Any,
        *,
        fallback_note: NoteLike,
    ) -> dict[str, Any]:
        """Serialize an updated note while preserving known updated ENML content.

        Evernote may accept an update but return a note payload with `content`
        omitted or set to `None`. Returning the in-memory updated content avoids
        misleading MCP clients into treating a successful write as dropped data.
        """

        serialized_note = cast(dict[str, Any], self._serialize_evernote_value(updated_note))
        if serialized_note.get("content") is None and fallback_note.content is not None:
            serialized_note["content"] = fallback_note.content

        return serialized_note

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
