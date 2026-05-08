from __future__ import annotations

from pathlib import Path, PureWindowsPath

from scripts.install_gemini_mcp import (
    build_docker_server_config,
    build_python_server_config,
    upsert_mcp_server_entry,
)


def test_windows_python_config_uses_repo_virtualenv_without_bash() -> None:
    repository_path = PureWindowsPath("D:/repos/evernote-mcp-server")

    server_config = build_python_server_config(
        repository_path=repository_path,
        platform_name="nt",
    )

    assert server_config["command"] == (
        "D:\\repos\\evernote-mcp-server\\.venv\\Scripts\\python.exe"
    )
    assert server_config["args"] == [
        "-m",
        "evernote_mcp",
        "--transport",
        "stdio",
    ]
    assert server_config["cwd"] == "D:\\repos\\evernote-mcp-server"
    assert "bash" not in server_config["command"].lower()
    assert "bash" not in " ".join(server_config["args"]).lower()
    assert "source" not in " ".join(server_config["args"]).lower()


def test_python_config_env_includes_absolute_src_path_and_safe_defaults() -> None:
    repository_path = Path("/work/evernote-mcp-server").resolve()

    server_config = build_python_server_config(repository_path=repository_path)

    assert server_config["env"] == {
        "PYTHONPATH": str(repository_path / "src"),
        "READ_ONLY": "true",
        "EVERNOTE_SANDBOX": "false",
        "LOG_LEVEL": "INFO",
    }
    assert Path(server_config["env"]["PYTHONPATH"]).is_absolute()


def test_python_config_allows_runtime_option_overrides() -> None:
    repository_path = Path("/work/evernote-mcp-server").resolve()
    python_executable = Path("/opt/python/bin/python3.13")

    server_config = build_python_server_config(
        repository_path=repository_path,
        python_executable=python_executable,
        read_only="false",
        sandbox="true",
        log_level="DEBUG",
    )

    assert server_config["command"] == str(python_executable)
    assert server_config["env"]["READ_ONLY"] == "false"
    assert server_config["env"]["EVERNOTE_SANDBOX"] == "true"
    assert server_config["env"]["LOG_LEVEL"] == "DEBUG"


def test_upsert_mcp_server_entry_is_idempotent() -> None:
    settings_data = {"mcpServers": {"other-server": {"command": "other"}}}
    server_config = {"command": "python", "args": ["-m", "evernote_mcp"]}

    assert upsert_mcp_server_entry(settings_data, "evernote", server_config) is True
    first_settings_data = settings_data.copy()

    assert upsert_mcp_server_entry(settings_data, "evernote", server_config) is False
    assert settings_data == first_settings_data
    assert settings_data["mcpServers"]["other-server"] == {"command": "other"}


def test_docker_mode_config_remains_unchanged() -> None:
    repository_path = Path("/work/evernote-mcp-server").resolve()

    server_config = build_docker_server_config(
        repository_path=repository_path,
        docker_image="evernote-mcp-server:local",
        docker_volume_name="evernote-mcp-auth",
    )

    assert server_config == {
        "command": "bash",
        "args": [
            "-lc",
            (
                "docker run --rm -i --env-file .env "
                "-v evernote-mcp-auth:/home/appuser/.config/evernote-mcp-server "
                "evernote-mcp-server:local"
            ),
        ],
        "cwd": str(repository_path),
        "trust": True,
    }
