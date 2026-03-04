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
1. parse env config (`EVERNOTE_TOKEN`, `READ_ONLY`, optional logging)
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
v0.1 implements stdio only in `transport/stdio.py`.

`transport/sse.py` exists intentionally as a placeholder. CLI accepts `--transport sse` but returns a clear not-implemented error. This keeps the CLI and module layout future-proof while preventing partial or insecure SSE behavior in v0.1.

## 5. Security model
- Required secret: `EVERNOTE_TOKEN`.
- Write gate: `READ_ONLY` (default `true`).
- Every write tool calls centralized policy enforcement before mutation.
- Blocked writes raise a clear message:
  - `Set READ_ONLY=false to enable write operations.`
- No secret logging.

The default state is read-only, which limits accidental destructive behavior in local and shared environments.

## 6. Release model
- `scripts/release.sh` is the single tag creation entrypoint.
- It requires clean, synced `main` and passing `make check` before creating an annotated tag.
- `release.yml` runs only on `v*` tags and enforces:
  1. tag commit reachable from `origin/main`
  2. checks pass (`make check`)
  3. only then image publish + GitHub Release

This design prevents off-branch or unvalidated release tags from being published.

## 7. Future improvements
- Implement SSE transport with explicit auth and origin controls.
- Add structured JSON logging mode.
- Add focused integration tests with mocked Evernote API responses.
- Add richer tool-level input validation and error mapping.
