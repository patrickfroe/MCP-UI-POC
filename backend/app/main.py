"""FastAPI application: WebSocket gateway for the MCP-Apps chat PoC.

Run with:

    uvicorn app.main:app --reload --port 8000

See ``README.md`` (repo root) for full setup instructions.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from app.agent.loop import AgentSession
from app.config import Settings, load_settings
from app.llm.base import LLMProvider
from app.mcp_client.manager import MCPServerManager
from app.ws.protocol import (
    ClientMessage,
    ErrorOut,
    UIActionIn,
    UserMessageIn,
    client_message_adapter,
    dump_server_message,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise RuntimeError("LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY")
        from app.llm.anthropic_provider import AnthropicLLMProvider

        return AnthropicLLMProvider(api_key=settings.anthropic_api_key, model=settings.anthropic_model)

    from app.llm.mock import MockLLMProvider

    return MockLLMProvider()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    manager = MCPServerManager(settings.mcp_servers)
    await manager.start()

    app.state.settings = settings
    app.state.mcp_manager = manager
    try:
        yield
    finally:
        await manager.stop()


app = FastAPI(title="MCP Apps Chat PoC Backend", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket) -> None:
    settings: Settings = websocket.app.state.settings
    manager: MCPServerManager = websocket.app.state.mcp_manager

    await websocket.accept()

    async def send(message) -> None:
        await websocket.send_json(dump_server_message(message))

    session = AgentSession(manager=manager, llm=get_llm_provider(settings), send=send)

    try:
        while True:
            raw = await websocket.receive_json()
            try:
                message: ClientMessage = client_message_adapter.validate_python(raw)
            except ValidationError as exc:
                await send(ErrorOut(message=f"Ungueltige Nachricht: {exc}"))
                continue

            if isinstance(message, UserMessageIn):
                await session.handle_user_message(message.text)
            elif isinstance(message, UIActionIn):
                await session.handle_ui_action(message.callId, message.action)
    except WebSocketDisconnect:
        logger.info("Client disconnected")
