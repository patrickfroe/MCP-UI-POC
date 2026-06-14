"""WebSocket message protocol between the Angular frontend and the backend.

See ``docs/konzept-mcp-apps.md`` section 5.2 for the full message catalogue
and the rationale (WebSocket transport, ``callId`` correlation).

``UIActionResult`` (the ``tool``/``prompt``/``link``/``intent``/``notify``
payloads sent by the rendered UI resource) is reused as-is from
``mcp_ui_server`` - it is exactly the contract the example server's HTML
speaks (see ``mcp-server-example``).
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from mcp_ui_server.types import UIActionResult
from pydantic import BaseModel, Field, TypeAdapter

from app.mcp_client.ui import SandboxPolicy

# ---- Client -> Server -------------------------------------------------------


class UserMessageIn(BaseModel):
    type: Literal["user_message"] = "user_message"
    text: str


class UIActionIn(BaseModel):
    type: Literal["ui_action"] = "ui_action"
    callId: str
    action: UIActionResult


ClientMessage = Annotated[Union[UserMessageIn, UIActionIn], Field(discriminator="type")]
client_message_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


# ---- Server -> Client --------------------------------------------------------


class AssistantMessageOut(BaseModel):
    type: Literal["assistant_message"] = "assistant_message"
    text: str


class ToolCallOut(BaseModel):
    """Transparency: the agent is calling a tool."""

    type: Literal["tool_call"] = "tool_call"
    callId: str
    server: str
    tool: str
    args: dict


class ToolResultOut(BaseModel):
    """Transparency: result of a tool call."""

    type: Literal["tool_result"] = "tool_result"
    callId: str
    server: str
    tool: str
    isError: bool
    summary: str


class ResourcePayload(BaseModel):
    uri: str
    mimeType: str
    text: str | None = None
    blob: str | None = None


class UIResourceOut(BaseModel):
    """A new UI resource to render in a sandboxed iframe."""

    type: Literal["ui_resource"] = "ui_resource"
    callId: str
    server: str
    resource: ResourcePayload
    sandbox: SandboxPolicy


class UIUpdateOut(BaseModel):
    """Push data into an already-rendered iframe (identified by callId)."""

    type: Literal["ui_update"] = "ui_update"
    callId: str
    data: dict


class StatusOut(BaseModel):
    type: Literal["status"] = "status"
    state: Literal["thinking", "idle"]


class NoticeOut(BaseModel):
    """Out-of-band UI actions (``link``/``notify``/``intent``) surfaced as a
    small banner in the chat."""

    type: Literal["notice"] = "notice"
    level: Literal["info", "link"]
    message: str
    url: str | None = None


class ErrorOut(BaseModel):
    type: Literal["error"] = "error"
    message: str


ServerMessage = Union[
    AssistantMessageOut,
    ToolCallOut,
    ToolResultOut,
    UIResourceOut,
    UIUpdateOut,
    StatusOut,
    NoticeOut,
    ErrorOut,
]


def dump_server_message(message: ServerMessage) -> dict:
    return message.model_dump(by_alias=True, exclude_none=True)
