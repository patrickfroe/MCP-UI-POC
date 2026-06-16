"""HTML templates for the ui:// resources exposed by this server.

The HTML returned here is intentionally framework-free: it only relies on the
``window.parent.postMessage`` contract defined by MCP-UI (``UIActionResult``,
see ``docs/konzept-mcp-apps.md`` section 2.2) and on a ``mcp-ui-update``
``CustomEvent`` that the host (Angular) dispatches on ``document`` whenever it
forwards a backend push (``ui_update``) into this iframe.

``create_ui_resource`` from ``mcp_ui_server`` is used to validate/build the
resource payload (correct ``ui://`` prefix, MIME type derivation, encoding).
The resulting text is then re-published as a SEP-1865 style ``ui://`` resource
with MIME type ``text/html;profile=mcp-app`` by ``server.py``.
"""

from __future__ import annotations

import json
from typing import Any

from mcp_ui_server import create_ui_resource


def render_booking_form_html(rooms: list[dict[str, Any]]) -> str:
    """Render the interactive meeting-room booking form.

    The list of bookable rooms is baked into the document as
    ``window.__MCP_UI_INITIAL_DATA__`` so the form can populate its room
    selector and show capacities without a separate round-trip.
    """

    rooms_json = json.dumps(rooms)

    html = f"""<!DOCTYPE html>
<html lang="de">
  <head>
    <meta charset="utf-8" />
    <style>
      :root {{
        color-scheme: light dark;
        font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
      }}
      body {{
        margin: 0;
        padding: 16px;
        box-sizing: border-box;
      }}
      h2 {{
        margin: 0 0 12px;
        font-size: 1.05rem;
      }}
      form {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px 12px;
      }}
      label {{
        display: flex;
        flex-direction: column;
        font-size: 0.8rem;
        font-weight: 600;
        gap: 4px;
      }}
      label.full {{
        grid-column: 1 / -1;
      }}
      input, select {{
        font-size: 0.95rem;
        padding: 6px 8px;
        border-radius: 6px;
        border: 1px solid #9098a8;
        background: Field;
        color: FieldText;
      }}
      .actions {{
        grid-column: 1 / -1;
        display: flex;
        align-items: center;
        gap: 12px;
        margin-top: 4px;
      }}
      button {{
        padding: 8px 16px;
        border-radius: 6px;
        border: none;
        background: #2563eb;
        color: #fff;
        font-weight: 600;
        cursor: pointer;
      }}
      button:hover {{
        background: #1d4ed8;
      }}
      a.policy-link {{
        font-size: 0.8rem;
        color: #2563eb;
        text-decoration: none;
      }}
      #status {{
        margin-top: 14px;
        padding: 10px 12px;
        border-radius: 6px;
        font-size: 0.9rem;
        display: none;
      }}
      #status.confirmed {{
        display: block;
        background: #dcfce7;
        color: #166534;
        border: 1px solid #86efac;
      }}
      #status.rejected {{
        display: block;
        background: #fee2e2;
        color: #991b1b;
        border: 1px solid #fca5a5;
      }}
      #status.pending {{
        display: block;
        background: #e0e7ff;
        color: #3730a3;
        border: 1px solid #a5b4fc;
      }}
    </style>
  </head>
  <body>
    <h2>Meetingraum buchen</h2>
    <form id="booking-form">
      <label class="full">
        Raum
        <select id="room" name="room"></select>
      </label>
      <label>
        Datum
        <input type="date" id="date" name="date" required />
      </label>
      <label>
        Uhrzeit
        <input type="time" id="time" name="time" required />
      </label>
      <label class="full">
        Anzahl Teilnehmer
        <input type="number" id="attendees" name="attendees" min="1" value="2" required />
      </label>
      <div class="actions">
        <button type="submit">Raum buchen</button>
        <a class="policy-link" href="#" id="policy-link">Buchungsrichtlinien</a>
      </div>
    </form>
    <div id="status"></div>

    <script>
      const ROOMS = {rooms_json};

      const roomSelect = document.getElementById("room");
      for (const room of ROOMS) {{
        const option = document.createElement("option");
        option.value = room.id;
        option.textContent = `${{room.name}} (max. ${{room.capacity}} Personen)`;
        roomSelect.appendChild(option);
      }}

      const statusEl = document.getElementById("status");

      function showStatus(cls, text) {{
        statusEl.className = cls;
        statusEl.textContent = text;
      }}

      document.getElementById("booking-form").addEventListener("submit", (event) => {{
        event.preventDefault();

        const params = {{
          room_id: roomSelect.value,
          date: document.getElementById("date").value,
          time: document.getElementById("time").value,
          attendees: Number(document.getElementById("attendees").value),
        }};

        showStatus("pending", "Buchung wird angefragt …");

        // UIActionResult (MCP-UI): the host translates this into a
        // tools/call("book_room", params) against this server and pushes
        // the result back via a "ui_update" -> "mcp-ui-update" event.
        window.parent.postMessage(
          {{ type: "tool", payload: {{ toolName: "book_room", params }} }},
          "*"
        );
      }});

      document.getElementById("policy-link").addEventListener("click", (event) => {{
        event.preventDefault();
        window.parent.postMessage(
          {{ type: "link", payload: {{ url: "https://example.com/booking-policy" }} }},
          "*"
        );
      }});

      // Backend push (ui_update) is re-dispatched by the host as a
      // "mcp-ui-update" CustomEvent on `document`.
      document.addEventListener("mcp-ui-update", (event) => {{
        const data = event.detail || {{}};
        if (data.status === "confirmed") {{
          showStatus(
            "confirmed",
            `✅ Gebucht: ${{data.roomName}} am ${{data.date}} um ${{data.time}} ` +
              `für ${{data.attendees}} Personen (Buchungs-ID ${{data.bookingId}}).`
          );
        }} else if (data.status === "rejected") {{
          showStatus("rejected", `❌ Buchung abgelehnt: ${{data.reason}}`);
        }}
      }});
    </script>
  </body>
</html>
"""

    # Validate/normalize through mcp-ui-server's helper. This ensures the
    # `ui://` prefix and content-type/encoding rules are honoured even though
    # the final MIME type used for the registered resource is overridden to
    # `text/html;profile=mcp-app` in server.py to align with SEP-1865.
    resource = create_ui_resource(
        {
            "uri": "ui://room-booking/booking-form",
            "content": {"type": "rawHtml", "htmlString": html},
            "encoding": "text",
        }
    )
    return resource.resource.text


def render_dashboard_html(data: dict[str, Any]) -> str:
    """Render the analytics dashboard showing booking counts as a bar chart.

    The chart is drawn as plain inline SVG, generated and updated by
    framework-free JS - no external chart library / CDN script is used,
    since the sandbox CSP only allows ``script-src 'unsafe-inline'`` and
    forbids loading external resources.

    ``data`` (``{"metric": ..., "labels": [...], "values": [...]}``) is baked
    in as ``window.__MCP_UI_INITIAL_DATA__``, mirroring the room list in
    ``render_booking_form_html``. Selecting a different metric posts a
    ``tool`` UIActionResult for ``get_dashboard_data``; the result comes back
    as a ``mcp-ui-update`` event and is rendered with the same function.
    """

    data_json = json.dumps(data)

    html = f"""<!DOCTYPE html>
<html lang="de">
  <head>
    <meta charset="utf-8" />
    <style>
      :root {{
        color-scheme: light dark;
        font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
      }}
      body {{
        margin: 0;
        padding: 16px;
        box-sizing: border-box;
      }}
      h2 {{
        margin: 0 0 12px;
        font-size: 1.05rem;
      }}
      label {{
        display: flex;
        flex-direction: column;
        font-size: 0.8rem;
        font-weight: 600;
        gap: 4px;
        max-width: 220px;
        margin-bottom: 12px;
      }}
      select {{
        font-size: 0.95rem;
        padding: 6px 8px;
        border-radius: 6px;
        border: 1px solid #9098a8;
        background: Field;
        color: FieldText;
      }}
      #chart {{
        width: 100%;
        height: 220px;
        overflow: visible;
      }}
      .bar {{
        fill: #2563eb;
      }}
      .bar-label {{
        font-size: 11px;
        fill: currentColor;
        text-anchor: middle;
      }}
      .value-label {{
        font-size: 11px;
        font-weight: 600;
        fill: currentColor;
        text-anchor: middle;
      }}
    </style>
  </head>
  <body>
    <h2>Buchungs-Statistik</h2>
    <label>
      Metrik
      <select id="metric">
        <option value="by_room">Buchungen pro Raum</option>
        <option value="by_day">Buchungen pro Tag</option>
      </select>
    </label>
    <svg id="chart" viewBox="0 0 320 220" preserveAspectRatio="xMidYMid meet"></svg>

    <script>
      const INITIAL = {data_json};

      const metricSelect = document.getElementById("metric");
      metricSelect.value = INITIAL.metric;

      const svg = document.getElementById("chart");

      function renderChart(data) {{
        const labels = data.labels || [];
        const values = data.values || [];
        const maxValue = Math.max(1, ...values);

        const width = 320;
        const height = 220;
        const chartHeight = 160;
        const barWidth = labels.length ? width / labels.length : width;

        svg.innerHTML = "";

        labels.forEach((label, index) => {{
          const value = values[index] || 0;
          const barHeight = (value / maxValue) * chartHeight;
          const x = index * barWidth + barWidth * 0.15;
          const y = chartHeight - barHeight;
          const barW = barWidth * 0.7;

          const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
          rect.setAttribute("class", "bar");
          rect.setAttribute("x", x);
          rect.setAttribute("y", y);
          rect.setAttribute("width", barW);
          rect.setAttribute("height", Math.max(barHeight, 1));
          svg.appendChild(rect);

          const valueText = document.createElementNS("http://www.w3.org/2000/svg", "text");
          valueText.setAttribute("class", "value-label");
          valueText.setAttribute("x", x + barW / 2);
          valueText.setAttribute("y", y - 4);
          valueText.textContent = value;
          svg.appendChild(valueText);

          const labelText = document.createElementNS("http://www.w3.org/2000/svg", "text");
          labelText.setAttribute("class", "bar-label");
          labelText.setAttribute("x", x + barW / 2);
          labelText.setAttribute("y", chartHeight + 20);
          labelText.textContent = label;
          svg.appendChild(labelText);
        }});
      }}

      renderChart(INITIAL);

      metricSelect.addEventListener("change", () => {{
        // UIActionResult (MCP-UI): the host translates this into a
        // tools/call("get_dashboard_data", params) against this server and
        // pushes the result back via a "ui_update" -> "mcp-ui-update" event.
        window.parent.postMessage(
          {{
            type: "tool",
            payload: {{ toolName: "get_dashboard_data", params: {{ metric: metricSelect.value }} }},
          }},
          "*"
        );
      }});

      // Backend push (ui_update) is re-dispatched by the host as a
      // "mcp-ui-update" CustomEvent on `document`.
      document.addEventListener("mcp-ui-update", (event) => {{
        const data = event.detail || {{}};
        if (data.labels && data.values) {{
          renderChart(data);
        }}
      }});
    </script>
  </body>
</html>
"""

    resource = create_ui_resource(
        {
            "uri": "ui://room-booking/analytics-dashboard",
            "content": {"type": "rawHtml", "htmlString": html},
            "encoding": "text",
        }
    )
    return resource.resource.text
