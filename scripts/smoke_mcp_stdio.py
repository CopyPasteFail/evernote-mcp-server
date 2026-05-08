#!/usr/bin/env python3
"""Smoke-test the local stdio MCP server with a minimal initialize request."""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any


DEFAULT_TIMEOUT_SECONDS = 10.0


def enqueue_lines(stream: Any, output_queue: queue.Queue[str]) -> None:
    """Read subprocess stdout lines into a queue until EOF."""
    for line in iter(stream.readline, ""):
        output_queue.put(line)


def read_json_rpc_response(
    output_queue: queue.Queue[str],
    request_id: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Read lines until the matching JSON-RPC response arrives or times out."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        remaining_seconds = max(0.0, deadline - time.monotonic())
        try:
            raw_line = output_queue.get(timeout=remaining_seconds)
        except queue.Empty as error:
            raise TimeoutError("Timed out waiting for MCP initialize response.") from error

        stripped_line = raw_line.strip()
        if not stripped_line:
            continue

        try:
            response = json.loads(stripped_line)
        except json.JSONDecodeError:
            continue

        if response.get("jsonrpc") == "2.0" and response.get("id") == request_id:
            return response

    raise TimeoutError("Timed out waiting for MCP initialize response.")


def build_argument_parser() -> argparse.ArgumentParser:
    """Create CLI parser for the smoke test."""
    repository_root = Path(__file__).resolve().parent.parent
    default_python_executable = (
        repository_root / ".venv" / "Scripts" / "python.exe"
        if os.name == "nt"
        else repository_root / ".venv" / "bin" / "python"
    )

    parser = argparse.ArgumentParser(
        description="Start the local stdio MCP server and verify initialize responds."
    )
    parser.add_argument(
        "--python-executable",
        default=str(default_python_executable),
        help="Python executable used to launch the server.",
    )
    parser.add_argument(
        "--repo-path",
        default=str(repository_root),
        help="Repository root used as subprocess cwd.",
    )
    parser.add_argument(
        "--timeout",
        default=DEFAULT_TIMEOUT_SECONDS,
        type=float,
        help=f"Response timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS}).",
    )
    return parser


def main() -> int:
    """Run the smoke test."""
    arguments = build_argument_parser().parse_args()
    repository_path = Path(arguments.repo_path).expanduser().resolve()
    python_executable = Path(arguments.python_executable).expanduser().resolve()

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repository_path / "src")
    environment.setdefault("READ_ONLY", "true")
    environment.setdefault("EVERNOTE_SANDBOX", "false")
    environment.setdefault("LOG_LEVEL", "INFO")

    process = subprocess.Popen(
        [
            str(python_executable),
            "-m",
            "evernote_mcp",
            "--transport",
            "stdio",
        ],
        cwd=str(repository_path),
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )

    assert process.stdin is not None
    assert process.stdout is not None

    output_queue: queue.Queue[str] = queue.Queue()
    stdout_thread = threading.Thread(
        target=enqueue_lines,
        args=(process.stdout, output_queue),
        daemon=True,
    )
    stdout_thread.start()

    request_id = 1
    initialize_request = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "evernote-mcp-stdio-smoke",
                "version": "0.1.0",
            },
        },
    }

    try:
        process.stdin.write(json.dumps(initialize_request) + "\n")
        process.stdin.flush()
        response = read_json_rpc_response(
            output_queue=output_queue,
            request_id=request_id,
            timeout_seconds=arguments.timeout,
        )
    except Exception as error:
        process.terminate()
        try:
            _, stderr_text = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            _, stderr_text = process.communicate(timeout=2)
        print(f"Smoke test failed: {error}", file=sys.stderr)
        if stderr_text.strip():
            print(stderr_text.strip(), file=sys.stderr)
        return 1
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)

    if "result" not in response:
        print(f"Smoke test failed: initialize returned {response}", file=sys.stderr)
        return 1

    server_info = response["result"].get("serverInfo", {})
    print(
        "MCP stdio initialize succeeded: "
        f"{server_info.get('name', 'unknown')} "
        f"{server_info.get('version', 'unknown')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
