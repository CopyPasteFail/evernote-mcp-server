#!/usr/bin/env bash
set -euo pipefail

# Install or update Gemini MCP settings for evernote-mcp-server using the
# published GHCR image from the latest GitHub release tag.
#
# This installer is intended for end users and is fully clone-free:
# - creates a persistent host env file for Evernote credentials/settings
# - creates a persistent Docker volume for OAuth token storage
# - configures Gemini to run the published container directly

DEFAULT_GITHUB_OWNER="CopyPasteFail"
DEFAULT_GITHUB_REPO="evernote-mcp-server"
DEFAULT_SETTINGS_PATH="$HOME/.gemini/settings.json"
DEFAULT_SERVER_NAME="evernote-mcp-server"
DEFAULT_DOCKER_VOLUME="evernote-mcp-auth"
DEFAULT_ENV_FILE_PATH="$HOME/.config/evernote-mcp-server/evernote-mcp.env"
DEFAULT_GEMINI_CWD="$HOME"
EXPECTED_TAG_PREFIX="v"

print_usage() {
  cat <<'USAGE'
Usage:
  install_gemini_mcp_release.sh [options]

Options:
  --settings-path <path>   Gemini settings file path (default: ~/.gemini/settings.json)
  --server-name <name>     Name under mcpServers (default: evernote-mcp-server)
  --docker-volume <name>   Docker volume for token persistence (default: evernote-mcp-auth)
  --env-file <path>        Host env file for Evernote credentials/settings
                           (default: ~/.config/evernote-mcp-server/evernote-mcp.env)
  --gemini-cwd <path>      Gemini cwd for this MCP entry (default: ~)
  --github-owner <owner>   GitHub owner for release lookup (default: CopyPasteFail)
  --github-repo <repo>     GitHub repository name (default: evernote-mcp-server)
  --tag <tag>              Override release tag lookup and pin a specific tag
  --help                   Show this help text
USAGE
}

# Validate that a required executable exists in PATH.
#
# Inputs:
# - command_name: executable name to check
#
# Output:
# - no output on success
# - exits with an error message if command is unavailable
require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Error: required command not found: $command_name" >&2
    exit 1
  fi
}

# Resolve the latest GitHub release tag for a repository.
#
# Inputs:
# - github_owner: GitHub organization or user
# - github_repo: repository name
#
# Output:
# - writes the resolved tag (for example: v0.2.1) to stdout
#
# Edge cases:
# - exits if the API response does not contain tag_name
# - exits if tag_name does not match expected v* pattern
fetch_latest_release_tag() {
  local github_owner="$1"
  local github_repo="$2"
  local release_api_url="https://api.github.com/repos/${github_owner}/${github_repo}/releases/latest"
  local latest_tag

  latest_tag="$(
    curl -fsSL "$release_api_url" | python3 -c '
import json
import sys

try:
    release_payload = json.load(sys.stdin)
except json.JSONDecodeError:
    print("")
    sys.exit(0)

tag_name = release_payload.get("tag_name")
if isinstance(tag_name, str):
    print(tag_name)
else:
    print("")
'
  )"

  if [[ -z "$latest_tag" ]]; then
    echo "Error: could not determine latest release tag from $release_api_url" >&2
    exit 1
  fi

  if [[ "$latest_tag" != ${EXPECTED_TAG_PREFIX}* ]]; then
    echo "Error: latest release tag '$latest_tag' does not match expected '${EXPECTED_TAG_PREFIX}*' format." >&2
    exit 1
  fi

  printf '%s\n' "$latest_tag"
}

# Ensure the host env file exists for Evernote credentials/settings.
#
# Inputs:
# - env_file_path: target env file path
#
# Output:
# - creates the parent directory if missing
# - creates a template env file only when the file does not already exist
# - prints whether the file was created or reused
ensure_env_file_exists() {
  local env_file_path="$1"
  local env_directory_path

  env_directory_path="$(dirname "$env_file_path")"
  mkdir -p "$env_directory_path"

  if [[ -f "$env_file_path" ]]; then
    echo "Using existing env file: $env_file_path"
    return
  fi

  cat >"$env_file_path" <<'ENV_TEMPLATE'
EVERNOTE_CONSUMER_KEY=
EVERNOTE_CONSUMER_SECRET=
EVERNOTE_SANDBOX=false
READ_ONLY=true
ENV_TEMPLATE

  echo "Created env template: $env_file_path"
}

# Ensure a Docker named volume exists for persistent OAuth token storage.
#
# Inputs:
# - docker_volume_name: volume name to verify/create
#
# Output:
# - creates the volume when missing
# - prints whether the volume was created or already existed
ensure_docker_volume_exists() {
  local docker_volume_name="$1"

  if docker volume inspect "$docker_volume_name" >/dev/null 2>&1; then
    echo "Using existing Docker volume: $docker_volume_name"
    return
  fi

  docker volume create "$docker_volume_name" >/dev/null
  echo "Created Docker volume: $docker_volume_name"
}

# Build a single Gemini `mcpServers` entry JSON object for published Docker use.
#
# Inputs:
# - gemini_cwd_path: Gemini working directory
# - env_file_path: host env file path passed to docker --env-file
# - docker_volume_name: Docker volume used for persistent auth token storage
# - docker_image: full image reference including resolved release tag
#
# Output:
# - JSON object on stdout
build_server_config_json() {
  local gemini_cwd_path="$1"
  local env_file_path="$2"
  local docker_volume_name="$3"
  local docker_image="$4"

  python3 - <<'PY' "$gemini_cwd_path" "$env_file_path" "$docker_volume_name" "$docker_image"
import json
import shlex
import sys

gemini_cwd_path = sys.argv[1]
env_file_path = sys.argv[2]
docker_volume_name = sys.argv[3]
docker_image = sys.argv[4]

docker_command_parts = [
    "docker",
    "run",
    "--rm",
    "-i",
    "--env-file",
    env_file_path,
    "-v",
    f"{docker_volume_name}:/home/appuser/.config/evernote-mcp-server",
    docker_image,
]
docker_run_command = " ".join(shlex.quote(part) for part in docker_command_parts)

server_config = {
    "command": "bash",
    "args": ["-lc", docker_run_command],
    "cwd": gemini_cwd_path,
    "trust": True,
}
print(json.dumps(server_config))
PY
}

# Insert or update one MCP server entry in Gemini settings JSON.
#
# Inputs:
# - settings_path: Gemini settings JSON path
# - server_name: key under mcpServers
# - server_config_json: JSON object for the target server entry
#
# Output:
# - prints whether settings changed
#
# Edge cases:
# - creates parent directory when missing
# - treats an empty settings file as {}
# - exits when settings root is not a JSON object
# - exits when mcpServers exists but is not a JSON object
upsert_gemini_settings() {
  local settings_path="$1"
  local server_name="$2"
  local server_config_json="$3"
  local upsert_status

  if ! upsert_status="$(
    python3 - <<'PY' "$settings_path" "$server_name" "$server_config_json"
import json
import pathlib
import sys

settings_path = pathlib.Path(sys.argv[1])
server_name = sys.argv[2]
server_config_json = sys.argv[3]

try:
    target_server_config = json.loads(server_config_json)
except json.JSONDecodeError:
    print("Error: internal failure while decoding target server config JSON.", file=sys.stderr)
    sys.exit(1)

settings_path.parent.mkdir(parents=True, exist_ok=True)

if not settings_path.exists():
    settings_data = {}
else:
    raw_text = settings_path.read_text(encoding="utf-8").strip()
    if raw_text == "":
        settings_data = {}
    else:
        try:
            settings_data = json.loads(raw_text)
        except json.JSONDecodeError:
            print(
                f"Error: Gemini settings file is not valid JSON: {settings_path}",
                file=sys.stderr,
            )
            sys.exit(1)

if not isinstance(settings_data, dict):
    print(f"Error: Gemini settings root must be a JSON object: {settings_path}", file=sys.stderr)
    sys.exit(1)

current_mcp_servers = settings_data.get("mcpServers")
if current_mcp_servers is None:
    current_mcp_servers = {}
elif not isinstance(current_mcp_servers, dict):
    print("Error: field 'mcpServers' must be a JSON object when present.", file=sys.stderr)
    sys.exit(1)

existing_server_config = current_mcp_servers.get(server_name)
if existing_server_config == target_server_config:
    print("unchanged")
    sys.exit(0)

current_mcp_servers[server_name] = target_server_config
settings_data["mcpServers"] = current_mcp_servers
settings_path.write_text(json.dumps(settings_data, indent=2) + "\n", encoding="utf-8")
print("updated")
PY
  )"; then
    exit 1
  fi

  if [[ "$upsert_status" == "unchanged" ]]; then
    echo "No changes needed in $settings_path; MCP server '$server_name' is already configured."
    return
  fi

  if [[ "$upsert_status" == "updated" ]]; then
    echo "Updated $settings_path with MCP server '$server_name'."
    return
  fi

  echo "Error: unexpected settings upsert status: $upsert_status" >&2
  exit 1
}

# Print the post-install user steps including the one-time OAuth bootstrap
# command that matches the generated Gemini Docker command.
#
# Inputs:
# - env_file_path: host env file path used in docker --env-file
# - docker_volume_name: Docker volume used for token persistence
# - docker_image: published image used for both OAuth bootstrap and Gemini
print_next_steps() {
  local env_file_path="$1"
  local docker_volume_name="$2"
  local docker_image="$3"
  local server_name="$4"
  local oauth_bootstrap_command

  oauth_bootstrap_command="$(
    python3 - <<'PY' "$env_file_path" "$docker_volume_name" "$docker_image"
import shlex
import sys

env_file_path = sys.argv[1]
docker_volume_name = sys.argv[2]
docker_image = sys.argv[3]

docker_command_parts = [
    "docker",
    "run",
    "--rm",
    "-it",
    "--env-file",
    env_file_path,
    "-v",
    f"{docker_volume_name}:/home/appuser/.config/evernote-mcp-server",
    docker_image,
    "python",
    "-m",
    "evernote_mcp",
    "auth",
]
print(" ".join(shlex.quote(part) for part in docker_command_parts))
PY
  )"

  echo
  echo "Next steps:"
  echo "1. Edit your env file and fill Evernote credentials:"
  echo "   $env_file_path"
  echo "2. Run one-time OAuth bootstrap:"
  echo "   $oauth_bootstrap_command"
  echo "3. Start using Gemini CLI with MCP server '$server_name'."
}

# Parse CLI arguments, resolve release tag, ensure host/docker prerequisites,
# then apply Gemini configuration.
#
# The workflow is deterministic and idempotent for repeated runs with the same
# inputs. Existing non-target Gemini settings fields remain untouched.
main() {
  local settings_path="$DEFAULT_SETTINGS_PATH"
  local server_name="$DEFAULT_SERVER_NAME"
  local docker_volume_name="$DEFAULT_DOCKER_VOLUME"
  local env_file_path="$DEFAULT_ENV_FILE_PATH"
  local gemini_cwd_path="$DEFAULT_GEMINI_CWD"
  local github_owner="$DEFAULT_GITHUB_OWNER"
  local github_repo="$DEFAULT_GITHUB_REPO"
  local explicit_tag=""
  local resolved_tag
  local docker_image
  local server_config_json

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --settings-path)
        settings_path="$2"
        shift 2
        ;;
      --server-name)
        server_name="$2"
        shift 2
        ;;
      --docker-volume)
        docker_volume_name="$2"
        shift 2
        ;;
      --env-file)
        env_file_path="$2"
        shift 2
        ;;
      --gemini-cwd)
        gemini_cwd_path="$2"
        shift 2
        ;;
      --github-owner)
        github_owner="$2"
        shift 2
        ;;
      --github-repo)
        github_repo="$2"
        shift 2
        ;;
      --tag)
        explicit_tag="$2"
        shift 2
        ;;
      --help)
        print_usage
        exit 0
        ;;
      *)
        echo "Error: unknown argument: $1" >&2
        print_usage
        exit 1
        ;;
    esac
  done

  require_command "python3"
  require_command "docker"
  if [[ -z "$explicit_tag" ]]; then
    require_command "curl"
  fi

  settings_path="${settings_path/#\~/$HOME}"
  env_file_path="${env_file_path/#\~/$HOME}"
  gemini_cwd_path="${gemini_cwd_path/#\~/$HOME}"

  if [[ ! -d "$gemini_cwd_path" ]]; then
    echo "Error: --gemini-cwd must be an existing directory: $gemini_cwd_path" >&2
    exit 1
  fi

  gemini_cwd_path="$(cd "$gemini_cwd_path" && pwd)"

  if [[ -n "$explicit_tag" ]]; then
    resolved_tag="$explicit_tag"
  else
    resolved_tag="$(fetch_latest_release_tag "$github_owner" "$github_repo")"
  fi

  if [[ "$resolved_tag" != ${EXPECTED_TAG_PREFIX}* ]]; then
    echo "Error: release tag '$resolved_tag' does not match expected '${EXPECTED_TAG_PREFIX}*' format." >&2
    exit 1
  fi

  ensure_env_file_exists "$env_file_path"
  ensure_docker_volume_exists "$docker_volume_name"

  docker_image="ghcr.io/${github_owner}/${github_repo}:${resolved_tag}"
  server_config_json="$(
    build_server_config_json \
      "$gemini_cwd_path" \
      "$env_file_path" \
      "$docker_volume_name" \
      "$docker_image"
  )"

  upsert_gemini_settings "$settings_path" "$server_name" "$server_config_json"

  echo "Configured image: $docker_image"
  print_next_steps "$env_file_path" "$docker_volume_name" "$docker_image" "$server_name"
}

main "$@"
