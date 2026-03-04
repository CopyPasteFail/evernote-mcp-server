# evernote-mcp-server

`evernote-mcp-server` is a Python MCP server that exposes Evernote notebook and note operations over MCP `stdio`.

It is primarily documented for people who want to use it from Gemini CLI with the published Docker image. Contributor and maintainer workflows appear later in this README so the first-run path stays simple.

## Overview

This server exposes Evernote operations as MCP tools. The current tool surface includes:

- Notebook tools: `list_notebooks`
- Read tools: `search_notes`, `get_note`, `get_note_metadata`
- Write tools: `append_to_note_plaintext`, `set_note_title`, `add_tags_by_name`, `move_note`, `create_note`, `delete_note`

## Important Defaults Before You Start

- `READ_ONLY=true` by default, so write tools are blocked unless you explicitly opt in.
- One-time OAuth bootstrap is required before normal runtime startup can talk to Evernote.
- OAuth access tokens are not stored in `.env`; they are saved in the Evernote MCP config directory.
- Only `stdio` transport is implemented in v0.1. `--transport sse` is intentionally not available yet.

## Choose a Setup Path

Most people should use the released Docker path. It is the shortest route to a working Gemini MCP server and does not require cloning this repository.

- Use [Quick Start: Released Docker + Gemini](#quick-start-released-docker--gemini) if you want the default end-user setup.
- Use [Contributor Setup](#contributor-setup) if you are changing code, running tests, or debugging locally.
- Use [Troubleshooting](#troubleshooting) if setup fails after you follow the matching path below.

## Configuration and Auth Model

These settings apply across all runtime paths. Keep this section as the canonical reference for configuration behavior.

### Shared Prerequisites

Every runtime path needs the same Evernote-side prerequisites:

- Evernote consumer credentials: `EVERNOTE_CONSUMER_KEY` and `EVERNOTE_CONSUMER_SECRET`
- A browser-capable environment for one-time OAuth authorization on localhost

### Environment Variables

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `EVERNOTE_CONSUMER_KEY` | Required for `auth` | None | Evernote OAuth consumer key |
| `EVERNOTE_CONSUMER_SECRET` | Required for `auth` | None | Evernote OAuth consumer secret |
| `EVERNOTE_SANDBOX` | No | `false` | Use Evernote sandbox OAuth and API endpoints |
| `READ_ONLY` | No | `true` | Block write tools unless set to `false` |
| `LOG_LEVEL` | No | `INFO` | Process log verbosity |

Accepted boolean values for `EVERNOTE_SANDBOX` and `READ_ONLY`:

- `true` / `false`
- `1` / `0`
- `yes` / `no`
- `on` / `off`

### Config File Locations By Path

- Released Docker path uses a host env file at `~/.config/evernote-mcp-server/evernote-mcp.env`
- Contributor local paths use a repository-local `.env`, usually created from `.env.example`

### Saved Token Location and Persistence

OAuth bootstrap saves the Evernote access token in the Evernote MCP config directory, not in `.env`.

- On a normal local machine, the saved token lives at `$XDG_CONFIG_HOME/evernote-mcp-server/token.json` when `XDG_CONFIG_HOME` is set
- Otherwise it lives at `~/.config/evernote-mcp-server/token.json`
- In the released Docker path, the recommended persistence model is a Docker named volume mounted at `/home/appuser/.config/evernote-mcp-server`

This separation matters because startup reads the saved token from disk. If the token is missing, normal server startup fails until you run OAuth bootstrap again.

## Quick Start: Released Docker + Gemini

This is the recommended path for most users. It configures Gemini CLI to run the published GHCR image, creates a persistent env file if needed, and creates a Docker volume for saved OAuth state.

### Path-Specific Prerequisites

Before you run the installer, make sure these local tools are available:

- `bash`
- `curl`
- `docker`
- `python3`
- Gemini CLI

### Install the Gemini MCP Entry

Run the release installer to configure Gemini with the latest published `v*` image tag.

```bash
curl -fsSL https://raw.githubusercontent.com/CopyPasteFail/evernote-mcp-server/main/scripts/install_gemini_mcp_release.sh | bash
```

The installer does three important things for this path:

- configures Gemini MCP settings to use the published GHCR image
- creates `~/.config/evernote-mcp-server/evernote-mcp.env` if it does not exist
- creates Docker volume `evernote-mcp-auth` if it does not exist

### Fill the Env File

Edit the generated env file before you try OAuth bootstrap. At minimum, fill in the Evernote consumer credentials. Leave `READ_ONLY=true` unless you intentionally want write tools enabled.

- Env file: `~/.config/evernote-mcp-server/evernote-mcp.env`

### Run One-Time OAuth Bootstrap

After the env file is populated, run the one-time OAuth bootstrap command. The installer prints the exact command that matches the configured image tag and volume.

It will look like this:

```bash
docker run --rm -it --env-file ~/.config/evernote-mcp-server/evernote-mcp.env -v evernote-mcp-auth:/home/appuser/.config/evernote-mcp-server ghcr.io/CopyPasteFail/evernote-mcp-server:<tag> python -m evernote_mcp auth
```

OAuth bootstrap opens a browser for Evernote authorization and then saves the token into the mounted config volume so Gemini can reuse it on later runs.

## Contributor Setup

Use this path if you are iterating on code, running tests, or debugging the server locally.

### Shared Contributor Prerequisites

Pick the local runtime you want later, but the repository bootstrap is shared:

- Git
- Python 3.13
- Gemini CLI if you want Gemini to launch your local runtime
- Docker only if you choose the local Docker runtime

### Clone the Repo and Create Local Config

Clone the repository and create the local env file before choosing a runtime path.

```bash
git clone https://github.com/CopyPasteFail/evernote-mcp-server.git
cd evernote-mcp-server
cp .env.example .env
```

After that shared setup, choose one local runtime.

### Option A: Local Python Runtime

Use this path when you want the fastest edit-run-test loop and direct access to the Python process.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
PYTHONPATH=src python -m evernote_mcp auth
PYTHONPATH=src python -m evernote_mcp --transport stdio
python3 scripts/install_gemini_mcp.py --mode python
```

This path installs development dependencies, runs OAuth bootstrap against your local environment, lets you start the server directly, and optionally updates Gemini settings so Gemini can launch the local Python runtime.

### Option B: Local Docker Runtime

Use this path when you want local code changes packaged in a container while keeping the same general runtime model as Docker-based usage.

```bash
docker build -t evernote-mcp-server:local .
python3 scripts/install_gemini_mcp.py --mode docker
```

After the local image is built and Gemini settings are updated, run OAuth bootstrap against the same local Docker runtime you plan to use so the saved token is available inside the Docker-backed config directory.

## Verify the Installation

After you finish either setup path, verify the server with a simple read-only call before you try anything more complex.

Use a Gemini prompt like this:

```text
Use MCP server "evernote-mcp-server" and call list_notebooks. Return the names of 2 notebooks.
```

If that works, the MCP wiring, Evernote auth, and saved token state are all in the expected place.

A second sanity check is to keep `READ_ONLY=true` at first. That confirms write tools stay blocked until you intentionally enable them.

## Troubleshooting

### Missing Consumer Credentials

If OAuth bootstrap fails because credentials are missing, verify that both of these are set in the env file for your chosen path:

- `EVERNOTE_CONSUMER_KEY`
- `EVERNOTE_CONSUMER_SECRET`

### Missing Saved Token

If startup fails because the Evernote token is missing, run OAuth bootstrap again using the same env file and the same persistence location for your chosen path.

### Sandbox Mismatch Warning

If the saved token was created with a different sandbox setting than the current `EVERNOTE_SANDBOX` value, re-run OAuth bootstrap with the sandbox mode you actually want to use.

### Writes Are Blocked

If write tools fail, check `READ_ONLY`. The secure default is `true`, so writes remain blocked until you set `READ_ONLY=false` and restart the runtime that reads that env file.

### `sse` Does Not Work

`sse` transport is intentionally not implemented in v0.1. Use `--transport stdio`.

## Contributor Workflow

These steps are for ongoing development after your local setup already works.

### Run Development Checks

Run the full local check suite before pushing changes.

```bash
make lint
make security
make test
make check
```

### Optional Pre-Push Hook

If you want Git to run `make check` automatically before pushes to `main`, point Git at the repository hook path.

```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-push
```

## Maintainer Workflow

This section is intentionally separate from first-time setup and contributor onboarding.

### Create a Release Tag

Use the release script to create and push the next semantic version tag from `main`.

```bash
./scripts/release.sh patch
```

Supported bump types are `patch`, `minor`, and `major`.

### Release Workflow Behavior

The release process is guarded:

- releases are created only from tags matching `v*`
- the script requires a clean working tree on `main`
- the script fetches `origin/main` and refuses to continue if local `HEAD` does not match it
- `make check` must pass before the tag is created
- the GitHub release workflow verifies the tagged commit is reachable from `origin/main`, reruns `make check`, then publishes the GHCR image and GitHub release

### Optional Repository Hardening Scripts

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

## Architecture and Further Reading

This README is intentionally focused on onboarding and common workflows. For deeper design and implementation details, read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

That document covers:

- transport abstraction and the current `stdio` / future `sse` split
- how MCP tools are registered and exposed to clients
- the security model, including token persistence and write-policy enforcement
- the Evernote Thrift integration rationale
- release-model details and future improvement areas
