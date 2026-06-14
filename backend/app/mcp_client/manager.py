"""Connects to the configured MCP servers and exposes a unified registry.

Each server gets one persistent ``ClientSession`` for the lifetime of the
backend process (opened in :meth:`MCPServerManager.start`, closed in
:meth:`MCPServerManager.stop`). Tools are exposed to callers under
``"<server_id>.<tool_name>"`` keys so multiple servers can be aggregated
without name collisions (see docs/konzept-mcp-apps.md section 8.1).
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass

import mcp.types as types
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from pydantic import AnyUrl

from app.config import MCPServerConfig, TrustLevel
from app.mcp_client.ui import UIMeta, extract_ui_meta

logger = logging.getLogger(__name__)


@dataclass
class ToolEntry:
    server_id: str
    tool: types.Tool
    ui_meta: UIMeta | None


class MCPServerManager:
    """Owns the MCP client sessions and the aggregated tool registry."""

    def __init__(self, configs: list[MCPServerConfig]):
        self._configs: dict[str, MCPServerConfig] = {c.id: c for c in configs}
        self._sessions: dict[str, ClientSession] = {}
        self._tools: dict[str, ToolEntry] = {}
        self._stack = AsyncExitStack()

    async def start(self) -> None:
        for config in self._configs.values():
            if config.transport != "stdio":
                # See docs/konzept-mcp-apps.md section 8/9: streamable-http
                # and sse are the documented extension points for real
                # external servers, not implemented in this PoC.
                raise NotImplementedError(
                    f"Server '{config.id}': transport '{config.transport}' is "
                    "not implemented in this PoC (only 'stdio' is supported)."
                )
            if not config.command:
                raise ValueError(f"Server '{config.id}': stdio transport requires 'command'")

            params = StdioServerParameters(command=config.command[0], args=config.command[1:])
            read, write = await self._stack.enter_async_context(stdio_client(params))
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self._sessions[config.id] = session

            listed = await session.list_tools()
            for tool in listed.tools:
                key = f"{config.id}.{tool.name}"
                self._tools[key] = ToolEntry(
                    server_id=config.id,
                    tool=tool,
                    ui_meta=extract_ui_meta(tool),
                )
            logger.info(
                "Connected to MCP server '%s' (trust=%s, %d tools)",
                config.id,
                config.trust_level,
                len(listed.tools),
            )

    async def stop(self) -> None:
        await self._stack.aclose()

    def trust_level(self, server_id: str) -> TrustLevel:
        return self._configs[server_id].trust_level

    def list_tool_entries(self) -> list[ToolEntry]:
        """All known tools, across all connected servers."""
        return list(self._tools.values())

    def list_tools_for_llm(self) -> list[ToolEntry]:
        """Tools the model is allowed to call directly.

        A tool is hidden from the model if it declares
        ``_meta.ui.visibility`` *without* ``"model"`` (app-only tools).
        Tools without ``_meta.ui`` default to visible for both model and app.
        """
        return [
            entry
            for entry in self._tools.values()
            if entry.ui_meta is None or "model" in entry.ui_meta.visibility
        ]

    def get_tool_entry(self, tool_key: str) -> ToolEntry | None:
        return self._tools.get(tool_key)

    def find_tool_on_server(self, server_id: str, tool_name: str) -> ToolEntry | None:
        """Look up a tool by name, scoped to a specific server.

        Used to translate a ``UIActionResult`` (which only carries a bare
        tool name) back into a fully-qualified tool key, while making sure a
        UI action can never address a *different* server than the one that
        rendered it (see docs/konzept-mcp-apps.md section 7.4).
        """
        return self._tools.get(f"{server_id}.{tool_name}")

    async def call_tool(
        self, tool_key: str, arguments: dict
    ) -> tuple[ToolEntry, types.CallToolResult]:
        entry = self._tools.get(tool_key)
        if entry is None:
            raise ValueError(f"Unknown tool: {tool_key}")
        session = self._sessions[entry.server_id]
        result = await session.call_tool(entry.tool.name, arguments)
        return entry, result

    async def read_resource(self, server_id: str, uri: str) -> types.ReadResourceResult:
        session = self._sessions[server_id]
        return await session.read_resource(AnyUrl(uri))
