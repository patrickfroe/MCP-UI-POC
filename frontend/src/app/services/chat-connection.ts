import { Injectable, signal } from '@angular/core';
import { ReplaySubject, Subject } from 'rxjs';

import { ClientMessage, ServerMessage } from '../models/protocol';

export type ConnectionState = 'connecting' | 'open' | 'closed';

/**
 * Default WebSocket endpoint of the PoC backend (`backend/app/main.py`,
 * `/ws/chat`). The Angular dev server runs on port 4200, the backend on
 * 8000 - both are assumed to run on the same host.
 */
function defaultWsUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${protocol}://${window.location.hostname}:8000/ws/chat`;
}

/**
 * Thin wrapper around the `/ws/chat` WebSocket. Owns the connection and the
 * per-`callId` `ui_update` streams (see docs/konzept-mcp-apps.md 5.2/6.2) so
 * that `ChatComponent` and `McpUiFrameComponent` instances can be created
 * and destroyed independently of the socket lifecycle.
 */
@Injectable({
  providedIn: 'root',
})
export class ChatConnection {
  readonly state = signal<ConnectionState>('connecting');
  readonly messages = new Subject<ServerMessage>();

  private socket?: WebSocket;
  private readonly updateStreams = new Map<string, ReplaySubject<Record<string, unknown>>>();

  connect(url: string = defaultWsUrl()): void {
    if (this.socket) {
      return;
    }

    this.state.set('connecting');
    const socket = new WebSocket(url);
    this.socket = socket;

    socket.addEventListener('open', () => this.state.set('open'));
    socket.addEventListener('close', () => this.state.set('closed'));
    socket.addEventListener('error', () => this.state.set('closed'));
    socket.addEventListener('message', (event) => this.onMessage(event));
  }

  send(message: ClientMessage): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      console.warn('Cannot send message, WebSocket is not open', message);
      return;
    }
    this.socket.send(JSON.stringify(message));
  }

  /**
   * Stream of `ui_update.data` for a given `callId`, replaying the most
   * recent value to late subscribers (a `ui_update` may arrive before the
   * corresponding `McpUiFrameComponent` has finished rendering).
   */
  updatesFor(callId: string): ReplaySubject<Record<string, unknown>> {
    let subject = this.updateStreams.get(callId);
    if (!subject) {
      subject = new ReplaySubject<Record<string, unknown>>(1);
      this.updateStreams.set(callId, subject);
    }
    return subject;
  }

  private onMessage(event: MessageEvent): void {
    let message: ServerMessage;
    try {
      message = JSON.parse(event.data);
    } catch (err) {
      console.error('Received invalid JSON from /ws/chat', event.data, err);
      return;
    }

    if (message.type === 'ui_update') {
      this.updatesFor(message.callId).next(message.data);
    }

    this.messages.next(message);
  }
}
