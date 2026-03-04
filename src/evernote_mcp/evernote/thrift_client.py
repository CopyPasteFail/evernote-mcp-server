"""Minimal Evernote EDAM Thrift-over-HTTP client.

This module intentionally bypasses the legacy Evernote SDK convenience client and
connects directly to Evernote's Thrift services. It supports developer-token
authentication only.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from types import SimpleNamespace
from typing import Any, Protocol, TypeAlias, TypeGuard, cast, runtime_checkable

EVERNOTE_USER_STORE_URL = "https://www.evernote.com/edam/user"
EVERNOTE_SANDBOX_USER_STORE_URL = "https://sandbox.evernote.com/edam/user"


@runtime_checkable
class Transport(Protocol):
    """Represent the minimal Thrift transport lifecycle used by this module."""

    def open(self) -> None:
        """Open the transport."""

    def close(self) -> None:
        """Close the transport."""


ClientWithTransport: TypeAlias = tuple[object, Transport]
ClientFactoryResult: TypeAlias = object | ClientWithTransport
ClientFactory: TypeAlias = Callable[[str], ClientFactoryResult]


def _build_binary_protocol_fallback(transport: Transport) -> SimpleNamespace:
    """Build a minimal fallback protocol object that exposes `.trans`.

    Args:
        transport: Transport instance associated with the protocol.

    Returns:
        Namespace with a `trans` attribute used by transport extraction.
    """

    return SimpleNamespace(trans=transport)


def _is_client_with_transport(candidate_client: object) -> TypeGuard[ClientWithTransport]:
    """Check whether a factory result is a `(client, transport)` tuple.

    Args:
        candidate_client: Value returned by a client factory.

    Returns:
        `True` when the value matches `(client, transport)` shape with open/close.

    Edge cases:
        The client value type is intentionally broad (`object`) because generated
        Thrift client classes are loaded dynamically.
    """

    if not isinstance(candidate_client, tuple):
        return False
    candidate_client_tuple = cast(tuple[object, ...], candidate_client)
    if len(candidate_client_tuple) != 2:
        return False
    candidate_transport = candidate_client_tuple[1]
    return isinstance(candidate_transport, Transport)


def _missing_dependency_callable(dependency_name: str) -> Callable[..., Any]:
    """Build a callable that raises a clear error for missing optional dependencies.

    Args:
        dependency_name: Package users must install to use the callable.

    Returns:
        Callable that raises `ModuleNotFoundError` when invoked.
    """

    def raise_missing_dependency(*_arguments: Any, **_keyword_arguments: Any) -> Any:
        raise ModuleNotFoundError(
            f"Missing dependency '{dependency_name}'. Install project requirements first."
        )

    return raise_missing_dependency


def _load_module_or_fallback(module_name: str, fallback_value: Any) -> Any:
    """Import a module by name and return a fallback object when unavailable.

    Args:
        module_name: Fully qualified module import path.
        fallback_value: Value returned when import fails.

    Returns:
        Imported module object, or the provided fallback value.
    """

    try:
        return import_module(module_name)
    except ModuleNotFoundError:
        return fallback_value


NoteStore = _load_module_or_fallback(
    "evernote.edam.notestore.NoteStore",
    SimpleNamespace(Client=_missing_dependency_callable("evernote3")),
)
UserStore = _load_module_or_fallback(
    "evernote.edam.userstore.UserStore",
    SimpleNamespace(Client=_missing_dependency_callable("evernote3")),
)
TBinaryProtocol = _load_module_or_fallback(
    "thrift.protocol.TBinaryProtocol",
    SimpleNamespace(TBinaryProtocol=_build_binary_protocol_fallback),
)
THttpClient = _load_module_or_fallback(
    "thrift.transport.THttpClient",
    SimpleNamespace(THttpClient=_missing_dependency_callable("thrift")),
)

NoteFilter = cast(
    Callable[..., Any],
    getattr(
        _load_module_or_fallback(
            "evernote.edam.notestore.ttypes",
            SimpleNamespace(NoteFilter=_missing_dependency_callable("evernote3")),
        ),
        "NoteFilter",
    ),
)
NotesMetadataResultSpec = cast(
    Callable[..., Any],
    getattr(
        _load_module_or_fallback(
            "evernote.edam.notestore.ttypes",
            SimpleNamespace(
                NotesMetadataResultSpec=_missing_dependency_callable("evernote3")
            ),
        ),
        "NotesMetadataResultSpec",
    ),
)
Note = cast(
    Callable[..., Any],
    getattr(
        _load_module_or_fallback(
            "evernote.edam.type.ttypes",
            SimpleNamespace(Note=_missing_dependency_callable("evernote3")),
        ),
        "Note",
    ),
)
Tag = cast(
    Callable[..., Any],
    getattr(
        _load_module_or_fallback(
            "evernote.edam.type.ttypes",
            SimpleNamespace(Tag=_missing_dependency_callable("evernote3")),
        ),
        "Tag",
    ),
)


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
        user_store_factory: ClientFactory | None = None,
        note_store_factory: ClientFactory | None = None,
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

    def build_note(self, title: str, content: str) -> Any:
        """Construct an EDAM Note value object for create/update flows.

        Args:
            title: Note title to assign.
            content: Full ENML document string to persist as the note body.

        Returns:
            Fresh EDAM `Note` struct instance with the supplied title/content.

        Edge cases:
            Additional fields such as `notebookGuid` and `tagGuids` are intentionally
            left unset so callers can apply them conditionally.
        """

        return Note(title=title, content=content)

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

    def build_tag(self, name: str) -> Any:
        """Construct an EDAM Tag value object for tag-creation flows.

        Args:
            name: Human-readable tag name.

        Returns:
            Fresh EDAM `Tag` struct instance with the supplied name.

        Edge cases:
            The object includes only the `name` field, leaving GUID assignment to
            Evernote during `createTag`.
        """

        return Tag(name=name)

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

    def _build_user_store_client(self, user_store_url: str) -> tuple[Any, Transport]:
        """Create a UserStore client and its HTTP transport for one call.

        Args:
            user_store_url: Fully qualified UserStore endpoint URL.

        Returns:
            Tuple of `(UserStore.Client, transport)` for single-call lifecycle control.
        """

        user_store_transport: Transport = THttpClient.THttpClient(user_store_url)
        user_store_protocol: Any = TBinaryProtocol.TBinaryProtocol(user_store_transport)
        return UserStore.Client(user_store_protocol), user_store_transport

    def _build_note_store_client(self, note_store_url: str) -> tuple[Any, Transport]:
        """Create a NoteStore client and its HTTP transport for one call.

        Args:
            note_store_url: Fully qualified NoteStore endpoint URL.

        Returns:
            Tuple of `(NoteStore.Client, transport)` for single-call lifecycle control.
        """

        note_store_transport: Transport = THttpClient.THttpClient(note_store_url)
        note_store_protocol: Any = TBinaryProtocol.TBinaryProtocol(note_store_transport)
        return NoteStore.Client(note_store_protocol), note_store_transport

    def _call_with_transport(
        self,
        service_url: str,
        client_factory: ClientFactory,
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

    def _extract_client_and_transport(
        self,
        built_client: ClientFactoryResult,
    ) -> tuple[Any, Transport]:
        """Resolve `(client, transport)` from client-factory output.

        Args:
            built_client: Result returned by a `user_store_factory` or `note_store_factory`.

        Returns:
            Tuple of `(client, transport)` needed for lifecycle management.

        Raises:
            ValueError: If a transport cannot be resolved from the factory output.
        """

        if _is_client_with_transport(built_client):
            service_client, service_transport = built_client
            return cast(Any, service_client), service_transport

        client_protocol = getattr(built_client, "_iprot", None) or getattr(
            built_client,
            "_oprot",
            None,
        )
        client_transport = getattr(client_protocol, "trans", None)
        if client_transport is None:
            raise ValueError("Failed to resolve Thrift transport from client factory output.")

        return built_client, cast(Transport, client_transport)
