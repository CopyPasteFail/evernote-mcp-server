"""Evernote API gateway used by MCP tool handlers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from evernote.edam.type.ttypes import Note, Tag

from evernote_mcp.evernote.enml import (
    append_plaintext_to_existing_enml,
    build_enml_document,
    escape_plaintext_for_enml,
)
from evernote_mcp.evernote.thrift_client import EvernoteThriftClient


class EvernoteApiError(RuntimeError):
    """Raised when the Evernote API layer returns an error."""


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
        """Return all notebooks visible to the authenticated account."""

        notebooks = self._run_api_call("listNotebooks", self._thrift_client.list_notebooks)
        return self._serialize_evernote_value(notebooks)

    def search_notes(
        self,
        search_query: str,
        offset: int = 0,
        max_results: int = 20,
    ) -> dict[str, Any]:
        """Search notes using Evernote's note metadata search endpoint.

        Args:
            search_query: Evernote search syntax string.
            offset: Zero-based offset into result set.
            max_results: Maximum number of notes to return.

        Returns:
            Serialized metadata search result payload.
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
        """Fetch full note details including ENML content for a note GUID."""

        note = self._run_api_call("getNote", lambda: self._thrift_client.get_note(note_guid))
        return self._serialize_evernote_value(note)

    def get_note_metadata(self, note_guid: str) -> dict[str, Any]:
        """Fetch note metadata without full content payload."""

        note = self._run_api_call(
            "getNote",
            lambda: self._thrift_client.get_note_metadata(note_guid),
        )
        return self._serialize_evernote_value(note)

    def append_to_note_plaintext(self, note_guid: str, plaintext_content: str) -> dict[str, Any]:
        """Append plaintext to the ENML body of an existing note and persist it."""

        note = self._call_note_store_method(
            "getNote",
            note_guid,
            True,
            False,
            False,
            False,
        )
        note.content = append_plaintext_to_existing_enml(note.content, plaintext_content)
        updated_note = self._call_note_store_method("updateNote", note)
        return self._serialize_evernote_value(updated_note)

    def set_note_title(self, note_guid: str, new_title: str) -> dict[str, Any]:
        """Update and persist a note's title."""

        note = self._call_note_store_method(
            "getNote",
            note_guid,
            False,
            False,
            False,
            False,
        )
        note.title = new_title
        updated_note = self._call_note_store_method("updateNote", note)
        return self._serialize_evernote_value(updated_note)

    def add_tags_by_name(self, note_guid: str, tag_names: list[str]) -> dict[str, Any]:
        """Attach tags to a note, creating missing tags by name when needed."""

        note = self._call_note_store_method(
            "getNote",
            note_guid,
            False,
            False,
            False,
            False,
        )
        existing_tag_guids = set(note.tagGuids or [])
        resolved_tag_guids = self._resolve_tag_guids_by_name(tag_names)
        note.tagGuids = sorted(existing_tag_guids.union(resolved_tag_guids))
        updated_note = self._call_note_store_method("updateNote", note)
        return self._serialize_evernote_value(updated_note)

    def move_note(self, note_guid: str, destination_notebook_guid: str) -> dict[str, Any]:
        """Move a note to another notebook and persist the update."""

        note = self._call_note_store_method(
            "getNote",
            note_guid,
            False,
            False,
            False,
            False,
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
        """Create a new note from plaintext content and optional notebook/tag metadata."""

        enml_content = build_enml_document(escape_plaintext_for_enml(plaintext_body))
        note = Note(title=title, content=enml_content)
        if notebook_guid:
            note.notebookGuid = notebook_guid

        if tag_names:
            note.tagGuids = self._resolve_tag_guids_by_name(tag_names)

        created_note = self._call_note_store_method("createNote", note)
        return self._serialize_evernote_value(created_note)

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

        existing_tags = self._run_api_call("listTags", self._thrift_client.list_tags)
        tag_guid_by_name = {
            tag.name.strip().lower(): tag.guid
            for tag in existing_tags
            if getattr(tag, "name", None) and getattr(tag, "guid", None)
        }

        resolved_tag_guids: list[str] = []
        for normalized_tag_name in normalized_tag_names:
            normalized_tag_name_key = normalized_tag_name.lower()
            existing_guid = tag_guid_by_name.get(normalized_tag_name_key)
            if existing_guid:
                resolved_tag_guids.append(existing_guid)
                continue

            created_tag = self._run_api_call(
                "createTag",
                lambda: self._thrift_client.create_tag(Tag(name=normalized_tag_name)),
            )
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
            return [self._serialize_evernote_value(item) for item in value]

        if isinstance(value, tuple):
            return tuple(self._serialize_evernote_value(item) for item in value)

        if isinstance(value, dict):
            return {
                key: self._serialize_evernote_value(item_value)
                for key, item_value in value.items()
            }

        if hasattr(value, "__dict__"):
            serializable_mapping = {
                attribute_name: self._serialize_evernote_value(attribute_value)
                for attribute_name, attribute_value in value.__dict__.items()
                if not attribute_name.startswith("_")
            }
            return serializable_mapping

        return str(value)
