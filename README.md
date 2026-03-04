# evernote-mcp-server

## 1. Project overview
`evernote-mcp-server` is a production-style MCP server for Evernote, implemented in Python 3.13 with `fastmcp`.

The server is designed for:
- Secure defaults (`READ_ONLY=true`)
- Local usage over stdio, with Gemini CLI as the primary supported MCP client in v0.1
- Distribution as a Docker image via GHCR
- Clean transport separation so SSE can be added later without rewriting tool logic

> v0.1 implements stdio only.

## 2. Features
- Read tools:
  - `list_notebooks`
  - `search_notes`
  - `get_note`
  - `get_note_metadata`
- Write tools (implemented and registered):
  - `append_to_note_plaintext`
  - `set_note_title`
  - `add_tags_by_name`
  - `move_note`
  - `create_note`
- Write gating with one env var:
  - `READ_ONLY=true` by default
- Pluggable transport architecture:
  - `stdio` implemented
  - `sse` planned and intentionally not implemented in v0.1
- CI checks with `ruff`, `bandit`, `pip-audit`, `pytest`
- Release flow for GHCR image publishing on `v*` tags

## 3. Security model
- Server startup reads only the saved OAuth token at `~/.config/evernote-mcp-server/token.json`.
- First-time OAuth bootstrap requires:
  - `EVERNOTE_CONSUMER_KEY`
  - `EVERNOTE_CONSUMER_SECRET`
- Optional: `EVERNOTE_SANDBOX=true` switches Evernote API calls to sandbox endpoints (default `false`). Sandbox availability may be limited or deprecated; most users should leave this as default false.

- `READ_ONLY` defaults to `true`.
- Every write tool calls shared policy enforcement first.
- When writes are blocked, tools fail with:
  - `Write operations are disabled. Set READ_ONLY=false to enable write operations.`
- Secrets are not logged.

## 4. Quickstart for users
### Prerequisites
- Python 3.13
- Evernote OAuth app credentials (`EVERNOTE_CONSUMER_KEY`, `EVERNOTE_CONSUMER_SECRET`) for first-time bootstrap
- For Windows users: run these commands inside WSL (confirmed with Ubuntu)

### Local Python usage (stdio)
```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and set EVERNOTE_CONSUMER_KEY / EVERNOTE_CONSUMER_SECRET
PYTHONPATH=src python -m evernote_mcp auth
PYTHONPATH=src python -m evernote_mcp
```

`.env` is auto-loaded at startup when present, and existing environment variables still take precedence. Run commands from the repo root so `.env` is discovered.

### First-time auth
Run OAuth bootstrap once to acquire and persist the Evernote access token:
```bash
PYTHONPATH=src python -m evernote_mcp auth
```

Behavior:
- Starts a local callback server on `127.0.0.1` with a random free port.
- Attempts to open the Evernote authorize URL automatically.
- In WSL or headless environments, browser opening can fail; the command prints the URL for manual copy/paste.
- Saves token to `~/.config/evernote-mcp-server/token.json` with restricted permissions.

Reset saved auth by deleting:
```bash
rm -f ~/.config/evernote-mcp-server/token.json
```

Explicit stdio selection:
```bash
python -m evernote_mcp --transport stdio
```

SSE in v0.1 (planned, not implemented):
```bash
python -m evernote_mcp --transport sse
```
This exits with a clear not-yet-implemented message.

### Gemini CLI over stdio
Gemini CLI is the primary supported local MCP client in v0.1. Exact MCP client configuration shape can vary by Gemini CLI version, but the important values are:
- command: `python`
- args: `-m evernote_mcp --transport stdio`
- environment: OAuth consumer credentials for first-time bootstrap, optional `READ_ONLY` (defaults to true)

### Docker usage
```bash
docker build -t evernote-mcp-server:local .

# Recommended: pass vars with an env file
docker run --rm -i --env-file .env \
  evernote-mcp-server:local
```
Without a persisted volume, you'll need to re-run `python -m evernote_mcp auth` for each new container.

#### Persist OAuth token with a Docker named volume

1. Create a named volume for persisted auth state
    ```bash
    docker volume create evernote-mcp-auth
    ```

2. Run one-time OAuth bootstrap with the named volume mounted
    ```bash
    docker run --rm -it --env-file .env \
      -v evernote-mcp-auth:/home/appuser/.config/evernote-mcp-server \
      evernote-mcp-server:local \
      python -m evernote_mcp auth
    ```

3. Run the server with the same named volume mounted
    ```bash
    docker run --rm -i --env-file .env \
      -v evernote-mcp-auth:/home/appuser/.config/evernote-mcp-server \
      evernote-mcp-server:local
    ```
If you set `XDG_CONFIG_HOME`, token storage moves under that directory instead.

GHCR image example:
```bash
docker run --rm -i --env-file .env \
  ghcr.io/<owner>/evernote-mcp-server:v0.1.0
```

## 5. One-time maintainer setup
### Clone and install tools
```bash
git clone <repo-url>
cd evernote-mcp-server
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```
Edit `.env` and set `EVERNOTE_CONSUMER_KEY` and `EVERNOTE_CONSUMER_SECRET`, and then run auth once

### Enable repository pre-push hook
```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-push
```

Behavior:
- pushes to `main`: runs `make check` and blocks on failures
- pushes to non-`main` branches: no checks, exits successfully

### Configure Dependabot and security alerts
```bash
chmod +x scripts/setup-dependabot.sh
./scripts/setup-dependabot.sh
```

### Configure tag protection (`v*`)
```bash
chmod +x scripts/setup-tag-protection.sh
./scripts/setup-tag-protection.sh
```

If automation fails, use the script’s printed UI fallback guidance:
- Settings -> Rules -> Rulesets
- create a tag ruleset; the tag pattern is typically `v*`
- if GitHub UI requires a fully-qualified pattern, use `refs/tags/v*`
- restrict release-tag creation to maintainers/admins

## 6. Regular maintainer development flow
```bash
source .venv/bin/activate
# Ensure .env exists (copy from .env.example) and includes auth settings.
# Run commands from the repository root so .env is discovered.

make check
PYTHONPATH=src python -m evernote_mcp --transport stdio
```

Useful commands:
- `make lint`
- `make security`
- `make test`
- `make check`

## 7. Release flow
Releases are tag-driven and intentionally explicit.

```bash
source .venv/bin/activate
./scripts/release.sh patch
# or: ./scripts/release.sh minor
# or: ./scripts/release.sh major
```

`./scripts/release.sh` does all of the following:
1. requires one argument: `patch|minor|major`
2. verifies clean working tree
3. verifies current branch is `main`
4. fetches `origin/main` and tags
5. verifies `HEAD == origin/main`
6. runs `make check`
7. computes next `vX.Y.Z` tag
8. creates an annotated tag
9. pushes only the tag

The GitHub `release.yml` workflow then:
1. runs on `v*` tags
2. verifies tag commit is reachable from `origin/main`
3. runs `make check`
4. builds and publishes GHCR image tags (`vX.Y.Z`, `latest`)
5. creates a GitHub Release

## 8. Contributor workflow
Contributors should:
1. create feature branches
2. open pull requests targeting `main`
3. run `make check` locally before pushing

Contributors should not run `scripts/release.sh` and should not create release tags (`v*`). Release tags are maintainer-controlled.

## 9. Troubleshooting
- `Configuration error: Missing Evernote authentication token.`
  - run `PYTHONPATH=src python -m evernote_mcp auth` with consumer key/secret set
- `Write operations are disabled. Set READ_ONLY=false to enable write operations.`
  - expected while `READ_ONLY=true`
- `SSE transport is planned but not implemented yet in v0.1. Use --transport stdio.`
  - expected for `--transport sse`
- `make security` fails on dependency vulnerabilities
  - review findings and upgrade dependencies before release

## 10. Architecture
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the transport abstraction, security model, repository layout rationale, and release design.
