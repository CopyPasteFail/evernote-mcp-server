"""Structural protocol definitions for MCP server interactions.

This module isolates type-checking contracts from concrete `fastmcp` imports,
so static analysis can succeed even when optional runtime dependencies are not
installed in the editor environment.
"""

from __future__ import annotations

from typing import Callable, Protocol, TypeVar

ToolCallable = TypeVar("ToolCallable", bound=Callable[..., object])


class MCPServerProtocol(Protocol):
    """Structural contract used by MCP server construction and tool registration.

    Implementations must support:
    - `tool(name=...)` for decorator-based tool registration.
    - `run(...)` for transport startup.
    """

    def tool(
        self,
        *,
        name: str,
    ) -> Callable[[ToolCallable], ToolCallable]:
        """Return a decorator that registers a callable as an MCP tool."""
        ...

    def run(self, **kwargs: object) -> None:
        """Start the MCP server runtime using implementation-specific options."""
        ...
