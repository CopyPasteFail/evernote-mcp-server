# Native Windows Local Python Setup

Use this path when you want Gemini CLI or Piebald to launch this repository as a local stdio MCP server on Windows without WSL, Bash, or Docker.

## Bootstrap In PowerShell

Run these commands from PowerShell:

```powershell
cd D:\repos\evernote-mcp-server
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
notepad .env
```

Fill `EVERNOTE_CONSUMER_KEY` and `EVERNOTE_CONSUMER_SECRET` in `.env`. Keep `READ_ONLY=true` for first verification.

Run OAuth bootstrap:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m evernote_mcp auth
```

Check the local import and saved token:

```powershell
.\.venv\Scripts\python.exe -c "import evernote_mcp; print('import ok')"
Test-Path "$env:USERPROFILE\.config\evernote-mcp-server\token.json"
```

The token check should print `True`.

## Configure Gemini Or Piebald

The installer can print the native Windows MCP entry without changing your settings:

```powershell
.\.venv\Scripts\python.exe scripts\install_gemini_mcp.py --mode python --print-config
```

To update Gemini settings idempotently:

```powershell
.\.venv\Scripts\python.exe scripts\install_gemini_mcp.py --mode python
```

You can also paste this JSON into a Gemini or Piebald MCP configuration:

```json
{
  "mcpServers": {
    "evernote-mcp-server": {
      "command": "D:\\repos\\evernote-mcp-server\\.venv\\Scripts\\python.exe",
      "args": [
        "-m",
        "evernote_mcp",
        "--transport",
        "stdio"
      ],
      "cwd": "D:\\repos\\evernote-mcp-server",
      "env": {
        "PYTHONPATH": "D:\\repos\\evernote-mcp-server\\src",
        "READ_ONLY": "true",
        "EVERNOTE_SANDBOX": "false",
        "LOG_LEVEL": "INFO"
      },
      "trust": true
    }
  }
}
```

This config launches the repo-local virtualenv Python directly. It does not use `bash`, `source`, WSL, Docker, or shell wrappers.

## Verification Notes

Do not treat this command as an end-to-end test:

```powershell
.\.venv\Scripts\python.exe -m evernote_mcp --transport stdio
```

Stdio MCP servers wait for JSON-RPC messages from an MCP client. Starting the process by hand in a terminal can look idle even when the server is working.

After Gemini or Piebald is configured, verify with a read-only MCP request such as `list_notebooks`. Keep `READ_ONLY=true` until you have confirmed the wiring and auth state.

For a local protocol smoke test, you can run:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_mcp_stdio.py
```

The smoke script starts the server subprocess, sends a minimal MCP `initialize` request, and checks for a JSON-RPC response. It still depends on your local `.env` and saved OAuth token being valid.
