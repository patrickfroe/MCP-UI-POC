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

from mcp_server_example.templates import render_booking_form_html, render_dashboard_html

mcp = FastMCP("room-booking")

BOOKING_FORM_RESOURCE_URI = "ui://room-booking/booking-form"
DASHBOARD_RESOURCE_URI = "ui://room-booking/analytics-dashboard"

ROOMS: list[dict[str, Any]] = [
    {"id": "room-a", "name": "Raum A", "capacity": 4},
    {"id": "room-b", "name": "Raum B", "capacity": 8},
    {"id": "room-c", "name": "Raum C (groß)", "capacity": 20},
]

# In-memory booking store - good enough for a PoC, no persistence needed.
# Seeded with a few bookings so the analytics dashboard has data to show.
BOOKINGS: dict[str, dict[str, Any]] = {}
for _seed in [
    {"roomId": "room-a", "roomName": "Raum A", "date": "2025-06-02", "time": "09:00", "attendees": 3},
    {"roomId": "room-a", "roomName": "Raum A", "date": "2025-06-03", "time": "14:00", "attendees": 2},
    {"roomId": "room-b", "roomName": "Raum B", "date": "2025-06-02", "time": "11:00", "attendees": 6},
    {"roomId": "room-c", "roomName": "Raum C (groß)", "date": "2025-06-04", "time": "10:00", "attendees": 15},
    {"roomId": "room-b", "roomName": "Raum B", "date": "2025-06-04", "time": "13:00", "attendees": 5},
]:
    _booking_id = str(uuid.uuid4())
    BOOKINGS[_booking_id] = {"status": "confirmed", "bookingId": _booking_id, **_seed}


def _compute_dashboard_data(metric: str) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for booking in BOOKINGS.values():
        key = booking["roomName"] if metric == "by_room" else booking["date"]
        counts[key] = counts.get(key, 0) + 1

    labels = sorted(counts.keys())
    values = [counts[label] for label in labels]
    return {"metric": metric, "labels": labels, "values": values}


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


@mcp.tool(
    description=(
        "Zeigt ein interaktives Analytics-Dashboard mit Buchungsstatistiken "
        "an (z.B. Buchungen pro Raum oder pro Tag)."
    ),
    meta={
        "ui": {
            "resourceUri": DASHBOARD_RESOURCE_URI,
            "visibility": ["model", "app"],
        }
    },
)
def show_analytics_dashboard() -> str:
    return "Das Analytics-Dashboard wurde geöffnet."


@mcp.tool(
    description=(
        "Liefert aggregierte Buchungsstatistiken, gefiltert nach Metrik "
        "('by_room' fuer Buchungen pro Raum oder 'by_day' fuer Buchungen pro Tag)."
    )
)
def get_dashboard_data(metric: str = "by_room") -> dict[str, Any]:
    if metric not in ("by_room", "by_day"):
        metric = "by_room"
    return _compute_dashboard_data(metric)


@mcp.resource(
    DASHBOARD_RESOURCE_URI,
    name="analytics_dashboard",
    title="Analytics-Dashboard",
    description="Interaktives Dashboard mit Buchungsstatistiken.",
    mime_type="text/html;profile=mcp-app",
)
def analytics_dashboard_resource() -> str:
    return render_dashboard_html(_compute_dashboard_data("by_room"))


if __name__ == "__main__":
    mcp.run()
