"""Real LLM provider backed by the Anthropic Messages API.

Activated when ``ANTHROPIC_API_KEY`` is set (see ``app/config.py``). Not
exercised by the automated tests (no live credentials in CI/PoC), but
implements the same :class:`app.llm.base.LLMProvider` interface as
:class:`app.llm.mock.MockLLMProvider`, so the agent loop is identical either
way.

Anthropic tool names must match ``^[a-zA-Z0-9_-]{1,128}$`` and therefore
cannot contain the ``.`` used in our ``"<server_id>.<tool_name>"`` keys. We
map ``.`` <-> ``__`` (first occurrence only) when talking to the API.
"""

from __future__ import annotations

import anthropic

from app.llm.base import (
    AssistantMessage,
    AssistantTurn,
    LLMProvider,
    Message,
    ToolCallRequest,
    ToolResultMessage,
    ToolSpec,
    UserMessage,
)

SYSTEM_PROMPT = (
    "Du bist ein hilfreicher Assistent in einer Chat-Anwendung mit MCP-Tools. "
    "Wenn ein Tool eine interaktive UI-Ressource bereitstellt, ruf es auf und "
    "beschreibe dem Nutzer kurz, was als Naechstes zu tun ist. Antworte auf "
    "Deutsch."
)


def _to_anthropic_name(fq_name: str) -> str:
    return fq_name.replace(".", "__", 1)


def _from_anthropic_name(name: str) -> str:
    return name.replace("__", ".", 1)


def _build_anthropic_messages(messages: list[Message]) -> list[dict]:
    result: list[dict] = []
    for msg in messages:
        if isinstance(msg, UserMessage):
            result.append({"role": "user", "content": msg.text})
        elif isinstance(msg, AssistantMessage):
            content: list[dict] = []
            if msg.text:
                content.append({"type": "text", "text": msg.text})
            for tc in msg.tool_calls:
                content.append(
                    {
                        "type": "tool_use",
                        "id": tc.id,
                        "name": _to_anthropic_name(tc.name),
                        "input": tc.arguments,
                    }
                )
            result.append({"role": "assistant", "content": content})
        elif isinstance(msg, ToolResultMessage):
            block: dict = {
                "type": "tool_result",
                "tool_use_id": msg.tool_call_id,
                "content": msg.content,
            }
            if msg.is_error:
                block["is_error"] = True

            last = result[-1] if result else None
            if (
                last is not None
                and last["role"] == "user"
                and isinstance(last["content"], list)
                and last["content"]
                and last["content"][0].get("type") == "tool_result"
            ):
                last["content"].append(block)
            else:
                result.append({"role": "user", "content": [block]})
    return result


class AnthropicLLMProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def generate(self, messages: list[Message], tools: list[ToolSpec]) -> AssistantTurn:
        anthropic_tools = [
            {
                "name": _to_anthropic_name(tool.name),
                "description": tool.description,
                "input_schema": tool.input_schema or {"type": "object", "properties": {}},
            }
            for tool in tools
        ]

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=_build_anthropic_messages(messages),
            tools=anthropic_tools,
        )

        text_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCallRequest(
                        id=block.id,
                        name=_from_anthropic_name(block.name),
                        arguments=block.input,
                    )
                )

        return AssistantTurn(text="\n".join(text_parts) or None, tool_calls=tool_calls)
