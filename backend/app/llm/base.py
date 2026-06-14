"""Abstraction for the LLM provider used by the agent loop.

The agent loop (``app/agent/loop.py``) only depends on :class:`LLMProvider`.
This keeps the MCP/UI plumbing fully testable without API credentials via
:class:`app.llm.mock.MockLLMProvider`, while :class:`app.llm.anthropic_provider.AnthropicLLMProvider`
provides a real implementation for the same interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal, Union


@dataclass
class ToolSpec:
    """Tool definition as presented to the LLM."""

    name: str  # fully-qualified "<server_id>.<tool_name>"
    description: str
    input_schema: dict


@dataclass
class ToolCallRequest:
    id: str
    name: str  # fully-qualified "<server_id>.<tool_name>"
    arguments: dict


@dataclass
class UserMessage:
    text: str
    role: Literal["user"] = "user"


@dataclass
class AssistantMessage:
    text: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    role: Literal["assistant"] = "assistant"


@dataclass
class ToolResultMessage:
    tool_call_id: str
    tool_name: str  # fully-qualified "<server_id>.<tool_name>"
    content: str
    is_error: bool = False
    role: Literal["tool"] = "tool"


Message = Union[UserMessage, AssistantMessage, ToolResultMessage]


@dataclass
class AssistantTurn:
    text: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)


class LLMProvider(ABC):
    """One step of the agent loop: given the conversation so far and the
    available tools, produce the next assistant turn (text and/or tool
    calls)."""

    @abstractmethod
    async def generate(self, messages: list[Message], tools: list[ToolSpec]) -> AssistantTurn:
        raise NotImplementedError
