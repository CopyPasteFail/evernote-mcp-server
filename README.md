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
- Write tools (implemented and registered, gated by `READ_ONLY`):
  - `append_to_note_plaintext`
  - `set_note_title`
  - `add_tags_by_name`
  - `move_note`
  - `create_note`
- Pluggable transport architecture:
  - `stdio` implemented
  - `sse` planned and intentionally not implemented in v0.1
- CI checks with `ruff`, `bandit`, `pip-audit`, `pytest`
- Release flow for GHCR image publishing on `v*` tags

## 3. Security model
### Authentication
- Runtime auth uses a saved OAuth token at:
  - `~/.config/evernote-mcp-server/token.json` (default)
  - or `$XDG_CONFIG_HOME/evernote-mcp-server/token.json` if `XDG_CONFIG_HOME` is set
- First-time OAuth bootstrap requires:
  - `EVERNOTE_CONSUMER_KEY`
  - `EVERNOTE_CONSUMER_SECRET`
- Optional: `EVERNOTE_SANDBOX=true` routes OAuth and API calls to sandbox endpoints (default `false`). Sandbox availability may be limited; most users should leave it as `false`.

### Write safety
- `READ_ONLY` defaults to `true`.
- Every write tool calls shared policy enforcement first.
- When writes are blocked, tools fail with:
  - `Write operations are disabled. Set READ_ONLY=false to enable write operations.`
- Secrets are not logged.

## 4. Getting started
There are two common ways to use this repo:

- **[Local](#5-local) (recommended for development)**: fastest loop when you’re editing code and running tests.
- **[Docker](#6-docker) (recommended for users)**: closest to “install and run”, and matches how the published image is intended to be used.

Pick one. You do not need both.

### 4.1 One-time: create `.env`
```bash
cp .env.example .env
```
Edit `.env` and set `EVERNOTE_CONSUMER_KEY` and `EVERNOTE_CONSUMER_SECRET`

`.env` is auto-loaded at startup when present. Run commands from the repo root so `.env` is discovered.

### 4.2 One-time: OAuth bootstrap
You must do this once per environment where you want to run the server (your local machine, or a Docker volume).

```bash
PYTHONPATH=src python -m evernote_mcp auth
```

Behavior:
- Starts a local callback server on `127.0.0.1` with a random free port.
- Attempts to open the Evernote authorize URL automatically.
- In WSL/headless environments, browser opening can fail; the command prints the URL for manual copy/paste.
- Saves token to `~/.config/evernote-mcp-server/token.json` (or under `$XDG_CONFIG_HOME` when set) with restricted permissions.

Reset saved auth by deleting:
```bash
rm -f ~/.config/evernote-mcp-server/token.json
```

## 5. Local
Use this if you’re working on the repo (development, debugging, fast iteration).

### 5.1 Prerequisites
- Python 3.13
- WSL users: run inside WSL

### 5.2 Install
```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 5.3 Run (stdio)
```bash
PYTHONPATH=src python -m evernote_mcp --transport stdio
```

SSE in v0.1 (planned, not implemented):
```bash
PYTHONPATH=src python -m evernote_mcp --transport sse
```

## 6. Docker
Use this if you want a “just run it” experience, or you plan to use the GHCR image.

### 6.1 Build image
```bash
docker build -t evernote-mcp-server:local .
```

### 6.2 Quick run (no persistence)
Use this only to confirm the container starts. Without persistence, you’ll need to run OAuth bootstrap again for each new container.

```bash
docker run --rm -i --env-file .env \
  evernote-mcp-server:local
```

### 6.3 Persist auth (recommended)
```bash
docker volume create evernote-mcp-auth

docker run --rm -it --env-file .env \
  -v evernote-mcp-auth:/home/appuser/.config/evernote-mcp-server \
  evernote-mcp-server:local \
  python -m evernote_mcp auth

docker run --rm -i --env-file .env \
  -v evernote-mcp-auth:/home/appuser/.config/evernote-mcp-server \
  evernote-mcp-server:local
```

If you set `XDG_CONFIG_HOME`, token storage moves under that directory instead.

### 6.4 GHCR image example
```bash
docker run --rm -i --env-file .env \
  ghcr.io/<owner>/evernote-mcp-server:v0.1.0
```

## 7. Gemini CLI
Gemini CLI is the primary supported local MCP client in v0.1. Exact config shape can vary by Gemini CLI version, but the important values are:
- `command`: the Python executable used to launch the MCP server
- `args`: starts `evernote_mcp` over stdio with `-m evernote_mcp --transport stdio`
- `environment`: the server reads these values from its process environment, which can come from exported variables or the auto-loaded `.env` when launched from the repo root
  - `EVERNOTE_CONSUMER_KEY`: Evernote API consumer key
  - `EVERNOTE_CONSUMER_SECRET`: Evernote API consumer secret
  - `READ_ONLY`: optional flag that keeps write operations disabled; defaults to `true`
  - `EVERNOTE_SANDBOX`: optional flag that targets the Evernote sandbox environment; defaults to `false`

Gemini CLI settings can be user-wide in `~/.gemini/settings.json` or project-specific in `.gemini/settings.json` at the repo root.

Recommended project-specific config for WSL/Linux:
```json
{
  "mcpServers": {
    "evernote-mcp-server": {
      "command": "bash",
      "args": [
        "-lc",
        "source .venv/bin/activate && PYTHONPATH=src python -m evernote_mcp --transport stdio"
      ],
      "cwd": "/absolute/path/to/evernote-mcp-server",
      "trust": true
    }
  }
}
```

`cwd` should point at the repo root because the server auto-loads `.env` from the current working directory.

Before using Gemini CLI with this MCP server, run:
```bash
PYTHONPATH=src python -m evernote_mcp auth
```

Replace `/absolute/path/to/evernote-mcp-server` with your actual absolute repo path.

## 8. Maintainer setup
### 8.1 Clone and install dev dependencies
```bash
git clone <repo-url>
cd evernote-mcp-server
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```
Edit `.env` and set `EVERNOTE_CONSUMER_KEY` and `EVERNOTE_CONSUMER_SECRET`

### 8.2 Bootstrap auth once
```bash
PYTHONPATH=src python -m evernote_mcp auth
```

### 8.3 Enable pre-push hook
```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-push
```

Behavior:
- pushes to `main`: runs `make check` and blocks on failures
- pushes to non-`main` branches: no checks, exits successfully

### 8.4 Dependabot
```bash
chmod +x scripts/setup-dependabot.sh
./scripts/setup-dependabot.sh
```

### 8.5 Tag protection (`v*`)
```bash
chmod +x scripts/setup-tag-protection.sh
./scripts/setup-tag-protection.sh
```

If automation fails, use the script’s printed UI fallback guidance:
- Settings -> Rules -> Rulesets
- create a tag ruleset; the tag pattern is typically `v*`
- if GitHub UI requires a fully-qualified pattern, use `refs/tags/v*`
- restrict release-tag creation to maintainers/admins

## 9. Maintainer workflow
```bash
source .venv/bin/activate
make check
PYTHONPATH=src python -m evernote_mcp --transport stdio
```

Useful commands:
- `make lint`
- `make security`
- `make test`
- `make check`

## 10. Release flow
Releases are tag-driven and intentionally explicit.

```bash
source .venv/bin/activate
./scripts/release.sh patch # <patch|minor|major>
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

## 11. Contributor workflow
Contributors should:
1. create feature branches
2. open pull requests targeting `main`
3. run `make check` locally before pushing

Contributors should not run `scripts/release.sh` and should not create release tags (`v*`). Release tags are maintainer-controlled.

## 12. Troubleshooting
- `Configuration error: Missing Evernote authentication token.`
  - run `PYTHONPATH=src python -m evernote_mcp auth` with consumer key/secret set
- `Write operations are disabled. Set READ_ONLY=false to enable write operations.`
  - expected while `READ_ONLY=true`
- `SSE transport is planned but not implemented yet in v0.1. Use --transport stdio.`
  - expected for `--transport sse`
- `make security` fails on dependency vulnerabilities
  - review findings and upgrade dependencies before release

## 13. Architecture
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the transport abstraction, security model, repository layout rationale, and release design.
