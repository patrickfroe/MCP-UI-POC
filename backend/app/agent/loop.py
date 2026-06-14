"""Per-connection agent session.

Implements the three flows from ``docs/konzept-mcp-apps.md``:

- (a) "Tool-Call mit UI-Ergebnis" - :meth:`AgentSession.handle_user_message`
  -> :meth:`_run_loop` -> :meth:`_send_ui_resource`.
- (b) "UI-Aktion zurueck in den Loop" - :meth:`AgentSession.handle_ui_action`
  -> :meth:`_handle_tool_action` -> :meth:`_run_loop`.
- (c) "Backend-Push in den iframe" - :meth:`_push_ui_update`, sent for any
  UI-initiated tool call using the *same* ``callId`` as the originating
  ``ui_resource``.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Awaitable, Callable

from mcp_ui_server.types import (
    UIActionResult,
    UIActionResultIntent,
    UIActionResultLink,
    UIActionResultNotification,
    UIActionResultPrompt,
    UIActionResultToolCall,
)

from app.llm.base import (
    AssistantMessage,
    LLMProvider,
    Message,
    ToolCallRequest,
    ToolResultMessage,
    ToolSpec,
    UserMessage,
)
from app.mcp_client.manager import MCPServerManager, ToolEntry
from app.mcp_client.ui import build_sandbox_policy, summarize_tool_result
from app.ws.protocol import (
    AssistantMessageOut,
    ErrorOut,
    NoticeOut,
    ResourcePayload,
    ServerMessage,
    StatusOut,
    ToolCallOut,
    ToolResultOut,
    UIResourceOut,
    UIUpdateOut,
)

logger = logging.getLogger(__name__)

SendFn = Callable[[ServerMessage], Awaitable[None]]

MAX_LOOP_ITERATIONS = 5


class AgentSession:
    """Holds the conversation state for one chat / WebSocket connection."""

    def __init__(self, manager: MCPServerManager, llm: LLMProvider, send: SendFn):
        self._manager = manager
        self._llm = llm
        self._send = send
        self._messages: list[Message] = []

        # callId -> server_id. Used to (1) route ui_action messages to the
        # right server and (2) ensure a UI action can only ever address the
        # server that produced the resource it came from (konzept 7.4).
        self._ui_resources: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Entry points (from the WS endpoint)
    # ------------------------------------------------------------------

    async def handle_user_message(self, text: str) -> None:
        self._messages.append(UserMessage(text=text))
        await self._run_loop()

    async def handle_ui_action(self, call_id: str, action: UIActionResult) -> None:
        server_id = self._ui_resources.get(call_id)
        if server_id is None:
            await self._send(ErrorOut(message=f"Unbekannte callId: {call_id}"))
            return

        if isinstance(action, UIActionResultToolCall):
            await self._handle_tool_action(call_id, server_id, action)
        elif isinstance(action, UIActionResultPrompt):
            await self.handle_user_message(action.payload.prompt)
        elif isinstance(action, UIActionResultLink):
            await self._send(
                NoticeOut(level="link", message="Link von der UI angefordert", url=action.payload.url)
            )
        elif isinstance(action, UIActionResultNotification):
            await self._send(NoticeOut(level="info", message=action.payload.message))
        elif isinstance(action, UIActionResultIntent):
            await self._send(
                NoticeOut(
                    level="info",
                    message=f"Intent '{action.payload.intent}' wird in diesem PoC nicht behandelt.",
                )
            )

    # ------------------------------------------------------------------
    # (b) UI action -> tool call -> push result back into the same iframe
    # ------------------------------------------------------------------

    async def _handle_tool_action(
        self, call_id: str, server_id: str, action: UIActionResultToolCall
    ) -> None:
        tool_name = action.payload.toolName
        entry = self._manager.find_tool_on_server(server_id, tool_name)
        if entry is None:
            await self._send(
                ErrorOut(message=f"Tool '{tool_name}' ist auf Server '{server_id}' nicht verfuegbar.")
            )
            return

        if entry.ui_meta is not None and "app" not in entry.ui_meta.visibility:
            await self._send(
                ErrorOut(message=f"Tool '{tool_name}' ist nicht fuer App-initiierte Aufrufe freigegeben.")
            )
            return

        tool_key = f"{server_id}.{tool_name}"

        # Record this as a regular tool call in the conversation history so
        # the LLM can react to its result in the next turn - and so the
        # Anthropic provider has a matching tool_use block for the
        # tool_result it will append (see app/llm/anthropic_provider.py).
        tool_call_id = str(uuid.uuid4())
        self._messages.append(
            AssistantMessage(
                text=None,
                tool_calls=[ToolCallRequest(id=tool_call_id, name=tool_key, arguments=action.payload.params)],
            )
        )

        await self._call_tool_and_record(
            tool_key,
            action.payload.params,
            tool_call_id=tool_call_id,
            call_id_for_ui_update=call_id,
        )

        # Let the model comment on the result.
        await self._run_loop()

    # ------------------------------------------------------------------
    # Agent loop (LLM <-> tool calls)
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        await self._send(StatusOut(state="thinking"))
        try:
            for _ in range(MAX_LOOP_ITERATIONS):
                tools = self._tool_specs()
                turn = await self._llm.generate(self._messages, tools)

                if turn.text:
                    self._messages.append(AssistantMessage(text=turn.text, tool_calls=[]))
                    await self._send(AssistantMessageOut(text=turn.text))

                if not turn.tool_calls:
                    break

                self._messages.append(AssistantMessage(text=None, tool_calls=turn.tool_calls))

                for tool_call in turn.tool_calls:
                    await self._call_tool_and_record(
                        tool_call.name, tool_call.arguments, tool_call_id=tool_call.id
                    )
        finally:
            await self._send(StatusOut(state="idle"))

    # ------------------------------------------------------------------
    # Shared tool-call helper: call MCP tool, report, record, maybe push
    # ui_update (b/c) and/or a new ui_resource (a).
    # ------------------------------------------------------------------

    async def _call_tool_and_record(
        self,
        tool_key: str,
        arguments: dict,
        *,
        tool_call_id: str,
        call_id_for_ui_update: str | None = None,
    ) -> None:
        entry = self._manager.get_tool_entry(tool_key)
        if entry is None:
            await self._send(ErrorOut(message=f"Unbekanntes Tool: {tool_key}"))
            return

        call_id = call_id_for_ui_update or str(uuid.uuid4())

        await self._send(
            ToolCallOut(callId=call_id, server=entry.server_id, tool=entry.tool.name, args=arguments)
        )

        try:
            entry, result = await self._manager.call_tool(tool_key, arguments)
        except Exception as exc:  # pragma: no cover - defensive, MCP transport errors
            logger.exception("Tool call %s failed", tool_key)
            await self._send(ErrorOut(message=f"Tool-Aufruf fehlgeschlagen: {exc}"))
            self._messages.append(
                ToolResultMessage(tool_call_id=tool_call_id, tool_name=tool_key, content=str(exc), is_error=True)
            )
            return

        summary = summarize_tool_result(result)

        await self._send(
            ToolResultOut(
                callId=call_id,
                server=entry.server_id,
                tool=entry.tool.name,
                isError=bool(result.isError),
                summary=summary,
            )
        )

        self._messages.append(
            ToolResultMessage(
                tool_call_id=tool_call_id,
                tool_name=tool_key,
                content=summary,
                is_error=bool(result.isError),
            )
        )

        if call_id_for_ui_update is not None:
            await self._push_ui_update(call_id_for_ui_update, summary)

        if entry.ui_meta is not None and entry.ui_meta.resource_uri:
            await self._send_ui_resource(call_id, entry)

    # ------------------------------------------------------------------
    # (c) Backend push into an already-rendered iframe
    # ------------------------------------------------------------------

    async def _push_ui_update(self, call_id: str, summary: str) -> None:
        try:
            data = json.loads(summary)
        except (TypeError, ValueError, json.JSONDecodeError):
            data = {"message": summary}
        if not isinstance(data, dict):
            data = {"value": data}
        await self._send(UIUpdateOut(callId=call_id, data=data))

    # ------------------------------------------------------------------
    # (a) Fetch and forward a UI resource
    # ------------------------------------------------------------------

    async def _send_ui_resource(self, call_id: str, entry: ToolEntry) -> None:
        assert entry.ui_meta is not None
        try:
            read_result = await self._manager.read_resource(entry.server_id, entry.ui_meta.resource_uri)
        except Exception as exc:
            logger.exception("resources/read failed for %s", entry.ui_meta.resource_uri)
            await self._send(
                AssistantMessageOut(text=f"(Interaktive Ansicht aktuell nicht verfuegbar: {exc})")
            )
            return

        if not read_result.contents:
            return

        content = read_result.contents[0]
        trust_level = self._manager.trust_level(entry.server_id)
        sandbox = build_sandbox_policy(trust_level, content, content_type="rawHtml")

        resource = ResourcePayload(
            uri=str(content.uri),
            mimeType=content.mimeType or "text/html",
            text=getattr(content, "text", None),
            blob=getattr(content, "blob", None),
        )

        self._ui_resources[call_id] = entry.server_id
        await self._send(
            UIResourceOut(callId=call_id, server=entry.server_id, resource=resource, sandbox=sandbox)
        )

    # ------------------------------------------------------------------

    def _tool_specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name=f"{entry.server_id}.{entry.tool.name}",
                description=entry.tool.description or "",
                input_schema=entry.tool.inputSchema,
            )
            for entry in self._manager.list_tools_for_llm()
        ]
