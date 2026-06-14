import { JsonPipe } from '@angular/common';
import { Component, ElementRef, OnDestroy, OnInit, ViewChild, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';

import {
  ErrorOut,
  NoticeOut,
  ResourcePayload,
  SandboxPolicy,
  ServerMessage,
  ToolCallOut,
  ToolResultOut,
  UIActionResult,
} from '../../models/protocol';
import { ChatConnection } from '../../services/chat-connection';
import { McpUiFrame } from '../mcp-ui-frame/mcp-ui-frame';

type ChatItemContent =
  | { kind: 'user'; text: string }
  | { kind: 'assistant'; text: string }
  | { kind: 'tool_call'; data: ToolCallOut }
  | { kind: 'tool_result'; data: ToolResultOut }
  | { kind: 'ui_resource'; callId: string; resource: ResourcePayload; sandbox: SandboxPolicy }
  | { kind: 'notice'; data: NoticeOut }
  | { kind: 'error'; data: ErrorOut };

type ChatItem = ChatItemContent & { id: string };

/**
 * Main (and only) view of the PoC: a chat transcript plus, inline, any
 * `ui_resource` the agent sends. Owns no LLM/MCP logic - it only renders the
 * `ServerMessage` stream from `ChatConnection` and forwards
 * `user_message`/`ui_action` back (docs/konzept-mcp-apps.md section 4).
 */
@Component({
  selector: 'app-chat',
  imports: [FormsModule, JsonPipe, McpUiFrame],
  templateUrl: './chat.html',
  styleUrl: './chat.css',
})
export class Chat implements OnInit, OnDestroy {
  private readonly connection = inject(ChatConnection);

  readonly items = signal<ChatItem[]>([]);
  readonly thinking = signal(false);
  readonly connectionState = this.connection.state;

  draft = '';

  @ViewChild('messages') private messagesRef?: ElementRef<HTMLDivElement>;

  private subscription?: Subscription;
  private nextId = 0;

  constructor() {
    effect(() => {
      this.items();
      this.thinking();
      queueMicrotask(() => this.scrollToBottom());
    });
  }

  ngOnInit(): void {
    this.connection.connect();
    this.subscription = this.connection.messages.subscribe((message) => this.onMessage(message));
  }

  ngOnDestroy(): void {
    this.subscription?.unsubscribe();
  }

  send(): void {
    const text = this.draft.trim();
    if (!text) {
      return;
    }
    this.append({ kind: 'user', text });
    this.connection.send({ type: 'user_message', text });
    this.draft = '';
  }

  onUiAction(callId: string, action: UIActionResult): void {
    this.connection.send({ type: 'ui_action', callId, action });
  }

  updatesFor(callId: string) {
    return this.connection.updatesFor(callId);
  }

  openLink(url: string): void {
    window.open(url, '_blank', 'noopener,noreferrer');
  }

  private onMessage(message: ServerMessage): void {
    switch (message.type) {
      case 'assistant_message':
        this.append({ kind: 'assistant', text: message.text });
        break;
      case 'tool_call':
        this.append({ kind: 'tool_call', data: message });
        break;
      case 'tool_result':
        this.append({ kind: 'tool_result', data: message });
        break;
      case 'ui_resource':
        this.append({
          kind: 'ui_resource',
          callId: message.callId,
          resource: message.resource,
          sandbox: message.sandbox,
        });
        break;
      case 'ui_update':
        // Consumed directly by the matching McpUiFrame via
        // ChatConnection.updatesFor(callId) - no chat item for this.
        break;
      case 'status':
        this.thinking.set(message.state === 'thinking');
        break;
      case 'notice':
        this.append({ kind: 'notice', data: message });
        break;
      case 'error':
        this.append({ kind: 'error', data: message });
        break;
    }
  }

  private append(item: ChatItemContent): void {
    const withId: ChatItem = { ...item, id: `item-${this.nextId++}` };
    this.items.update((items) => [...items, withId]);
  }

  private scrollToBottom(): void {
    const el = this.messagesRef?.nativeElement;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }
}
