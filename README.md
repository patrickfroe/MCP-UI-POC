# MCP Apps (UI) Chat PoC

Proof-of-concept for integrating **MCP Apps / MCP-UI** interactive resources
(forms, charts, ...) into a chat application:

- **Backend (Python/FastAPI)**: owns the agent loop, the LLM calls and all
  MCP client sessions/tool calls. No secrets ever reach the browser.
- **Frontend (Angular)**: a thin chat UI that renders assistant messages,
  tool-call/result cards and `ui://` resources in a sandboxed `<iframe>`,
  and relays UI actions back to the backend over a WebSocket.
- **`mcp-server-example`**: a small example MCP server (room booking) that
  exposes an interactive HTML booking form as an MCP-UI resource.

The architecture, security model and design decisions are documented in
[`docs/konzept-mcp-apps.md`](docs/konzept-mcp-apps.md). This README only
covers how to run the PoC.

## Prerequisites

- Python ≥ 3.10
- Node.js ≥ 22.12 (tested with 22.22.2) and npm

> **Note on the Angular version**: `docs/konzept-mcp-apps.md` (section 0)
> pins `@angular/core`/`@angular/cli` to `22.0.1`. Angular 22 requires Node
> `>=22.22.3`, which was not available in the dev environment used to build
> this PoC (Node 22.22.2). The frontend therefore uses **Angular 21.2.15**
> (requires Node `^20.19.0 || ^22.12.0 || >=24.0.0`), which is
> protocol-compatible and uses the same standalone-component/signals APIs.
> If Node ≥ 22.22.3 is available, upgrading to Angular 22 should be a
> drop-in change.

## Setup

From the repository root:

```bash
# 1. Python environment (backend + example MCP server)
python -m venv .venv
source .venv/bin/activate
pip install -e ./mcp-server-example
pip install -e "./backend[dev]"

# 2. Frontend dependencies
cd frontend
npm install
cd ..
```

## Running the PoC

### 1. Backend (FastAPI + WebSocket gateway)

```bash
source .venv/bin/activate
cd backend
uvicorn app.main:app --reload --port 8000
```

This starts the WebSocket gateway at `ws://localhost:8000/ws/chat` and a
health check at `http://localhost:8000/health`. On startup it spawns the
bundled `mcp-server-example` over stdio (configured as the `trusted`
`room-booking` server, see `app/config.py`).

By default the backend uses a **mock LLM provider** (`LLM_PROVIDER=mock`,
the default), so no API key is required and the demo runs fully offline.

#### Environment variables (optional)

Set these in your shell before starting `uvicorn` if you want to change the
defaults:

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `mock` (or `anthropic` if `ANTHROPIC_API_KEY` is set) | `mock` uses canned, deterministic responses; `anthropic` calls the real Claude API. |
| `ANTHROPIC_API_KEY` | – | Required when `LLM_PROVIDER=anthropic`. |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Model used by the Anthropic provider. |
| `CORS_ORIGINS` | `http://localhost:4200` | Comma-separated list of allowed frontend origins. |
| `MCP_SERVERS_CONFIG` | bundled `room-booking` example server | JSON array of `MCPServerConfig` objects to connect additional/other MCP servers (see `app/config.py` and section 8 of the concept doc for the trust-level model). |

### 2. Frontend (Angular chat UI)

In a second terminal:

```bash
cd frontend
npm start   # ng serve --port 4200
```

Open `http://localhost:4200/` in a browser. The chat UI connects to the
backend's WebSocket at `ws://localhost:8000/ws/chat`.

## Demo walkthrough

1. Open the frontend and check that the header shows the connection as
   "open" (connected to the backend).
2. Type **"Ich möchte einen Raum buchen"** and send it.
   - The backend calls the `room-booking` server's `show_booking_form`
     tool and the response is rendered as an interactive booking form
     inside a sandboxed iframe in the chat.
3. Fill out the form (choose a room, date, time, number of attendees) and
   submit.
   - The form's `tool` action is sent back to the backend as a regular
     tool call (`book_room`), correlated via the original `callId`.
   - The backend calls `book_room` on the MCP server and pushes the result
     back into the **same** iframe via a `ui_update` message.
   - The assistant posts a follow-up chat message confirming (or
     rejecting, e.g. if the room is over capacity) the booking.

## Tests

### Backend

```bash
source .venv/bin/activate
cd backend
pytest
```

`tests/test_agent_loop.py` runs full roundtrip tests of `AgentSession`
against the real `mcp-server-example` (spawned over stdio) using a mock LLM
provider — covering flows (a)/(b)/(c) from the concept doc: a user message
triggering a `ui_resource`, a UI action booking a room and pushing a
`ui_update`, a rejected (over-capacity) booking, and an unknown `callId`
being rejected.

### Frontend

```bash
cd frontend
npm test
```

Runs the Vitest unit tests for `ChatConnection`, `McpUiFrame` (sandboxing,
CSP/bootstrap injection, postMessage protocol, resizing) and the `Chat`
component.

> No real-browser end-to-end tests are included: the sandboxed environment
> used to build this PoC could not download Playwright's browser binaries.
> The protocol roundtrip was instead verified against the running backend
> and covered by the jsdom-based unit tests above.

## Security model (summary)

- All MCP tool calls, LLM calls and credentials live in the backend. The
  frontend never talks to MCP servers or LLM providers directly.
- Every `ui://` resource is rendered in a sandboxed `<iframe srcdoc>` with a
  restrictive `sandbox` attribute and an injected CSP `<meta>` tag.
- UI resources from servers configured as `untrusted` are rendered with a
  visible "nicht vertrauenswürdige Quelle" badge in the UI.
- Communication between the iframe and the host happens exclusively via
  `postMessage`, validated against the iframe's `contentWindow` and parsed
  through a strict `UIActionResult` schema (`app/models/protocol.ts` /
  `mcp_ui_server.types`) before being acted upon.

See [`docs/konzept-mcp-apps.md`](docs/konzept-mcp-apps.md) sections 7–10 for
the full security model, multi-server/trust-level design and known
limitations.

## Project structure

```
backend/                Python backend (FastAPI, agent loop, MCP client)
mcp-server-example/     Example MCP server (room booking + MCP-UI form)
frontend/               Angular chat UI (host/renderer)
docs/konzept-mcp-apps.md  Architecture & security concept document
```
