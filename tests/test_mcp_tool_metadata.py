"""Regression tests for compact MCP tool metadata."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import cast

from evernote_mcp.evernote.client import EvernoteGateway
from evernote_mcp.tools.notebooks import register_notebook_tools
from evernote_mcp.tools.read_notes import register_read_note_tools
from evernote_mcp.tools.write_notes import register_write_note_tools


class RecordingMCPServer:
    """Minimal MCP registration recorder used without a FastMCP runtime."""

    def __init__(self) -> None:
        self.tools: dict[str, Callable[..., object]] = {}

    def tool(
        self,
        *,
        name: str,
    ) -> Callable[[Callable[..., object]], Callable[..., object]]:
        """Return a decorator that records one registered tool."""

        def register(tool: Callable[..., object]) -> Callable[..., object]:
            self.tools[name] = tool
            return tool

        return register

    def run(self, **kwargs: object) -> None:
        """Satisfy the MCP server protocol without starting a runtime."""

        del kwargs


def _registered_tools() -> dict[str, Callable[..., object]]:
    server = RecordingMCPServer()
    gateway = cast(EvernoteGateway, object())

    register_notebook_tools(server, gateway)
    register_read_note_tools(server, gateway)
    register_write_note_tools(server, gateway)

    return server.tools


def _description(tool: Callable[..., object]) -> str:
    return inspect.getdoc(tool) or ""


def test_registered_tools_keep_expected_call_shapes() -> None:
    tools = _registered_tools()
    expected_signatures = {
        "list_notebooks": ((), {}),
        "search_notes": (
            ("search_query", "offset", "max_results"),
            {"offset": 0, "max_results": 20},
        ),
        "get_note": (("note_guid",), {}),
        "get_note_metadata": (("note_guid",), {}),
        "append_to_note_plaintext": (("note_guid", "plaintext_content"), {}),
        "insert_into_note_plaintext": (
            ("note_guid", "anchor_text", "plaintext_content", "position", "occurrence"),
            {"position": "after", "occurrence": 1},
        ),
        "set_note_title": (("note_guid", "new_title"), {}),
        "add_tags_by_name": (("note_guid", "tag_names"), {}),
        "move_note": (("note_guid", "destination_notebook_guid"), {}),
        "create_note": (
            ("title", "plaintext_body", "notebook_guid", "tag_names"),
            {"notebook_guid": None, "tag_names": None},
        ),
        "delete_note": (("note_guid",), {}),
    }

    assert set(tools) == set(expected_signatures)

    for tool_name, (parameter_names, expected_defaults) in expected_signatures.items():
        parameters = inspect.signature(tools[tool_name]).parameters

        assert tuple(parameters) == parameter_names
        for parameter_name in parameter_names:
            parameter = parameters[parameter_name]
            if parameter_name in expected_defaults:
                assert parameter.default == expected_defaults[parameter_name]
            else:
                assert parameter.default is inspect.Parameter.empty


def test_compact_descriptions_keep_required_safety_cues() -> None:
    tools = _registered_tools()

    assert "not note content" in _description(tools["search_notes"])
    assert "full ENML body" in _description(tools["get_note"])
    assert "without its ENML body" in _description(tools["get_note_metadata"])
    assert "distinctive anchor" in _description(tools["insert_into_note_plaintext"])
    assert "Evernote trash" in _description(tools["delete_note"])

    write_tools = {
        "append_to_note_plaintext",
        "insert_into_note_plaintext",
        "set_note_title",
        "add_tags_by_name",
        "move_note",
        "create_note",
        "delete_note",
    }
    for tool_name in write_tools:
        assert "Requires writes enabled." in _description(tools[tool_name])


def test_compact_descriptions_exclude_repeated_sections() -> None:
    repeated_headings = ("Use first:", "Returns keys:", "Fails when:")

    for tool in _registered_tools().values():
        description = _description(tool)
        for heading in repeated_headings:
            assert heading not in description
