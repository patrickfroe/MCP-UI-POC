"""End-to-end roundtrip tests for AgentSession against the bundled example
MCP server (see docs/konzept-mcp-apps.md flows a/b/c).

Uses MockLLMProvider so the test runs without any LLM credentials. Each test
spawns the real `mcp-server-example` over stdio via MCPServerManager.
"""

from __future__ import annotations

import asyncio
import json

import pytest_asyncio
from mcp_ui_server.types import UIActionResultToolCall

from app.agent.loop import AgentSession
from app.config import _default_servers
from app.llm.mock import MockLLMProvider
from app.mcp_client.manager import MCPServerManager
from app.ws.protocol import (
    AssistantMessageOut,
    ServerMessage,
    StatusOut,
    ToolCallOut,
    ToolResultOut,
    UIResourceOut,
    UIUpdateOut,
)


@pytest_asyncio.fixture
async def manager():
    # MCPServerManager.start()/stop() open anyio task groups (via
    # stdio_client/ClientSession) whose cancel scopes must be entered and
    # exited from the same asyncio task. pytest-asyncio drives a fixture's
    # setup and teardown phases via separate `asend()` calls, which can land
    # on different tasks. Running both start() and stop() inside one
    # explicitly created task avoids the resulting
    # "cancel scope in a different task" RuntimeError on teardown.
    mgr = MCPServerManager(_default_servers())
    started = asyncio.Event()
    stop_requested = asyncio.Event()

    async def runner() -> None:
        await mgr.start()
        started.set()
        await stop_requested.wait()
        await mgr.stop()

    task = asyncio.create_task(runner())
    await started.wait()
    try:
        yield mgr
    finally:
        stop_requested.set()
        await task


def _new_session(manager: MCPServerManager) -> tuple[AgentSession, list[ServerMessage]]:
    sent: list[ServerMessage] = []

    async def send(message: ServerMessage) -> None:
        sent.append(message)

    return AgentSession(manager=manager, llm=MockLLMProvider(), send=send), sent


def _book_room_action(**params) -> UIActionResultToolCall:
    return UIActionResultToolCall.model_validate({"type": "tool", "payload": {"toolName": "book_room", "params": params}})


async def test_user_message_triggers_ui_resource(manager: MCPServerManager) -> None:
    session, sent = _new_session(manager)

    await session.handle_user_message("Ich möchte einen Raum buchen")

    assert isinstance(sent[0], StatusOut) and sent[0].state == "thinking"
    assert isinstance(sent[-1], StatusOut) and sent[-1].state == "idle"

    tool_call = next(m for m in sent if isinstance(m, ToolCallOut))
    assert tool_call.server == "room-booking"
    assert tool_call.tool == "show_booking_form"

    tool_result = next(m for m in sent if isinstance(m, ToolResultOut))
    assert tool_result.tool == "show_booking_form"
    assert not tool_result.isError

    ui_resource = next(m for m in sent if isinstance(m, UIResourceOut))
    assert ui_resource.server == "room-booking"
    assert ui_resource.resource.uri == "ui://room-booking/booking-form"
    assert ui_resource.resource.mimeType == "text/html;profile=mcp-app"
    assert ui_resource.resource.text is not None and "booking-form" in ui_resource.resource.text
    assert ui_resource.sandbox.sandbox_attributes == "allow-scripts allow-forms"
    assert ui_resource.sandbox.trust_level == "trusted"

    assistant_messages = [m for m in sent if isinstance(m, AssistantMessageOut)]
    assert assistant_messages, "expected the mock LLM to comment on the tool result"


async def test_ui_action_books_room_and_pushes_update(manager: MCPServerManager) -> None:
    session, sent = _new_session(manager)
    await session.handle_user_message("Ich möchte einen Raum buchen")

    call_id = next(m for m in sent if isinstance(m, UIResourceOut)).callId
    sent.clear()

    await session.handle_ui_action(
        call_id, _book_room_action(room_id="room-a", date="2026-06-20", time="10:00", attendees=3)
    )

    # (b) the UI action is recorded as a regular tool call ...
    tool_call = next(m for m in sent if isinstance(m, ToolCallOut))
    assert tool_call.callId == call_id
    assert tool_call.tool == "book_room"
    assert tool_call.args == {"room_id": "room-a", "date": "2026-06-20", "time": "10:00", "attendees": 3}

    tool_result = next(m for m in sent if isinstance(m, ToolResultOut))
    assert not tool_result.isError
    booking = json.loads(tool_result.summary)
    assert booking["status"] == "confirmed"
    assert booking["roomName"] == "Raum A"

    # (c) ... and pushed back into the same iframe via callId correlation.
    ui_update = next(m for m in sent if isinstance(m, UIUpdateOut))
    assert ui_update.callId == call_id
    assert ui_update.data["status"] == "confirmed"
    assert ui_update.data["roomName"] == "Raum A"

    final_message = next(m for m in sent if isinstance(m, AssistantMessageOut))
    assert "Raum A" in final_message.text
    assert "gebucht" in final_message.text

    assert isinstance(sent[-1], StatusOut) and sent[-1].state == "idle"


async def test_ui_action_rejects_booking_over_capacity(manager: MCPServerManager) -> None:
    session, sent = _new_session(manager)
    await session.handle_user_message("Ich möchte einen Raum buchen")

    call_id = next(m for m in sent if isinstance(m, UIResourceOut)).callId
    sent.clear()

    # Raum A has capacity 4 (see mcp_server_example.server.ROOMS).
    await session.handle_ui_action(
        call_id, _book_room_action(room_id="room-a", date="2026-06-20", time="10:00", attendees=99)
    )

    tool_result = next(m for m in sent if isinstance(m, ToolResultOut))
    assert not tool_result.isError  # rejection is a normal tool result, not a transport error
    booking = json.loads(tool_result.summary)
    assert booking["status"] == "rejected"

    ui_update = next(m for m in sent if isinstance(m, UIUpdateOut))
    assert ui_update.callId == call_id
    assert ui_update.data["status"] == "rejected"

    final_message = next(m for m in sent if isinstance(m, AssistantMessageOut))
    assert "nicht möglich" in final_message.text


async def test_ui_action_for_unknown_call_id_is_rejected(manager: MCPServerManager) -> None:
    from app.ws.protocol import ErrorOut

    session, sent = _new_session(manager)

    await session.handle_ui_action("does-not-exist", _book_room_action(room_id="room-a", date="2026-06-20", time="10:00", attendees=1))

    assert len(sent) == 1
    assert isinstance(sent[0], ErrorOut)
