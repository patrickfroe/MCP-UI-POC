"""Example MCP server: a tiny meeting-room booking tool with an MCP Apps UI.

Run with:

    python -m mcp_server_example

This uses the stdio transport (FastMCP default), which is how the PoC
backend spawns it (see ``backend/app/mcp_client/manager.py``).

Tool/resource design (see ``docs/konzept-mcp-apps.md`` for the full
rationale):

- ``list_rooms``       - plain data tool, no UI.
- ``show_booking_form`` - UI tool. Declares ``_meta.ui.resourceUri`` pointing
  at the ``ui://room-booking/booking-form`` resource (SEP-1865 tool-UI
  linkage convention).
- ``book_room``        - performs the booking. Called either directly by the
  agent/model, or indirectly via a ``UIActionResult`` of type ``tool`` sent
  from the rendered form.
- ``ui://room-booking/booking-form`` - the interactive form, served with MIME
  type ``text/html;profile=mcp-app``.
"""

from __future__ import annotations

import uuid
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_server_example.templates import render_booking_form_html

mcp = FastMCP("room-booking")

BOOKING_FORM_RESOURCE_URI = "ui://room-booking/booking-form"

ROOMS: list[dict[str, Any]] = [
    {"id": "room-a", "name": "Raum A", "capacity": 4},
    {"id": "room-b", "name": "Raum B", "capacity": 8},
    {"id": "room-c", "name": "Raum C (groß)", "capacity": 20},
]

# In-memory booking store - good enough for a PoC, no persistence needed.
BOOKINGS: dict[str, dict[str, Any]] = {}


@mcp.tool(description="Liste der buchbaren Meetingräume mit Kapazität.")
def list_rooms() -> list[dict[str, Any]]:
    return ROOMS


@mcp.tool(
    description=(
        "Zeigt ein interaktives Formular zur Buchung eines Meetingraums an. "
        "Benutze dieses Tool, wenn der Nutzer einen Raum buchen moechte."
    ),
    meta={
        "ui": {
            "resourceUri": BOOKING_FORM_RESOURCE_URI,
            "visibility": ["model", "app"],
        }
    },
)
def show_booking_form() -> str:
    return (
        "Das Buchungsformular wurde geöffnet. Bitte Raum, Datum, Uhrzeit und "
        "Teilnehmerzahl auswählen und absenden."
    )


@mcp.tool(
    description=(
        "Bucht einen Meetingraum fuer ein Datum/Uhrzeit und eine Anzahl von "
        "Teilnehmern. Wird sowohl direkt vom Modell als auch ueber das "
        "Buchungsformular aufgerufen."
    )
)
def book_room(room_id: str, date: str, time: str, attendees: int) -> dict[str, Any]:
    room = next((r for r in ROOMS if r["id"] == room_id), None)
    if room is None:
        return {"status": "rejected", "reason": f"Unbekannter Raum: {room_id}"}

    if attendees > room["capacity"]:
        return {
            "status": "rejected",
            "reason": (
                f"{room['name']} hat nur Platz fuer {room['capacity']} "
                f"Personen, angefragt wurden {attendees}."
            ),
        }

    booking_id = str(uuid.uuid4())
    booking = {
        "status": "confirmed",
        "bookingId": booking_id,
        "roomId": room["id"],
        "roomName": room["name"],
        "date": date,
        "time": time,
        "attendees": attendees,
    }
    BOOKINGS[booking_id] = booking
    return booking


@mcp.resource(
    BOOKING_FORM_RESOURCE_URI,
    name="booking_form",
    title="Meetingraum-Buchungsformular",
    description="Interaktives Formular zur Buchung eines Meetingraums.",
    mime_type="text/html;profile=mcp-app",
)
def booking_form_resource() -> str:
    return render_booking_form_html(ROOMS)


if __name__ == "__main__":
    mcp.run()
