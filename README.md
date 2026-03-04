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
- `EVERNOTE_TOKEN` is required at startup.
- `READ_ONLY` defaults to `true`.
- Every write tool calls shared policy enforcement first.
- When writes are blocked, tools fail with:
  - `Write operations are disabled. Set READ_ONLY=false to enable write operations.`
- Secrets are not logged.

## 4. Quickstart for users
### Prerequisites
- Python 3.13
- Evernote token (`EVERNOTE_TOKEN`)
- For Windows users: run these commands inside WSL (confirmed with Ubuntu)

### Local Python usage (stdio)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and set EVERNOTE_TOKEN (READ_ONLY defaults to true)
export PYTHONPATH=src

python -m evernote_mcp
```

`.env` is auto-loaded at startup when present. Existing environment variables are preserved (for example shell exports, Docker `-e`, or CI variables). It is loaded from the current working directory, so run commands from the repo root (or mount `.env` to `/app/.env` in Docker as shown below).

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
- environment: `EVERNOTE_TOKEN`, optional `READ_ONLY` (defaults to true)

### Docker usage
```bash
docker build -t evernote-mcp-server:local .

# Option 1: pass vars with an env file
docker run --rm -i --env-file .env \
  evernote-mcp-server:local

# Option 2: mount .env to /app/.env for automatic dotenv loading
docker run --rm -i \
  -v "$(pwd)/.env:/app/.env:ro" \
  evernote-mcp-server:local
```

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
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
# Edit .env and set EVERNOTE_TOKEN
```

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
- create a tag ruleset for `v*`
- restrict release-tag creation to maintainers/admins

## 6. Regular maintainer development flow
```bash
source .venv/bin/activate
export EVERNOTE_TOKEN="your-token"
export READ_ONLY=true
export PYTHONPATH=src

make check
python -m evernote_mcp --transport stdio
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
- `Configuration error: Missing required environment variable: EVERNOTE_TOKEN.`
  - set `EVERNOTE_TOKEN` before starting the server
- `Write operations are disabled. Set READ_ONLY=false to enable write operations.`
  - expected while `READ_ONLY=true`
- `SSE transport is planned but not implemented yet in v0.1. Use --transport stdio.`
  - expected for `--transport sse`
- `make security` fails on dependency vulnerabilities
  - review findings and upgrade dependencies before release

## 10. Architecture
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the transport abstraction, security model, repository layout rationale, and release design.
