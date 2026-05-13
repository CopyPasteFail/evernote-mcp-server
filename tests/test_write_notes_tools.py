"""Unit tests for write note MCP tool registration."""

from __future__ import annotations

from typing import Callable
from unittest.mock import Mock

from evernote_mcp.core.policies import set_read_only_mode
from evernote_mcp.tools.write_notes import register_write_note_tools


class FakeMCPServer:
    """Capture registered tools without importing FastMCP."""

    def __init__(self) -> None:
        self.tools: dict[str, Callable[..., object]] = {}

    def tool(self, *, name: str) -> Callable[[Callable[..., object]], Callable[..., object]]:
        def register(tool_callable: Callable[..., object]) -> Callable[..., object]:
            self.tools[name] = tool_callable
            return tool_callable

        return register


def test_registers_insert_into_note_plaintext_tool() -> None:
    fake_server = FakeMCPServer()
    fake_gateway = Mock()

    register_write_note_tools(fake_server, fake_gateway)

    assert "insert_into_note_plaintext" in fake_server.tools


def test_insert_into_note_plaintext_enforces_policy_and_calls_gateway() -> None:
    set_read_only_mode(False)
    fake_server = FakeMCPServer()
    fake_gateway = Mock()
    fake_gateway.insert_plaintext_near_anchor.return_value = {"guid": "note-guid"}
    register_write_note_tools(fake_server, fake_gateway)

    result = fake_server.tools["insert_into_note_plaintext"](
        note_guid="note-guid",
        anchor_text="anchor block",
        plaintext_content="new section",
        position="before",
        occurrence=2,
    )

    fake_gateway.insert_plaintext_near_anchor.assert_called_once_with(
        note_guid="note-guid",
        anchor_text="anchor block",
        plaintext_content="new section",
        position="before",
        occurrence=2,
    )
    assert result == {"guid": "note-guid"}
