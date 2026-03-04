# evernote-mcp-server

`evernote-mcp-server` is a Python MCP server that exposes Evernote notebook and note operations over MCP `stdio`.

## What It Does

This server exposes Evernote operations as MCP tools. The current tool surface includes:

- Notebook tools: `list_notebooks`
- Read tools: `search_notes`, `get_note`, `get_note_metadata`
- Write tools: `append_to_note_plaintext`, `set_note_title`, `add_tags_by_name`, `move_note`, `create_note`, `delete_note`

The server is transport-aware, but v0.1 is intentionally narrow in scope:

- `stdio` is implemented and is the supported runtime path
- `sse` is intentionally not implemented yet

## Important Defaults and Caveats

Read this section before setup so the later commands behave as expected.

- `READ_ONLY=true` by default, so all write tools are blocked unless you opt in
- The server loads `.env` from the current working directory, so run commands from the repository root
- OAuth access tokens are not stored in `.env`; they are saved in a local config directory after you run the bootstrap command
- `--transport sse` currently fails with a clear not-implemented error; use `--transport stdio`

## Choose a Setup Path

Both setup paths use the same repository checkout and the same `.env` file. They diverge only when you bootstrap OAuth and start the server.

- Use [Docker Setup](#docker-setup) if you mainly want to run the server as a container
- Use [Local Python Setup](#local-python-setup) if you are developing, debugging, or running tests in this repository

## Shared Prerequisites

These requirements apply to every setup path.

- Evernote API credentials: `EVERNOTE_CONSUMER_KEY` and `EVERNOTE_CONSUMER_SECRET`
- Network access to Evernote OAuth and API endpoints
- A browser or browser-capable environment for the one-time OAuth approval flow

## Shared Initial Setup

Start with the repository checkout and the shared environment file. This is the only part of setup that both paths have in common.

Clone the repository and enter it:

```bash
git clone <repo-url>
cd evernote-mcp-server
```

Create your local environment file from the example:

```bash
cp .env.example .env
```

Then edit `.env` and set your Evernote API credentials:

- `EVERNOTE_CONSUMER_KEY`
- `EVERNOTE_CONSUMER_SECRET`

The full configuration surface is documented once in [Configuration](#configuration).

## Configuration

Use this section as the canonical reference for environment variables and saved auth state.

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

### Token Storage

The OAuth bootstrap command saves the Evernote access token to a config directory so runtime startup does not need the token in `.env`.

Saved token location:

- `$XDG_CONFIG_HOME/evernote-mcp-server/token.json` when `XDG_CONFIG_HOME` is set
- otherwise `~/.config/evernote-mcp-server/token.json`

This matters for both setup paths:

- local runs use your normal user config directory
- Docker runs need a persistent mounted directory or named volume so the token survives container restarts

If you need to reset local auth and bootstrap again, remove the saved token file:

```bash
rm -f ~/.config/evernote-mcp-server/token.json
```

## Local Python Setup

Use this path if you are working on the codebase, running tests, or debugging local behavior.

### Install the local development environment

This step creates a virtual environment and installs both runtime and development dependencies. It applies only to the local path.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### Run the one-time OAuth bootstrap locally

This step authorizes the application against Evernote and saves the token to your local config directory. You only need to do this again if you remove the saved token or switch auth state.

```bash
PYTHONPATH=src python -m evernote_mcp auth
```

### Start the local MCP server

This starts the supported `stdio` transport from your local Python environment.

```bash
PYTHONPATH=src python -m evernote_mcp --transport stdio
```

## Docker Setup

Use this path if you want to run the server as a container and keep local Python tooling out of the way. This is the more direct runtime path for most non-contributors.

### Build the image or choose a published image

If you are running from this repository, build the local image first:

```bash
docker build -t evernote-mcp-server:local .
```

If you prefer a published image instead, you can use `ghcr.io/<owner>/evernote-mcp-server:<tag>` in the later run commands.

### Create persistent token storage

This step creates a named volume so the OAuth token survives container restarts. Without persistent storage, you would need to repeat the interactive auth flow.

```bash
docker volume create evernote-mcp-auth
```

### Run the one-time OAuth bootstrap in Docker

This step authorizes the containerized runtime and saves the token into the same named volume used at runtime.

```bash
docker run --rm -it --env-file .env \
  -v evernote-mcp-auth:/home/appuser/.config/evernote-mcp-server \
  evernote-mcp-server:local \
  python -m evernote_mcp auth
```

### Start the server container

This starts the supported `stdio` transport using the same `.env` file and the same persistent token volume.

```bash
docker run --rm -i --env-file .env \
  -v evernote-mcp-auth:/home/appuser/.config/evernote-mcp-server \
  evernote-mcp-server:local
```

If you are using a published image instead of a locally built one, use the same volume and env-file pattern with the published image tag:

```bash
docker run --rm -i --env-file .env \
  -v evernote-mcp-auth:/home/appuser/.config/evernote-mcp-server \
  ghcr.io/<owner>/evernote-mcp-server:v0.1.0
```

## Verify It Works

Once you finish either setup path, verify behavior before connecting an MCP client.

Expected results:

- the OAuth bootstrap command ends with a success message that includes the token file path
- the `stdio` server starts without configuration errors and waits for MCP traffic
- write tools remain blocked until you explicitly set `READ_ONLY=false`

If you installed the local development environment, run the repository checks from the repo root to verify the codebase state as well:

```bash
source .venv/bin/activate
make check
```

### Basic sanity check (Gemini)

After you install the Gemini MCP config, you can run the following prompt in Gemini CLI to test the MCP:

`Use MCP server "evernote-mcp-server" and call list_notebooks. Return the names of 2 notebooks`

### Install Gemini MCP config (idempotent)

Use the installer script to create or update the `mcpServers` entry without duplicating it on repeated runs.

Install for local Python development mode into user-wide Gemini settings (default path is `~/.gemini/settings.json`):

```bash
python3 scripts/install_gemini_mcp.py --mode python
```

Install for Docker mode into user-wide Gemini settings:

```bash
python3 scripts/install_gemini_mcp.py --mode docker
```

Install into project-local Gemini settings instead:

```bash
python3 scripts/install_gemini_mcp.py --mode python --settings-path .gemini/settings.json
```

Common optional flags:

- `--server-name` to change the key under `mcpServers` (default: `evernote-mcp-server`)
- `--repo-path` to override Gemini `cwd` (default: this repository root)
- `--docker-image` and `--docker-volume` to customize Docker mode command

## Use with an MCP Client

Use this section after the server itself is working. The repository currently documents Gemini CLI because it is the primary supported MCP client for v0.1.

Gemini settings can be project-local in `.gemini/settings.json` or user-wide in `~/.gemini/settings.json`.

### Gemini CLI with Local Python

Use this when Gemini should start the server from your local virtual environment.

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

### Gemini CLI with Docker

Use this when Gemini should start the server through Docker instead of a local Python environment.

```json
{
  "mcpServers": {
    "evernote-mcp-server": {
      "command": "bash",
      "args": [
        "-lc",
        "docker run --rm -i --env-file .env -v evernote-mcp-auth:/home/appuser/.config/evernote-mcp-server evernote-mcp-server:local"
      ],
      "cwd": "/absolute/path/to/evernote-mcp-server",
      "trust": true
    }
  }
}
```

## Contributor Workflow

This section is for repository contributors. It is separate from first-run usage so new runtime users do not have to sort through development tasks.

### Run development checks

These commands use the local Python environment and are the standard contributor verification workflow.

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

This section is for release and repository administration work. Keep it out of the initial setup flow unless you maintain this repository.

### Create a release tag

The release script is the canonical release entrypoint. It requires:

- a clean working tree
- the current branch to be `main`
- `HEAD` to match `origin/main`
- passing `make check`

Use one of the supported bump types to create and push the next annotated tag:

```bash
./scripts/release.sh patch
```

Supported version bump types are `patch`, `minor`, and `major`.

### Understand the release workflow

The GitHub release workflow runs only for tags matching `v*`. It verifies that the tagged commit is reachable from `origin/main`, reruns `make check`, then publishes the container image to GHCR and creates a GitHub release.

### Optional repository hardening scripts

These scripts are maintainer utilities, not part of normal development or runtime setup.

Set up Dependabot defaults and vulnerability alerts:

```bash
./scripts/setup-dependabot.sh
```

Apply release tag protection rules:

```bash
./scripts/setup-tag-protection.sh
```

Both scripts expect an authenticated GitHub CLI session.

## Troubleshooting

Use this section when setup or startup does not behave as expected.

### Missing consumer credentials

If `python -m evernote_mcp auth` fails with a configuration error about missing variables, check that `.env` contains:

- `EVERNOTE_CONSUMER_KEY`
- `EVERNOTE_CONSUMER_SECRET`

and that you are running the command from the repository root so `.env` is loaded.

### Missing saved token

If server startup fails because the Evernote authentication token is missing, the OAuth bootstrap has not been completed for the current environment or token storage location. Run the `auth` command again for your chosen setup path.

### Sandbox mismatch warning

If the server warns that the saved token sandbox setting does not match `EVERNOTE_SANDBOX`, the token was created under a different sandbox mode than the current runtime configuration. Re-run the OAuth bootstrap with the desired `EVERNOTE_SANDBOX` value.

### Writes are blocked

If write tools fail with a message that write operations are disabled, set `READ_ONLY=false` in `.env` and restart the server. The default is intentionally conservative.

### `.env` is not being picked up

The process only auto-loads `.env` from the current working directory. Start commands from the repository root, or export the variables in your shell yourself.

### `sse` does not work

`sse` is not implemented in v0.1. Use `--transport stdio`.

## Further Reading

For implementation details and design rationale beyond setup and day-to-day workflows, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
