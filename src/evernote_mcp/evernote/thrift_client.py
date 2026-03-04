"""Minimal Evernote EDAM Thrift-over-HTTP client.

This module intentionally bypasses the legacy Evernote SDK convenience client and
connects directly to Evernote's Thrift services. It supports developer-token
authentication only.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from evernote.edam.notestore import NoteStore
from evernote.edam.notestore.ttypes import NoteFilter, NotesMetadataResultSpec
from evernote.edam.userstore import UserStore
from thrift.protocol import TBinaryProtocol
from thrift.transport import THttpClient

EVERNOTE_USER_STORE_URL = "https://www.evernote.com/edam/user"
EVERNOTE_SANDBOX_USER_STORE_URL = "https://sandbox.evernote.com/edam/user"


class EvernoteThriftClient:
    """Execute Evernote EDAM API calls over Thrift/HTTP.

    Args:
        authentication_token: Evernote developer token.
        is_sandbox: Whether to use Evernote's sandbox environment.
        note_store_url: Optional explicit NoteStore URL override.
        user_store_factory: Optional injected factory for UserStore client creation.
        note_store_factory: Optional injected factory for NoteStore client creation.

    Inputs and outputs:
        Public methods return raw EDAM/Thrift objects from Evernote service methods.

    Edge cases:
        If `note_store_url` is omitted, the constructor discovers it using UserStore.

    Concurrency:
        This client is effectively stateless after initialization and creates a fresh
        Thrift transport/client per call. It does not share open transports across
        calls, which avoids cross-call state leakage.
    """

    def __init__(
        self,
        authentication_token: str,
        is_sandbox: bool = False,
        note_store_url: str | None = None,
        user_store_factory: Callable[[str], Any] | None = None,
        note_store_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self._authentication_token = authentication_token
        self._is_sandbox = is_sandbox
        self._user_store_factory = user_store_factory or self._build_user_store_client
        self._note_store_factory = note_store_factory or self._build_note_store_client
        self._note_store_url = note_store_url or self._discover_note_store_url()

    def list_notebooks(self) -> Any:
        """Return notebooks visible to the authenticated account."""

        return self.call_note_store_method("listNotebooks")

    def search_notes_metadata(self, search_query: str, offset: int, max_results: int) -> Any:
        """Search note metadata using Evernote's query syntax.

        Args:
            search_query: Evernote search syntax string.
            offset: Zero-based result offset.
            max_results: Maximum number of notes to return.
        """

        note_filter = NoteFilter(words=search_query)
        metadata_spec = NotesMetadataResultSpec(
            includeTitle=True,
            includeCreated=True,
            includeUpdated=True,
            includeNotebookGuid=True,
            includeTagGuids=True,
        )

        return self.call_note_store_method(
            "findNotesMetadata",
            note_filter,
            offset,
            max_results,
            metadata_spec,
        )

    def get_note(self, note_guid: str, with_content: bool = True) -> Any:
        """Fetch a note with configurable content inclusion."""

        return self.call_note_store_method(
            "getNote",
            note_guid,
            with_content,
            False,
            False,
            False,
        )

    def get_note_metadata(self, note_guid: str) -> Any:
        """Fetch note metadata without ENML content payload."""

        return self.get_note(note_guid=note_guid, with_content=False)

    def update_note(self, note: Any) -> Any:
        """Persist an existing note update."""

        return self.call_note_store_method("updateNote", note)

    def create_note(self, note: Any) -> Any:
        """Create a new note."""

        return self.call_note_store_method("createNote", note)

    def delete_note(self, note_guid: str) -> Any:
        """Move a note to trash using its GUID.

        Args:
            note_guid: Evernote note GUID for the note to soft-delete.

        Returns:
            Evernote deleteNote response payload, typically an update sequence
            number.
        """

        return self.call_note_store_method("deleteNote", note_guid)

    def list_tags(self) -> Any:
        """Return tags visible to the authenticated account."""

        return self.call_note_store_method("listTags")

    def create_tag(self, tag: Any) -> Any:
        """Create a tag with the supplied EDAM Tag object."""

        return self.call_note_store_method("createTag", tag)

    def call_note_store_method(self, method_name: str, *arguments: Any) -> Any:
        """Invoke an arbitrary NoteStore method with token-first authentication.

        Args:
            method_name: Name of the NoteStore method on the generated client.
            *arguments: Method arguments excluding the auth token.

        Returns:
            Raw response returned by the underlying NoteStore method.

        Edge cases:
            Raises `AttributeError` when the requested method is unavailable.
        """

        return self._call_with_transport(
            service_url=self._note_store_url,
            client_factory=self._note_store_factory,
            service_call=lambda note_store_client: getattr(note_store_client, method_name)(
                self._authentication_token,
                *arguments,
            ),
        )

    def _discover_note_store_url(self) -> str:
        """Resolve the account-specific NoteStore URL via UserStore."""

        user_store_url = self._resolve_user_store_url()
        return self._call_with_transport(
            service_url=user_store_url,
            client_factory=self._user_store_factory,
            service_call=lambda user_store_client: user_store_client.getNoteStoreUrl(
                self._authentication_token
            ),
        )

    def _resolve_user_store_url(self) -> str:
        """Return the base UserStore URL for production or sandbox."""

        if self._is_sandbox:
            return EVERNOTE_SANDBOX_USER_STORE_URL
        return EVERNOTE_USER_STORE_URL

    def _build_user_store_client(self, user_store_url: str) -> tuple[UserStore.Client, Any]:
        """Create a UserStore client and its HTTP transport for one call.

        Args:
            user_store_url: Fully qualified UserStore endpoint URL.

        Returns:
            Tuple of `(UserStore.Client, transport)` for single-call lifecycle control.
        """

        user_store_transport = THttpClient.THttpClient(user_store_url)
        user_store_protocol = TBinaryProtocol.TBinaryProtocol(user_store_transport)
        return UserStore.Client(user_store_protocol), user_store_transport

    def _build_note_store_client(self, note_store_url: str) -> tuple[NoteStore.Client, Any]:
        """Create a NoteStore client and its HTTP transport for one call.

        Args:
            note_store_url: Fully qualified NoteStore endpoint URL.

        Returns:
            Tuple of `(NoteStore.Client, transport)` for single-call lifecycle control.
        """

        note_store_transport = THttpClient.THttpClient(note_store_url)
        note_store_protocol = TBinaryProtocol.TBinaryProtocol(note_store_transport)
        return NoteStore.Client(note_store_protocol), note_store_transport

    def _call_with_transport(
        self,
        service_url: str,
        client_factory: Callable[[str], Any],
        service_call: Callable[[Any], Any],
    ) -> Any:
        """Execute one Thrift API call with explicit transport open/close lifecycle.

        Args:
            service_url: Target service URL for `UserStore` or `NoteStore`.
            client_factory: Factory that builds either a client or `(client, transport)`.
            service_call: Callable that executes exactly one API method on the client.

        Returns:
            Raw value returned by `service_call`.

        Edge cases:
            If the factory returns only a client, transport is resolved from the
            client's protocol transport fields for backward compatibility.

        Concurrency:
            A fresh transport is used per call; no open transports are shared.
        """

        built_client = client_factory(service_url)
        service_client, service_transport = self._extract_client_and_transport(built_client)

        service_transport.open()
        try:
            return service_call(service_client)
        finally:
            service_transport.close()

    def _extract_client_and_transport(self, built_client: Any) -> tuple[Any, Any]:
        """Resolve `(client, transport)` from client-factory output.

        Args:
            built_client: Result returned by a `user_store_factory` or `note_store_factory`.

        Returns:
            Tuple of `(client, transport)` needed for lifecycle management.

        Raises:
            ValueError: If a transport cannot be resolved from the factory output.
        """

        if isinstance(built_client, tuple) and len(built_client) == 2:
            return built_client

        client_protocol = getattr(built_client, "_iprot", None) or getattr(
            built_client,
            "_oprot",
            None,
        )
        client_transport = getattr(client_protocol, "trans", None)
        if client_transport is None:
            raise ValueError("Failed to resolve Thrift transport from client factory output.")

        return built_client, client_transport
