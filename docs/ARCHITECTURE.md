# Architecture

## 1. Design goals
- Keep the server portfolio-quality and maintainable.
- Default to safe behavior (`READ_ONLY=true`).
- Support local stdio MCP usage now.
- Keep transport pluggable so SSE can be added later without changing tool logic.
- Keep release and operational workflows explicit and auditable.

## 2. System overview
The server process loads config from environment, builds a shared Evernote gateway, registers MCP tools, and runs a selected transport.

Main flow:
1. parse env config (OAuth token file, `READ_ONLY`, optional logging)
2. set policy mode (`read-only` by default)
3. register read and write MCP tools
4. run transport (`stdio` implemented)

## 3. Repository structure
- `src/evernote_mcp/core`: config, policy, and logging primitives
- `src/evernote_mcp/evernote`: Evernote API wrapper and ENML helpers
- `src/evernote_mcp/tools`: MCP tool registration split by domain and capability
- `src/evernote_mcp/transport`: transport runners (`stdio` now, `sse` placeholder)
- `tests`: focused unit tests for config and policy behavior
- `.github/workflows`: CI and guarded release automation
- `scripts`: operational helper scripts for release and repository hardening

This structure isolates tool logic from transport logic, so adding SSE later should not require changes in the tool modules.

## 4. Transport abstraction
The architecture is intentionally transport-agnostic: tool modules and Evernote logic do not depend on a specific transport. In v0.1, only stdio is implemented in `transport/stdio.py`.

`transport/sse.py` exists intentionally as a placeholder. CLI accepts `--transport sse` but returns a clear not-implemented error. SSE is deliberately deferred in v0.1, and adding it later should not require changes to Evernote logic or tool modules.

## 5. MCP tool model and capability discovery
`src/evernote_mcp/server.py` builds the FastMCP server and registers tool modules. That registration step is where the server's MCP capability surface is defined. MCP clients do not infer what the server can do from Evernote itself. They learn it from the tools exposed by FastMCP.

In practice, every `@mcp_server.tool(...)` decorator adds one callable MCP capability. For write operations, `src/evernote_mcp/tools/write_notes.py` currently exposes:
- `append_to_note_plaintext`
- `set_note_title`
- `add_tags_by_name`
- `move_note`
- `create_note`
- `delete_note`

Those names, together with the read and notebook tools registered from the other modules, are what an MCP client such as Gemini CLI receives when it asks the server for available tools.

FastMCP derives tool metadata directly from the Python function:
- Tool name comes from the decorator argument, for example `@mcp_server.tool(name="append_to_note_plaintext")`.
- Tool description comes from the function docstring.
- Tool input schema comes from the function signature and type hints.
- Return typing is only loosely described here because the handlers currently return plain `dict` values rather than a stricter typed model.

For example, this handler:

```python
@mcp_server.tool(name="append_to_note_plaintext")
def append_to_note_plaintext(note_guid: str, plaintext_content: str) -> dict:
    """Append plaintext content to an existing note body."""
```

produces MCP tool metadata equivalent to:
- name: `append_to_note_plaintext`
- description: append plaintext content to an existing note body
- inputs:
  - `note_guid: string`
  - `plaintext_content: string`

This means the Python function acts as the tool manifest. There is no separate JSON schema file or handwritten capability catalog.

### 5.1 How clients choose tools
When an MCP client connects, it performs the normal MCP handshake and requests the tool list from the server. FastMCP responds with the registered tool definitions and schemas. The client then uses that list as its available action set.

For example, if a user asks to add tags to a note, a client such as Gemini CLI can match that request to `add_tags_by_name(note_guid, tag_names)` because:
- the tool name is semantically aligned with the request
- the description explains that tags are attached by name
- the argument schema makes the required inputs explicit

The important architectural point is that tool selection is driven by the registered MCP metadata, not by implicit Evernote knowledge inside the client.

### 5.2 Why write policy enforcement lives in the server
Write protection is enforced inside the tool handlers, not delegated to client prompting behavior. Every mutating note tool calls `_enforce_write_policy()`, which delegates to `require_writes_enabled()` in `src/evernote_mcp/core/policies.py`.

That gives the server final authority over mutations:
- a client may attempt to call `create_note`
- the server checks `READ_ONLY`
- if writes are disabled, the server raises `WriteAccessError` with a clear message

This is an enforcement boundary, not a hint. Clients can learn from the returned error and adapt their future behavior, but the permission decision is always made server-side.

### 5.3 Why the tool functions are nested
`register_write_note_tools(...)` defines the handlers as nested functions so each tool can close over shared dependencies without relying on module-level mutable globals.

The nested handlers capture:
- `evernote_gateway`, which performs the actual Evernote operation
- `_enforce_write_policy()`, which applies the shared write gate

This keeps registration explicit, preserves dependency injection, and makes `build_mcp_server(...)` easy to test with a substituted gateway instance.

### 5.4 Stable MCP contract over mutable Evernote internals
The MCP handlers are intentionally thin wrappers. They translate:

1. MCP tool call (`name + arguments`)
2. into an `EvernoteGateway` method call
3. which then uses the Thrift client
4. which finally calls Evernote

This layering keeps the external MCP contract stable even if Evernote-specific implementation details change. Tool names, descriptions, and schemas form the client-facing API surface; `EvernoteGateway` and the Thrift layer remain internal implementation details.

## 6. Security model
- Runtime auth token source:
  - Saved OAuth token file at `$XDG_CONFIG_HOME/evernote-mcp-server/token.json` when `XDG_CONFIG_HOME` is set; otherwise `~/.config/evernote-mcp-server/token.json`
- OAuth bootstrap credentials for first-time auth:
  - `EVERNOTE_CONSUMER_KEY`
  - `EVERNOTE_CONSUMER_SECRET`
- Write gate: `READ_ONLY` (default `true`).
- Every write tool calls centralized policy enforcement before mutation.
- Blocked writes raise a clear message:
  - `Write operations are disabled. Set READ_ONLY=false to enable write operations.`
- No secret logging.

The default state is read-only, which limits accidental destructive behavior in local and shared environments.

## 7. Evernote API integration: why Thrift
Evernote Cloud API endpoints are exposed as EDAM Thrift services (`UserStore` and `NoteStore`).  
This server now calls those services directly over HTTPS using a small Thrift client layer.

Why this design:
- The legacy Python SDK client wrapper depends on an old oauth2 chain that is unreliable on modern Python (including Python 3.13).
- OAuth bootstrapping is implemented once in a dedicated CLI command (`python -m evernote_mcp auth`) and token persistence layer.
- Runtime API calls continue to use a single EDAM authentication token, independent of how that token was obtained.
- A thin Thrift client keeps dependencies smaller and behavior explicit.
- Optional sandbox (deprecated) routing is supported through `EVERNOTE_SANDBOX=true` for development/testing accounts.

Token storage is intentionally separated from `.env`:
- `.env` is convenient for configuration and bootstrap credentials.
- OAuth access tokens are persisted in the config directory (`$XDG_CONFIG_HOME/evernote-mcp-server` or default `~/.config/evernote-mcp-server`) with restricted file permissions.
- Container deployments should persist that config directory; a Docker named volume is the recommended default.
- This allows one-time interactive auth and non-interactive runtime startup without repeatedly copying secrets into `.env`.

In simple terms:
- Thrift is a schema + RPC system.
- Evernote defines service methods and data types in that schema.
- Our code uses generated EDAM types and calls those methods over HTTP.
- This is still Evernote’s official API, just without the outdated wrapper layer.

## 8. Release model
- `scripts/release.sh` is the single tag creation entrypoint.
- It requires clean, synced `main` and passing `make check` before creating an annotated tag.
- `release.yml` runs only on `v*` tags and enforces:
  1. tag commit reachable from `origin/main`
  2. checks pass (`make check`)
  3. only then image publish + GitHub Release

This design prevents off-branch or unvalidated release tags from being published.

## 9. Future improvements
- Implement SSE transport with explicit auth and origin controls; v0.1 intentionally postpones SSE so a remote surface is not shipped before auth, origin, and security boundaries are fully designed.
- Add structured JSON logging mode.
- Add focused integration tests with mocked Evernote API responses.
- Add richer tool-level input validation and error mapping.
