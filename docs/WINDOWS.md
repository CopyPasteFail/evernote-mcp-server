# Native Windows Local Python Setup

Use this path when you want Gemini CLI to launch this repository as a local stdio MCP server on Windows without WSL, Bash, or Docker. Piebald can reuse the printed MCP config manually, but this installer writes Gemini CLI settings only.

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

## Configure Gemini CLI

Check that Gemini CLI is installed and available in PowerShell:

```powershell
Get-Command gemini
```

Then run Gemini once and sign in with the Google account that has your Gemini subscription:

```powershell
gemini
```

The installer can print the native Windows MCP entry without changing Gemini CLI settings. This is useful for inspection or for copying into another client manually:

```powershell
.\.venv\Scripts\python.exe scripts\install_gemini_mcp.py --mode python --print-config
```

To update Gemini CLI settings idempotently:

```powershell
.\.venv\Scripts\python.exe scripts\install_gemini_mcp.py --mode python
```

If Gemini CLI is not on `PATH`, the installer exits before writing settings. Advanced users can bypass only that preflight with `--skip-gemini-check`.

## Manual MCP Config

You can paste this JSON into another MCP client later, including Piebald after you have confirmed where it expects MCP configuration:

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

After Gemini CLI is configured, verify with a read-only MCP request such as `list_notebooks`. Keep `READ_ONLY=true` until you have confirmed the wiring and auth state. For Piebald or another client, copy the printed config manually and verify through that client's MCP flow.

For a local protocol smoke test, you can run:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_mcp_stdio.py
```

The smoke script starts the server subprocess, sends a minimal MCP `initialize` request, and checks for a JSON-RPC response. It still depends on your local `.env` and saved OAuth token being valid.
