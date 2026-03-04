#!/usr/bin/env python3
"""Install or update Gemini MCP server settings for evernote-mcp-server.

This script edits a Gemini settings JSON file and ensures a single MCP server
entry exists for this repository. It supports two runtime modes:
- `python`: run from local virtualenv/development environment
- `docker`: run through a Docker container

The operation is idempotent: running the script multiple times with the same
inputs produces the same resulting settings content.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_SERVER_NAME = "evernote-mcp-server"
DEFAULT_SETTINGS_PATH = "~/.gemini/settings.json"
DEFAULT_DOCKER_IMAGE = "evernote-mcp-server:local"
DEFAULT_DOCKER_VOLUME = "evernote-mcp-auth"
SUPPORTED_MODES = ("python", "docker")


def build_python_server_config(repository_path: Path) -> dict[str, Any]:
    """Build Gemini MCP server configuration for local Python development.

    Inputs:
    - repository_path: absolute repository root used as Gemini `cwd`

    Output:
    - A JSON-serializable dict for one `mcpServers` entry

    Edge cases:
    - The function does not validate `.venv` existence; runtime startup will
      fail naturally if prerequisites are missing.

    Concurrency/atomicity:
    - Pure function with no side effects.
    """
    return {
        "command": "bash",
        "args": [
            "-lc",
            "source .venv/bin/activate && PYTHONPATH=src python -m evernote_mcp --transport stdio",
        ],
        "cwd": str(repository_path),
        "trust": True,
    }


def build_docker_server_config(
    repository_path: Path, docker_image: str, docker_volume_name: str
) -> dict[str, Any]:
    """Build Gemini MCP server configuration for Docker runtime.

    Inputs:
    - repository_path: absolute repository root used as Gemini `cwd`
    - docker_image: image tag Gemini should run
    - docker_volume_name: volume mounted for persistent auth token storage

    Output:
    - A JSON-serializable dict for one `mcpServers` entry

    Edge cases:
    - This function does not verify the image or volume exists; it only builds
      the command Gemini should execute.

    Concurrency/atomicity:
    - Pure function with no side effects.
    """
    docker_run_command = (
        "docker run --rm -i --env-file .env "
        f"-v {docker_volume_name}:/home/appuser/.config/evernote-mcp-server "
        f"{docker_image}"
    )
    return {
        "command": "bash",
        "args": ["-lc", docker_run_command],
        "cwd": str(repository_path),
        "trust": True,
    }


def load_settings_json(settings_path: Path) -> dict[str, Any]:
    """Load existing Gemini settings or return a new default object.

    Inputs:
    - settings_path: full filesystem path to Gemini settings JSON

    Output:
    - Parsed settings object as a mutable dictionary

    Edge cases:
    - Missing file returns an empty object.
    - Empty file returns an empty object.
    - Non-object root or invalid JSON raises `ValueError` with context.

    Concurrency/atomicity:
    - Read-only operation.
    """
    if not settings_path.exists():
        return {}

    raw_text = settings_path.read_text(encoding="utf-8").strip()
    if raw_text == "":
        return {}

    try:
        parsed_settings = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Settings file is not valid JSON: {settings_path}"
        ) from exc

    if not isinstance(parsed_settings, dict):
        raise ValueError(
            f"Gemini settings root must be a JSON object: {settings_path}"
        )

    return parsed_settings


def upsert_mcp_server_entry(
    settings_data: dict[str, Any], server_name: str, server_config: dict[str, Any]
) -> bool:
    """Insert or update an `mcpServers` entry in settings data.

    Inputs:
    - settings_data: mutable settings dictionary
    - server_name: key under `mcpServers`
    - server_config: value for the selected MCP server entry

    Output:
    - `True` when settings were changed; `False` when already up to date

    Edge cases:
    - If `mcpServers` exists and is not an object, raises `ValueError`.

    Concurrency/atomicity:
    - In-memory mutation only; no filesystem writes.
    """
    current_mcp_servers = settings_data.get("mcpServers")
    if current_mcp_servers is None:
        settings_data["mcpServers"] = {}
    elif not isinstance(current_mcp_servers, dict):
        raise ValueError("Field `mcpServers` must be a JSON object.")

    mcp_servers = settings_data["mcpServers"]
    existing_server_config = mcp_servers.get(server_name)
    if existing_server_config == server_config:
        return False

    mcp_servers[server_name] = server_config
    return True


def parse_arguments() -> argparse.Namespace:
    """Parse CLI arguments for the Gemini MCP installer.

    Inputs:
    - Command-line arguments from `sys.argv`

    Output:
    - Parsed namespace with validated options

    Edge cases:
    - Unsupported mode values are rejected by argparse choices.

    Concurrency/atomicity:
    - Pure argument parsing.
    """
    repository_root = Path(__file__).resolve().parent.parent

    parser = argparse.ArgumentParser(
        description="Install/update evernote-mcp-server in Gemini settings."
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=SUPPORTED_MODES,
        help="Runtime mode Gemini should launch: python or docker.",
    )
    parser.add_argument(
        "--settings-path",
        default=DEFAULT_SETTINGS_PATH,
        help="Gemini settings JSON path (default: ~/.gemini/settings.json).",
    )
    parser.add_argument(
        "--server-name",
        default=DEFAULT_SERVER_NAME,
        help=f"Entry name inside mcpServers (default: {DEFAULT_SERVER_NAME}).",
    )
    parser.add_argument(
        "--repo-path",
        default=str(repository_root),
        help="Repository root used as Gemini cwd (default: this repo root).",
    )
    parser.add_argument(
        "--docker-image",
        default=DEFAULT_DOCKER_IMAGE,
        help=(
            "Docker image to run in docker mode "
            f"(default: {DEFAULT_DOCKER_IMAGE})."
        ),
    )
    parser.add_argument(
        "--docker-volume",
        default=DEFAULT_DOCKER_VOLUME,
        help=(
            "Docker volume for token persistence in docker mode "
            f"(default: {DEFAULT_DOCKER_VOLUME})."
        ),
    )
    return parser.parse_args()


def main() -> int:
    """Run the Gemini MCP settings installation workflow.

    Inputs:
    - CLI arguments parsed by `parse_arguments`

    Output:
    - Process exit code (`0` success, raises on validation errors)

    Edge cases:
    - Creates parent directories and settings file if they do not exist.
    - Leaves file untouched when the target entry is already up to date.

    Concurrency/atomicity:
    - Performs a single deterministic read-modify-write sequence on one JSON
      file. There is no lock; concurrent writers may race.
    """
    arguments = parse_arguments()
    settings_path = Path(arguments.settings_path).expanduser().resolve()
    repository_path = Path(arguments.repo_path).expanduser().resolve()

    if arguments.mode == "python":
        target_server_config = build_python_server_config(repository_path)
    else:
        target_server_config = build_docker_server_config(
            repository_path=repository_path,
            docker_image=arguments.docker_image,
            docker_volume_name=arguments.docker_volume,
        )

    settings_data = load_settings_json(settings_path)
    did_change_settings = upsert_mcp_server_entry(
        settings_data=settings_data,
        server_name=arguments.server_name,
        server_config=target_server_config,
    )

    if did_change_settings:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps(settings_data, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            f"Updated {settings_path} with MCP server "
            f"'{arguments.server_name}' ({arguments.mode} mode)."
        )
    else:
        print(
            f"No changes needed in {settings_path}; MCP server "
            f"'{arguments.server_name}' is already configured."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
