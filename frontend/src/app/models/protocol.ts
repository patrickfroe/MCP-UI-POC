/**
 * WebSocket message protocol shared with the backend.
 *
 * Mirrors `backend/app/ws/protocol.py` (server messages) and
 * `mcp_ui_server.types.UIActionResult` (client/iframe actions). See
 * `docs/konzept-mcp-apps.md` section 5.2 for the authoritative description.
 */

// ---- UIActionResult (emitted by a ui_resource iframe) ----------------------

export interface UIActionResultToolCall {
  type: 'tool';
  messageId?: string | null;
  payload: { toolName: string; params: Record<string, unknown> };
}

export interface UIActionResultPrompt {
  type: 'prompt';
  messageId?: string | null;
  payload: { prompt: string };
}

export interface UIActionResultLink {
  type: 'link';
  messageId?: string | null;
  payload: { url: string };
}

export interface UIActionResultIntent {
  type: 'intent';
  messageId?: string | null;
  payload: { intent: string; params: Record<string, unknown> };
}

export interface UIActionResultNotification {
  type: 'notify';
  messageId?: string | null;
  payload: { message: string };
}

export type UIActionResult =
  | UIActionResultToolCall
  | UIActionResultPrompt
  | UIActionResultLink
  | UIActionResultIntent
  | UIActionResultNotification;

/**
 * Strict validator for messages received from a sandboxed ui_resource
 * iframe (see docs/konzept-mcp-apps.md 7.3, "Schema-Validierung"). Returns
 * `null` for anything that does not match the UIActionResult union exactly
 * so the caller can drop/log it instead of forwarding malformed data to the
 * backend.
 */
export function parseUIActionResult(data: unknown): UIActionResult | null {
  if (typeof data !== 'object' || data === null) {
    return null;
  }
  const { type, payload } = data as Record<string, unknown>;
  if (typeof payload !== 'object' || payload === null) {
    return null;
  }
  const p = payload as Record<string, unknown>;

  switch (type) {
    case 'tool':
      if (typeof p['toolName'] === 'string' && typeof p['params'] === 'object' && p['params'] !== null) {
        return data as UIActionResultToolCall;
      }
      return null;
    case 'prompt':
      if (typeof p['prompt'] === 'string') {
        return data as UIActionResultPrompt;
      }
      return null;
    case 'link':
      if (typeof p['url'] === 'string') {
        return data as UIActionResultLink;
      }
      return null;
    case 'intent':
      if (typeof p['intent'] === 'string' && typeof p['params'] === 'object' && p['params'] !== null) {
        return data as UIActionResultIntent;
      }
      return null;
    case 'notify':
      if (typeof p['message'] === 'string') {
        return data as UIActionResultNotification;
      }
      return null;
    default:
      return null;
  }
}

// ---- Client -> Server --------------------------------------------------------

export interface UserMessageIn {
  type: 'user_message';
  text: string;
}

export interface UIActionIn {
  type: 'ui_action';
  callId: string;
  action: UIActionResult;
}

export type ClientMessage = UserMessageIn | UIActionIn;

// ---- Server -> Client --------------------------------------------------------

export interface AssistantMessageOut {
  type: 'assistant_message';
  text: string;
}

export interface ToolCallOut {
  type: 'tool_call';
  callId: string;
  server: string;
  tool: string;
  args: Record<string, unknown>;
}

export interface ToolResultOut {
  type: 'tool_result';
  callId: string;
  server: string;
  tool: string;
  isError: boolean;
  summary: string;
}

export interface ResourcePayload {
  uri: string;
  mimeType: string;
  text?: string | null;
  blob?: string | null;
}

export interface SandboxPolicy {
  sandboxAttributes: string;
  csp: string;
  trustLevel: 'trusted' | 'untrusted';
}

export interface UIResourceOut {
  type: 'ui_resource';
  callId: string;
  server: string;
  resource: ResourcePayload;
  sandbox: SandboxPolicy;
}

export interface UIUpdateOut {
  type: 'ui_update';
  callId: string;
  data: Record<string, unknown>;
}

export interface StatusOut {
  type: 'status';
  state: 'thinking' | 'idle';
}

export interface NoticeOut {
  type: 'notice';
  level: 'info' | 'link';
  message: string;
  url?: string | null;
}

export interface ErrorOut {
  type: 'error';
  message: string;
}

export type ServerMessage =
  | AssistantMessageOut
  | ToolCallOut
  | ToolResultOut
  | UIResourceOut
  | UIUpdateOut
  | StatusOut
  | NoticeOut
  | ErrorOut;

// ---- Host <-> iframe (postMessage, internal to McpUiFrame) -------------------

/** Sent by the iframe bootstrap script when the document size changes. */
export interface UISizeChangedMessage {
  type: 'ui-size-changed';
  payload: { height: number };
}

/**
 * Sent by the host into the iframe to relay a backend `ui_update`. The
 * bootstrap script re-dispatches this as a `mcp-ui-update` CustomEvent on
 * `document` (see `mcp-server-example`'s templates.py).
 */
export interface UIUpdateMessage {
  type: 'ui-update';
  payload: Record<string, unknown>;
}
