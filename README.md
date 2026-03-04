# evernote-mcp-server

`evernote-mcp-server` is a Python MCP server that exposes Evernote notebook and note operations over MCP `stdio`.

## What It Does

This server exposes Evernote operations as MCP tools. The current tool surface includes:

- Notebook tools: `list_notebooks`
- Read tools: `search_notes`, `get_note`, `get_note_metadata`
- Write tools: `append_to_note_plaintext`, `set_note_title`, `add_tags_by_name`, `move_note`, `create_note`, `delete_note`

## Important Defaults and Caveats

- `READ_ONLY=true` by default, so all write tools are blocked unless you opt in.
- OAuth access tokens are not stored in `.env`; they are saved in a config directory after bootstrap.
- `--transport sse` is intentionally not implemented yet. Use `--transport stdio`.

## Gemini Quick Start (Clone-Free, End Users)

This is the default path for normal users. It uses the published GHCR image and does not require cloning this repository or installing Python locally.

### Prerequisites

- bash
- curl
- Docker
- python3
- Gemini CLI
- Evernote consumer credentials (`EVERNOTE_CONSUMER_KEY`, `EVERNOTE_CONSUMER_SECRET`)

### 1. Run the end-user installer

```bash
curl -fsSL https://raw.githubusercontent.com/CopyPasteFail/evernote-mcp-server/main/scripts/install_gemini_mcp_release.sh | bash
```

The installer:

- resolves the latest GitHub release tag (`v*`)
- configures Gemini MCP settings to use `ghcr.io/CopyPasteFail/evernote-mcp-server:<tag>`
- creates `~/.config/evernote-mcp-server/evernote-mcp.env` if missing
- creates Docker volume `evernote-mcp-auth` if missing
- remains idempotent on repeated runs

### 2. Edit the env file

Open:

- `~/.config/evernote-mcp-server/evernote-mcp.env`

Set at least:

- `EVERNOTE_CONSUMER_KEY`
- `EVERNOTE_CONSUMER_SECRET`

Default template values created by installer:

- `EVERNOTE_SANDBOX=false`
- `READ_ONLY=true`

### 3. Run one-time OAuth bootstrap

The installer prints the exact command. It will look like:

```bash
docker run --rm -it --env-file ~/.config/evernote-mcp-server/evernote-mcp.env -v evernote-mcp-auth:/home/appuser/.config/evernote-mcp-server ghcr.io/CopyPasteFail/evernote-mcp-server:<tag> python -m evernote_mcp auth
```

### 4. Use Gemini CLI

After OAuth bootstrap succeeds, Gemini can run the MCP server using the installed `mcpServers` entry.

Sanity-check prompt:

`Use MCP server "evernote-mcp-server" and call list_notebooks. Return the names of 2 notebooks.`

### Persistence model

- Env file (`~/.config/evernote-mcp-server/evernote-mcp.env`) stores Evernote consumer credentials and runtime settings.
- Docker volume (`evernote-mcp-auth`) stores OAuth access token state at `/home/appuser/.config/evernote-mcp-server`.
- This avoids re-authentication on every run.

## Configuration Reference

### Environment Variables

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `EVERNOTE_CONSUMER_KEY` | Required for `auth` | None | Evernote OAuth consumer key |
| `EVERNOTE_CONSUMER_SECRET` | Required for `auth` | None | Evernote OAuth consumer secret |
| `EVERNOTE_SANDBOX` | No | `false` | Use Evernote sandbox OAuth and API endpoints |
| `READ_ONLY` | No | `true` | Block all write tools unless set to `false` |
| `LOG_LEVEL` | No | `INFO` | Process log verbosity |

Boolean values accepted for `EVERNOTE_SANDBOX` and `READ_ONLY`:

- `true` / `false`
- `1` / `0`
- `yes` / `no`
- `on` / `off`

## Runtime Paths

### Published Release Docker (End Users)

Use this for regular Gemini usage:

- image: `ghcr.io/CopyPasteFail/evernote-mcp-server:<release-tag>`
- release tags: `v*`
- installer: `scripts/install_gemini_mcp_release.sh`
- host env file: `~/.config/evernote-mcp-server/evernote-mcp.env`
- Docker token volume: `evernote-mcp-auth`

### Local Development Docker (Contributors)

Use this when iterating on code with a local image:

```bash
git clone https://github.com/CopyPasteFail/evernote-mcp-server.git
cd evernote-mcp-server
cp .env.example .env
docker build -t evernote-mcp-server:local .
python3 scripts/install_gemini_mcp.py --mode docker
```

### Local Python (Contributors)

Use this for local development, tests, and debugging:

```bash
git clone https://github.com/CopyPasteFail/evernote-mcp-server.git
cd evernote-mcp-server
cp .env.example .env
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
PYTHONPATH=src python -m evernote_mcp auth
PYTHONPATH=src python -m evernote_mcp --transport stdio
python3 scripts/install_gemini_mcp.py --mode python
```

## Contributor Workflow

### Run development checks

```bash
make lint
make security
make test
make check
```

### Enable the pre-push hook

This step makes Git use the repository’s existing pre-push hook.

```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-push
```

## Maintainer Workflow

### Create a release tag

```bash
./scripts/release.sh patch
```

Supported version bump types: `patch`, `minor`, `major`.

### Release workflow behavior

The GitHub release workflow runs only for tags matching `v*`. It verifies that the tagged commit is reachable from `origin/main`, reruns `make check`, then publishes the container image to GHCR and creates a GitHub release.

### Optional repository hardening scripts

These scripts are maintainer-only repository hardening utilities and are typically only need to be run once per repository:

Suggested one-time setup for Dependabot defaults and vulnerability alerts:

```bash
./scripts/setup-dependabot.sh
```

Suggested one-time setup for release tag protection rules:

```bash
./scripts/setup-tag-protection.sh
```

Both scripts use an authenticated GitHub CLI session to apply repository settings.

## Troubleshooting

### Missing consumer credentials

If OAuth bootstrap fails for missing credentials, verify:

- `EVERNOTE_CONSUMER_KEY`
- `EVERNOTE_CONSUMER_SECRET`

### Missing saved token

If startup fails due to missing token, run OAuth bootstrap again using the same env file and Docker volume.

### Sandbox mismatch warning

If token sandbox mode and `EVERNOTE_SANDBOX` differ, re-run OAuth bootstrap with the desired sandbox setting.

### Writes are blocked

Set `READ_ONLY=false` in the env file and restart.

### `sse` does not work

`sse` is not implemented in v0.1. Use `--transport stdio`.

## Further Reading

For architecture details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
