"""Deterministic mock LLM provider.

Implements just enough "intent recognition" to drive the meeting-room
booking demo end-to-end without any API key. It is the default provider
(see ``app/config.py``) and the one exercised by the automated roundtrip
test (``backend/tests/test_agent_loop.py``).
"""

from __future__ import annotations

import json
import uuid

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

_BOOKING_KEYWORDS = ("raum", "room", "buchen", "book", "meeting", "termin")
_LIST_KEYWORDS = ("liste", "list", "verfügbar", "verfuegbar", "welche raeume", "welche räume")


def _find_tool(tools: list[ToolSpec], suffix: str) -> str | None:
    for tool in tools:
        if tool.name.endswith(f".{suffix}"):
            return tool.name
    return None


class MockLLMProvider(LLMProvider):
    async def generate(self, messages: list[Message], tools: list[ToolSpec]) -> AssistantTurn:
        if not messages:
            return AssistantTurn(text=self._greeting())

        last = messages[-1]

        if isinstance(last, UserMessage):
            return self._handle_user_message(last, tools)

        if isinstance(last, ToolResultMessage):
            return self._handle_tool_result(last)

        # Last message is our own AssistantMessage (e.g. after a tool_calls
        # turn whose results haven't arrived yet) - nothing to add.
        return AssistantTurn(text=None)

    def _greeting(self) -> str:
        return (
            "Hallo! Ich bin der Demo-Agent für die Meetingraum-Buchung. "
            "Frag mich z. B. 'Ich möchte einen Meetingraum buchen' oder "
            "'Welche Räume sind verfügbar?'."
        )

    def _handle_user_message(self, message: UserMessage, tools: list[ToolSpec]) -> AssistantTurn:
        text = message.text.lower()

        if any(keyword in text for keyword in _BOOKING_KEYWORDS):
            tool_name = _find_tool(tools, "show_booking_form")
            if tool_name:
                return AssistantTurn(
                    text=None,
                    tool_calls=[ToolCallRequest(id=str(uuid.uuid4()), name=tool_name, arguments={})],
                )

        if any(keyword in text for keyword in _LIST_KEYWORDS):
            tool_name = _find_tool(tools, "list_rooms")
            if tool_name:
                return AssistantTurn(
                    text=None,
                    tool_calls=[ToolCallRequest(id=str(uuid.uuid4()), name=tool_name, arguments={})],
                )

        return AssistantTurn(
            text=(
                "Das habe ich nicht verstanden. Ich kann dir helfen, einen "
                "Meetingraum zu buchen oder die verfügbaren Räume aufzulisten."
            )
        )

    def _handle_tool_result(self, message: ToolResultMessage) -> AssistantTurn:
        tool_name = message.tool_name

        if tool_name.endswith(".show_booking_form"):
            return AssistantTurn(
                text="Hier ist das Buchungsformular. Bitte Raum, Datum, Uhrzeit und "
                "Teilnehmerzahl auswählen und absenden."
            )

        if tool_name.endswith(".list_rooms"):
            try:
                rooms = json.loads(message.content)
            except (TypeError, ValueError, json.JSONDecodeError):
                return AssistantTurn(text=message.content)
            lines = [f"- {r['name']} (max. {r['capacity']} Personen)" for r in rooms]
            return AssistantTurn(text="Verfügbare Räume:\n" + "\n".join(lines))

        if tool_name.endswith(".book_room"):
            try:
                booking = json.loads(message.content)
            except (TypeError, ValueError, json.JSONDecodeError):
                return AssistantTurn(text=message.content)

            if booking.get("status") == "confirmed":
                return AssistantTurn(
                    text=(
                        f"✅ {booking['roomName']} wurde für {booking['date']} um "
                        f"{booking['time']} für {booking['attendees']} Personen "
                        f"gebucht (Buchungs-ID {booking['bookingId']})."
                    )
                )
            return AssistantTurn(text=f"❌ Buchung nicht möglich: {booking.get('reason', 'unbekannter Fehler')}")

        if message.is_error:
            return AssistantTurn(text=f"Beim Aufruf von {tool_name} ist ein Fehler aufgetreten: {message.content}")

        return AssistantTurn(text=f"Ergebnis von {tool_name}: {message.content}")
