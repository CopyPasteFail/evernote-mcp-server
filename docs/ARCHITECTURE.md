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

## 5. Security model
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

## 6. Evernote API integration: why Thrift
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

## 7. Release model
- `scripts/release.sh` is the single tag creation entrypoint.
- It requires clean, synced `main` and passing `make check` before creating an annotated tag.
- `release.yml` runs only on `v*` tags and enforces:
  1. tag commit reachable from `origin/main`
  2. checks pass (`make check`)
  3. only then image publish + GitHub Release

This design prevents off-branch or unvalidated release tags from being published.

## 8. Future improvements
- Implement SSE transport with explicit auth and origin controls; v0.1 intentionally postpones SSE so a remote surface is not shipped before auth, origin, and security boundaries are fully designed.
- Add structured JSON logging mode.
- Add focused integration tests with mocked Evernote API responses.
- Add richer tool-level input validation and error mapping.
